from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import exceptions

from r3sourcer.apps.core.api.serializers import ApiBaseModelSerializer
from r3sourcer.apps.skills.models import SkillBaseRate, Skill, SkillTag, SkillName, SkillRateRange, WorkType
from r3sourcer.apps.hr.models import TimeSheet


class SkillBaseRateSerializer(ApiBaseModelSerializer):
    class Meta:
        model = SkillBaseRate
        fields = ('__all__', )


class SkillSerializer(ApiBaseModelSerializer):

    class Meta:
        model = Skill
        fields = (
            'id', 'company', 'carrier_list_reserve', 'short_name', 'employment_classification', 'active',
            {'name': ('id', 'name', {'translations': ('language', 'value')},
                      {'industry': ('id', 'type', {'translations': ('language', 'value')})})
            },
            {'skill_rate_ranges': ('id',
                                   {'worktype': ('id', 'name', {'translations': ('language', 'value')})},
                                   'upper_rate_limit', 'lower_rate_limit', 'default_rate',
                                   'price_list_upper_rate_limit', 'price_list_lower_rate_limit',
                                   'price_list_default_rate'),
            },
        )


class SkillTagSerializer(ApiBaseModelSerializer):

    class Meta:
        model = SkillTag
        fields = (
            'id',
            {'tag': ('name', {'translations': ('language', 'value')})},
            {'skill': ('id', {'name': ('name', {'translations': ('language', 'value')})})},
        )


class SkillNameSerializer(ApiBaseModelSerializer):

    method_fields = ('active', 'skill_id', 'carrier_list_reserve')

    class Meta:
        model = SkillName
        fields = (
            'id',
            {'name': ('name', {'translations': ('language', 'value')})},
            {'industry': ('id', 'type', {'translations': ('language', 'value')}),
             'translations': ('language', 'value'),
             'work_types': ('id', 'name', {'translations': ('language', 'value')}),
            },
        )

    def get_active(self, obj):
        try:
            return self.context['view']._filter_list()[obj.name].active
        except KeyError:
            return False

    def get_skill_id(self, obj):
        try:
            return self.context['view']._filter_list()[obj.name].id
        except KeyError:
            return None

    def get_carrier_list_reserve(self, obj):
        try:
            return self.context['view']._filter_list()[obj.name].carrier_list_reserve
        except KeyError:
            return None


class SkillRateRangeSerializer(ApiBaseModelSerializer):

    class Meta:
        model = SkillRateRange
        fields = (
            'id', 'skill', 'worktype',
            {'worktype': ('id', 'name', {'translations': ('language', 'value')})},
            'upper_rate_limit', 'lower_rate_limit', 'default_rate',
            'price_list_upper_rate_limit', 'price_list_lower_rate_limit', 'price_list_default_rate'
            )

    def validate(self, validated_data):
        lower_rate = validated_data.get('lower_rate_limit')
        upper_rate = validated_data.get('upper_rate_limit')
        default_rate = validated_data.get('default_rate')
        price_list_lower_rate = validated_data.get('price_list_lower_rate_limit')
        price_list_upper_rate = validated_data.get('price_list_upper_rate_limit')
        price_list_default_rate = validated_data.get('price_list_default_rate')

        errors = {}

        if lower_rate and upper_rate and lower_rate > upper_rate:
            errors['lower_rate_limit'] = _('Lower Rate Limit should be lesser than or equal Upper Rate Limit')
        if lower_rate and default_rate and lower_rate > default_rate:
            errors['default_rate'] = _('Default Rate should be greater than or equal Lower Rate Limit')
        if upper_rate and default_rate and default_rate > upper_rate:
            errors['upper_rate_limit'] = _('Upper Rate Limit should be greater than or equal Default Rate')

        if price_list_lower_rate and price_list_upper_rate and price_list_lower_rate > price_list_upper_rate:
            errors['price_list_lower_rate_limit'] = _('Lower Rate Limit should be lesser than or equal Upper Rate Limit')
        if price_list_lower_rate and price_list_default_rate and price_list_lower_rate > price_list_default_rate:
            errors['price_list_default_rate'] = _('Default Rate should be greater than or equal Lower Rate Limit')
        if price_list_upper_rate and price_list_default_rate and price_list_default_rate > price_list_upper_rate:
            errors['price_list_upper_rate_limit'] = _('Upper Rate Limit should be greater than or equal Default Rate')

        if lower_rate and price_list_lower_rate and lower_rate >= price_list_lower_rate:
            errors['lower_rate_limit'] = _('Lower Rate Limit should be lesser than Price List Lower Rate Limit')
        if default_rate and price_list_default_rate and default_rate >= price_list_default_rate:
            errors['default_rate'] = _('Default Rate should be lesser than Price List Default Rate')
        if upper_rate and price_list_upper_rate and upper_rate >= price_list_upper_rate:
            errors['upper_rate_limit'] = _('Upper Rate Limit should be lesser than Price List Upper Rate Limit')

        if errors:
            raise exceptions.ValidationError(errors)

        return validated_data


class WorkTypeSerializer(ApiBaseModelSerializer):

    method_fields = ['skill_rate_ranges', 'skill_rate', 'default_rate', 'amount']

    class Meta:
        model = WorkType
        fields = (
            '__all__',
            {'uom': ('id', 'name', 'short_name'),
            'translations': ('language', 'value')},
            )

        extra_kwargs = {
            'skill_name': {'required': False},
            'skill': {'required': False}
        }

    def get_skill_rate_ranges(self, obj):
        if not obj:
            return

        request = self.context.get('request')
        if obj.skill_name and request:
            return SkillRateRangeSerializer(obj.skill_rate_ranges.filter(
                                            skill__company=request.user.company),
                                            fields=['id', 'default_rate', 'upper_rate_limit', 'lower_rate_limit'],
                                            many=True).data
        else:
            return SkillRateRangeSerializer(obj.skill_rate_ranges.filter(skill=obj.skill),
                                            fields=['id', 'default_rate'],
                                            many=True).data

    def get_skill_rate(self, obj):
        request = self.context.get('request')
        if request:
            timesheet_id = request.query_params.get('timesheet', None)
            if timesheet_id:
                try:
                    timesheet = TimeSheet.objects.get(pk=timesheet_id)

                    # search skill activity rate in job's skill activity rates
                    rate = timesheet.job_offer.job.get_rate_for_worktype(obj)
                    if not rate:
                        # search skill activity rate in candidate's skill activity rates
                        rate = timesheet.job_offer.candidate_contact.get_candidate_rate_for_worktype(obj)

                    return rate if rate else 0
                except ObjectDoesNotExist:
                    pass
        return 0

    def get_amount(self, obj):
        request = self.context.get('request')
        if request:
            timesheet_id = request.query_params.get('timesheet', None)
            if timesheet_id:
                try:
                    timesheet = TimeSheet.objects.get(pk=timesheet_id)
                    amount = timesheet.job_offer.job.get_amount_for_worktype(obj)
                    return amount
                except ObjectDoesNotExist:
                    pass
        return None

    def get_default_rate(self, obj):
        request = self.context.get('request')
        if request:
            skill_id = request.query_params.get('skill')
            if skill_id:
                try:
                    skill = Skill.objects.get(pk=skill_id)
                    skill_rate_ranges = obj.skill_rate_ranges.filter(skill=skill)
                    if skill_rate_ranges.exists():
                        return skill_rate_ranges.first().default_rate
                except ObjectDoesNotExist:
                    pass
        return 0
