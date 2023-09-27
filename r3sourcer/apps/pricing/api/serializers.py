from r3sourcer.apps.skills.models import Skill
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from inflector import Inflector, English
from rest_framework import serializers, exceptions

from r3sourcer.apps.core.api.serializers import ApiBaseModelSerializer
from r3sourcer.apps.core_adapter.utils import api_reverse_lazy
from r3sourcer.apps.pricing import models as pricing_models


class DynamicCoefficientRuleSerializer(ApiBaseModelSerializer):

    method_fields = ('rule', 'rule_endpoint')

    class Meta:
        model = pricing_models.DynamicCoefficientRule
        fields = ('rate_coefficient', 'priority', 'id', 'used')

    def get_rule(self, obj):
        if obj is None:
            return

        return str(obj.rule)

    def get_rule_endpoint(self, obj):
        if obj is None:
            return

        endpoint = '%s/%s' % (
            obj.rule_type.app_label.replace('_', '-'),
            Inflector(English).pluralize(obj.rule_type.model)
        )
        return api_reverse_lazy(endpoint, 'detail', pk=str(obj.rule_id))


class OvertimeRuleSerializer(ApiBaseModelSerializer):

    used = serializers.BooleanField(required=False, label=_('Used for overtime'))

    class Meta:
        model = pricing_models.OvertimeWorkRule
        fields = ('id', 'overtime_hours_from', 'overtime_hours_to', 'used')


class TimeOfDayRuleSerializer(ApiBaseModelSerializer):

    used = serializers.BooleanField(required=False, label=_('Used for Time of The Day'))

    class Meta:
        model = pricing_models.TimeOfDayWorkRule
        fields = ('id', 'time_start', 'time_end', 'used')


class AllowanceRuleSerializer(ApiBaseModelSerializer):

    used = serializers.BooleanField(required=False, label=_('Is Allowance'))

    class Meta:
        model = pricing_models.AllowanceWorkRule
        fields = ('id', 'allowance_description', 'used')


class WeekdaysRuleSerializer(ApiBaseModelSerializer):

    class Meta:
        model = pricing_models.WeekdayWorkRule
        fields = '__all__'


class RateCoefficientSerializer(ApiBaseModelSerializer):

    method_fields = ('rules', )

    overtime = OvertimeRuleSerializer(required=False)
    weekdays = WeekdaysRuleSerializer(required=False)
    timeofday = TimeOfDayRuleSerializer(required=False, read_only=False)
    allowance = AllowanceRuleSerializer(required=False)

    class Meta:
        model = pricing_models.RateCoefficient
        fields = (
            'id', 'industry', 'name', 'active', 'group', 'overtime', 'weekdays', 'timeofday',
            'allowance', 'overlaps', 'priority',
        )

    def get_rules(self, obj):
        if obj is None:
            return []

        return [rule['rule'] for rule in DynamicCoefficientRuleSerializer(
            obj.rate_coefficient_rules.filter(used=True).order_by('-priority'),
            many=True, fields=['priority', 'rule', 'rule_endpoint']
        ).data]

    def _get_rule_objects(self, validated_data):
        rules = []
        for field_name, field in self.fields.items():
            if not isinstance(field, ApiBaseModelSerializer):
                continue

            model = field.Meta.model
            data = validated_data.pop(field_name, {})
            data_id = data.pop('id', None) or None

            if isinstance(field, WeekdaysRuleSerializer):
                save = used = any(data.values())
            else:
                used = data.pop('used', False)
                save = data

            if save or used:
                rule_obj, created = model.objects.update_or_create(
                    id=data_id,
                    defaults=data
                )

                rules.append((rule_obj, used, model))

        return rules

    def create(self, validated_data):
        rules = self._get_rule_objects(validated_data)

        obj = super(RateCoefficientSerializer, self).create(validated_data)

        for rule_obj, used, model in rules:
            pricing_models.DynamicCoefficientRule.objects.create(
                rate_coefficient=obj, rule=rule_obj, used=used
            )

        return obj

    def update(self, obj, validated_data):
        rules = self._get_rule_objects(validated_data)

        for rule_obj, used, model in rules:
            rule_ct = ContentType.objects.get_for_model(model)
            pricing_models.DynamicCoefficientRule.objects.update_or_create(
                rate_coefficient=obj, rule_type=rule_ct, rule_id=rule_obj.id, defaults={'used': used}
            )

        return super(RateCoefficientSerializer, self).update(obj, validated_data)


class IndustrySerializer(ApiBaseModelSerializer):

    class Meta:
        model = pricing_models.Industry
        fields = ('id', 'type', {'translations': ('language', 'value')})


class PriceListRateSerializer(ApiBaseModelSerializer):

    method_fields = ['skill']

    class Meta:
        model = pricing_models.PriceListRate
        fields = ('__all__',
                  {
                   'worktype': ('id', 'name', {'translations': ('language', 'value')}),
                  },)

    def get_skill(self, obj):
        return obj.get_skill()
