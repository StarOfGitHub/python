from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, serializers
from rest_framework.exceptions import ValidationError

from r3sourcer.apps.candidate import models as candidate_models
from r3sourcer.apps.candidate.models import VisaType
from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.core.api import serializers as core_serializers, mixins as core_mixins, fields as core_fields
from r3sourcer.apps.core.utils.companies import get_site_master_company
from r3sourcer.apps.core.utils.utils import normalize_phone_number
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.apps.company_settings.models import SAASCompanySettings
from r3sourcer.apps.skills import models as skill_models
from r3sourcer.apps.skills.api.serializers import WorkTypeSerializer


class FavouriteListSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = hr_models.FavouriteList
        fields = '__all__'


class BlackListSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = hr_models.BlackList
        fields = '__all__'


class JobOfferSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = hr_models.JobOffer
        fields = '__all__'


class SkillRelSerializer(core_mixins.CreatedUpdatedByMixin, core_serializers.ApiBaseModelSerializer):

    class Meta:
        model = candidate_models.SkillRel
        fields = (
            'id', 'score', 'candidate_contact', 'prior_experience',
            {'skill': ('id', {'name': ('__str__', {'translations': ('language', 'value')})}, '__str__')},
            'created_at', 'updated_at',
        )
        extra_kwargs = {
            'score': {'max_value': Decimal(5)},
        }

    def create(self, validated_data):
        default_rate = validated_data.pop('default_rate', None)
        # create SkillRel
        skill_rel = super().create(validated_data)

        # create default rate for SkillRel
        if default_rate:
            default_uom = core_models.UnitOfMeasurement.objects.get(default=True)
            candidate_models.SkillRate.objects.create(skill_rel=skill_rel,
                                                      uom=default_uom,
                                                      rate=default_rate)
        return skill_rel


class SkillRateSerializer(core_mixins.CreatedUpdatedByMixin, core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = candidate_models.SkillRate
        fields = (
            '__all__',
            {
                'worktype': ('id', {'translations': ('language', 'value')}),
            },
        )
        extra_kwargs = {
            'worktype': {'required': False}
        }

    def validate(self, data):
        skill_rel = data.get('skill_rel')
        worktype = data.get('worktype')

        # check if candidate rate in skill_rate_range
        skill_rate_range = skill_rel.skill.skill_rate_ranges.filter(worktype=worktype).first()
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


class TagRelSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = candidate_models.TagRel
        fields = (
            '__all__',
            {
                'tag': ('id', 'name', 'evidence_required_for_approval', 'active', 'confidential',
                        {'translations': ('language', 'value')}),
                'verified_by': ('id', 'contact', 'job_title'),
            }
        )

    def validate(self, data):
        if data.get('tag').evidence_required_for_approval and not data.get('verification_evidence'):
            raise serializers.ValidationError({'verification_evidence': _('Verification evidence is requred')})

        return data


class CandidateContactSerializer(core_mixins.WorkflowStatesColumnMixin,
                                 core_mixins.WorkflowLatestStateMixin,
                                 core_mixins.ApiContentTypeFieldMixin,
                                 core_serializers.ApiBaseModelSerializer):

    emergency_contact_phone = serializers.CharField(allow_null=True, required=False)
    tax_number = serializers.CharField(required=False)
    personal_id = serializers.CharField(required=False)

    method_fields = ('average_score', 'bmi', 'skill_list', 'tag_list', 'workflow_score',
                     'master_company', 'myob_name', 'address', 'formality_attributes')

    def create(self, validated_data):
        contact = validated_data.get('contact', None)
        if not isinstance(contact, core_models.Contact):
            raise exceptions.ValidationError(
                _('Contact is required.')
            )

        request = self.context.get('request')
        if request:

            access_levels = (core_models.constants.MANAGER, core_models.constants.CLIENT)
            if not request.user.is_authenticated or request.user.access_level not in access_levels:
                raise exceptions.PermissionDenied()

            master_company = get_site_master_company()
            company_contact = request.user.contact.get_company_contact_by_company(master_company)

            if candidate_models.CandidateContact.objects.filter(contact=contact,
                                                                candidate_rels__master_company=master_company) \
                                                        .exists():
                raise exceptions.ValidationError(
                    _('Candidate Contact with this Contact already exists.')
                )

            if request and contact.candidate_contacts.exists():
                # copy CandidateContact
                candidate = candidate_models.CandidateContact.objects.filter(contact=contact).last()
                recruitment_agent = company_contact
                if candidate:
                    # copy related objects
                    related_m2m = ['candidate_acceptance_tests',
                                'candidate_evaluations',
                                'candidate_skills',
                                'formalities',
                                'tag_rels',
                                ]
                    fks_to_copy = []
                    import copy
                    candidate_score = copy.deepcopy(candidate.candidate_scores)

                    for rm in related_m2m:
                        related_model = getattr(candidate, rm)
                        fks_to_copy += related_model.all()

                    # Now we can make the new record
                    candidate.id = None
                    candidate.recruitment_agent = recruitment_agent
                    candidate.save()

                    # Create CandidateScore
                    candidate_score.id = None
                    candidate_score.candidate_contact = candidate
                    candidate_score.save()

                    # create CandidateRel
                    candidate_models.CandidateRel.objects.get_or_create(
                        candidate_contact=candidate,
                        master_company=master_company,
                        company_contact=recruitment_agent
                    )

                    foreign_keys = {}
                    for fk in fks_to_copy:
                        fk.pk = None
                        fk.candidate_contact = candidate
                        # Likewise make any changes to the related model here
                        # However, we avoid calling fk.save() here to prevent
                        # hitting the database once per iteration of this loop
                        try:
                            # Use fk.__class__ here to avoid hard-coding the class name
                            foreign_keys[fk.__class__].append(fk)
                        except KeyError:
                            foreign_keys[fk.__class__] = [fk]

                    # Now we can issue just two calls to bulk_create,
                    # one for fkeys_a and one for fkeys_b
                    for cls, list_of_fks in foreign_keys.items():
                        cls.objects.bulk_create(list_of_fks)

            else:
                candidate = super().create(validated_data)

            candidate_models.CandidateRel.objects.create(
                master_company=master_company,
                candidate_contact=candidate,
                company_contact=company_contact,
                owner=True,
                active=True,
            )

            return candidate


    class Meta:
        model = candidate_models.CandidateContact
        fields = (
            '__all__',
            {
                'contact': (
                    'id', 'first_name', 'last_name', 'email', 'phone_mobile', 'is_available', 'picture', 'gender',
                    'birthday', 'myob_card_id', 'old_myob_card_id',
                    {
                        'contact_address': (
                            {'address': ('id', 'country', 'state', 'city', 'street_address', 'postal_code'),},
                            'is_active'
                        ),
                    }
                ),
                'candidate_scores': (
                    'id', 'client_feedback', 'reliability', 'loyalty', 'recruitment_score', 'skill_score'
                ),
                'recruitment_agent': ('id', 'job_title', {
                    'contact': ('id', 'phone_mobile')
                }),
                'superannuation_fund': ('id', 'product_name'),
                'tax_number': (),
                'personal_id': ()
            }
        )
        read_only_fields = ('candidate_scores', 'old_myob_card_id')

        related = core_serializers.RELATED_DIRECT

    def validate_emergency_contact_phone(self, value):
        if value:
            master_company = get_site_master_company(request=self.context['request'])
            if not master_company:
                raise ValidationError(_('Master company not found'))
            country_code = master_company.get_hq_address().address.country.code2
            value = normalize_phone_number(value, country_code)
        return value

    def validate(self, data):
        # restrict disabling both notification channels
        message_by_sms = data.get('message_by_sms')
        message_by_email = data.get('message_by_email')
        if message_by_email == False and message_by_sms == False:
            raise exceptions.ValidationError({
                'message_by_email': _('At least one notofication channel should be active')
            })
        return data

    def get_average_score(self, obj):
        if not obj:
            return
        if obj.candidate_scores:
            score = obj.candidate_scores.get_average_score()
        else:
            score = None
        return score and '{0:.3}'.format(score)

    def get_bmi(self, obj):
        if not obj:
            return

        return obj.get_bmi()

    def get_skill_list(self, obj):
        if not obj:
            return

        return SkillRelSerializer(obj.candidate_skills.all(), many=True, fields=['score', 'skill', 'id']).data

    def get_tag_list(self, obj):
        if not obj:
            return

        return TagRelSerializer(obj.tag_rels.all(), many=True, fields=['id', 'tag']).data

    def get_workflow_score(self, obj):
        return obj.get_active_states().aggregate(score=Avg('score'))['score']

    def get_master_company(self, obj):
        master_company = obj.get_closest_company()
        return master_company and core_fields.ApiBaseRelatedField.to_read_only_data(master_company)

    def get_myob_name(self, obj):
        sync_obj = self._get_sync_object(obj)
        return sync_obj and sync_obj.legacy_myob_card_number

    def _get_sync_object(self, obj):
        return MYOBSyncObject.objects.filter(record=obj.id).first()

    def get_formality_attributes(self, obj):
        if hasattr(obj, 'pk'):
            return obj.get_formality_attributes()
        else:
            return None

    def get_address(self, obj):
        return obj.contact.get_active_address()

class CandidateContactRegisterSerializer(core_serializers.ContactRegisterSerializer):

    candidate = CandidateContactSerializer(required=False)
    agree = serializers.BooleanField(required=True)
    is_subcontractor = serializers.BooleanField(required=False)
    tags = serializers.PrimaryKeyRelatedField(
        required=True,
        queryset=core_models.Tag.objects,
        many=True
    )
    skills = serializers.PrimaryKeyRelatedField(
        required=True,
        queryset=skill_models.Skill.objects,
        many=True
    )

    def create(self, validated_data):
        candidate = validated_data.pop('candidate', {})
        agree = validated_data.pop('agree', False)
        tags = validated_data.pop('tags', []) or []
        skills = validated_data.pop('skills', []) or []

        if not agree:
            raise exceptions.ValidationError(_('You should agree'))

        contact = super().create(validated_data)

        candidate['contact'] = contact
        candidate_contact = CandidateContactSerializer().create(candidate)

        for tag in tags:
            candidate_models.TagRel.objects.create(
                candidate_contact=candidate_contact,
                tag=tag,
            )

        for skill in skills:
            candidate_models.SkillRel.objects.create(
                candidate_contact=candidate_contact,
                skill=skill,
                hourly_rate=0
            )

        return candidate_contact

    class Meta:
        fields = (
            'title', 'first_name', 'birthday', 'email', 'phone_mobile', 'tags',
            'last_name', 'picture', 'agree', 'skills', 'is_subcontractor',
            {
                'contact_address': (
                    {'address': ('country', 'state', 'city', 'street_address', 'postal_code'),},
                    'is_active'
                ),
            }
        )


class SubcontractorSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        fields = '__all__'
        model = candidate_models.Subcontractor


class SubcontractorCandidateRelationSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        fields = ('id', 'subcontractor', 'candidate_contact')
        model = candidate_models.SubcontractorCandidateRelation


class CandidatePoolSerializer(core_mixins.WorkflowStatesColumnMixin, core_mixins.WorkflowLatestStateMixin,
                              core_serializers.ApiBaseModelSerializer):

    method_fields = ('profile_price', 'average_score', 'owned_by', 'bmi', 'tag_list', 'skill_list')

    class Meta:
        model = candidate_models.CandidateContactAnonymous
        fields = ('id', 'transportation_to_work', 'height',
                  'weight', 'nationality',
                  {
                      'candidate_scores': (
                            'id', 'client_feedback', 'reliability', 'loyalty', 'recruitment_score', 'skill_score'
                          ),
                      'contact': (
                          '__str__', 'is_available', 'picture', 'gender'
                          ),
                  }
                  )
        related = core_serializers.RELATED_DIRECT

    def get_profile_price(self, obj):
        saas_settings = SAASCompanySettings.objects.first()
        if saas_settings:
            return obj.profile_price * (1 + saas_settings.candidate_sale_commission / 100)
        return obj.profile_price

    def get_average_score(self, obj):
        return obj.candidate_scores.get_average_score()

    def get_owned_by(self, obj):
        return core_fields.ApiBaseRelatedField.to_read_only_data(obj.candidate_rels.get(owner=True).master_company)

    def get_bmi(self, obj):
        if not obj:
            return

        return obj.get_bmi()

    def get_tag_list(self, obj):
        if not obj:
            return

        return TagRelSerializer(obj.tag_rels.all(), many=True, fields=['id', 'tag']).data

    def get_skill_list(self, obj):
        if not obj:
            return

        return SkillRelSerializer(obj.candidate_skills.all(), many=True, fields=['score', 'skill', 'id']).data


class CandidatePoolDetailSerializer(core_serializers.ApiBaseModelSerializer):

    method_fields = ('profile_price', 'average_score', 'owned_by', 'bmi')

    class Meta:
        model = candidate_models.CandidateContactAnonymous
        fields = ('id', 'updated_at', 'created_at', 'transportation_to_work', 'height',
                  'weight', 'residency', 'visa_type', 'visa_expiry_date', 'nationality',
                  'vevo_checked_at',
                  {
                      'candidate_scores': (
                            'id', 'client_feedback', 'reliability', 'loyalty', 'recruitment_score', 'skill_score'
                          ),
                      'contact': (
                          '__str__', 'is_available', 'picture',
                          ),
                  }
                  )

    def get_profile_price(self, obj):
        saas_settings = SAASCompanySettings.objects.first()
        if saas_settings:
            return obj.profile_price * (1 + saas_settings.candidate_sale_commission / 100)
        return obj.profile_price

    def get_average_score(self, obj):
        return obj.candidate_scores.get_average_score()

    def get_owned_by(self, obj):
        return core_fields.ApiBaseRelatedField.to_read_only_data(obj.candidate_rels.get(owner=True).master_company)

    def get_bmi(self, obj):
        if not obj:
            return

        return obj.get_bmi()


class CandidateRelSerializer(core_serializers.ApiBaseModelSerializer):

    class Meta:
        fields = '__all__'
        model = candidate_models.CandidateRel


class VisaTypeSerializer(core_serializers.ApiBaseModelSerializer):

    class Meta:
        fields = ('id', 'subclass', 'name', 'general_type', 'work_hours_allowed', 'is_available')
        model = VisaType


class FormalitySerializer(core_serializers.ApiBaseModelSerializer):
    method_fields = ['formality_attributes']

    class Meta:
        fields = ["candidate_contact", "country", "tax_number", "personal_id"]
        model = candidate_models.Formality

    def get_formality_attributes(self, obj):
        if hasattr(obj, 'pk'):
            return obj.get_formality_attributes()
        else:
            return None


class CandidateStatisticsSerializer(core_serializers.ApiBaseModelSerializer):

    method_fields = (
        'shifts_total', 'hourly_work', 'skill_activities', 'currency'
    )

    class Meta:
        model = candidate_models.CandidateContact
        fields = ('id',)

    def get_shifts_total(self, obj):
        return hr_models.TimeSheet.objects.filter(job_offer__candidate_contact=obj,
                                                  status=7,
                                                  job_offer__shift__date__shift_date__gte=self.context['from_date'],
                                                  job_offer__shift__date__shift_date__lte=self.context['to_date']) \
                                          .count()

    def get_hourly_work(self, obj):
        hours = timedelta(hours=0)
        earned = 0
        timesheets = hr_models.TimeSheet.objects.filter(job_offer__candidate_contact=obj,
                                                        status=7,
                                                        job_offer__shift__date__shift_date__gte=self.context['from_date'],
                                                        job_offer__shift__date__shift_date__lte=self.context['to_date'])

        for ts in timesheets:
            if ts.shift_duration:
                hours += ts.shift_duration
                earned += ts.get_hourly_rate * Decimal(ts.shift_duration.total_seconds()/3600)

        data = {
            'total_hours': round(hours.total_seconds()/3600, 2),
            'total_earned': earned
        }

        return data


    def get_skill_activities(self, obj):
        timesheets = hr_models.TimeSheet.objects.filter(job_offer__candidate_contact=obj,
                                                        status=7,
                                                        job_offer__shift__date__shift_date__gte=self.context['from_date'],
                                                        job_offer__shift__date__shift_date__lte=self.context['to_date'])
        activities = {}
        total_earned = 0
        for ts in timesheets:
            for rate in ts.timesheet_rates.exclude(worktype__name=skill_models.WorkType.DEFAULT):
                if rate.worktype.name not in activities:
                    serializer = WorkTypeSerializer(rate.worktype)
                    activities[rate.worktype.name] = serializer.data
                    activities[rate.worktype.name]['value_sum'] = rate.value
                    activities[rate.worktype.name]['earned_sum'] = rate.value * rate.rate
                    total_earned += rate.value * rate.rate
                else:
                    activities[rate.worktype.name]['value_sum'] += rate.value
                    activities[rate.worktype.name]['earned_sum'] += rate.value * rate.rate
                    total_earned += rate.value * rate.rate

        activities['total_earned'] = total_earned

        return activities

    def get_currency(self, obj):
        return obj.get_closest_company().currency
