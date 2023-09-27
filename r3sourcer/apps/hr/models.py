from itertools import chain
from uuid import UUID  # not remove

from datetime import timedelta, date, time, datetime
from decimal import Decimal
import math
import logging
import pytz
from django.db.models import F
from easy_thumbnails.fields import ThumbnailerImageField

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import models, IntegrityError, transaction
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _
from filer.models import Folder
from model_utils import Choices

from r3sourcer import ref
from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.core.decorators import workflow_function
from r3sourcer.apps.core.managers import AbstractObjectOwnerQuerySet
from r3sourcer.apps.core.mixins import CategoryFolderMixin, MYOBMixin
from r3sourcer.apps.core.workflow import WorkflowProcess
from r3sourcer.apps.hr.tasks import send_jo_confirmation, send_recurring_jo_confirmation
from r3sourcer.apps.logger.main import endless_logger
from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.skills.models import SkillBaseRate, SkillRateRange, WorkType
from r3sourcer.apps.sms_interface.models import SMSMessage
from r3sourcer.apps.pricing.models import Industry, PriceListRate
from r3sourcer.apps.hr.utils import utils as hr_utils
from r3sourcer.celeryapp import app
from r3sourcer.helpers.datetimes import utc_now, tz2utc
from r3sourcer.helpers.models.abs import UUIDModel, TimeZoneUUIDModel

NOT_FULFILLED, FULFILLED, LIKELY_FULFILLED, IRRELEVANT = range(4)


class Jobsite(CategoryFolderMixin,
              MYOBMixin,
              TimeZoneUUIDModel,
              WorkflowProcess):

    industry = models.ForeignKey(
        'pricing.Industry',
        related_name="jobsites",
        verbose_name=_("Industry"),
        on_delete=models.PROTECT
    )

    short_name = models.CharField(
        max_length=63,
        help_text=_('Used for jobsite naming'),
        verbose_name=_("Site short name"),
        blank=True,
        null=True
    )

    master_company = models.ForeignKey(
        'core.Company',
        related_name="jobsites",
        verbose_name=_("Master company"),
        on_delete=models.CASCADE
    )

    regular_company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name="jobsites_regular",
        verbose_name=_("Client"),
    )

    address = models.ForeignKey(
        'core.Address',
        on_delete=models.PROTECT,
        related_name="jobsites",
        verbose_name=_("Address"),
        blank=True,
        null=True
    )

    portfolio_manager = models.ForeignKey(
        'core.CompanyContact',
        related_name="managed_jobsites",
        verbose_name=_("Portfolio Manager"),
        on_delete=models.PROTECT,
        null=True
    )

    primary_contact = models.ForeignKey(
        'core.CompanyContact',
        related_name="jobsites",
        verbose_name=_("Primary Contact"),
        on_delete=models.PROTECT,
        null=True
    )

    is_available = models.BooleanField(
        verbose_name=_("Available"),
        default=True
    )

    notes = models.TextField(
        verbose_name=_("Notes"),
        blank=True
    )

    start_date = models.DateField(
        verbose_name=_("Start Date"),
        null=True,
        blank=True
    )

    end_date = models.DateField(
        verbose_name=_("End Date"),
        null=True,
        blank=True
    )

    files = models.ForeignKey(
        Folder,
        related_name='jobsites',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _("Jobsite")
        verbose_name_plural = _("Jobsites")
        unique_together = ('industry', 'regular_company', 'short_name')

    def __str__(self):
        return self.get_site_name()

    def main_geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('address__longitude'),
            latitude=F('address__latitude')
        ).values_list('longitude', 'latitude').get()

    def regular_company_geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
            company__company_addresses__hq=True,
        ).annotate(
            longitude=F('regular_company__company_addresses__address__longitude'),
            latitude=F('regular_company__company_addresses__address__latitude')
        ).values_list('longitude', 'latitude').get()

    def master_company_geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
            company__company_addresses__hq=True,
        ).annotate(
            longitude=F('master_company__company_addresses__address__longitude'),
            latitude=F('master_company__company_addresses__address__latitude')
        ).values_list('longitude', 'latitude').get()

    @property
    def geo(self):
        for geo in (self.main_geo, self.regular_company_geo, self.master_company_geo):
            try:
                return geo()
            except ObjectDoesNotExist:
                continue
        raise ObjectDoesNotExist

    def get_availability(self):
        today = date.today()
        unavailable = self.jobsite_unavailabilities.filter(
            unavailable_from__lte=today,
            unavailable_until__gte=today
        )
        if len(unavailable) > 0:
            return False
        else:
            return self.is_available

    def get_site_name(self):
        if self.short_name:
            return self.short_name

        job_address = self.get_address()
        if job_address:
            return "{}, {}, {}".format(
                self.regular_company, job_address.street_address, job_address.city
            )

        return str(self.master_company)

    def get_address(self):
        return self.address

    def get_duration(self):
        return self.end_date - self.start_date

    @workflow_function
    def is_address_set(self):
        return self.address is not None
    is_address_set.short_description = _("Address is required.")

    @workflow_function
    def is_supervisor_set(self):
        return self.primary_contact and self.primary_contact.contact.email
    is_supervisor_set.short_description = _("Supervisor with valid email is required.")

    def save(self, *args, **kwargs):
        just_added = self._state.adding
        changed_primary_contact = False
        if not just_added:
            original = Jobsite.objects.get(pk=self.id)
            changed_primary_contact = \
                original.primary_contact != self.primary_contact

        super().save(*args, **kwargs)

        if just_added:
            if self.is_allowed(10):
                self.create_state(10)
        elif changed_primary_contact:
            # update supervisor related future timesheets
            for job in self.jobs.all():
                for sd in job.shift_dates.all():
                    TimeSheet.objects.filter(
                        job_offer__in=sd.job_offers,
                        shift_started_at__date__gte=self.tomorrow_tz
                    ).update(supervisor=self.primary_contact)

    def get_closest_company(self):
        return self.master_company

    def get_myob_name(self):
        return self.get_site_name()[:30]

    def get_timezone(self):
        time_zone = pytz.timezone(settings.TIME_ZONE)
        if self.address:
            time_zone = self.tz
        return time_zone


class JobsiteUnavailability(UUIDModel):

    jobsite = models.ForeignKey(
        Jobsite,
        related_name="jobsite_unavailabilities",
        verbose_name=_("Jobsite"),
        on_delete=models.PROTECT
    )

    unavailable_from = models.DateField(
        verbose_name=_("From"),
        null=True,
        blank=True
    )

    unavailable_until = models.DateField(
        verbose_name=_("Until"),
        null=True,
        blank=True
    )

    notes = models.TextField(
        verbose_name=_("Notes"),
        help_text=_("Unavailability Description"),
        blank=True
    )

    class Meta:
        verbose_name = _("Jobsite Unavailability")
        verbose_name_plural = _("Jobsite Unavailabilities")


class Job(core_models.AbstractBaseOrder):

    jobsite = models.ForeignKey(
        'hr.Jobsite',
        related_name="jobs",
        on_delete=models.PROTECT,
        verbose_name=_("Jobsite")
    )

    position = models.ForeignKey(
        'skills.Skill',
        related_name="jobs",
        on_delete=models.PROTECT,
        verbose_name=_("Category")
    )

    published = models.BooleanField(
        default=False,
        verbose_name=_("Published")
    )

    publish_on = models.DateField(
        verbose_name=_("To be published on"),
        null=True,
        blank=True
    )

    expires_on = models.DateField(
        verbose_name=_("Expires on"),
        null=True,
        blank=True
    )

    work_start_date = models.DateField(
        verbose_name=_("Work Start Date"),
        default=date.today
    )

    workers = models.PositiveSmallIntegerField(
        verbose_name=_("Workers"),
        default=1,
        validators=[MinValueValidator(1)]
    )

    default_shift_starting_time = models.TimeField(
        verbose_name=_('Default Shift Starting Time'),
        default=time(hour=7)
    )

    notes = models.TextField(
        verbose_name=_("Notes"),
        help_text=_("Job Description/Instructions for candidate"),
        blank=True
    )

    TRANSPORTATION_CHOICES = Choices(
        (1, 'own', _("Own Car")),
        (2, 'public', _("Public Transportation")),
    )

    transportation_to_work = models.PositiveSmallIntegerField(
        choices=TRANSPORTATION_CHOICES,
        verbose_name=_("Transportation to Work"),
        null=True,
        blank=True
    )

    hourly_rate_default = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = _("Job")
        verbose_name_plural = _("Jobs")

    def __str__(self):
        return self.get_title()

    def get_title(self):
        return f'{self.position} - {self.jobsite} ({self.workers} workers)'
    get_title.short_description = _('Title')

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('jobsite__address__longitude'),
            latitude=F('jobsite__address__latitude')
        ).values_list('longitude', 'latitude').get()

    def get_job_offers(self):
        return JobOffer.objects.filter(shift__date__job=self)

    def get_total_bookings_count(self):
        return self.get_job_offers().distinct('candidate_contact').count()
    get_total_bookings_count.short_description = _('Bookings')

    def is_fulfilled(self):
        irrelevant_state_exist = core_models.WorkflowObject.objects.filter(
            object_id=self.pk, state__number__in=[40, 60], active=True
        ).exists()

        if irrelevant_state_exist:
            return IRRELEVANT

        result = NOT_FULFILLED
        # get today and future shift dates
        next_dates = self.shift_dates.filter(
            shift_date__gte=self.now_utc.date(),
            cancelled=False,
        ).order_by('shift_date')

        if next_dates.count() > 0:
            # check if all offers for these dates
            acceptance = {y.status for x in next_dates for y in x.job_offers if y.is_last()}

            # If shift has no job offers or rejected offers only it shows red
            if len(acceptance) == 0 or {JobOffer.STATUS_CHOICES.cancelled} == acceptance:
                result = NOT_FULFILLED
            # if shift has all job offers accepted it remains green
            elif {JobOffer.STATUS_CHOICES.accepted} == acceptance:
                result = FULFILLED
            # if shift has pending job offers it remains yellow
            else:
                result = LIKELY_FULFILLED
        else:
            result = IRRELEVANT
        return result
    is_fulfilled.short_description = _('Fulfilled')

    def is_fulfilled_today(self):
        irrelevant_state_exist = core_models.WorkflowObject.objects.filter(
            object_id=self.pk, state__number__in=[40, 60], active=True
        ).exists()

        if irrelevant_state_exist:
            return IRRELEVANT

        result = NOT_FULFILLED
        sd_today = self.shift_dates.filter(shift_date=self.now_utc.date(), cancelled=False).first()
        if sd_today:
            result = sd_today.is_fulfilled()
        else:
            result = IRRELEVANT
        return result

    def can_fillin(self):
        not_filled_future_sd = False
        future_sds = self.shift_dates.filter(shift_date__gte=self.now_utc.date())
        for sd in future_sds:
            if sd.is_fulfilled() == NOT_FULFILLED:
                not_filled_future_sd = True
                break

        # FIXME: change to new workflow
        # return self.order.get_state() not in [OrderState.STATE_CHOICES.cancelled,
        #                                       OrderState.STATE_CHOICES.completed,
        #                                       OrderState.STATE_CHOICES.new] and \
        return self.is_fulfilled() in [NOT_FULFILLED, LIKELY_FULFILLED] or not_filled_future_sd

    @workflow_function
    def has_active_price_list_and_rate(self):
        # this is implemented in skill queryset
        return True
    has_active_price_list_and_rate.short_description = _('Customer active price list for skill')

    @workflow_function
    def is_start_date_set(self):
        return bool(self.work_start_date)
    is_start_date_set.short_description = _('Work Start Date')

    # @workflow_function
    # def is_default_rate_set(self):
    #     return self.hourly_rate_default is not None or self.hourly_rate_default <= 0
    # is_default_rate_set.short_description = _('Default hourly rate')

    @workflow_function
    def is_all_sd_filled(self):
        for sd in self.shift_dates.all():
            if sd.is_fulfilled() != FULFILLED:
                return False

        return True
    is_all_sd_filled.short_description = _('Fill in all Shift Dates')

    @workflow_function
    def is_all_timesheets_approved(self):
        return not TimeSheet.objects.filter(
            job_offer__shift__date__job=self,
            supervisor_approved_at__isnull=True
        ).exists()
    is_all_timesheets_approved.short_description = _('All Time Sheets approvment')

    @workflow_function
    def is_client_active(self):
        if self.customer_company.type == core_models.Company.COMPANY_TYPES.master:
            content_type = ContentType.objects.get_for_model(core_models.Company)
            obj = self.customer_company
            number = 40
        else:
            content_type = ContentType.objects.get_for_model(core_models.CompanyRel)
            obj = self.customer_company.regular_companies.filter(master_company=self.provider_company).first()
            number = 70

        res = core_models.WorkflowObject.objects.filter(
            state__number=number, state__workflow__model=content_type, active=True, object_id=obj.id
        ).exists()
        return res
    is_client_active.short_description = _('Active Client')

    @workflow_function
    def is_unique_position_jobsite(self):
        existing_jobs = Job.objects.filter(
            jobsite=self.jobsite, position=self.position
        ).exclude(id=self.pk)
        completed_list = core_models.WorkflowObject.objects.filter(
            object_id__in=existing_jobs.values_list('id', flat=True), state__number=60, active=True
        ).values_list('object_id', flat=True)

        return not existing_jobs.exclude(id__in=completed_list).exists()
    is_unique_position_jobsite.short_description = _('Unique Position and Jobsite')

    @workflow_function
    def is_position_active(self):
        if self.customer_company.type != core_models.Company.COMPANY_TYPES.master:
            return True

        return self.position and self.position.active

    is_position_active.short_description = _('Active position')

    def after_state_created(self, workflow_object):
        if workflow_object.state.number == 20:
            sd, _ = ShiftDate.objects.get_or_create(job=self, shift_date=self.work_start_date)
            # fix: commented due to https://taavisaavo.atlassian.net/browse/RV-1279
            # Shift.objects.get_or_create(date=sd, time=self.default_shift_starting_time, workers=self.workers)

            hr_utils.send_job_confirmation_sms(self)

    def after_state_activated(self, workflow_object):
        if workflow_object.state.number == 20:
            core_models.WorkflowObject.objects.filter(
                object_id=self.pk, state__number=40, active=True
            ).update(active=False)

        if workflow_object.state.number == 40:
            core_models.WorkflowObject.objects.filter(
                object_id=self.pk, state__number=20, active=True
            ).update(active=False)

    def save(self, *args, **kwargs):
        just_added = self._state.adding
        if just_added:
            self.provider_signed_at = self.now_utc
            existing_jobs = Job.objects.filter(
                jobsite=self.jobsite,
                position=self.position,
            )
            completed_list = core_models.WorkflowObject.objects.filter(
                object_id__in=existing_jobs.values_list('id', flat=True), state__number=60, active=True
            ).values_list('object_id', flat=True)

            if existing_jobs.exclude(id__in=completed_list).exists():
                raise ValidationError(_('Active Job for Jobsite and Position already exist'))

        super().save(*args, **kwargs)

        if just_added and self.is_allowed(10):
            self.create_state(10)

    def get_distance_matrix(self, candidate_contact):
        """
        Get temporal and metric distance from the candidate contact to jobsite
        :param candidate_contact:
        :return: dictionary {"distance": float, "time": str, "seconds": int} or None
        """
        if self.jobsite:
            distancematrix_obj = ContactJobsiteDistanceCache.objects.filter(
                jobsite=self.jobsite, contact=candidate_contact.contact
            ).first()
            if distancematrix_obj:
                return {
                    "distance": hr_utils.meters_to_km(distancematrix_obj.distance),
                    "time": hr_utils.seconds_to_hrs(distancematrix_obj.time) if distancematrix_obj.time else 0,
                    "seconds": int(distancematrix_obj.time) if distancematrix_obj.time else -1
                }
        return None

    def get_hourly_rate_for_skill(self, skill):
        # search skill activity rate in job's skill activity rates
        hourly_work = WorkType.objects.filter(name='Hourly work',
                                              skill_name=skill.name) \
                                      .first()
        job_skill_activity = self.job_rates.filter(worktype=hourly_work).first()
        return job_skill_activity.rate if job_skill_activity else None

    def get_rate_for_worktype(self, worktype):
        # search skill activity rate in job's skill activity rates
        job_skill_activity = self.job_rates.filter(worktype=worktype).first()
        return job_skill_activity.rate if job_skill_activity else None

    def get_amount_for_worktype(self, worktype):
        job_amount = self.job_amounts.filter(worktype=worktype).first()
        return job_amount.amount if job_amount else None


class ShiftDate(TimeZoneUUIDModel):

    job = models.ForeignKey(
        'hr.Job',
        related_name="shift_dates",
        on_delete=models.CASCADE,
        verbose_name=_("Job")
    )

    shift_date = models.DateField(verbose_name=_("Shift date"))

    hourly_rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )

    cancelled = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Shift Date")
        verbose_name_plural = _("Shift Dates")

    def __str__(self):
        return date_format(self.shift_date, settings.DATE_FORMAT)

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('job__jobsite__address__longitude'),
            latitude=F('job__jobsite__address__latitude')
        ).values_list('longitude', 'latitude').get()

    @property
    def job_offers(self):
        return JobOffer.objects.filter(shift__date=self)

    def is_fulfilled(self):
        for shift in self.shifts.all():
            if shift.is_fulfilled() != FULFILLED:
                return NOT_FULFILLED

        return FULFILLED
    is_fulfilled.short_description = _('Fulfilled')


class SQCount(models.Subquery):
    template = "(SELECT count(*) FROM (%(subquery)s) _count)"
    output_field = models.IntegerField()


class ShiftQuerySet(AbstractObjectOwnerQuerySet):
    def annotate_is_fulfilled(self):

        return self.annotate(accepted_jos=SQCount(JobOffer.objects.filter(shift_id=models.OuterRef('id'),
                                                                          status=JobOffer.STATUS_CHOICES.accepted))).annotate(
                             is_fulfilled_annotated=models.Case(
                                 models.When(condition=models.Q(
                                        accepted_jos__gte=models.F('workers')),
                                     then=models.Value(FULFILLED)),
                                 default=models.Value(NOT_FULFILLED),
                                 output_field=models.IntegerField()))


class Shift(TimeZoneUUIDModel):
    time = models.TimeField(verbose_name=_("Time"))

    date = models.ForeignKey(
        'hr.ShiftDate',
        related_name="shifts",
        on_delete=models.CASCADE,
        verbose_name=_("Date")
    )

    workers = models.PositiveSmallIntegerField(
        verbose_name=_("Workers"),
        default=1,
        validators=[MinValueValidator(1)]
    )

    hourly_rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )

    objects = ShiftQuerySet.as_manager()

    class Meta:
        verbose_name = _("Shift")
        verbose_name_plural = _("Shifts")

    def __str__(self):
        return date_format(
            datetime.combine(self.date.shift_date, self.time),
            settings.DATETIME_FORMAT
        )

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('date__job__jobsite__address__longitude'),
            latitude=F('date__job__jobsite__address__latitude')
        ).values_list('longitude', 'latitude').get()

    @property
    def shift_date_at_tz(self):
        shift_date = datetime.combine(self.date.shift_date, self.time)
        shift_date_tz = self.tz.localize(shift_date)
        return shift_date_tz.astimezone(pytz.utc)

    @property
    def job(self):
        return self.date.job

    def is_fulfilled(self):
        result = NOT_FULFILLED
        jos = self.job_offers
        accepted_jos = jos.filter(status=JobOffer.STATUS_CHOICES.accepted)

        if jos.exists() and self.workers <= accepted_jos.count():
            result = FULFILLED
        return result


class JobOffer(TimeZoneUUIDModel):
    STATUS_CHOICES = Choices(
        (0, 'undefined', _("Undefined")),
        (1, 'accepted', _("Accepted")),
        (2, 'cancelled', _("Cancelled")),
    )
    CANDIDATE_STATUS_CHOICES = STATUS_CHOICES + [
        (0, 'undefined', _("Undefined")),
        (1, 'accepted', _("Accepted")),
        (2, 'cancelled', _("Cancelled")),
        (3, 'already_filled', _("Already filled")),
        (4, 'declined_by_candidate', _("Declined by Candidate")),
        (5, 'cancelled_by_job_site_contact', _("Cancelled by Job Site Contact")),
        (6, 'cancelled_by', _("Cancelled by {additional_text}")),
    ]

    shift = models.ForeignKey(
        'hr.Shift',
        on_delete=models.CASCADE,
        related_name='job_offers',
        verbose_name=_('Shift')
    )

    candidate_contact = models.ForeignKey(
        'candidate.CandidateContact',
        verbose_name=_('Candidate contact'),
        on_delete=models.PROTECT,
        related_name='job_offers'
    )

    status = models.PositiveSmallIntegerField(
        verbose_name=_("Status"),
        choices=STATUS_CHOICES,
        default=STATUS_CHOICES.undefined
    )

    scheduled_sms_datetime = ref.DTField(
        null=True,
        blank=True,
        verbose_name=_("Scheduled date")
    )

    class Meta:
        verbose_name = _("Job Offer")
        verbose_name_plural = _("Job Offers")

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('shift__date__job__jobsite__address__longitude'),
            latitude=F('shift__date__job__jobsite__address__latitude')
        ).values_list('longitude', 'latitude').get()

    @property
    def scheduled_sms_datetime_tz(self):
        return self.utc2local(self.scheduled_sms_datetime)

    @property
    def scheduled_sms_datetime_utc(self):
        return self.scheduled_sms_datetime

    def __str__(self):
        return '{}'.format(date_format(self.created_at,
                                       settings.DATETIME_FORMAT))

    @property
    def job(self):
        return self.shift.job

    @property
    def start_time(self):
        return datetime.combine(self.shift.date.shift_date, self.shift.time)

    @property
    def start_time_tz(self):
        return self.dt2local(self.start_time)

    @property
    def start_time_utc(self):
        return self.local2utc(self.start_time_tz)

    def is_accepted(self):
        return self.status == JobOffer.STATUS_CHOICES.accepted

    def is_cancelled(self):
        return self.status == JobOffer.STATUS_CHOICES.cancelled

    def is_recurring(self):
        return self.job.get_job_offers().filter(
            candidate_contact=self.candidate_contact,
            shift__date__shift_date__lt=self.shift.date.shift_date,
            status=JobOffer.STATUS_CHOICES.accepted
        ).exists()

    def is_first(self):
        return not self.job.get_job_offers().filter(
            candidate_contact=self.candidate_contact,
            shift__date__shift_date__lt=self.shift.date.shift_date
        ).exists()

    def is_last(self):
        return not self.job.get_job_offers().filter(
            candidate_contact=self.candidate_contact,
            shift__date__shift_date__gt=self.shift.date.shift_date
        ).exists()

    def get_future_offers(self):
        return self.job.get_job_offers().filter(
            candidate_contact=self.candidate_contact,
            shift__date__shift_date__gt=self.shift.date.shift_date
        )

    def get_previous_offers(self):
        return self.job.get_job_offers().filter(
            candidate_contact=self.candidate_contact,
            shift__date__shift_date__lt=self.shift.date.shift_date
        )

    def move_candidate_to_carrier_list(self, new_offer=False, confirmed_available=None):
        if not confirmed_available:
            confirmed_available = self.is_accepted()

        cl = CarrierList.objects.filter(
            candidate_contact=self.candidate_contact,
            target_date=self.start_time_utc
        ).first()

        if cl is not None:
            cl.target_date = self.start_time_utc
            cl.confirmed_available = confirmed_available
        else:
            # TODO: uncomment after dynamic workflow upgrade
            # invalid_states = [
            #     RecruitmentStatus.STATE_CHOICES.failed,
            #     RecruitmentStatus.STATE_CHOICES.banned,
            #     RecruitmentStatus.STATE_CHOICES.suspended
            # ]
            # if self.candidate_contact.get_state() not in invalid_states:

            cl = CarrierList.objects.create(
                candidate_contact=self.candidate_contact,
                target_date=self.start_time_utc,
                confirmed_available=confirmed_available,
                skill=self.job.position
            )

        if cl:
            if new_offer:
                cl.job_offer = self
            else:
                cl.referral_job_offer = self
                cl.job_offer = None
            cl.save()

    def get_timesheets_with_going_work_unset_or_timeout(self, check_date=None):
        if check_date is None:
            check_date = self.now_tz.date()

        jos_with_timesheets = self.candidate_contact.job_offers.filter(
            time_sheets__shift_started_at__date=check_date,
            time_sheets__going_to_work_confirmation__isnull=True,
            time_sheets__going_to_work_sent_sms__check_reply_at__gte=self.now_tz
        )
        return jos_with_timesheets

    def has_timesheets_with_going_work_unset_or_timeout(self, check_date=None):
        return self.get_timesheets_with_going_work_unset_or_timeout(check_date).exists()

    def has_future_accepted_jo(self):
        """
        Check if there are future accepted JO for the candidate/job
        :return: True or False
        """
        return self.job.get_job_offers().filter(
            candidate_contact=self.candidate_contact,
            shift__time__gt=self.shift.time,
            shift__date__shift_date__gte=self.shift.date.shift_date,
            status=self.STATUS_CHOICES.accepted
        ).exists()

    def has_previous_jo(self):
        """
        Check if there are JO for the candidate/job earlier than this one
        :return: True or False
        """
        return self.job.get_job_offers().filter(
            models.Q(shift__date__shift_date=self.now_tz.date(),
                     shift__time__gte=self.now_tz.timetz()) |
            models.Q(shift__date__shift_date__gt=self.now_tz.date()),
            models.Q(shift__date__shift_date=self.shift.date.shift_date,
                     shift__time__lte=self.shift.time) |
            models.Q(shift__date__shift_date__lt=self.shift.date.shift_date),
            candidate_contact=self.candidate_contact,
        ).exists()

    def process_sms_reply(self, sent_sms, reply_sms, positive):
        if not (self.is_accepted() or self.is_cancelled()):
            assert isinstance(positive, bool), _('Looks like we could not decide if reply was positive')

            sent_offer_sms = self.job_offer_smses.filter(offer_sent_by_sms=sent_sms).first()
            if sent_offer_sms is not None:
                sent_offer_sms.reply_received_by_sms = reply_sms
                sent_offer_sms.save()

                if positive:
                    self.accept('status', 'scheduled_sms_datetime')
                else:
                    self.cancel()

    def accept(self, *update_fields):
        self.status = JobOffer.STATUS_CHOICES.accepted
        self.scheduled_sms_datetime = None
        if update_fields:
            self.save(update_fields=update_fields)
        else:
            self.save()

        if self.is_quota_filled():
            self._cancel_for_filled_quota()

    def cancel(self):
        if self.is_accepted():
            self.move_candidate_to_carrier_list()

        self.status = self.STATUS_CHOICES.cancelled
        self.scheduled_sms_datetime = None
        self.save()

        try:
            time_sheet = self.time_sheets.filter(
                job_offer__candidate_contact=self.candidate_contact,
                shift_started_at__gt=self.now_utc
            ).earliest('shift_started_at')
        except TimeSheet.DoesNotExist:
            time_sheet = None

        if time_sheet is not None:
            pre_shift_check_enabled = time_sheet.master_company.company_settings.pre_shift_sms_enabled
            if ((pre_shift_check_enabled and time_sheet.candidate_submitted_at is None) or
                    (time_sheet.shift_started_at - self.now_utc).total_seconds() > 3600):
                from r3sourcer.apps.hr.tasks import send_job_offer_cancelled
                send_job_offer_cancelled.delay(self.pk)

                time_sheet.delete()
            else:
                from r3sourcer.apps.hr.tasks import send_job_offer_cancelled_lt_one_hour
                send_job_offer_cancelled_lt_one_hour.delay(self.pk)

                if time_sheet.going_to_work_confirmation:
                    time_sheet.auto_fill_four_hours()

    def is_quota_filled(self):
        accepted_count = self.job.get_job_offers().filter(
            status=JobOffer.STATUS_CHOICES.accepted,
            shift=self.shift
        ).count()

        return accepted_count >= self.shift.workers

    def _cancel_for_filled_quota(self):
        with transaction.atomic():
            # if celery worked with JO sending
            qs = self.job.get_job_offers().filter(
                models.Q(job_offer_smses__offer_sent_by_sms=None) | models.Q(time_sheets=None),
                shift=self.shift
            ).exclude(status=JobOffer.STATUS_CHOICES.accepted)
            jo_with_sms_sent = list(qs.filter(job_offer_smses__offer_sent_by_sms__isnull=False).distinct())
            qs.update(status=JobOffer.STATUS_CHOICES.cancelled)

            # send placement rejection sms
            for sent_jo in jo_with_sms_sent:
                if sent_jo.id == self.id:
                    continue
                if self.now_tz <= sent_jo.start_time_tz:
                    hr_utils.send_jo_rejection(sent_jo)

    def check_job_quota(self, is_initial):
        if is_initial:
            if self.is_quota_filled() or self.is_cancelled():
                self._cancel_for_filled_quota()
                self.move_candidate_to_carrier_list()
                self.status = JobOffer.STATUS_CHOICES.cancelled

                if self.now_tz <= self.start_time_tz:
                    hr_utils.send_jo_rejection(self)

                return False
            else:
                self.status = JobOffer.STATUS_CHOICES.accepted
                return True
        else:
            return True

    def save(self, *args, **kwargs):
        is_resend = kwargs.pop('initial', False)
        just_added = self._state.adding or is_resend
        is_initial = not self.is_recurring()
        is_accepted = self.is_accepted()

        if not just_added:
            orig = JobOffer.objects.get(pk=self.pk)
            if self.is_cancelled() and orig.is_accepted():
                orig.move_candidate_to_carrier_list(confirmed_available=True)

            if self.is_accepted():
                is_accepted = orig.is_accepted() != self.is_accepted()

        create_time_sheet = False
        if is_accepted:
            create_time_sheet = self.check_job_quota(is_initial)

        super().save(*args, **kwargs)

        if create_time_sheet:
            TimeSheet.get_or_create_for_job_offer_accepted(self)

        if just_added:
            if not self.is_cancelled() and CarrierList.objects.filter(
                    candidate_contact=self.candidate_contact,
                    target_date=self.start_time_utc,
            ).exists():
                self.move_candidate_to_carrier_list(new_offer=True)

            # offer = JobOffer.objects.get(pk=self.pk)
            tomorrow = self.now_tz + timedelta(days=1)
            tomorrow_end = tomorrow.replace(hour=5, minute=0, second=0, microsecond=0) + timedelta(days=1)
            # TODO: maybe need to rethink, but it should work
            # compute eta to schedule SMS sending
            if is_resend:
                eta = self.now_tz + timedelta(seconds=10)
            elif self.start_time_tz <= tomorrow_end:
                # today and tomorrow day and night shifts
                eta = self.now_tz.replace(hour=10, minute=0, second=0, microsecond=0)

                if self.now_tz >= self.start_time_tz - timedelta(hours=1):
                    if self.now_tz >= self.start_time_tz + timedelta(hours=2):
                        eta = None
                    else:
                        eta = self.now_tz + timedelta(seconds=10)
                elif eta <= self.now_tz or eta >= self.start_time_tz - timedelta(hours=1, minutes=30):
                    eta = self.now_tz + timedelta(seconds=10)
            else:
                if not self.has_future_accepted_jo() \
                        and not self.has_previous_jo() \
                        and self.start_time_tz <= self.now_tz + timedelta(days=4):
                    eta = self.now_tz + timedelta(seconds=10)
                else:
                    # future date day shift
                    __target = self.start_time_tz.replace(hour=10, minute=0, second=0, microsecond=0)
                    eta = __target - timedelta(days=1)
            if eta:
                utc_eta = tz2utc(eta)
                self.scheduled_sms_datetime = utc_eta
                self.save(update_fields=['scheduled_sms_datetime'])
                if self.is_first() and not self.is_accepted():
                    task = send_jo_confirmation
                elif self.is_recurring():
                    task = send_recurring_jo_confirmation
                else:
                    # FIXME: send job confirmation SMS because there is pending job's JOs for candidate
                    task = send_jo_confirmation

                master_company = self.candidate_contact.contact.get_closest_company()

                task.apply_async(args=[self.id, master_company.id], eta=utc_eta)

class JobOfferSMS(UUIDModel):

    job_offer = models.ForeignKey(
        JobOffer,
        on_delete=models.CASCADE,
        related_name='job_offer_smses',
        verbose_name=_('Job Offer')
    )

    offer_sent_by_sms = models.ForeignKey(
        'sms_interface.SMSMessage',
        on_delete=models.SET_NULL,
        related_name='job_offer_smses',
        verbose_name=_("Offer sent by sms"),
        null=True,
        blank=True
    )

    reply_received_by_sms = models.ForeignKey(
        'sms_interface.SMSMessage',
        on_delete=models.SET_NULL,
        related_name='reply_job_offer_smses',
        verbose_name=_("Reply received by sms"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("Job Offer SMS")
        verbose_name_plural = _("Job Offer SMSes")


class TimeSheet(TimeZoneUUIDModel, WorkflowProcess):
    sent_sms_field = 'going_to_work_sent_sms'
    receive_sms_field = 'going_to_work_reply_sms'

    job_offer = models.ForeignKey(
        'hr.JobOffer',
        unique=True,
        on_delete=models.CASCADE,
        related_name='time_sheets',
        verbose_name=_('Job Offer')
    )

    going_to_work_sent_sms = models.ForeignKey(
        'sms_interface.SMSMessage',
        verbose_name=_('Going to Work Sent SMS'),
        related_name='time_sheets_going_to_work',
        blank=True,
        null=True,
        on_delete=models.PROTECT
    )

    going_to_work_reply_sms = models.ForeignKey(
        'sms_interface.SMSMessage',
        verbose_name=_('Going to Work Reply SMS'),
        related_name='time_sheets_going_to_work_reply',
        blank=True,
        null=True,
        on_delete=models.PROTECT
    )

    going_to_work_confirmation = models.NullBooleanField(
        verbose_name=_("Going to Work")
    )

    shift_started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Shift Started at"))
    break_started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Break Started at"))
    break_ended_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Break Ended at"))
    shift_ended_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Shift Ended at"))

    supervisor = models.ForeignKey(
        'core.CompanyContact',
        related_name="supervised_time_sheets",
        on_delete=models.PROTECT,
        verbose_name=_("Supervisor"),
        blank=True,
        null=True
    )

    WAGE_CHOICES = Choices(
        (0,'HOURLY', _("Hourly wage")),
        (1, 'PIECEWORK', _("Piecework wage")),
    )

    wage_type = models.PositiveSmallIntegerField(
        choices=WAGE_CHOICES,
        verbose_name=_("Type of wage"),
        default=WAGE_CHOICES.HOURLY
    )

    def supervisor_signature_path(self, filename):
        """ Supervisor signature upload handler """

        ext = filename.split('.')[-1]
        pattern = 'timesheets/signature/{ts_id}.{ext}'
        return pattern.format(
            ts_id=self.id,
            ext=ext
        )

    supervisor_signature = ThumbnailerImageField(
        _("Supervisor signature"),
        upload_to=supervisor_signature_path,
        blank=True,
        null=True,
    )

    candidate_submitted_at = ref.DTField(
        null=True,
        blank=True,
        verbose_name=_("Candidate Submitted at")
    )

    supervisor_approved_at = ref.DTField(
        null=True,
        blank=True,
        verbose_name=_("Supervisor Approved at")
    )

    supervisor_approved_scheme = models.CharField(
        verbose_name=_("Supervisor Approved scheme"),
        max_length=16,
        default='',
        choices=core_models.Company.TIMESHEET_APPROVAL_SCHEME,
        editable=False
    )

    supervisor_modified = models.BooleanField(
        verbose_name=_('Supervisor modified shift'),
        default=False
    )

    supervisor_modified_at = ref.DTField(
        null=True,
        blank=True,
        verbose_name=_("Supervisor modified at")
    )

    manager_who_approved = models.ForeignKey(
        core_models.CompanyContact,
        related_name="manager_approved_time_sheets",
        on_delete=models.PROTECT,
        verbose_name=_("Manager who approved"),
        blank=True,
        null=True
    )

    candidate_rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )

    worktype_rates = models.ManyToManyField(
        WorkType,
        through='hr.TimeSheetRate',
        blank=True,
        verbose_name=_("Activities rates"),
    )

    rate_overrides_approved_by = models.ForeignKey(
        'core.CompanyContact',
        related_name='timesheet_rate_override_approvals',
        on_delete=models.PROTECT,
        verbose_name=_("Candidate and Client Rate Overrides Approved by"),
        null=True,
        blank=True
    )

    rate_overrides_approved_at = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Candidate and Client Rate Overrides Approved at")
    )

    SYNC_STATUS_CHOICES = Choices(
        (0, 'not_synced', _('Not synced')),
        (1, 'sync_scheduled', _('Sync scheduled')),
        (2, 'syncing', _('Syncing...')),
        (3, 'synced', _('Synced')),
        (4, 'sync_failed', _('Sync failed')),
    )

    sync_status = models.PositiveSmallIntegerField(
        verbose_name=_("Sync status"),
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_STATUS_CHOICES.not_synced
    )

    STATUS_CHOICES = Choices(
        (0, 'new', _('New')),
        (1, 'check_pending', _('Check pending')),
        (2, 'check_confirmed', _('Check confirmed')),
        (3, 'check_failed', _('Check failed')),
        (4, 'submit_pending', _('Submit pending')),
        (5, 'approval_pending', _('Pending approval')),
        (6, 'modified', _('Supervisor modified')),
        (7, 'approved', _('Approved')),
    )

    status = models.PositiveSmallIntegerField(
        verbose_name=_('Status'),
        choices=STATUS_CHOICES,
        default=STATUS_CHOICES.new
    )

    __original_supervisor_id = None
    __original_going_to_work_confirmation = None
    __original_candidate_submitted_at = None

    class Meta:
        verbose_name = _("Timesheet Entry")
        verbose_name_plural = _("Timesheet Entries")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__original_supervisor_id = self.supervisor_id
        self.__original_going_to_work_confirmation = self.going_to_work_confirmation
        self.__original_candidate_submitted_at = self.candidate_submitted_at

    def __str__(self):
        fields = [self.shift_started_at_tz, self.candidate_submitted_at_tz]
        return ' '.join([str(x) for x in fields])

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('job_offer__shift__date__job__jobsite__address__longitude'),
            latitude=F('job_offer__shift__date__job__jobsite__address__latitude')
        ).values_list('longitude', 'latitude').get()

    @property
    def shift_started_at_tz(self):
        return self.utc2local(self.shift_started_at)

    @property
    def shift_started_at_utc(self):
        return self.shift_started_at

    @property
    def shift_ended_at_tz(self):
        return self.utc2local(self.shift_ended_at)

    @property
    def shift_ended_at_utc(self):
        return self.shift_ended_at

    @property
    def planned_shift_end_at_tz(self):
        return self.utc2local(self.shift_started_at + timedelta(hours=8, minutes=30))

    @property
    def planned_shift_end_at_utc(self):
        if self.shift_ended_at_utc:
            return self.shift_ended_at_utc

        return self.shift_started_at + timedelta(hours=8, minutes=30)

    @property
    def break_started_at_tz(self):
        return self.utc2local(self.break_started_at)

    @property
    def break_started_at_utc(self):
        return self.break_started_at

    @property
    def break_ended_at_tz(self):
        return self.utc2local(self.break_ended_at)

    @property
    def break_ended_at_utc(self):
        return self.break_ended_at

    def get_job_offer(self):
        return self.job_offer

    @property
    def candidate_submitted_at_tz(self):
        return self.utc2local(self.candidate_submitted_at)

    @property
    def candidate_submitted_at_utc(self):
        return self.candidate_submitted_at

    @property
    def supervisor_approved_at_tz(self):
        return self.utc2local(self.supervisor_approved_at)

    @property
    def supervisor_approved_at_utc(self):
        return self.supervisor_approved_at

    @property
    def supervisor_modified_at_tz(self):
        return self.utc2local(self.supervisor_modified_at)

    @property
    def supervisor_modified_at_utc(self):
        return self.supervisor_modified_at

    @property
    def today_5_am(self):
        return self.now_tz.replace(hour=5, minute=0, second=0, microsecond=0)

    @property
    def today_7_am(self):
        return self.now_tz.replace(hour=7, minute=0, second=0, microsecond=0)

    @property
    def today_12_pm(self):
        return self.now_tz.replace(hour=12, minute=0, second=0, microsecond=0)

    @property
    def today_12_30_pm(self):
        return self.now_tz.replace(hour=12, minute=30, second=0, microsecond=0)

    @property
    def today_3_30_pm(self):
        return self.now_tz.replace(hour=15, minute=30, second=0, microsecond=0)

    @property
    def tomorrow(self):
        return self.now_tz + timedelta(days=1)

    @property
    def master_company(self):
        return self.job_offer.shift.date.job.jobsite.master_company

    @property
    def regular_company(self):
        jobsite = self.job_offer.shift.date.job.jobsite
        return jobsite and jobsite.regular_company

    @classmethod
    def get_or_create_for_job_offer_accepted(cls, job_offer):
        master_company = job_offer.shift.date.job.jobsite.master_company
        going_to_work_confirmation = None
        status = cls.STATUS_CHOICES.new

        if not master_company.company_settings.pre_shift_sms_enabled:
            going_to_work_confirmation = True
            status = cls.STATUS_CHOICES.check_confirmed

        data = {
            'job_offer': job_offer,
            'shift_started_at': job_offer.start_time_utc,
            # 'break_started_at': job_offer.start_time_utc + timedelta(hours=5),
            # 'break_ended_at': job_offer.start_time_utc + timedelta(hours=5, minutes=30),
            # 'shift_ended_at': job_offer.start_time_utc + timedelta(hours=8, minutes=30),
            'supervisor': job_offer.job.jobsite.primary_contact,
            'candidate_rate': job_offer.shift.hourly_rate,
            'going_to_work_confirmation': going_to_work_confirmation,
            'status': status,
        }

        try:
            time_sheet, created = cls.objects.get_or_create(**data)
        except IntegrityError:
            time_sheet, created = cls.objects.update_or_create(
                job_offer=job_offer,
                shift_started_at=job_offer.start_time_utc,
                defaults=data
            )

        if utc_now() <= job_offer.start_time_utc + timedelta(hours=2):
            cls._send_placement_acceptance_sms(time_sheet, job_offer)

        return time_sheet

    @classmethod
    def _send_placement_acceptance_sms(cls, time_sheet, job_offer):
        from r3sourcer.apps.hr.tasks import send_placement_acceptance_message
        send_placement_acceptance_message.apply_async(args=[time_sheet.id, job_offer.id], countdown=10)

    def get_closest_company(self):
        return self.job_offer.job.get_closest_company()

    @property
    def candidate_contact(self):
        return self.job_offer.candidate_contact

    @property
    def skill(self):
        return self.job_offer.job.position

    @property
    def shift_delta(self):
        if self.shift_ended_at and self.shift_started_at:
            return self.shift_ended_at - self.shift_started_at
        return None

    @property
    def break_delta(self):
        if self.break_ended_at and self.break_started_at:
            return self.break_ended_at - self.break_started_at
        return None

    @property
    def shift_duration(self):
        if self.shift_delta and self.break_delta:
            return self.shift_delta - self.break_delta
        elif self.shift_delta and not self.break_delta:
            return self.shift_delta
        else:
            return timedelta(0)

    @property
    def get_hourly_rate(self):
        return self.timesheet_rates.filter(worktype__name=WorkType.DEFAULT).first().rate if self.timesheet_rates.filter(
            worktype__name=WorkType.DEFAULT) else 0

    @property
    def candidate_earning(self):
        earning = 0
        ts_rates = self.timesheet_rates.all()
        for ts_rate in ts_rates:
            earning += ts_rate.rate * ts_rate.value
        return math.ceil(earning * 100) / 100

    @property
    def profit_for_master_company(self):
        master_company_gross_profit = 0
        for ts_rate in self.timesheet_rates.all():
            master_company_gross_profit += ts_rate.master_company_profit
        return math.ceil(master_company_gross_profit * 100) / 100

    def calc_gross_summary_profit(self):
        for ts_rate in self.timesheet_rates.all():
            price_list_rate = PriceListRate.objects.filter(
                worktype=ts_rate.worktype,
                price_list__company=self.job_offer.shift.date.job.customer_company,
            ).last()

            if not price_list_rate:
                raise Exception('Price list missing for the company. Cannot continue.')

    def auto_fill_four_hours(self):
        self.candidate_submitted_at = utc_now()
        self.supervisor_approved_at = utc_now()
        self.shift_started_at = utc_now()
        self.shift_ended_at = utc_now() + timedelta(hours=4)
        self.break_started_at = None
        self.break_ended_at = None
        self.supervisor_modified = False
        self.supervisor_modified_at = None
        self.save()

    def _send_going_to_work(self, going_eta):
        if going_eta.tzinfo is None:
            raise ValueError('Invalid eta, datetime without timezone')
        from r3sourcer.apps.hr.tasks import send_going_to_work_message
        utc_going_eta = tz2utc(going_eta)
        send_going_to_work_message.apply_async(args=[self.pk], eta=utc_going_eta)

    def _send_submit_sms(self, going_eta):
        if going_eta.tzinfo is None:
            raise ValueError('Invalid eta, datetime without timezone')

        if going_eta.tzinfo != pytz.utc:
            raise ValueError('Invalid timezone, need UTC but provided %s' % {going_eta.tzinfo})

        from r3sourcer.apps.hr.tasks import process_time_sheet_log_and_send_notifications, SHIFT_ENDING
        if app.control.inspect().scheduled():
            for task in chain.from_iterable(app.control.inspect().scheduled().values()):
                if str(eval(task['request']['args'])[0]) == str(self.id) and task['request'][
                    'name'] == \
                        'r3sourcer.apps.hr.tasks.process_time_sheet_log_and_send_notifications':
                    if str(eval(task['request']['args'])[1]) == '1':
                        app.control.revoke(task['request']['id'], terminate=True, signal='SIGKILL')
            process_time_sheet_log_and_send_notifications.apply_async(args=[self.pk, SHIFT_ENDING], eta=going_eta)

    def process_sms_reply(self, sent_sms, reply_sms, positive):
        if self.going_to_work_confirmation is None:
            assert isinstance(positive, bool), _('Looks like we could not decide if reply was positive')
            if self.going_to_work_sent_sms == sent_sms:
                self.going_to_work_reply_sms = reply_sms
                self.going_to_work_confirmation = positive
                self.update_status(False)
                self.save()

    def set_sync_status(self, status):
        self.sync_status = status
        self.save(update_fields=['sync_status'])

    def process_status(self):
        if self.status == self.STATUS_CHOICES.check_confirmed:
            if self.shift_started_at <= utc_now():
                self.status = self.STATUS_CHOICES.submit_pending
                self.save(update_fields=['status'])

    def process_pending_status(self):
        if self.going_to_work_confirmation is None:
            pre_shift_confirmation_delta = self.master_company.company_settings.pre_shift_sms_delta
            utc_going_eta = self.shift_started_at - timedelta(minutes=pre_shift_confirmation_delta)
            if utc_going_eta <= utc_now():
                self.status = self.STATUS_CHOICES.check_pending
                self.save(update_fields=['status'])

    def update_status(self, save=True):
        if self.supervisor_approved_at is not None:
            self.status = self.STATUS_CHOICES.approved

        elif self.supervisor_modified:
            if self.status != self.STATUS_CHOICES.approved \
                    or self.supervisor_approved_at is None:
                self.status = self.STATUS_CHOICES.modified

        elif self.candidate_submitted_at is not None:
            self.status = self.STATUS_CHOICES.approval_pending

        elif self.going_to_work_confirmation:
            if self.shift_started_at <= utc_now():
                self.status = self.STATUS_CHOICES.submit_pending
            else:
                self.status = self.STATUS_CHOICES.check_confirmed

        elif self.going_to_work_confirmation is None:
            pre_shift_confirmation_delta = self.master_company.company_settings.pre_shift_sms_delta
            going_eta = self.shift_started_at - timedelta(minutes=pre_shift_confirmation_delta)
            if going_eta <= utc_now():
                self.status = self.STATUS_CHOICES.check_pending

        elif not self.going_to_work_confirmation:
            self.status = self.STATUS_CHOICES.check_failed

        if save:
            self.save(update_fields=['status'])

    def _datetime_fields(self, just_added):
        fields = [
            ('candidate_submitted_at', self.candidate_submitted_at, None),
            ('supervisor_approved_at', self.supervisor_approved_at, None),
            ('supervisor_modified_at', self.supervisor_modified_at, None),
            ('rate_overrides_approved_at', self.rate_overrides_approved_at, None),
        ]
        if just_added:
            fields += [
                ('shift_started_at', self.shift_started_at, self.today_7_am),
                # ('shift_ended_at', self.shift_ended_at, self.today_3_30_pm),
                # ('break_started_at', self.break_started_at, self.today_12_pm),
                # ('break_ended_at', self.break_ended_at, self.today_12_30_pm),
            ]
        else:
            fields += [
                ('shift_started_at', self.shift_started_at, self.job_offer.start_time_tz),
                ('shift_ended_at', self.shift_ended_at, None),
                ('break_started_at', self.break_started_at, None),
                ('break_ended_at', self.break_ended_at, None),
            ]
        return tuple(fields)

    def convert_datetime_before_save(self, just_added):
        def setter_fn(args):
            field, value = args
            setattr(self, field, value)

        def filter_fn(args):
            _, value = args
            return value is not None

        fields = [(field, x or y) for field, x, y in self._datetime_fields(just_added)]
        list(map(setter_fn, filter(filter_fn, fields)))

    def save(self, *args, **kwargs):

        just_added = self._state.adding
        self.convert_datetime_before_save(just_added)

        going_set = self.going_to_work_confirmation is not None and (
            just_added or self.__original_going_to_work_confirmation != self.going_to_work_confirmation
        )
        candidate_submitted_at = self.candidate_submitted_at is not None and (
            just_added or self.__original_candidate_submitted_at != self.candidate_submitted_at
        )
        if just_added:
            if not self.supervisor and self.job_offer:
                self.supervisor = self.job_offer.job.jobsite.primary_contact
            if utc_now() <= self.shift_started_at:
                pre_shift_confirmation = self.master_company.company_settings.pre_shift_sms_enabled
                pre_shift_confirmation_delta = self.master_company.company_settings.pre_shift_sms_delta
                going_eta = self.shift_started_at - timedelta(minutes=pre_shift_confirmation_delta)
                if pre_shift_confirmation and going_eta > utc_now():
                    self._send_going_to_work(going_eta)
                else:
                    self.going_to_work_confirmation = True
        else:
            if self.candidate_submitted_at is not None and self.is_allowed(30):
                self.create_state(30)

            if self.supervisor_approved_at is not None and self.is_allowed(40):
                self.create_state(40)

            if self.is_allowed(70):
                self.create_state(70)
        if not self.supervisor_modified_at:
            self.supervisor_modified = False
        if self.supervisor_modified_at:
            self.supervisor_modified = True

        self.update_status(False)

        super().save(*args, **kwargs)

        if self.wage_type == self.WAGE_CHOICES.HOURLY and self.candidate_submitted_at:

            hourly_activity = None
            hourly_work = WorkType.objects.filter(name=WorkType.DEFAULT,
                                                  skill_name=self.job_offer.job.position.name) \
                                          .first()
            if hourly_work:
                hourly_activity = self.timesheet_rates.filter(worktype=hourly_work).first()

            # add or modify hourly_rate skill activity
            if hourly_activity:
                if self.shift_duration:
                    hourly_activity.value = self.shift_duration.total_seconds()/3600
                    hourly_activity.save()
                else:
                    hourly_activity.delete()
            elif self.shift_duration:
                TimeSheetRate.objects.create(timesheet=self,
                                             worktype=hourly_work,
                                             value=self.shift_duration.total_seconds()/3600,
                                             )

        if just_added and self.is_allowed(10):
            self.create_state(10)

        if going_set and self.going_to_work_confirmation and self.is_allowed(20):
            self.create_state(20)
            self._send_submit_sms(self.shift_started_at + timedelta(hours=8, minutes=30))

        # If accepted manually, disable reply checking.
        if self.going_to_work_confirmation and self.going_to_work_sent_sms and self.going_to_work_sent_sms.check_reply:
            self.going_to_work_sent_sms.no_check_reply()
        self.__original_supervisor_id = self.supervisor_id
        self.__original_going_to_work_confirmation = self.going_to_work_confirmation
        self.__original_candidate_submitted_at = self.candidate_submitted_at

        if candidate_submitted_at and self.supervisor and not self.supervisor_approved_at:
            hr_utils.send_supervisor_timesheet_approve(self)


class TimeSheetIssue(
        UUIDModel,
        WorkflowProcess):

    time_sheet = models.ForeignKey(
        TimeSheet,
        on_delete=models.PROTECT,
        related_name="timesheet_issues",
        verbose_name=_("TimeSheet")
    )

    subject = models.CharField(
        max_length=255,
        verbose_name=_("Subject")
    )

    description = models.TextField(
        verbose_name=_("Description")
    )

    supervisor = models.ForeignKey(
        core_models.CompanyContact,
        related_name="supervised_timesheet_issues",
        on_delete=models.PROTECT,
        verbose_name=_("Supervisor")
    )

    supervisor_approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Supervisor Approved at")
    )

    account_representative = models.ForeignKey(
        core_models.CompanyContact,
        related_name="timesheet_issues",
        verbose_name=_("Account Contact Responsible"),
        on_delete=models.PROTECT,
        null=True
    )

    class Meta:
        verbose_name = _("Timesheet Issue")
        verbose_name_plural = _("Timesheet Issues")

    def __str__(self):
        return '{}: {}'.format(str(self.time_sheet), str(self.subject))

    def get_closest_company(self):
        return self.time_sheet.get_closest_company()


class BlackList(UUIDModel):

    company = models.ForeignKey(
        'core.Company',
        related_name="blacklists",
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
        blank=True,
        null=True,
    )

    candidate_contact = models.ForeignKey(
        'candidate.CandidateContact',
        on_delete=models.CASCADE,
        related_name="blacklists",
        verbose_name=_("Candidate Contact")
    )

    timesheet = models.ForeignKey(
        TimeSheet,
        verbose_name=_('Timesheet'),
        related_name='blacklists',
        blank=True,
        null=True,
        on_delete=models.PROTECT
    )

    jobsite = models.ForeignKey(
        Jobsite,
        verbose_name=_('Jobsite'),
        related_name='blacklists',
        blank=True,
        null=True,
        on_delete=models.PROTECT
    )

    company_contact = models.ForeignKey(
        core_models.CompanyContact,
        verbose_name=_('Company Contact'),
        related_name='blacklists',
        blank=True,
        null=True,
        on_delete=models.PROTECT
    )

    client_contact = models.ForeignKey(
        core_models.CompanyContact,
        related_name='blacklists_client',
        verbose_name=_('Company Client'),
        blank=True,
        null=True,
        on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _("Black list")
        verbose_name_plural = _("Black lists")
        unique_together = ('company', 'company_contact', 'candidate_contact', 'timesheet', 'jobsite')

    def __str__(self):
        return "{}: {}".format(str(self.company), str(self.candidate_contact))

    def clean(self):
        """
        Checks that we do not create multiple BlackList items
        with same fields values.
        """
        if self.timesheet and not self.jobsite:
            self.jobsite = self.timesheet.job_offer.job.jobsite
        if self.timesheet and not self.company_contact:
            self.company_contact = self.timesheet.supervisor
        if BlackList.objects.filter(
            company=self.company,
            company_contact=self.company_contact,
            candidate_contact=self.candidate_contact,
            timesheet=self.timesheet,
            jobsite=self.jobsite,
        ).exists():
            raise ValidationError(_('Another BlackList item with such parameters already exists'))
        super().clean()

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, core_models.Company):
            return [
                models.Q(company=owner),
                models.Q(company__regular_companies__master_company=owner),
                models.Q(jobsite__master_company=owner),
            ]


class FavouriteList(UUIDModel):

    company_contact = models.ForeignKey(
        core_models.CompanyContact,
        related_name='favouritelist',
        verbose_name=_('Favourite list owner'),
        on_delete=models.CASCADE
    )

    candidate_contact = models.ForeignKey(
        'candidate.CandidateContact',
        related_name="favouritelists",
        verbose_name=_("Candidate Contact"),
        on_delete=models.CASCADE,
    )

    company = models.ForeignKey(
        'core.Company',
        related_name="favouritelists",
        verbose_name=_("Company"),
        blank=True,
        null=True,
        on_delete=models.SET_NULL
    )

    jobsite = models.ForeignKey(
        Jobsite,
        verbose_name=_('Jobsite'),
        related_name='favouritelists',
        blank=True,
        null=True,
        on_delete=models.CASCADE
    )

    job = models.ForeignKey(
        Job,
        verbose_name=_('Job'),
        related_name='favouritelists',
        blank=True,
        null=True,
        on_delete=models.CASCADE
    )

    client_contact = models.ForeignKey(
        core_models.CompanyContact,
        related_name='favouritelist_client',
        verbose_name=_('Favourite list client'),
        blank=True,
        null=True,
        on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _("Favourite list")
        verbose_name_plural = _("Favourite lists")
        unique_together = ('company_contact', 'candidate_contact', 'company', 'jobsite', 'job')

    def __str__(self):
        return "{}: {}".format(str(self.company_contact), str(self.candidate_contact))

    def clean(self):
        """
        Checks that we do not create multiple FavouriteList items
        with same fields values.
        """
        if not hasattr(self, 'candidate_contact'):
            raise ValidationError({
                'candidate_contact': _('Please select Candidate Contact')
            })

        if self.job:
            self.jobsite = self.job.jobsite
        if self.jobsite:
            self.company = self.jobsite.master_company
        if FavouriteList.objects.filter(
            company_contact=self.company_contact,
            candidate_contact=self.candidate_contact,
            company=self.company,
            jobsite=self.jobsite,
            job=self.job,
        ).exists() and not (self.company and self.jobsite and self.job):
            raise ValidationError(_('Another FavoritList item with such parameters already exists'))
        super().clean()

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, core_models.Company):
            return [
                models.Q(company=owner),
                models.Q(company__regular_companies__master_company=owner),
                models.Q(jobsite__master_company=owner),
            ]


class CarrierList(UUIDModel):
    """a backup list for specific date and skill"""

    candidate_contact = models.ForeignKey(
        'candidate.CandidateContact',
        on_delete=models.CASCADE,
        related_name='carrier_lists',
        verbose_name=_('Candidate Contact'),
        blank=True,
        null=True
    )

    target_date = models.DateField(verbose_name=_('Target Date'))

    confirmed_available = models.BooleanField(
        default=False,
        verbose_name=_('Confirmed Available')
    )

    sent_message = models.ForeignKey(
        'sms_interface.SMSMessage',
        verbose_name=_('Sent SMS Message'),
        related_name='sent_carrier_lists',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    reply_message = models.ForeignKey(
        'sms_interface.SMSMessage',
        verbose_name=_('Reply SMS Message'),
        related_name='reply_carrier_lists',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    job_offer = models.ForeignKey(
        'hr.JobOffer',
        verbose_name=_('Job Offer'),
        related_name='carrier_lists',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    referral_job_offer = models.ForeignKey(
        'hr.JobOffer',
        verbose_name=_('Referral Job Offer'),
        related_name='referral_carrier_lists',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    sms_sending_scheduled_at = models.DateTimeField(
        verbose_name=_("SMS sending scheduled at"),
        null=True,
        blank=True
    )

    skill = models.ForeignKey(
        'skills.Skill',
        verbose_name=_('Skill'),
        related_name='carrier_lists',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _("Carrier List")
        verbose_name_plural = _("Carrier Lists")
        unique_together = ('candidate_contact', 'target_date')

    def __str__(self):
        return '{}: {}'.format(
            str(self.candidate_contact),
            date_format(self.target_date, settings.DATE_FORMAT)
        )

    def confirm(self):
        self.confirmed_available = True
        self.save(update_fields=['confirmed_available'])

    def deny(self):
        self.confirmed_available = False
        self.save(update_fields=['confirmed_available'])

    def save(self, *args, **kwargs):
        just_added = self._state.adding
        super(CarrierList, self).save(*args, **kwargs)

        if not self.confirmed_available:
            from .tasks import send_carrier_list_offer_sms
            send_carrier_list_offer_sms.apply_async(args=[self.id], countdown=5)

    def process_sms_reply(self, sent_sms, reply_sms, positive):
        assert isinstance(positive, bool), _('Looks like we could not decide if reply was positive')
        if self.sent_message == sent_sms:
            self.reply_message = reply_sms
            self.confirmed_available = positive
            self.save()


class CandidateEvaluation(UUIDModel):

    candidate_contact = models.ForeignKey(
        'candidate.CandidateContact',
        on_delete=models.CASCADE,
        related_name="candidate_evaluations",
        verbose_name=_("Candidate Contact")
    )

    supervisor = models.ForeignKey(
        core_models.CompanyContact,
        related_name="supervised_candidate_evaluations",
        on_delete=models.PROTECT,
        verbose_name=_("Supervisor"),
        blank=True,
        null=True
    )

    evaluated_at = models.DateTimeField(
        verbose_name=_("Evaluated at"),
        auto_now_add=True,
        blank=True,
        null=True
    )

    reference_timesheet = models.ForeignKey(
        TimeSheet,
        on_delete=models.CASCADE,
        related_name="candidate_evaluations",
        verbose_name=_("Reference TimeSheet"),
        blank=True,
        null=True
    )

    EVALUATION_SCORE_CHOICES = Choices(
        (0, 'unrated', _("Not Rated")),
        (1, 'impossible', _("Impossible")),
        (2, 'hard', _("Hard")),
        (3, 'decent', _("Decent")),
        (4, 'good', _("Good")),
        (5, 'excellent', _("Excellent")),
    )

    evaluation_score = models.PositiveSmallIntegerField(
        verbose_name=_("Level of Communication"),
        choices=EVALUATION_SCORE_CHOICES,
        default=EVALUATION_SCORE_CHOICES.unrated
    )

    was_on_time = models.NullBooleanField(
        verbose_name=_("Was on time?")
    )
    was_motivated = models.NullBooleanField(
        verbose_name=_("Was motivated?")
    )
    had_ppe_and_tickets = models.NullBooleanField(
        verbose_name=_("Had PPE and tickets?")
    )
    met_expectations = models.NullBooleanField(
        verbose_name=_("Met Your expectations?")
    )
    representation = models.NullBooleanField(
        verbose_name=_("Was clean, well presented?")
    )

    class Meta:
        verbose_name = _("Candidate Evaluation")
        verbose_name_plural = _("Candidate Evaluations")

    def single_evaluation_average(self):
        return self.evaluation_score
    single_evaluation_average.short_description = _("Jobsite Feedback")


class ContactJobsiteDistanceCache(UUIDModel):
    contact = models.ForeignKey(
        'core.Contact',
        on_delete=models.CASCADE,
        related_name='distance_caches',
        verbose_name=_("Contact")
    )

    jobsite = models.ForeignKey(
        'hr.Jobsite',
        on_delete=models.CASCADE,
        related_name='distance_caches',
        verbose_name=_("Jobsite")
    )

    distance = models.IntegerField()

    time = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("contact", "jobsite")


class Payslip(UUIDModel):

    payment_date = models.DateField(
        verbose_name=_("Payment Date"),
        null=True,
        blank=True
    )

    annual_salary = models.DecimalField(
        verbose_name=_("Annual salary"),
        max_digits=8,
        decimal_places=2,
        default=0
    )

    hourly_rate = models.ForeignKey(
        SkillBaseRate,
        related_name="payslips",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("Hourly rate"),
    )

    from_date = models.DateField(
        verbose_name=_("From Date")
    )

    to_date = models.DateField(
        verbose_name=_("To Date")
    )

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.SET_NULL,
        verbose_name=_("Company"),
        related_name="payslips",
        null=True,
        blank=True
    )

    candidate = models.ForeignKey(
        'candidate.CandidateContact',
        verbose_name=_("Candidate contact"),
        related_name="payslips",
        on_delete=models.CASCADE,
    )

    cheque_number = models.TextField(
        verbose_name=_("Cheque number")
    )

    class Meta:
        verbose_name = _("Payslip")
        verbose_name_plural = _("Payslips")

    def save(self, *args, **kwargs):
        just_added = self._state.adding
        if just_added:
            rule = None
            if self.company.payslip_rules.exists():
                rule = self.company.payslip_rules.first()
            else:
                master_company = self.company.get_master_company()[0]
                if master_company.payslip_rules.exists():
                    rule = master_company.payslip_rules.first()

            if rule:
                self.cheque_number = str(rule.starting_number)
                rule.starting_number += 1
                rule.save()

        super(Payslip, self).save(*args, **kwargs)

    def get_gross_pay(self):
        sum_pay = Decimal()
        for line in self.payslip_lines.filter(type=0).all():
            sum_pay += line.amount

        return sum_pay

    def get_wage_pay(self):
        pay = self.get_gross_pay()
        pay += self.get_payg_pay()

        return pay

    def get_payg_pay(self):
        sum_pay = Decimal()
        for line in self.payslip_lines.filter(type=1).all():
            sum_pay += line.amount

        return sum_pay

    def get_superannuation_pay(self):
        sum_pay = Decimal()
        for line in self.payslip_lines.filter(type=2).all():
            sum_pay += line.amount

        return sum_pay


class PayslipRule(core_models.AbstractPayRuleMixin, UUIDModel):

    company = models.ForeignKey(
        'core.Company',
        related_name="payslip_rules",
        verbose_name=_("Company"),
        on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _("Payslip Rule")
        verbose_name_plural = _("Payslip Rules")


class PayslipLine(UUIDModel):

    description = models.CharField(
        max_length=255,
        verbose_name=_("Description")
    )

    hours = models.DecimalField(
        verbose_name=_("Hours"),
        max_digits=8,
        decimal_places=2,
        default=0
    )

    calc_rate = models.DecimalField(
        verbose_name=_("Calc. Rate"),
        max_digits=8,
        decimal_places=2,
        default=0
    )

    amount = models.DecimalField(
        verbose_name=_("Amount"),
        max_digits=8,
        decimal_places=2
    )

    ytd = models.DecimalField(
        verbose_name=_("YTD"),
        max_digits=8,
        decimal_places=2,
        default=0
    )

    TYPE_CHOICES = Choices(
        (0, 'wages', _('Wages')),
        (1, 'tax', _('Tax')),
        (2, 'superannuation', _('Superannuation Expenses')),
    )

    type = models.PositiveSmallIntegerField(
        choices=TYPE_CHOICES,
        verbose_name=_('Type'),
    )

    payslip = models.ForeignKey(
        Payslip,
        related_name="payslip_lines",
        verbose_name=_("Payslip"),
        on_delete=models.PROTECT
    )

    class Meta:
        verbose_name = _("Payslip Line")
        verbose_name_plural = _("Payslip Lines")

    def get_type(self):
        return self.TYPE_CHOICES[self.type]


class PersonalIncomeTax(UUIDModel):

    country = models.ForeignKey(
        core_models.Country,
        to_field='code2',
        default='AU',
        on_delete=models.CASCADE,
    )

    name = models.CharField(
        max_length=64,
        verbose_name=_("Name"),
    )

    PERIOD_CHOICES = Choices(
        ('weekly', _('Weekly')),
        ('fortnightly', _('Fortnightly')),
        ('monthly', _('Monthly')),
        ('daily', _('Daily'))
    )

    period = models.CharField(
        max_length=11,
        verbose_name=_("Period"),
        choices=PERIOD_CHOICES,
        default=PERIOD_CHOICES.weekly
    )

    rule = models.CharField(
        max_length=255,
        verbose_name=_("Rule")
    )

    start_date = models.DateField(
        verbose_name=_("Start Date")
    )

    end_date = models.DateField(
        verbose_name=_("End Date"),
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = _("Personal Income Tax")
        verbose_name_plural = _("Personal Income Taxes")


class SocialInsurance(UUIDModel):

    country = models.ForeignKey(
        core_models.Country,
        to_field='code2',
        default='AU',
        on_delete=models.CASCADE,
    )

    name = models.CharField(
        max_length=64,
        verbose_name=_("Name"),
        default=_("Superannuation")
    )

    threshold = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        verbose_name=_("Threshold"),
        default=0.00
    )

    rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        verbose_name=_("Rate"),
        default=0.00
    )

    start_date = models.DateField(
        verbose_name=_("Start Date")
    )

    end_date = models.DateField(
        verbose_name=_("End Date"),
        blank=True,
        null=True
    )

    age_threshold = models.IntegerField(
        verbose_name=_("Age threshold"),
        default=18,
        null=True
    )

    class Meta:
        verbose_name = _("Social Insurance")
        verbose_name_plural = _("Social Insurances")


class CandidateScore(UUIDModel):

    candidate_contact = models.OneToOneField(
        'candidate.CandidateContact',
        on_delete=models.CASCADE,
        related_name="candidate_scores",
        verbose_name=_("Candidate Scores"),
        null=True,
        blank=True,
    )

    client_feedback = models.DecimalField(
        decimal_places=2,
        max_digits=3,
        verbose_name=_("Client Feedback"),
        null=True
    )

    reliability = models.DecimalField(
        decimal_places=2,
        max_digits=3,
        verbose_name=_("Reliability"),
        null=True
    )

    loyalty = models.DecimalField(
        decimal_places=2,
        max_digits=3,
        verbose_name=_("Loyalty"),
        null=True
    )

    recruitment_score = models.DecimalField(
        decimal_places=2,
        max_digits=3,
        verbose_name=_("Recruitment Score"),
        null=True
    )

    average_score = models.DecimalField(
        decimal_places=2,
        max_digits=3,
        verbose_name=_("Average Score"),
        null=True,
        editable=False
    )

    skill_score = models.DecimalField(
        decimal_places=2,
        max_digits=3,
        verbose_name=_("Skill Score"),
        null=True,
        editable=False
    )

    class Meta:
        verbose_name = _("Candidate Score")
        verbose_name_plural = _("Candidates' Scores")

    def recalc_client_feedback(self):
        """
        Calculate client feedback score
        :return: self
        """
        total = 0
        counter = 0
        for evaluation in self.candidate_contact.candidate_evaluations.all():
            if evaluation.single_evaluation_average() > 0:
                total += evaluation.single_evaluation_average()
                counter += 1
        self.client_feedback = total / counter if counter > 0 else None

    def recalc_reliability(self, save=True):
        """
        Calculate reliability score
        :return: self
        """
        jos = JobOffer.objects.filter(
            candidate_contact=self.candidate_contact
        )
        accepted_jos = jos.filter(
            status=JobOffer.STATUS_CHOICES.accepted
        ).count()
        cancelled_jos = endless_logger.get_history_object_ids(
            JobOffer, 'status', '2', ids=jos.values_list('id', flat=True)
        )
        absent_jos = len(endless_logger.get_history_object_ids(
            JobOffer, 'status', '1', ids=cancelled_jos
        ))

        total_jos = accepted_jos + absent_jos

        reliability = (
            5 * (accepted_jos / total_jos) if total_jos > 4 else 0
        )
        if save:
            self.reliability = reliability if reliability >= 1 else None

        return reliability

    def recalc_loyalty(self):
        """
        Calculate loyalty score
        :return: self
        """
        loyalty = 0
        count = 1
        jos = JobOffer.objects.filter(
            candidate_contact=self.candidate_contact
        )
        accepted_jos = jos.filter(
            status=JobOffer.STATUS_CHOICES.accepted
        )

        # Calculate shift acceptance
        loyalty = self.recalc_reliability(False)

        # Calculate time bonus
        time_shift = timedelta(hours=1, minutes=30)
        time_bonus = accepted_jos.filter(
            job_offer_smses__offer_sent_by_sms__sent_at__gte=(
                models.F('shift__date__shift_date') - time_shift
            )
        ).count()
        if time_bonus:
            loyalty += time_bonus*5
            count += time_bonus

        # Calculate distance bonus
        distances = ContactJobsiteDistanceCache.objects.filter(
            contact=self.candidate_contact.contact,
            jobsite__in=jos.values_list(
                'shift__date__job__jobsite', flat=True
            ),
        )
        if (self.candidate_contact.transportation_to_work ==
                CandidateContact.TRANSPORTATION_CHOICES.own):
            distance_bonus = distances.filter(distance__gt=50000).count()
        else:
            distance_bonus = distances.filter(time__gt=3600).count()

        if distance_bonus:
            loyalty += distance_bonus*5
            count += distance_bonus

        # Calculate main loyalty value
        if count:
            self.loyalty = loyalty/count
        else:
            self.loyalty = None

    def recalc_recruitment_score(self):
        states = self.candidate_contact.get_active_states()
        company = self.candidate_contact.get_closest_company()

        scores = []
        for state in states:
            score = state.get_score(self.candidate_contact, company)
            if score > 0:
                scores.append(score)

        self.recruitment_score = sum(scores) / len(scores) if len(scores) > 0 else None

    def recalc_skill_score(self):
        """
        Calculate skill score
        :return: self
        """
        score = self.candidate_contact.candidate_skills.aggregate(avg_score=models.Avg('score'))['avg_score']
        self.skill_score = score or None

    def recalc_scores(self):
        self.recalc_client_feedback()
        self.recalc_reliability()
        self.recalc_loyalty()
        self.recalc_recruitment_score()
        self.recalc_skill_score()
        self.average_score = self.get_average_score()
        self.save()

    def get_average_score(self):
        total_score = 0
        scores_count = 0
        if self.client_feedback:
            total_score += self.client_feedback
            scores_count += 1
        if self.reliability:
            total_score += self.reliability
            scores_count += 1
        if self.loyalty:
            total_score += self.loyalty
            scores_count += 1
        if self.recruitment_score:
            total_score += self.recruitment_score
            scores_count += 1
        if self.skill_score:
            total_score += self.skill_score
            scores_count += 1
        self.average_score = total_score / scores_count if scores_count else None

        return self.average_score


class JobTag(UUIDModel):
    tag = models.ForeignKey(
        core_models.Tag,
        related_name="job_tags",
        on_delete=models.CASCADE,
        verbose_name=_("Tag")
    )

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="tags",
        verbose_name=_("Job")
    )

    class Meta:
        verbose_name = _("Job Tag")
        verbose_name_plural = _("Job Tags")
        unique_together = ("tag", "job")

    def __str__(self):
        return self.tag.name


class TimeSheetRate(UUIDModel):
    timesheet = models.ForeignKey(
        TimeSheet,
        verbose_name=_("TimeSheet"),
        on_delete=models.CASCADE,
        related_name='timesheet_rates')

    worktype = models.ForeignKey(
        WorkType,
        related_name="timesheet_rates",
        verbose_name=_("Type of work"),
        on_delete=models.CASCADE,
    )

    value = models.DecimalField(
        _("Timesheet Value"),
        default=0,
        max_digits=8,
        decimal_places=2)

    rate = models.DecimalField(
        _("Timesheet Rate"),
        default=0,
        max_digits=8,
        decimal_places=2)

    is_hourly = models.BooleanField(
        default=True,
        verbose_name=_('Is hourly')
    )

    class Meta:
        verbose_name = _("TimeSheet Rate")
        verbose_name_plural = _("TimeSheet Rates")
        unique_together = [
            'worktype',
            'timesheet',
        ]

    def __str__(self):
        return f'{self.timesheet}-{self.worktype}'

    @property
    def earning(self):
        return math.ceil(self.rate * self.value * 100) / 100

    @property
    def client_company_price_list_rate(self):
        price_list_rate = PriceListRate.objects.filter(
            worktype=self.worktype,
            price_list__company=self.timesheet.job_offer.shift.date.job.customer_company,
        ).last()

        if price_list_rate:
            return price_list_rate.rate
        return 0

    @property
    def client_company_expense(self):
        return math.ceil(self.client_company_price_list_rate * self.value * 100) / 100

    @property
    def master_company_profit(self):
        company_profit = self.client_company_expense - self.earning
        return math.ceil(company_profit * 100) / 100

    def get_rate(self):
        rate = self.timesheet.job_offer.job.get_rate_for_worktype(self.worktype)

        if not rate:
            # search skill activity rate in candidate's skill activity rates
            rate = self.timesheet.job_offer.candidate_contact.get_candidate_rate_for_worktype(self.worktype)

        return rate if rate else 0

    def save(self, *args, **kwargs):
        if not self.rate or self.rate == 0:
            self.rate = self.get_rate()
        self.is_hourly = self.worktype.is_hourly()
        super().save(*args, **kwargs)

        # The condition to check if the timesheetrate is created or updated should be added?
        is_post = True  # The value should be changed to False when the method is PUT.

        if self.is_hourly and is_post and not self.timesheet.shift_duration:
            self.timesheet.shift_ended_at = self.timesheet.shift_started_at + timedelta(hours=float(self.value))
            self.timesheet.save()


class JobRate(UUIDModel):
    job = models.ForeignKey(
        Job,
        verbose_name=_("Job"),
        on_delete=models.CASCADE,
        related_name='job_rates'
    )

    worktype = models.ForeignKey(
        WorkType,
        related_name='job_rates',
        verbose_name=_("Skill activity"),
        on_delete=models.CASCADE,
    )

    rate = models.DecimalField(
        _("Gob Skill Activity Rate"),
        default=0,
        max_digits=8,
        decimal_places=2)

    class Meta:
        verbose_name = _("Job Skill Activity Rate")
        verbose_name_plural = _("Job Skill Activity Rates")
        unique_together = [
            'job',
            'worktype',
        ]

    def __str__(self):
        return f'{self.job}-{self.worktype}'


class JobAmount(UUIDModel):
    job = models.ForeignKey(
        Job,
        verbose_name=_("Job"),
        on_delete=models.CASCADE,
        related_name='job_amounts'
    )

    worktype = models.ForeignKey(
        WorkType,
        related_name='job_amounts',
        verbose_name=_("Skill activity"),
        on_delete=models.CASCADE,
    )

    amount = models.DecimalField(
        _("Job Skill Activity Amount"),
        default=0,
        max_digits=8,
        decimal_places=2)

    class Meta:
        verbose_name = _("Job Skill Activity Amount")
        verbose_name_plural = _("Job Skill Activity Amounts")
        unique_together = [
            'job',
            'worktype',
        ]

    def __str__(self):
        return f'{self.job}-{self.worktype}'
