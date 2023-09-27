import datetime
import logging

from r3sourcer.apps.activity.models import Activity
from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.myob.mappers import JobsiteMapper
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.helpers.datetimes import utc_now

log = logging.getLogger(__name__)


class BaseCategoryMixin:
    _base_category = None

    def _get_base_category(self):
        if self._base_category is None:
            base_category = self._get_object_by_field(
                'base hourly',
                resource=self.client.api.Payroll.PayrollCategory.Wage,
                myob_field='tolower(Name)'
            )
            if not base_category or not base_category['Count']:
                base_category = self._get_object_by_field(
                    'base hourly - workers',
                    resource=self.client.api.Payroll.PayrollCategory.Wage,
                    myob_field='tolower(Name)'
                )
            self._base_category = base_category
        return self._base_category


class JobMixin:
    def _get_myob_job(self, jobsite):
        number = jobsite.get_myob_card_number()
        myob_job = self._get_object_by_field(
            number.lower(),
            resource=self.client.api.GeneralLedger.Job,
            myob_field='tolower(Number)',
            single=True
        )
        data = JobsiteMapper().map_to_myob(jobsite)

        if myob_job is None:
            resp = self.client.api.GeneralLedger.Job.post(json=data, raw_resp=True)
        else:
            data = self._get_data_to_update(myob_job, data)
            resp = self.client.api.GeneralLedger.Job.put(
                uid=myob_job['UID'], json=data, raw_resp=True
            )

        if resp.status_code >= 400:
            log.warning(resp.text)
        elif myob_job is None:
            myob_job = self._get_object_by_field(
                number.lower(),
                resource=self.client.api.GeneralLedger.Job,
                myob_field='tolower(Number)',
                single=True
            )

        return myob_job


class StandardPayMixin:
    def _put_standart_pay_info(self, employee_item, candidate_contact=None):
        emp_uid = employee_item.get('EmployeePayrollDetails')
        if not emp_uid:
            return

        standard_pay = self.client.api.Contact.EmployeeStandardPay.get(
            uid=employee_item['EmployeeStandardPay']['UID']
        )

        if 'UID' not in standard_pay:
            return

        uid = standard_pay['UID']
        base_category = self._get_base_category()

        memo = None
        if candidate_contact is not None:
            contact = candidate_contact.contact
            memo = '{} {}'.format(contact.first_name, contact.last_name)

        pay_data = self.mapper.map_standard_pay(
            emp_uid.get('UID', ''),
            standard_pay.get('PayrollCategories', []),
            base_category=base_category,
            memo=memo
        )
        pay_data = self._get_data_to_update(standard_pay, pay_data)
        pay_data['Employee'] = {
            'UID': employee_item['UID']
        }

        resp = self.client.api.Contact.EmployeeStandardPay.put(
            uid=uid,
            json=pay_data,
            raw_resp=True
        )

        if resp.status_code >= 400:
            log.warning("[MYOB API] Standart Pay for %s: %s",
                        candidate_contact.id if candidate_contact else uid,
                        resp.text)
        else:
            log.info('Candidate Contact %s Standart Pay synced',
                     candidate_contact.id if candidate_contact else uid)


class CandidateCardFinderMixin:
    def _find_old_myob_card(self, candidate_contact, resource=None):
        candidate_contact = CandidateContact.objects.select_related('contact').get(pk=candidate_contact.id)
        contact = candidate_contact.contact
        resp = self.client.api.Contact.Employee.get(params={
            '$filter':
                "tolower(FirstName) eq '{first_name}' and tolower(LastName) eq '{last_name}'"
                .format(first_name=contact.first_name.replace("'", "''").lower(),
                        last_name=contact.last_name.replace("'", "''").lower())
        })

        if 'Errors' in resp:
            for error in resp['Errors']:
                log.warning('[MYOB API] find by name %s: %s', str(contact), error['Message'])
            return
        elif not resp['Count']:
            return

        return resp


class SalespersonMixin:
    def _get_salesperson(self, portfolio_manager):
        myob_card_number = portfolio_manager.legacy_myob_card_number
        salesperson = None

        if myob_card_number:
            salesperson = self._get_object_by_field(
                myob_card_number, resource=self.client.api.Contact.Employee, single=True
            )

        if salesperson is None:
            contact = portfolio_manager.contact
            myob_card_number = contact.get_myob_card_number()

            candidate = getattr(contact, 'candidate_contacts', None)
            if candidate:
                model_parts = ['candidate', 'CandidateContact']
                sync_obj = MYOBSyncObject.objects.filter(
                    app=model_parts[0],
                    model=model_parts[1],
                    record=candidate.id,
                    company=self.company,
                    direction=MYOBSyncObject.SYNC_DIRECTION_CHOICES.myob
                ).first()

                old_myob_card_number = sync_obj and sync_obj.legacy_myob_card_number
                if old_myob_card_number:
                    myob_card_number = old_myob_card_number

            resp = self._get_object_by_field(myob_card_number, resource=self.client.api.Contact.Employee)
            if not resp or not resp['Count']:
                resp = self.client.api.Contact.Employee.get(params={
                    '$filter':
                        "tolower(FirstName) eq '{first_name}' and tolower(LastName) eq '{last_name}'"
                        .format(first_name=contact.first_name.replace("'", "''").lower(),
                                last_name=contact.last_name.replace("'", "''").lower())
                })

            if not resp or not resp['Count']:
                return self._sync_salesperson_employee(contact)

            if resp['Count'] == 1:
                salesperson = resp['Items'][0]
                if contact.get_myob_card_number() != salesperson['DisplayID']:
                    portfolio_manager.legacy_myob_card_number = salesperson['DisplayID']
                    portfolio_manager.save(update_fields=['legacy_myob_card_number'])
            else:
                now = utc_now()
                activity_values = {
                    'contact': contact,
                    'starts_at': now,
                    'ends_at': now + datetime.timedelta(days=1)
                }
                Activity.objects.create(**activity_values)

        return salesperson

    def _sync_salesperson_employee(self, contact):
        data = self.mapper._map_contact_to_myob(contact)

        data['DisplayID'] = contact.get_myob_card_number()
        data['IsIndividual'] = True
        resp = self.client.api.Contact.Employee.post(json=data, raw_resp=True)

        if 200 <= resp.status_code < 400:
            return self._get_object_by_field(
                contact.get_myob_card_number(),
                resource=self.client.api.Contact.Employee,
                single=True
            )
