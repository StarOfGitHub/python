import logging
from collections import defaultdict

from django.db.models import Q
from django.utils.decorators import method_decorator

from r3sourcer.apps.candidate.models import SkillRel
from r3sourcer.apps.hr.models import TimeSheet
from r3sourcer.apps.myob.helpers import get_myob_client
from r3sourcer.apps.myob.mappers import TimeSheetMapper, format_date_to_myob
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.apps.myob.services.base import BaseSync
from r3sourcer.apps.myob.services.candidate import CandidateSync
from r3sourcer.apps.myob.services.decorators import myob_enabled_mode
from r3sourcer.apps.myob.services.exceptions import MYOBClientException
from r3sourcer.apps.myob.services.mixins import BaseCategoryMixin, StandardPayMixin, CandidateCardFinderMixin, JobMixin
from r3sourcer.apps.pricing.models import RateCoefficientModifier
from r3sourcer.apps.pricing.services import CoefficientService

log = logging.getLogger(__name__)


def format_short_wage_category_name(skill_name, rate_name):
    return '{} {}'.format(skill_name, rate_name)[:31]


class TimeSheetSync(BaseCategoryMixin,
                    StandardPayMixin,
                    CandidateCardFinderMixin,
                    JobMixin,
                    BaseSync):

    app = "crm_hr"
    model = "TimeSheet"

    mapper_class = TimeSheetMapper
    timesheet_rates_calc = None

    rates_cache = {}

    def __init__(self, client, *args, **kwargs):
        super().__init__(client)

        self._existing_timesheets_dates = None
        self._customer_cache = {}
        self._employee_cache = {}

    def sync_from_myob(self):
        raise NotImplementedError

    @classmethod
    def from_candidate(cls, settings, company_id):
        if settings.get('time_sheet_company_file_id'):
            myob_client = get_myob_client(company_id=company_id,
                                          myob_company_file_id=settings['time_sheet_company_file_id'])
            return cls(myob_client)

        raise MYOBClientException('Could not get MYOB client')

    @method_decorator(myob_enabled_mode)
    def sync_to_myob(self, candidate):
        timesheets_q = (Q(candidate_submitted_at__isnull=True) | Q(candidate_submitted_at=None) |
                        Q(supervisor_approved_at__isnull=True) | Q(supervisor_approved_at=None))

        for company_file_token in self.company.company_file_tokens.all():
            enabled_qry = Q()
            if company_file_token.enable_from:
                enabled_qry |= Q(shift_started_at__date__lt=company_file_token.enable_from)
            if company_file_token.enable_until:
                enabled_qry |= Q(shift_started_at__date__gt=company_file_token.enable_until)

            # do:
            # prepare queryset for time sheet excluding not signed
            timesheet_qs = TimeSheet.objects.filter(job_offer__candidate_contact=candidate).exclude(
                timesheets_q | enabled_qry
            )
            # done;

            # exit if time sheets not found after excluding
            if not timesheet_qs.exists():
                continue

            # self._switch_client(company_file_token=company_file_token)
            self._sync_timesheets_to_myob(candidate, timesheet_qs)

    # @method_decorator(myob_enabled_mode)
    def sync_single_to_myob(self, time_sheet_id, candidate_contact, resync=False):
        time_sheets_q = (Q(candidate_submitted_at__isnull=True) |
                         Q(candidate_submitted_at=None) |
                         Q(supervisor_approved_at__isnull=True) |
                         Q(supervisor_approved_at=None))
        time_sheet_qs = TimeSheet.objects.filter(pk=time_sheet_id).exclude(time_sheets_q)

        for time_sheet in time_sheet_qs:
            time_sheet.set_sync_status(TimeSheet.SYNC_STATUS_CHOICES.sync_scheduled)

        self._sync_timesheets_to_myob(candidate_contact, time_sheet_qs, resync)

    def _sync_timesheets_to_myob(self, candidate, timesheet_qs, resync=False):
        if self.client is None:
            log.info('MYOB client is not defined')
            return

        # TODO: Urgent add resync logic
        # do:
        # get all synced time sheets and exclude it
        timesheets = timesheet_qs

        if resync is False:
            synced_timesheets = self._get_sync_objects_for_type().filter(
                record__in=timesheet_qs.values_list('id', flat=True)
            )
            timesheets_exclude = Q()
            for synced_timesheet in synced_timesheets:
                timesheet = TimeSheet.objects.get(pk=synced_timesheet.record)
                timesheet.set_sync_status(TimeSheet.SYNC_STATUS_CHOICES.synced)
                timesheets_exclude |= Q(id=synced_timesheet.record, updated_at__lte=synced_timesheet.synced_at)
            timesheets = timesheets.exclude(timesheets_exclude)
        # exit if times sheets not found after excluding
        if not timesheets.exists():
            return

        # find existing remote resource
        card_number = candidate.contact.get_myob_card_number()
        myob_employee = self.get_myob_employee_data(candidate, card_number)

        # TODO: fix this when candidate sync will be done
        # if resource was not exists then stop processing
        if not myob_employee:
            rs = CandidateSync(self.client)
            rs.sync_to_myob(candidate, partial=True)

            myob_employee = self.get_myob_employee_data(candidate, card_number)

        if not myob_employee:
            return

        # get existing remote time sheets in date range by job id
        start_date = timesheets.earliest('shift_started_at').shift_started_at
        end_date = timesheets.latest('shift_started_at').shift_started_at
        myob_employee_uid = myob_employee['UID']
        self._existing_timesheets_dates, payroll_categories = self._get_existing_timesheets_data(
            myob_employee_uid, start_date, end_date
        )

        is_synced = False

        for timesheet in timesheets:
            # check if company file is enabled
            cf_data = self.client.cf_data
            if not cf_data.is_enabled(timesheet.shift_started_at):
                continue

            sync_obj = self._get_sync_object(timesheet)  # type: MYOBSyncObject

            # if object was synced then skip processing
            if sync_obj and self._is_synced(timesheet, sync_obj=sync_obj) \
                    and resync is False:
                if timesheet.sync_status != TimeSheet.SYNC_STATUS_CHOICES.synced:
                    timesheet.set_sync_status(TimeSheet.SYNC_STATUS_CHOICES.synced)
                continue

            timesheet.set_sync_status(TimeSheet.SYNC_STATUS_CHOICES.syncing)

            # sync time sheet
            res = self._sync_to(timesheet, myob_employee, payroll_categories, sync_obj)

            if res:
                is_synced = True
                # update sync object in local db
                self._update_sync_object(timesheet)

                timesheet.set_sync_status(TimeSheet.SYNC_STATUS_CHOICES.synced)
            else:
                timesheet.set_sync_status(TimeSheet.SYNC_STATUS_CHOICES.sync_failed)

        if is_synced:
            self._put_standart_pay_info(myob_employee, candidate)
        self._existing_timesheets_dates = None

    def _get_resource(self):
        return self.client.api.Payroll.Timesheet

    def get_myob_employee_data(self, candidate, card_number=None):
        """
        Return myob candidate response if it exists in remote service.
        Find Employee card from remote resources.

        :param candidate: CandidateContact
        :param card_number: card number
        :return: dict MYOB response
        """
        cache_key = (candidate.id, self.client.cf_data.company_file.id)
        # check if candidate already was cached and return value
        if self._employee_cache.get(cache_key):
            return self._employee_cache[cache_key]

        # get latest sync instance for concrete candidate
        model_parts = ['hr', 'candidatecontact']
        sync_obj = MYOBSyncObject.objects.filter(
            app=model_parts[0],
            model=model_parts[1],
            record=candidate.id,
            company=self.company,
            direction=MYOBSyncObject.SYNC_DIRECTION_CHOICES.myob
        ).first()

        # find candidate resource by `DisplayID`
        _, _, myob_employee_resp = self._get_myob_existing_resp(candidate,
                                                                card_number,
                                                                sync_obj,
                                                                resource=self.client.api.Contact.Employee)

        myob_employee = None
        # if resource exists then return it
        if myob_employee_resp is not None and myob_employee_resp.get('Count'):
            myob_employee = myob_employee_resp['Items'][0]

        # set to cache
        if myob_employee is not None:
            self._employee_cache[cache_key] = myob_employee

        return myob_employee

    def _get_existing_timesheets_data(self, myob_employee_uid, start_date, end_date):
        """
        Returns existing MYOB timesheets dates and payroll categories
        """
        params = {
            'StartDate': format_date_to_myob(start_date),
            'EndDate': format_date_to_myob(end_date),
            '$filter': "Employee/UID eq guid'{}'".format(
                myob_employee_uid
            )
        }
        timesheet_obj = self._get_object(params, resource=self.client.api.Payroll.Timesheet, single=True)

        dates = set()
        payroll_categories = set()
        if not timesheet_obj:
            return dates, payroll_categories

        for line in timesheet_obj.get('Lines', []):
            payroll_categories.add(line['PayrollCategory']['UID'])
            for entry in line.get('Entries', []):
                dates.add(entry['Date'].split('T')[0])

        return dates, payroll_categories

    def _sync_to(self, timesheet, myob_employee, payroll_categories, sync_obj=None):
        if self.timesheet_rates_calc is None:
            self.timesheet_rates_calc = CoefficientService()

        data = self._get_timesheet_data(timesheet, myob_employee)

        # PUT times sheet data if it need
        if data is not None:
            resp = self.resource.put(uid=myob_employee['UID'], json=data, raw_resp=True)

            if resp.status_code >= 400:
                log.warning("[MYOB API] Timesheet %s: %s", timesheet.id, resp.text)

        log.info('Timesheet %s synced' % timesheet.id)
        return True

    def _get_timesheet_data(self, timesheet, myob_employee):
        """
        Return time sheet data for myob api scheme.

        :param timesheet: object TimeSheet
        :param myob_employee: dict MYOB employee
        :return: dict or None
        """

        timesheet_date = format_date_to_myob(timesheet.shift_started_at_tz.date())

        # slip processing if time sheet date already exists in myob
        if timesheet_date in self._existing_timesheets_dates:
            return

        timesheets_with_rates = self._process_employee_timesheet_rates(timesheet)
        wage_categories = timesheets_with_rates.keys()
        self._update_employee_payroll_categories(myob_employee, wage_categories)

        jobsite = timesheet.job_offer.shift.date.job.jobsite
        if jobsite:
            myob_job = self._get_myob_job(jobsite)
        else:
            myob_job = None

        customer_uid = self._get_myob_customer(timesheet)
        address = "{} {}".format(jobsite.address.street_address, jobsite.address.city)

        data = self.mapper.map_to_myob(
            timesheets_with_rates, myob_employee['UID'], timesheet.shift_started_at_tz, timesheet.shift_started_at_tz,
            myob_job=myob_job, customer_uid=customer_uid, address=address)

        return data

    def _process_employee_timesheet_rates(self, timesheet):
        """

        :param booking: object Booking
        :param timesheet: object TimeSheet
        :return:
        """

        job = timesheet.job_offer.job
        position = job.position
        timesheets_with_rates = self.timesheet_rates_calc.calc(timesheet.master_company,
                                                               job.jobsite.industry,
                                                               RateCoefficientModifier.TYPE_CHOICES.candidate,
                                                               timesheet.shift_started_at_tz,
                                                               timesheet.shift_duration,
                                                               break_started=timesheet.break_started_at,
                                                               break_ended=timesheet.break_ended_at,
                                                               overlaps=True)

        result = defaultdict(dict)
        rate_myob_id, base_rate = self._get_candidate_skill_rate_and_name(timesheet)
        if not rate_myob_id:
            rate_myob_id = position.get_myob_name()

        for coeff_hours in timesheets_with_rates:
            coefficient = coeff_hours['coefficient']

            if coefficient == 'base':
                myob_rate = self._get_base_rate_wage_category(rate_myob_id, timesheet, base_rate=base_rate)
            else:
                myob_rate = self._get_rate_wage_category(
                    job, coefficient, base_rate, timesheet, skill_name=rate_myob_id
                )

            if myob_rate:
                timesheets_rate = result[myob_rate['UID']]
                timesheets_rate['timesheets'] = [dict(
                    timesheet=timesheet,
                    **coeff_hours
                )]

        return result

    def _get_candidate_skill_rate_and_name(self, timesheet):
        offer = timesheet.job_offer
        shift = offer.shift
        name = None
        job = timesheet.job_offer.job
        skill_name = job.position.get_myob_name()
        if timesheet.rate_overrides_approved_by and timesheet.candidate_rate:
            return '{} {}'.format(
                str(skill_name),
                str(timesheet.candidate_rate)
            ), timesheet.candidate_rate
        if shift.hourly_rate:
            return '{} {}'.format(
                str(skill_name),
                str(shift.hourly_rate)
            ), shift.hourly_rate
        if shift.date.hourly_rate:
            return '{} {}'.format(
                str(skill_name),
                str(shift.date.hourly_rate)
            ), shift.date.hourly_rate
        # if job.hourly_rate_default:
        #     name = '{} {}'.format(
        #         str(job.position.get_myob_name()),
        #         str(job.hourly_rate_default)
        #     )
        #     base_rate = job.hourly_rate_default

        if name is None:
            candidate_skill_rate = SkillRel.objects.filter(
                candidate_contact=offer.candidate_contact,
                skill__active=True,
                skill=job.position,
            ).first()
            name = candidate_skill_rate and candidate_skill_rate.get_myob_name()
            base_rate = candidate_skill_rate.hourly_rate if candidate_skill_rate else 0
        return name, base_rate

    def _get_base_rate_wage_category(self, name, timesheet, rate=None, base_rate=None):
        myob_wage_category = self._get_object_by_field(
            name[:31].strip().lower(),
            resource=self.client.api.Payroll.PayrollCategory.Wage,
            myob_field='tolower(Name)',
            single=True
        )

        if rate:
            modifier_rel = rate.candidate_skill_coefficient_rels.filter(
                skill_rel__candidate_contact=timesheet.candidate_contact,
            ).first()

            if modifier_rel:
                modifier = modifier_rel.rate_coefficient_modifier
            else:
                modifier = rate.candidate_modifier

            fixed = modifier.calc(base_rate) if modifier else 0
            if fixed <= 0:
                return

            data = self.mapper.map_rate_to_myob_wage_category(name, fixed=fixed, coefficient=rate)
        elif base_rate:
            data = self.mapper.map_rate_to_myob_wage_category(name, fixed=base_rate)
        else:
            return myob_wage_category

        # create wage if category was not found from remote or update it by ID
        if myob_wage_category is None:
            resp = self.client.api.Payroll.PayrollCategory.Wage.post(json=data, raw_resp=True)
        else:
            data = self._get_data_to_update(myob_wage_category, data)
            resp = self.client.api.Payroll.PayrollCategory.Wage.put(
                uid=myob_wage_category['UID'], json=data, raw_resp=True
            )

        if resp.status_code >= 400:
            log.warning(resp.text)
        elif myob_wage_category is None:
            myob_wage_category = self._get_object_by_field(
                name[:31].strip().lower(),
                resource=self.client.api.Payroll.PayrollCategory.Wage,
                myob_field='tolower(Name)',
                single=True
            )

        return myob_wage_category

    def _get_rate_wage_category(self, job, rate, base_rate, timesheet, name=None, skill_name=''):
        if rate.is_allowance:
            industry = job.jobsite.industry
            name = '{} {}'.format(''.join([line[0] for line in industry.type.split(' ')]), rate.name)
        if not name:
            name = format_short_wage_category_name(skill_name, rate.name)
        return self._get_base_rate_wage_category(name[:31].strip(), timesheet, rate=rate, base_rate=base_rate)

    def _update_employee_payroll_categories(self, employee, categories):
        uid = employee['EmployeePayrollDetails']['UID']
        payroll_details = self.client.api.Contact.EmployeePayrollDetails.get(uid=uid) or {}
        wage = payroll_details.get('Wage', {})

        if self._employee_has_wage_categories(wage.get('WageCategories'), categories):
            return

        data_categories = self.mapper.map_extra_rates(categories, rates=wage.get('WageCategories'))
        wage.update(data_categories)
        payroll_details['Wage'] = wage
        resp = self.client.api.Contact.EmployeePayrollDetails.put(uid=uid, json=payroll_details, raw_resp=True)

        if resp.status_code >= 400:
            log.warning("[MYOB API] payroll details for myob %s: %s", uid, resp.text)
        else:
            log.info('payroll details for myob %s updated' % uid)

    def _employee_has_wage_categories(self, existing_categories, new_categories):
        existing_categories = existing_categories or []
        new_categories = new_categories or []
        found_cnt = 0
        for category_uid in new_categories:
            for existing in existing_categories:
                if existing['UID'] == category_uid:
                    found_cnt += 1
                    break
        return found_cnt == len(new_categories)

    def _get_myob_customer(self, timesheet):
        from r3sourcer.apps.myob.services.company import CompanySync
        params = {"$filter": "CompanyName eq '%s'" % timesheet.regular_company.name}
        customer_data = self.client.api.Contact.Customer.get(params=params)

        company = timesheet.regular_company

        if not customer_data['Items']:
            rs = CompanySync(self.client)
            rs.sync_to_myob(company)

            customer_uid = self._get_myob_customer(timesheet)
        else:
            customer_uid = customer_data['Items'][0]['UID']

        return customer_uid
