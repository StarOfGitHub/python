from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.formats import time_format
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers, exceptions

from r3sourcer.apps.core.api.fields import ApiBaseRelatedField, ApiContactPictureField
from r3sourcer.apps.core.api.serializers import ApiBaseModelSerializer, CompanyContactSerializer
from r3sourcer.apps.core.models import Company
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.apps.pricing.utils.utils import format_timedelta
from r3sourcer.apps.sms_interface import models as sms_models
from r3sourcer.apps.sms_interface.api import serializers as sms_serializers
from r3sourcer.helpers.datetimes import utc_now
from ...models import TimeSheet, CandidateEvaluation, TimeSheetRate, WorkType

__all__ = [
    'TimeSheetSignatureSerializer',
    'PinCodeSerializer',
    'TimeSheetSerializer',
    'TimeSheetRateSerializer',
]


def validate_timesheet(self, data):
    """
    Time validation on timesheet save
    """

    hours = data.get('hours')
    shift_started_at = data.get('shift_started_at', None)
    shift_ended_at = data.get('shift_ended_at', None)

    if hours is None:
        if shift_started_at is not None and shift_ended_at is not None:
            hours = True

    if self.instance.pk and hours is not None:

        # validate sent fields
        if hours:
            if data.get('no_break'):
                data['break_started_at'] = None
                data['break_ended_at'] = None
            break_started_at = data.get('break_started_at', None)
            break_ended_at = data.get('break_ended_at', None)

            if shift_started_at and shift_ended_at:
                shift_date = self.instance.job_offer.shift.shift_date_at_tz
                # shift_started_at >= shift__time - 4h
                if shift_started_at < shift_date - timedelta(hours=4):
                    raise serializers.ValidationError({'shift_started_at': 'error.invalid_shift_started_at_4'})
                # shift_started_at <= shift__time + 24h
                if shift_started_at > shift_date + timedelta(hours=12):
                    raise serializers.ValidationError({'shift_started_at': 'error.invalid_shift_started_at_12'})
                # shift_ended_at >= shift_started_at
                if shift_ended_at < shift_started_at:
                    raise serializers.ValidationError({'shift_started_at':
                        _('Incorrect shift starting or ending time.')})
                if break_ended_at and break_started_at:
                    # break_ended_at >= break_started_at
                    if break_started_at < break_started_at:
                        raise serializers.ValidationError({'break_started_at':
                            _('Incorrect break starting or ending time.')})
                    # shift_started_at <= break_started_at
                    if shift_started_at > break_started_at:
                        raise serializers.ValidationError({'break_started_at':
                            _('Break must start after shift starting time.')})
                    # shift_ended_at >= break_ended_at
                    if shift_ended_at < break_ended_at:
                        raise serializers.ValidationError({'break_ended_at':
                            _('Break must end before shift ending time.')})
                    # calculate break duration
                    break_duration = break_ended_at - break_started_at
                    if break_duration < timedelta(minutes=30) and shift_ended_at-shift_started_at >= timedelta(hours=8):
                        raise serializers.ValidationError({
                            'non_field_errors': _("The break time should be at least 30 minutes.")
                        })
                else:
                    break_duration = timedelta(0)
                    if shift_ended_at-shift_started_at >= timedelta(hours=8):
                        raise serializers.ValidationError({
                            'non_field_errors': _("No break time is set. It should be at least 30 minutes.")
                        })
                # (shift_ended_at - shift_started_at) - (break_ended_at - break_started_at)  <= 24h
                if (shift_ended_at - shift_started_at) - break_duration > timedelta(hours=24):
                    raise serializers.ValidationError({'shift_started_at': 'error.invalid_total_24'})
                # (shift_ended_at - shift_started_at) - (break_ended_at - break_started_at) >= 0
                if (shift_ended_at - shift_started_at) - break_duration <= timedelta(0):
                    raise serializers.ValidationError({'shift_started_at':
                        _('Total working hours must be longer than 0 hours.')})
                data['wage_type'] = 0
            else:
                raise serializers.ValidationError({'shift_started_at':
                    _('You need to specify shift end time.')})
        else:
            hourly_work = WorkType.objects.filter(name=WorkType.DEFAULT,
                                                    skill_name=self.instance.job_offer.job.position.name) \
                                            .first()
            if not TimeSheetRate.objects.filter(timesheet=self.instance).exclude(worktype=hourly_work).exists():
                TimeSheetRate.objects.filter(timesheet=self.instance).delete()
                raise exceptions.ValidationError({'non_field_errors': _("You need to add at least one skill activity")})
            data['wage_type'] = 1

    return data
    # raise exceptions.ValidationError({'non_field_errors': _("Timesheet data is not valid")})


class ValidateApprovalScheme(serializers.Serializer):
    APPROVAL_SCHEME = None

    def validate(self, attrs):
        # get master companies and check existing
        client_company = self.instance.job_offer.job.customer_company
        companies = self.instance.supervisor.get_master_company()
        if len(companies) == 0:
            raise serializers.ValidationError(_("Supervisor has not master company"))

        if client_company.timesheet_approval_scheme != self.APPROVAL_SCHEME:
            raise serializers.ValidationError(_("Incorrect approval scheme"))
        return attrs


class ApiTimesheetImageFieldsMixin():
    image_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        image_fields = self.image_fields or []
        for image_field in image_fields:
            self.fields[image_field] = ApiContactPictureField(required=False)


class TimeSheetSignatureSerializer(ValidateApprovalScheme, ApiTimesheetImageFieldsMixin, ApiBaseModelSerializer):
    image_fields = ('supervisor_signature',)
    APPROVAL_SCHEME = Company.TIMESHEET_APPROVAL_SCHEME.SIGNATURE

    class Meta:
        model = TimeSheet
        fields = ('supervisor_signature',)
        extra_kwargs = {
            'supervisor_signature': {
                'required': True,
                'allow_empty_file': False,
                'allow_null': False
            }
        }


class PinCodeSerializer(ValidateApprovalScheme):
    APPROVAL_SCHEME = Company.TIMESHEET_APPROVAL_SCHEME.PIN

    pin_code = serializers.CharField(min_length=4)

    def validate(self, attrs):
        attrs = super(PinCodeSerializer, self).validate(attrs)
        supervisor = self.instance.supervisor
        if supervisor.pin_code != attrs['pin_code']:
            raise serializers.ValidationError({'pin_code': _("Incorrect pin code")})
        return attrs


class TimeSheetSerializer(ApiTimesheetImageFieldsMixin, ApiBaseModelSerializer):
    image_fields = ('supervisor_signature',)
    hours = serializers.BooleanField(required=False)

    method_fields = (
        'company', 'jobsite', 'position', 'shift_started_ended',
        'break_started_ended', 'job', 'related_sms',
        'candidate_filled', 'supervisor_approved', 'resend_sms_candidate', 'resend_sms_supervisor', 'candidate_sms',
        'candidate_sms_old', 'candidate_submit_hidden', 'evaluated', 'myob_status', 'show_sync_button', 'supervisor_sms',
        'invoice', 'shift', 'evaluation', 'time_zone', 'is_30_days_old', 'default_shift_times', 'supervisor'
    )

    class Meta:
        model = TimeSheet
        fields = (
            'id',
            'job_offer',
            'going_to_work_sent_sms',
            'going_to_work_reply_sms',
            'going_to_work_confirmation',
            # 'supervisor',
            'candidate_submitted_at',
            'supervisor_approved_at',
            'supervisor_approved_scheme',
            'candidate_rate',
            'rate_overrides_approved_by',
            'rate_overrides_approved_at',
            'sync_status',
            'status',
            'supervisor_modified',
            'supervisor_modified_at',
            'supervisor_signature',
            'process_status',
            'process_pending_status',
            'shift_started_at',
            'shift_started_at_tz',
            'shift_started_at_utc',
            'shift_ended_at',
            'shift_ended_at_tz',
            'shift_ended_at_utc',
            'break_started_at',
            'break_started_at_tz',
            'break_started_at_utc',
            'break_ended_at',
            'break_ended_at_tz',
            'break_ended_at_utc',
            'timesheet_rates',
            'hours',
        )
        related_fields = {
            'job_offer': ('id',
                          {
                              'candidate_contact': ('id', {
                                  'contact': ('picture',),
                                  'candidate_scores': ['average_score'],
                              },),
                          },),
            'timesheet_rates': ('id',
                                'rate',
                                'value',
                                {'worktype': ('id', 'translations')}),
        }

    def get_default_shift_times(self, obj):
            return {'default_shift_start_time': settings.DEFAULT_SHIFT_START_TIME,
                    'default_shift_end_time': settings.DEFAULT_SHIFT_END_TIME,
                    'default_break_start_time': settings.DEFAULT_BREAK_START_TIME,
                    'default_break_end_time': settings.DEFAULT_BREAK_END_TIME
                    }

    def get_company(self, obj):
        if obj:
            company = obj.job_offer.job.customer_company
            return {
                'id': company.id, '__str__': str(company),
                'supervisor_approved_scheme': company.timesheet_approval_scheme
            }

    def get_supervisor(self, obj):
        approver = obj.supervisor
        if obj.manager_who_approved:
            approver = obj.manager_who_approved
        return {
            'id': approver.id, '__str__': str(approver),
            'name': str(approver)
        }


    def get_jobsite(self, obj):
        if obj:
            jobsite = obj.job_offer.job.jobsite
            return {
                'id': jobsite.id,
                'address': {
                    'id': jobsite.address.id,
                    '__str__': str(jobsite.address),
                },
                '__str__': str(jobsite),
            }

    def get_position(self, obj):
        if obj:
            position = obj.job_offer.job.position
            translations = [{
                                'language': {'id': i.language.alpha_2, 'name': i.language.name},
                                'value': i.value
                            } for i in position.name.translations.all()]
            return {'id': position.id, '__str__': str(position), 'translations': translations}

    def __format_datetime(self, date_time, default='-'):
        filtered = filter(bool, [date_time])
        datetimes, *_ = [*list(map(lambda x: time_format(x, settings.TIME_FORMAT), filtered)), default]
        return datetimes

    def _format_date_range(self, start, end):
        return ' / '.join(map(lambda x: self.__format_datetime(x), [start, end]))

    def get_time_zone(self, obj):
        return obj.tz.zone

    def get_shift_started_ended(self, obj):
        return self._format_date_range(obj.shift_started_at_tz, obj.shift_ended_at_tz)

    def get_break_started_ended(self, obj):
        return self._format_date_range(obj.break_started_at_tz, obj.break_ended_at_tz)

    def get_job(self, obj):
        job = obj.job_offer.job
        return {'id': job.id, '__str__': str(job)}

    def get_related_sms(self, obj):
        ct = ContentType.objects.get_for_model(TimeSheet)
        smses = sms_models.SMSMessage.objects.filter(
            related_objects__content_type=ct,
            related_objects__object_id=obj.id
        )
        if smses.exists():
            return sms_serializers.SMSMessageSerializer(smses, many=True, fields=['id', '__str__', 'type']).data

    def get_candidate_filled(self, obj):
        return obj.candidate_submitted_at is not None

    def get_supervisor_approved(self, obj):
        return obj.supervisor_approved_at is not None

    def get_resend_sms_candidate(self, obj):
        return (
                obj.going_to_work_confirmation and obj.candidate_submitted_at is None and
                obj.supervisor_approved_at is None and obj.planned_shift_end_at_utc <= utc_now()
        )

    def get_resend_sms_supervisor(self, obj):
        return (
            (obj.going_to_work_confirmation and
            obj.candidate_submitted_at is not None and
            obj.supervisor_approved_at is None) and
            (obj.wage_type == 1 or obj.planned_shift_end_at_utc <= utc_now())
        )

    def get_candidate_submit_hidden(self, obj):
        return not (
                obj.going_to_work_confirmation and obj.candidate_submitted_at is None and
                obj.supervisor_approved_at is None and obj.shift_started_at_utc <= utc_now()
        )

    def get_evaluated(self, obj):
        return obj.candidate_evaluations.exists()

    def get_evaluation(self, obj):
        if obj.candidate_evaluations.exists():
            return CandidateEvaluationSerializer(
                obj.candidate_evaluations.all().first(),
                fields=['id', 'evaluation_score', 'evaluated_at']
            ).data

    def get_myob_status(self, obj):
        if obj.supervisor_approved_at and obj.candidate_submitted_at:
            sync_objs = MYOBSyncObject.objects.filter(record=obj.id)
            if sync_objs.filter(synced_at__gte=obj.updated_at).exists():
                return _('Synced')
            elif sync_objs.exists():
                return _('Sync is outdated')
            else:
                return _('Not Synced')

        return None

    def get_show_sync_button(self, obj):
        allowed_states = [
            TimeSheet.SYNC_STATUS_CHOICES.not_synced,
            TimeSheet.SYNC_STATUS_CHOICES.sync_failed,
        ]
        return bool(obj.sync_status in allowed_states and obj.supervisor_approved_at and obj.candidate_submitted_at)

    def _get_related_sms(self, obj, template_slug):
        ct = ContentType.objects.get_for_model(TimeSheet)
        timesheet_date = obj.shift_started_at_tz.date()
        sms = sms_models.SMSMessage.objects.filter(
            related_objects__content_type=ct,
            related_objects__object_id=obj.id,
            template__slug=template_slug,
            sent_at__date=timesheet_date
        ).first()

        if not sms:
            sms = sms_models.SMSMessage.objects.filter(
                template__slug=template_slug,
                sent_at__date=timesheet_date,
                company=obj.master_company
            ).first()
            if not sms:
                sms = sms_models.SMSMessage.objects.filter(
                    template__slug=template_slug,
                    related_objects__object_id=obj.id,
                    company=obj.master_company
                ).first()

        return sms and sms_serializers.SMSMessageSerializer(sms, fields=['id', '__str__']).data

    def get_supervisor_sms(self, obj):
        return self._get_related_sms(obj, 'supervisor-timesheet-sign')

    def get_candidate_sms(self, obj):
        return self._get_related_sms(obj, 'candidate-timesheet-hours')

    def get_candidate_sms_old(self, obj):
        return self._get_related_sms(obj, 'candidate-timesheet-hours-old')

    def get_invoice(self, obj):
        invoice_line = obj.invoice_lines.first()
        invoice = invoice_line and invoice_line.invoice
        return invoice and ApiBaseRelatedField.to_read_only_data(invoice)

    def get_shift(self, obj):
        if obj:
            shift = obj.job_offer.shift
            return {
                'id': shift.id,
                'date': {
                    'id': shift.date.id,
                    '__str__': str(shift.date),
                },
                '__str__': str(shift),
            }

    def get_is_30_days_old(self, obj):
        return obj.shift_started_at_tz < obj.now_tz - timedelta(days=30)

    def validate(self, data):
        """
        Time validation on timesheet save
        """
        return validate_timesheet(self, data)


class CandidateEvaluationSerializer(ApiBaseModelSerializer):
    method_fields = ('jobsite', 'position')

    class Meta:
        model = CandidateEvaluation
        fields = (
            'candidate_contact', 'supervisor', 'evaluated_at', 'reference_timesheet', 'evaluation_score',
            {
                'supervisor': ('id', 'contact', 'job_title'),
                'reference_timesheet': ('id', 'shift_started_at', 'shift_ended_at'),
            }
        )

    def get_jobsite(self, obj):
        if not obj.reference_timesheet:
            return

        return ApiBaseRelatedField.to_read_only_data(obj.reference_timesheet.job_offer.job.jobsite)

    def get_position(self, obj):
        if not obj.reference_timesheet:
            return

        return ApiBaseRelatedField.to_read_only_data(obj.reference_timesheet.job_offer.job.position)


class TimeSheetManualSerializer(ApiBaseModelSerializer):
    method_fields = (
        'candidate_contact_id', 'company', 'shift_total', 'break_total', 'total_worked', 'time_zone', 'position',
        'default_shift_times'
    )

    hours = serializers.BooleanField(required=False)
    no_break = serializers.BooleanField(required=False)
    send_supervisor_message = serializers.BooleanField(required=False)
    send_candidate_message = serializers.BooleanField(required=False)
    candidate_submitted_at = serializers.DateTimeField(write_only=True, required=False)
    supervisor_approved_at = serializers.DateTimeField(write_only=True, required=False)
    manager_who_approved = CompanyContactSerializer(write_only=True, required=False)

    class Meta:
        model = TimeSheet
        fields = (
            'id', 'shift_started_at', 'break_started_at', 'break_ended_at',
            'shift_ended_at', 'no_break', 'hours', 'send_supervisor_message',
            'send_candidate_message', 'candidate_submitted_at',
            'supervisor_approved_at', 'shift_started_at_tz',
            'shift_ended_at_tz', 'break_started_at_tz', 'break_ended_at_tz',
            'shift_started_at_utc', 'shift_ended_at_utc',
            'break_started_at_utc', 'break_ended_at_utc',
            'manager_who_approved'
        )

    def validate(self, data):
        """
        Time validation on timesheet save
        """
        return validate_timesheet(self, data)

    def get_company(self, obj):
            if obj:
                company = obj.job_offer.job.customer_company
                return {
                    'id': company.id, '__str__': str(company),
                    'supervisor_approved_scheme': company.timesheet_approval_scheme
                }

    def get_candidate_contact_id(self, obj):
        if obj:
            return obj.job_offer.candidate_contact.id

    def get_position(self, obj):
        if obj:
            position = obj.job_offer.job.position
            translations = [{
                                'language': {'id': i.language.alpha_2, 'name': i.language.name},
                                'value': i.value
                            } for i in position.name.translations.all()]
            return {'id': position.id, '__str__': str(position), 'translations': translations}

    def get_shift_total(self, obj):
        if obj.shift_delta:
            return format_timedelta(obj.shift_delta)

    def get_break_total(self, obj):
        if obj.break_delta:
            return format_timedelta(obj.break_delta)

    def get_total_worked(self, obj):
        if obj.shift_delta and obj.break_delta:
            return format_timedelta(obj.shift_delta - obj.break_delta)
        else:
            return obj.shift_delta

    def get_time_zone(self, obj):
        return obj.tz.zone

    def get_default_shift_times(self, obj):
            return {'default_shift_start_time': settings.DEFAULT_SHIFT_START_TIME,
                    'default_shift_end_time': settings.DEFAULT_SHIFT_END_TIME,
                    'default_break_start_time': settings.DEFAULT_BREAK_START_TIME,
                    'default_break_end_time': settings.DEFAULT_BREAK_END_TIME
                    }


class TimeSheetRateSerializer(ApiBaseModelSerializer):
    class Meta:
        model = TimeSheetRate
        fields = (
            'id', 'timesheet', 'value', 'rate',
            {
                'worktype': ('id', 'name', {'translations': ('language', 'value')}),
            }
        )

    def validate(self, data):
        timesheet = data.get('timesheet')
        worktype = data.get('worktype', None)
        rate = data.get('rate')
        value = data.get('value')

        # validate value
        if value is None or value <= 0:
            raise exceptions.ValidationError({
                'value': _('Value must be greater then 0')
            })

        # validate rate
        if rate is None or rate <= 0:
            raise exceptions.ValidationError({
                'rate': _('Rate must be greater then 0')
            })

        # validate rate against the limited upper
        job_amount = timesheet.job_offer.shift.date.job.job_amounts.filter(worktype=worktype).last()
        if job_amount:
            skill_amount = job_amount.amount
            if value > skill_amount:
                raise exceptions.ValidationError({
                    'value': _('Value must be less than or equal to {}').format(skill_amount)
                })

        # validate rate    TODO choose betweann master company and regular company
        skill_rate_range = timesheet.job_offer.shift.date.job.position.skill_rate_ranges \
                                                    .filter(worktype=worktype) \
                                                    .last()
        if skill_rate_range:
            lower_limit = skill_rate_range.lower_rate_limit
            upper_limit = skill_rate_range.upper_rate_limit
            is_lower = lower_limit and rate < lower_limit
            is_upper = upper_limit and rate > upper_limit
            if is_lower or is_upper:
                raise exceptions.ValidationError({
                    'rate': _('Rate should be between {} and {}')
                        .format(lower_limit, upper_limit)
                })

        return data
