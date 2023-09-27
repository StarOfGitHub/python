from datetime import date, datetime, timedelta

import logging
from django.conf import settings
from django.db.models import Q, Max
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers, exceptions

from r3sourcer.apps.candidate import models as candidate_models
from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.core.api import serializers as core_serializers, mixins as core_mixins
from r3sourcer.apps.core.utils.user import get_default_user
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.hr.utils import utils as hr_utils, job as hr_job_utils
from r3sourcer.apps.logger.main import endless_logger
from r3sourcer.helpers.datetimes import utc_now

logger = logging.getLogger(__name__)

class FillinAvailableMixin:

    def _get_jo_messages(self, obj, date):
        from_date = date - timedelta(hours=settings.VACANCY_FILLING_TIME_DELTA)
        to_date = date + timedelta(hours=settings.VACANCY_FILLING_TIME_DELTA)
        job_offers = obj.job_offers.filter(
            Q(shift__date__shift_date=from_date.date(),
                shift__time__gte=from_date.timetz()) |
            Q(shift__date__shift_date__gt=from_date.date()),
            Q(shift__date__shift_date=to_date.date(),
                shift__time__lte=to_date.timetz()) |
            Q(shift__date__shift_date__lt=to_date.date())
        )

        accepted_messages = []
        not_accepted_messages = []

        for jo in job_offers.all():
            message = {
                'message': str(jo.shift.date.job.jobsite),
                'job': jo.shift.date.job.id,
            }
            if jo.status == hr_models.JobOffer.STATUS_CHOICES.accepted:
                message['status'] = _('Accepted')
                accepted_messages.append(message)
            elif jo.status == hr_models.JobOffer.STATUS_CHOICES.cancelled:
                message['status'] = _('Rejected')
                not_accepted_messages.append(message)
            else:
                message['status'] = _('Pending')
                accepted_messages.append(message)

        return accepted_messages, not_accepted_messages

    def get_available(self, obj):
        shifts_data = self.context['partially_available_candidates'].get(obj.id, {})
        init_shifts = self.context['init_shifts']

        response_data = []
        text = _('All shifts')

        unavailable_dates = []

        if len(shifts_data) > 0:
            dates = []

            for shift in shifts_data['shifts']:
                data = {
                    'datetime': datetime.combine(shift.date.shift_date, shift.time),
                }

                accepted_messages, not_accepted_messages = self._get_jo_messages(
                    obj, data['datetime'])

                if hr_job_utils.HAS_JOBOFFER in shifts_data['reasons'] and len(accepted_messages) > 0:
                    data['messages'] = accepted_messages
                elif hr_job_utils.UNAVAILABLE in shifts_data['reasons']:
                    data['messages'] = [{
                        'status': _('Unavailable'),
                        'message': None,
                        'job': None,
                    }]
                else:
                    continue

                dates.append(data)
                unavailable_dates.append(data['datetime'])

            if len(dates) > 0:
                response_data.append({
                    'text': _('Unavailable shifts'),
                    'shifts': dates,
                })

        dates = []
        unknown_dates = []

        for shift in init_shifts:
            data = {
                'datetime': datetime.combine(shift.date.shift_date, shift.time),
            }

            accepted_messages, not_accepted_messages = self._get_jo_messages(
                obj, data['datetime'])

            in_carrier_list = obj.carrier_lists.filter(
                target_date=shift.date.shift_date, confirmed_available=True)
            if in_carrier_list:
                if len(not_accepted_messages) > 0:
                    data['messages'] = not_accepted_messages
                    dates.append(data)
                elif data['datetime'] not in unavailable_dates:
                    data['messages'] = [{
                        'status': _('Available'),
                        'message': None,
                        'job': None,
                    }]
                    dates.append(data)
            else:
                if len(not_accepted_messages) > 0:
                    data['messages'] = not_accepted_messages
                    unknown_dates.append(data)
                elif data['datetime'] not in unavailable_dates:
                    data['messages'] = [{
                        'status': _('Unknown'),
                        'message': None,
                        'job': None,
                    }]
                    unknown_dates.append(data)

        has_unknown = len(unknown_dates) > 0 and len(
            unknown_dates) < len(init_shifts)
        if len(dates) > 0 and (has_unknown or len(response_data) > 0):
            response_data.append({
                'text': _('Available shifts'),
                'shifts': dates,
            })

        if len(response_data) == 0:
            response_data = [{
                'text': text,
                'shifts': [],
            }]

        return response_data


class JobSerializer(core_mixins.WorkflowStatesColumnMixin, core_serializers.ApiBaseModelSerializer):

    method_fields = ('is_fulfilled_today', 'is_fulfilled', 'no_sds', 'hide_fillin', 'title', 'extend', 'tags',
                     'jobsite_provider_signed_at',)

    class Meta:
        model = hr_models.Job
        fields = (
            '__all__',
            {
                'jobsite': ['id', {
                    'primary_contact': ['id', {
                        'contact': ['id', 'phone_mobile']
                    }],
                    'address': ['__all__'],
                }],
                'position': ['id', {'name': ('name', {'translations': ('language', 'value')})},
                             {'skill_rate_ranges': ('id', 'upper_rate_limit', 'lower_rate_limit', 'default_rate')}],
            }
        )

    def validate(self, data):
        customer_company = data.get('customer_company')
        provider_company = data.get('provider_company')
        company_rel = customer_company.regular_companies.filter(master_company=provider_company).last()

        # State number should be 70 (=active) to create the job
        if company_rel.get_active_states().first().state.number != 70:
            raise serializers.ValidationError(
                _('Cannot create a new booking. Company status is not Active.')
            )

        return data

    def get_is_fulfilled_today(self, obj):
        return obj and obj.is_fulfilled_today()  # pragma: no cover

    def get_is_fulfilled(self, obj):
        return obj and obj.is_fulfilled()  # pragma: no cover

    def get_no_sds(self, obj):  # pragma: no cover
        if obj is None:
            return True
        return not obj.shift_dates.filter(
            shift_date__gt=utc_now().date(),
            cancelled=False,
        ).exists()

    def get_hide_fillin(self, obj):  # pragma: no cover
        if obj is None:
            return True

        return not obj.can_fillin()

    def get_todays_timesheets(self, obj):
        result = "-"

        if obj is None:  # pragma: no cover
            return result

        timesheets = hr_models.TimeSheet.objects.filter(
            job_offer__shift__date__job_id=obj.id,
            shift_started_at__date=utc_now().date()
        )
        total_timesheets = timesheets.count()

        if total_timesheets != 0:
            going_to_work_timesheets = timesheets.filter(going_to_work_confirmation=True).count()
            submitted_timesheets = timesheets.filter(candidate_submitted_at__isnull=False).count()
            approved_timesheets = timesheets.filter(supervisor_approved_at__isnull=False).count()
            result = "{}% / {}% / {}%".format(
                int(going_to_work_timesheets * 100 / total_timesheets),
                int(submitted_timesheets * 100 / total_timesheets),
                int(approved_timesheets * 100 / total_timesheets)
            )

        return result

    def get_title(self, obj):  # pragma: no cover
        if obj is None:
            return None

        return obj.get_title()

    def _get_unfilled_future_vds_queryset(self, obj):
        today = date.today()
        shift_dates = obj.shift_dates.filter(
            shift_date__gte=today, cancelled=False
        ).distinct()
        return shift_dates

    def get_extend(self, obj):  # pragma: no cover
        current_state = obj.get_current_state()

        return current_state and current_state.number == 20

    def get_tags(self, obj):
        tags = core_models.Tag.objects.filter(job_tags__job=obj).distinct()
        return core_serializers.TagSerializer(tags, many=True, read_only=True, fields=['id', 'name', 'translations']).data

    def get_jobsite_provider_signed_at(self, obj):
        return obj.provider_signed_at_tz


class JobOfferSerializer(core_serializers.ApiBaseModelSerializer):

    method_fields = (
        'candidate_rate', 'client_rate', 'timesheets', 'has_accept_action', 'has_cancel_action', 'has_resend_action',
        'has_send_action', 'offer_smses', 'jo_type'
    )

    class Meta:
        model = hr_models.JobOffer
        fields = [
            '__all__',
            {
                'shift': ['id', 'time', {
                    'date': ['shift_date', 'job'],
                }],
                'candidate_contact': ['id', {
                    'contact': ['phone_mobile'],
                }]
            }
        ]

    def validate(self, validated_data):
        candidate_contact = validated_data['candidate_contact']
        shift = validated_data['shift']

        shift_start_time = datetime.combine(shift.date.shift_date, shift.time)
        from_date = shift_start_time - timedelta(hours=settings.VACANCY_FILLING_TIME_DELTA)
        to_date = shift_start_time + timedelta(hours=settings.VACANCY_FILLING_TIME_DELTA)

        overlapped_job_offers_count = candidate_contact.job_offers.filter(
            Q(shift__date__shift_date=from_date.date(),
              shift__time__gte=from_date.timetz()) |
            Q(shift__date__shift_date__gt=from_date.date()),
            Q(shift__date__shift_date=to_date.date(),
              shift__time__lte=to_date.timetz()) |
            Q(shift__date__shift_date__lt=to_date.date()),
            Q(status=hr_models.JobOffer.STATUS_CHOICES.accepted) |
            Q(status=hr_models.JobOffer.STATUS_CHOICES.undefined)
        ).count()

        if overlapped_job_offers_count:
            raise exceptions.ValidationError({
                'candidate_contact': _('Candidate contact has already job offers in this shift time')
            })

        # overlapped_timesheet_count = candidate_contact.job_offers.filter(
        #     time_sheets__shift_started_at__range=[from_date, to_date]
        # ).count()

        # if overlapped_timesheet_count:
        #     raise exceptions.ValidationError({
        #         'candidate_contact': _('Timesheets for this shift time already exist')
        #     })

        # contact_unavailable = candidate_contact.contact.contact_unavailabilities.filter(
        #     unavailable_from__lte=shift_start_time,
        #     unavailable_until__gte=shift_start_time,
        # ).count()

        # if contact_unavailable:
        #     raise exceptions.ValidationError({
        #         'candidate_contact': _('Candidate contact is unavailable for this shift time')
        #     })

        return validated_data

    def __init__(self, *args, **kwargs):
        many = kwargs.pop('many', True)
        super(JobOfferSerializer, self).__init__(many=many, *args, **kwargs)

    def get_candidate_rate(self, obj):
        if not obj:
            return None

        if obj.shift.hourly_rate:
            return obj.shift.hourly_rate
        elif obj.shift.date.hourly_rate:
            return obj.shift.date.hourly_rate
        elif obj.job.get_hourly_rate_for_skill(obj.job.position):
            return obj.job.get_hourly_rate_for_skill(obj.job.position)
        elif obj.shift.date.job.hourly_rate_default:
            return obj.shift.date.job.hourly_rate_default
        elif obj.candidate_contact.get_candidate_rate_for_skill(obj.job.position):
            return obj.candidate_contact.get_candidate_rate_for_skill(obj.job.position)
        return None

    def get_client_rate(self, obj):
        if not obj:
            return None

        price_list = obj.job.customer_company.get_effective_pricelist_qs(obj.job.position).first()
        if price_list:
            price_list_rate = price_list.price_list_rates.filter(worktype__skill_name=obj.job.position.name,
                                                                 worktype__name=hr_models.WorkType.DEFAULT) \
                                                         .first()
            rate = price_list_rate and price_list_rate.rate
        else:
            rate = None

        return rate

    def get_timesheets(self, obj):  # pragma: no cover
        if obj is None:
            return None

        timesheet = obj.time_sheets.first()
        return timesheet and timesheet.id

    def has_late_reply_handling(self, obj):
        sent_smses = obj.job_offer_smses.filter(offer_sent_by_sms__isnull=False)
        reply_smses = obj.job_offer_smses.filter(reply_received_by_sms__isnull=False)
        return (
            sent_smses.exists() and not reply_smses.exists() and
            sent_smses.filter(offer_sent_by_sms__late_reply__isnull=False) and not obj.is_accepted
        )

    def get_has_accept_action(self, obj):
        if obj is None or (obj.is_accepted() and not self.has_late_reply_handling(obj)):
            return None

        if obj.is_accepted() or obj.shift.is_fulfilled() == hr_models.FULFILLED:
            return None

        return True

    def get_has_cancel_action(self, obj):
        if obj is None or obj.is_cancelled():
            return None

        return True

    @classmethod
    def is_available_for_resend(cls, obj):
        not_received_or_scheduled = (
            obj.job_offer_smses.filter(reply_received_by_sms__isnull=True).exists() and not obj.is_accepted()
        )
        is_filled = obj.is_quota_filled()
        is_today_or_future = obj.start_time_tz.date() >= obj.today_tz

        if (obj.is_cancelled() or not_received_or_scheduled) and not is_filled and is_today_or_future:
            last_jo = obj.job.get_job_offers().filter(
                job_offer_smses__offer_sent_by_sms__isnull=False,
                candidate_contact=obj.candidate_contact
            ).order_by('job_offer_smses__offer_sent_by_sms__sent_at').last()
            return bool(
                obj.job_offer_smses.filter(offer_sent_by_sms__isnull=False).exists() and last_jo and
                last_jo.job_offer_smses.filter(offer_sent_by_sms__sent_at__lt=utc_now()).exists()
            )

        return False

    def get_has_resend_action(self, obj):
        if not obj:
            return None

        return self.is_available_for_resend(obj)

    @classmethod
    def is_available_for_send(cls, obj):
        has_not_sent = (
            obj.job_offer_smses.filter(offer_sent_by_sms__isnull=True).exists() or
            not obj.job_offer_smses.exists()
        )
        is_filled = obj.is_quota_filled()
        is_today_or_future = obj.start_time_tz.date() >= obj.today_tz

        return has_not_sent and not obj.is_accepted() and not is_filled and is_today_or_future

    def get_has_send_action(self, obj):
        return self.is_available_for_send(obj)

    def get_offer_smses(self, obj):
        return JobOfferSMSSimpleSerializer(obj.job_offer_smses.all(), many=True).data

    def get_jo_type(self, obj):
        statuses = obj.get_previous_offers().distinct('status').values_list('status', flat=True)

        if hr_models.JobOffer.STATUS_CHOICES.accepted in statuses:
            return 'recurring'
        return 'first'


class JobOfferSMSSimpleSerializer(core_serializers.ApiBaseModelSerializer):

    class Meta:
        model = hr_models.JobOfferSMS
        fields = (
            {
                'offer_sent_by_sms': ['id', 'text', 'status', 'sent_at'],
                'reply_received_by_sms': ['id', 'text', 'status', 'sent_at'],
            },
        )


class ShiftDateSerializer(core_serializers.UUIDApiSerializerMixin,
                          core_serializers.ApiBaseModelSerializer):
    method_fields = (
        *core_serializers.UUIDApiSerializerMixin.method_fields,
        'workers_details',
    )

    class Meta:
        model = hr_models.ShiftDate
        fields = ('__all__', {
                    'job': ('id',
                            {'jobsite': ('id', 'short_name')},
                            'default_shift_starting_time',
                            {'position': ['id', {'name': ('name', {'translations': ('language', 'value')})},
                                          ]},
                            'notes'),
                })

    def __init__(self, *args, **kwargs):
        many = kwargs.pop('many', True)
        super(ShiftDateSerializer, self).__init__(many=many, *args, **kwargs)

    def get_workers_details(self, obj):
        latest = hr_models.JobOffer.objects\
            .filter(shift__date=obj) \
            .values('candidate_contact') \
            .annotate(latest_date=Max('updated_at'))

        qs = obj.job_offers.filter(
            status__in=[
                hr_models.JobOffer.STATUS_CHOICES.accepted,
                hr_models.JobOffer.STATUS_CHOICES.cancelled,
                hr_models.JobOffer.STATUS_CHOICES.undefined,
            ]
        ).select_related('candidate_contact').distinct()
        result = {}
        for x in qs:
            storage = result.setdefault(x.status, [])
            if {'candidate_contact': x.candidate_contact.id, 'latest_date': x.updated_at} in latest:
                storage.append({
                    'id': x.candidate_contact.id,
                    'name': str(x.candidate_contact)
                })

        return {
            'accepted': result.get(hr_models.JobOffer.STATUS_CHOICES.accepted, []),
            'cancelled': result.get(hr_models.JobOffer.STATUS_CHOICES.cancelled, []),
            'undefined': result.get(hr_models.JobOffer.STATUS_CHOICES.undefined, []),
        }

    def create(self, validated_data):
        existing_date = hr_models.ShiftDate.objects.filter(
            shift_date=validated_data['shift_date'],
            job=validated_data['job'],
        ).first()

        if not existing_date:
            return super(ShiftDateSerializer, self).create(validated_data=validated_data)
        return existing_date


class ShiftSerializer(core_serializers.UUIDApiSerializerMixin,
                      core_serializers.ApiBaseModelSerializer):

    method_fields = (
        *core_serializers.UUIDApiSerializerMixin.method_fields,
        'is_fulfilled',
        'workers_details',
        'can_delete',
    )

    class Meta:
        model = hr_models.Shift
        fields = (
            '__all__', {
                'date': ('id', 'shift_date'),
            }
        )

    def get_is_fulfilled(self, obj):  # pragma: no cover
        return obj and (obj.is_fulfilled_annotated if hasattr(obj, 'is_fulfilled_annotated') else obj.is_fulfilled())

    def get_workers_details(self, obj):
        qs = hr_models.JobOffer.objects.filter(shift=obj)

        accepted = qs.filter(status=hr_models.JobOffer.STATUS_CHOICES.accepted).count()
        cancelled = qs.filter(status=hr_models.JobOffer.STATUS_CHOICES.cancelled).count()
        undefined = qs.filter(status=hr_models.JobOffer.STATUS_CHOICES.undefined).count()

        return {
            'accepted': accepted,
            'cancelled': cancelled,
            'undefined': undefined,
        }

    def get_can_delete(self, obj):  # pragma: no cover
        return not obj.job_offers.exists()

    def validate(self, validated_data):
        shift_date = validated_data['date']
        shift_time = validated_data['time']

        # we should not allow another shift to overlap existing accepted shift
        # creating new shift: check if there is another shift was accepted at the same time
        overlapped_shifts = hr_models.JobOffer.objects.filter(
            status__in=[
                hr_models.JobOffer.STATUS_CHOICES.accepted
            ]
        ).filter(
            shift__time=shift_time,
            shift__date=shift_date
        )
        # updating existing shift: same query excluding existing shift
        if self.instance:
            overlapped_shifts = overlapped_shifts.exclude(shift=self.instance)

        if overlapped_shifts.exists():
            raise exceptions.ValidationError({'time': _('Shift time must be unique')})

        return validated_data


class CandidateScoreSerializer(core_serializers.ApiBaseModelSerializer):

    method_fields = ('skill_score', 'client_feedback')

    class Meta:
        model = hr_models.CandidateScore
        fields = ('reliability', 'average_score', 'loyalty', 'recruitment_score')

    def get_skill_score(self, obj):
        return '{} ({})'.format(obj.skill_score or 0, obj.candidate_contact.candidate_skills.count())

    def get_client_feedback(self, obj):
        counter = 0
        for evaluation in obj.candidate_contact.candidate_evaluations.all():
            if evaluation.single_evaluation_average() > 0:
                counter += 1

        return '{} ({})'.format(obj.client_feedback or 0, counter)


class JobFillinSerialzier(FillinAvailableMixin, core_serializers.ApiBaseModelSerializer):

    method_fields = (
        'available', 'days_from_last_timesheet', 'distance_to_jobsite', 'time_to_jobsite', 'count_timesheets',
        'hourly_rate', 'tags', 'favourite'#, 'overpriced', 'color'
    )

    # jos = serializers.IntegerField(read_only=True)
    candidate_scores = CandidateScoreSerializer(read_only=True)

    class Meta:
        model = candidate_models.CandidateContact
        fields = (
            'id', 'transportation_to_work', 'candidate_scores',
            # 'recruitment_agent', 'nationality', 'jos',
            {
                'contact': [
                    'first_name',
                    'last_name',
                    {
                        'contact_address': (
                            {'address': ('id', 'latitude', 'longitude')},
                        ),
                    }
                ],
                # 'tag_rels': ['tag'],
            }
        )

    def get_days_from_last_timesheet(self, obj):
        last_timesheet = obj.last_timesheet_date
        if last_timesheet:
            return (utc_now().date() - last_timesheet.date()).days
        else:
            return 0

    def get_distance_to_jobsite(self, obj):
        return hr_utils.meters_to_km(obj.distance_to_jobsite) if obj.distance_to_jobsite > -1 else -1

    def get_time_to_jobsite(self, obj):
        return hr_utils.seconds_to_hrs(obj.time_to_jobsite) if obj.time_to_jobsite and obj.time_to_jobsite > 0 else -1

    def get_count_timesheets(self, obj):
        return obj.count_timesheets

    def get_hourly_rate(self, obj):
        hourly_rate = obj.get_candidate_rate_for_skill(
            self.context['job'].position, score__gt=0, skill__active=True
        )
        return hourly_rate

    def get_favourite(self, obj):
        return obj.id in self.context['favourite_list']

    # def get_overpriced(self, obj):
    #     return obj.id in self.context['overpriced']

    # def get_color(self, obj):
    #     is_partially_avail = obj.id in self.context['partially_available_candidates']
    #     # if self.get_overpriced(obj):
    #     #     if is_partially_avail:
    #     #         return 5
    #     #     return 3
    #     if is_partially_avail:
    #         return 4
    #     elif obj.id in self.context['carrier_list'] or obj.id in self.context['booked_before_list']:
    #         if obj.jos > 0:
    #             return 2
    #         return 1
    #     return 0

    def get_tags(self, obj):
        job_tags = self.context['job'].tags
        job_tags_ids = job_tags.values_list('tag_id', flat=True)

        existing = obj.tag_rels.exclude(tag_id__in=job_tags_ids).values_list('tag__name', flat=True)
        required = obj.tag_rels.filter(tag_id__in=job_tags_ids).values_list('tag__name', flat=True)
        missing = job_tags.exclude(
            tag_id__in=obj.tag_rels.values_list('tag_id', flat=True)
        ).values_list('tag__name', flat=True)

        return {
            'required': required,
            'missing': missing,
            'existing': existing,
        }


class JobExtendFillinSerialzier(core_serializers.ApiBaseModelSerializer):

    method_fields = ['distance', 'latest_activity_at']

    class Meta:
        model = candidate_models.CandidateContact
        fields = (
            'id', {
                'contact': ['id'],
                'candidate_scores': ['average_score'],
            }
        )

    def get_distance(self, obj):
        distance_cache = obj.contact.distance_caches.filter(jobsite=self.context['job'].jobsite).first()
        distance = distance_cache and distance_cache.distance
        return hr_utils.meters_to_km(distance) if distance and distance > -1 else -1

    def get_latest_activity_at(self, obj):
        timesheet = hr_models.TimeSheet.objects.filter(
            job_offer__candidate_contact=obj,
            supervisor_approved_at__isnull=False
        ).order_by('-shift_started_at').first()

        if timesheet:
            return timesheet.shift_started_at
        return datetime.now()


class CandidateJobOfferSerializer(core_serializers.ApiBaseModelSerializer):

    jobsite_address = core_serializers.AddressSerializer(read_only=True)

    method_fields = (
        'jobsite_address', 'hide_buttons', 'status', 'status_icon',
        'hide_text', 'latitude', 'longitude', 'jo_type'
    )

    class Meta:
        model = hr_models.JobOffer
        fields = [
            '__all__',
            {
                'jobsite_address': ('__all__', ),
                'shift': ['id', 'time', {
                    'date': ['shift_date', {
                        'job': ('id',
                                'customer_company',
                                {'jobsite': ['primary_contact']},
                                {'position': ['id', {'name': ('name', {'translations': ('language', 'value')})}]},
                                'notes'),

                        }],
                }],
            }
        ]

    def get_jobsite_address(self, obj):
        address = obj.job.jobsite.get_address()
        return address and core_serializers.AddressSerializer(address).data

    def get_hide_buttons(self, obj):
        return obj.status != hr_models.JobOffer.STATUS_CHOICES.undefined

    def get_hide_text(self, obj):
        return not self.get_hide_buttons(obj)

    @staticmethod
    def get_status_tuple(status, additional_text=None):
        if additional_text:
            return (
                status,
                hr_models.JobOffer.CANDIDATE_STATUS_CHOICES[status].format(additional_text=additional_text)
            )
        return (status, hr_models.JobOffer.CANDIDATE_STATUS_CHOICES[status])

    def get_status(self, obj):
        if obj.status == hr_models.JobOffer.STATUS_CHOICES.undefined:
            return self.get_status_tuple(obj.status)

        last_change = endless_logger.get_recent_field_change(hr_models.JobOffer, obj.id, 'status')
        if not last_change:
            return self.get_status_tuple(obj.status)

        updated_by_id = last_change['updated_by']
        system_user = get_default_user()
        reply_jo_sms = obj.job_offer_smses.filter(
            reply_received_by_sms__isnull=False
        ).order_by('-reply_received_by_sms__sent_at').first()
        reply_sms = reply_jo_sms and reply_jo_sms.reply_received_by_sms
        jobsite_contact = obj.job.jobsite.primary_contact

        if obj.is_quota_filled() or (reply_sms and reply_sms.is_positive_answer() and not obj.is_accepted()):
            return self.get_status_tuple(hr_models.JobOffer.CANDIDATE_STATUS_CHOICES.already_filled)

        if obj.is_cancelled():
            if str(obj.candidate_contact.contact.user.id) == updated_by_id:
                return self.get_status_tuple(
                    hr_models.JobOffer.CANDIDATE_STATUS_CHOICES.declined_by_candidate)
            elif str(system_user.id) == updated_by_id:
                if reply_sms and reply_sms.is_negative_answer():
                    return self.get_status_tuple(
                        hr_models.JobOffer.CANDIDATE_STATUS_CHOICES.declined_by_candidate)
                else:
                    return self.get_status_tuple(
                        hr_models.JobOffer.CANDIDATE_STATUS_CHOICES.cancelled)
            elif jobsite_contact and str(jobsite_contact.contact.user.id) == updated_by_id:
                return self.get_status_tuple(
                    hr_models.JobOffer.CANDIDATE_STATUS_CHOICES.cancelled_by_job_site_contact)
            else:
                return self.get_status_tuple(
                    hr_models.JobOffer.CANDIDATE_STATUS_CHOICES.cancelled_by,
                    additional_text=core_models.User.objects.get(id=updated_by_id))

        return self.get_status_tuple(obj.status)

    def get_status_icon(self, obj):
        return obj.status == hr_models.JobOffer.STATUS_CHOICES.accepted

    def get_latitude(self, obj):
        address = obj.job.jobsite.get_address()
        return address and address.latitude

    def get_longitude(self, obj):
        address = obj.job.jobsite.get_address()
        return address and address.longitude

    def get_jo_type(self, obj):
        statuses = obj.get_previous_offers().distinct('status').values_list('status', flat=True)

        if hr_models.JobOffer.STATUS_CHOICES.accepted in statuses:
            return 'recurring'
        return 'first'


class JobsiteSerializer(core_mixins.WorkflowStatesColumnMixin, core_mixins.WorkflowLatestStateMixin,
                        core_mixins.ApiContentTypeFieldMixin, core_serializers.ApiBaseModelSerializer):
    method_fields = ('timezone', )

    class Meta:
        model = hr_models.Jobsite
        validators = [
            serializers.UniqueTogetherValidator(
                queryset=model.objects.all(),
                fields=('industry', 'regular_company', 'short_name'),
                message=_("The Jobsite with such Client, Industry, and Site name already exists. Please change the Site name.")
            )
        ]
        fields = (
            '__all__',
            {
                'address': (
                    '__all__',
                    {
                        'city': ('id', 'name'),
                        'state': ('id', 'name'),
                    }
                ),
                'industry': ('id', 'type', {'translations': ('language', 'value')}),
                'master_company': ('id', ),
                'regular_company': ('id', 'short_name', 'logo',
                                    {'industries': ('id', {'translations': ('language', 'value')})},
                                    ),
                'portfolio_manager': (
                    'id', 'job_title',
                    {
                        'contact': ('id', 'phone_mobile'),
                    }
                ),
                'primary_contact': (
                    'id', 'job_title',
                    {
                        'contact': ('id', 'phone_mobile', 'email'),
                    }
                )
            }
        )

    def validate(self, validated_data):
        is_available = validated_data.get('is_available')
        primary_contact = validated_data.get('primary_contact')
        address = validated_data.get('address')

        if is_available:
            if not primary_contact or not primary_contact.contact.email:
                raise exceptions.ValidationError({
                    'is_available': _('Supervisor with valid email is required.')
                })

            if not address:
                raise exceptions.ValidationError({
                    'is_available': _('Address is required.')
                })

        return validated_data

    def get_timezone(self, obj):
        tz = obj.get_timezone()
        return tz.zone


class JobExtendSerialzier(FillinAvailableMixin, core_serializers.ApiBaseModelSerializer):

    method_fields = ('available', 'job_shift', 'latest_date', 'last_fullfilled')

    autofill = serializers.BooleanField(required=False)

    class Meta:
        model = hr_models.Job
        fields = ('id', 'autofill')

    def _get_latest_shift_date(self, obj):
        latest_date = obj.shift_dates.filter(cancelled=False, shifts__isnull=False)
        try:
            return latest_date.filter(shifts__job_offers__isnull=False).latest('shift_date')
        except hr_models.ShiftDate.DoesNotExist:
            return latest_date.order_by('-shift_date').first()

    def get_job_shift(self, obj):
        return [
            datetime.combine(shift.date.shift_date, shift.time)
            for shift in hr_models.Shift.objects.filter(date__job=obj)
        ]

    def get_latest_date(self, obj):
        latest_shift_date = self._get_latest_shift_date(obj)

        return latest_shift_date and latest_shift_date.pk

    def get_available(self, obj):
        candidates = self.context['candidates']
        available = {}

        for candidate in candidates:
            available[str(candidate)] = super().get_available(candidate)

        return available

    def get_last_fullfilled(self, obj):
        latest_shift_date = self._get_latest_shift_date(obj)

        if latest_shift_date and latest_shift_date.shifts.filter(job_offers__isnull=False).exists():
            latest_fullfilled_shifts = latest_shift_date.shifts.exclude(
                job_offers__status=hr_models.JobOffer.STATUS_CHOICES.cancelled
            ).order_by('-time')

            if not latest_fullfilled_shifts.exists():
                latest_fullfilled_shifts = latest_shift_date.shifts.all()

            return [{
                'shift_datetime': datetime.combine(latest_shift_date.shift_date, shift.time),
                'candidates': JobExtendFillinSerialzier([
                    jo.candidate_contact for jo in shift.job_offers.exclude(
                        status=hr_models.JobOffer.STATUS_CHOICES.cancelled
                    )
                ], many=True, context={'job': obj}).data
            } for shift in latest_fullfilled_shifts]


class JobsiteMapAddressSerializer(core_serializers.ApiMethodFieldsMixin, serializers.ModelSerializer):

    method_fields = ('contact', 'name', 'type')

    class Meta:
        model = core_models.Address
        fields = ('latitude', 'longitude', '__str__')

    def get_name(self, obj):
        prefix = 'client_' if obj.client_name else ''
        return getattr(obj, '%s%s' % (prefix, 'name'))

    def get_contact(self, obj):
        prefix = 'client_' if obj.client_name else ''

        first_name = getattr(obj, '%s%s' % (prefix, 'first_name'))
        last_name = getattr(obj, '%s%s' % (prefix, 'last_name'))
        title = getattr(obj, '%s%s' % (prefix, 'title'))

        if not first_name and not last_name:
            name = None
        else:
            name = '{} {}'.format(first_name, last_name)
            if title:
                name = '{} {}'.format(title, name)

        job_title = getattr(obj, '%s%s' % (prefix, 'job_title'))
        return {
            'name': '%s %s' % (job_title, name) if job_title else name,
            'phone_mobile': getattr(obj, '%s%s' % (prefix, 'phone_mobile')),
        }

    def get_type(self, obj):
        if obj.client_name:
            return 'client_hq' if obj.client_hq else 'client'
        else:
            # TODO: it takes a lot of time to check open state! do we need this?
            open_states = core_models.WorkflowObject.objects.filter(
                state__number=50,
                object_id=obj.jobsite_id,
                active=True,
            ).exists()
            return 'jobsite_open' if open_states else 'jobsite'


class JobsiteMapFilterSerializer(serializers.Serializer):

    client = serializers.CharField(required=False)
    jobsite = serializers.CharField(required=False)
    portfolio_manager = serializers.UUIDField(required=False)
    filter_by = serializers.CharField(required=False)
    show_all = serializers.BooleanField(required=False, default=False)


class FavouriteListSerializer(core_serializers.ApiBaseModelSerializer):

    class Meta:
        model = hr_models.FavouriteList

        fields = [
            '__all__',
            {
                'company': ['id', 'name', 'primary_contact'],
                },
            {
                'jobsite': ['id', 'short_name', 'primary_contact'],
                }
            ]

        extra_kwargs = {'job': {'required': False}}

    def validate(self, validated_data):
        company_contact = validated_data.get('company_contact')
        jobsite = validated_data.get('jobsite')
        company = validated_data.get('company')

        if not any([company, jobsite, company_contact]):
            raise exceptions.ValidationError({
                'non_field_errors': _('Client Contact, Jobsite or Client are required.')
            })

        return validated_data


class BlackListSerializer(core_serializers.ApiBaseModelSerializer):

    class Meta:
        model = hr_models.BlackList

        fields = [
            'id', 'company', 'candidate_contact', 'jobsite', 'company_contact', 'client_contact',
            {
                'company': ['id', 'name', 'primary_contact'],
                },
            {
                'jobsite': ['id', 'short_name', 'primary_contact'],
                }
            ]

        extra_kwargs = {'job': {'required': False},}

    def validate(self, validated_data):
        company_contact = validated_data.get('company_contact')
        jobsite = validated_data.get('jobsite')
        company = validated_data.get('company')

        if not any([company, jobsite, company_contact]):
            raise exceptions.ValidationError({
                'non_field_errors': _('Client Contact, Jobsite or Client are required.')
            })

        return validated_data


class CarrierListSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = hr_models.CarrierList
        fields = (
            '__all__',
            {
                'candidate_contact': (
                    'contact', 'recruitment_agent'
                )
            }
        )

    def validate(self, validated_data):
        candidate_contact = validated_data.get('candidate_contact')
        skill = validated_data.get('skill')

        if not any([candidate_contact, skill]):
            raise exceptions.ValidationError({
                'non_field_errors': _('Candidate Contact and Skill are required.')
            })

        return validated_data


class JobRateSerializer(core_mixins.CreatedUpdatedByMixin, core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = hr_models.JobRate
        fields = (
            '__all__',
            {
                'worktype': (
                    'id',
                    'name',
                    {'translations': ('language', 'value')}
                )
            }
        )

    def validate(self, data):
        job = data.get('job')
        worktype = data.get('worktype')
        skill_rate_range = job.position.skill_rate_ranges.filter(worktype=worktype).first()
        if skill_rate_range:
            lower_limit = skill_rate_range.lower_rate_limit
            upper_limit = skill_rate_range.upper_rate_limit
            is_lower = lower_limit and data.get('rate') < lower_limit
            is_upper = upper_limit and data.get('rate') > upper_limit
            if is_lower or is_upper:
                raise exceptions.ValidationError({
                    'rate': _('Rate should be between {} and {}')
                        .format(lower_limit, upper_limit)
                })

        return data


class JobAmountSerializer(core_mixins.CreatedUpdatedByMixin, core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = hr_models.JobAmount
        fields = (
            '__all__',
            {
                'worktype': (
                    'id',
                    'name',
                    {'translations': ('language', 'value')}
                )
            }
        )
