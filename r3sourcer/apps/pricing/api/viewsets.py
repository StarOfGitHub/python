from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _

from rest_framework.exceptions import ValidationError

from r3sourcer.apps.core.api import viewsets as core_viewsets
from r3sourcer.apps.core.utils.companies import get_site_master_company
from r3sourcer.apps.pricing import models as pricing_models


class RateCoefficientViewset(core_viewsets.BaseApiViewset):

    exclude_empty = True

    def get_object(self):
        obj = super().get_object()

        if self.request.method == 'POST':
            return obj

        extra_map = {
            'overtime': pricing_models.OvertimeWorkRule,
            'weekdays': pricing_models.WeekdayWorkRule,
            'timeofday': pricing_models.TimeOfDayWorkRule,
            'allowance': pricing_models.AllowanceWorkRule,
        }

        for extra, extra_class in extra_map.items():
            extra_obj = obj.rate_coefficient_rules.filter(
                rule_type=ContentType.objects.get_for_model(extra_class)
            ).first()
            rule = extra_obj and extra_obj.rule
            if rule:
                setattr(rule, 'used', extra_obj.used)
            setattr(obj, extra, rule)

        return obj

    def perform_create(self, serializer):
        instance = serializer.save()

        master_company = get_site_master_company(request=self.request)
        pricing_models.RateCoefficientRel.objects.create(
            rate_coefficient=instance,
            company=master_company
        )

    def perform_destroy(self, instance):
        if instance.rate_coefficient_modifiers.exists():
            raise ValidationError({
                'error': _('Unable to delete due to relation to modifier')
            })

        if instance.price_lists.all().exists():
            raise ValidationError({
                'error': _('Unable to delete due relation to price list')
            })

        for dynamic_coeff in instance.rate_coefficient_rules.all():
            dynamic_coeff.rule_type.get_object_for_this_type(id=dynamic_coeff.rule_id).delete()
            dynamic_coeff.delete()

        instance.delete()


class RateCoefficientModifierViewset(core_viewsets.BaseApiViewset):

    def perform_create(self, serializer):
        default = serializer.validated_data.get('default')

        if default or default is None:
            rate_coefficient = serializer.validated_data['rate_coefficient']
            rcm_type = serializer.validated_data['type']
            rate_coefficient.rate_coefficient_modifiers.filter(
                type=rcm_type, default=True
            ).update(default=False)

        instance = serializer.save()

        if default is None:
            instance.default = True
            instance.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        default = serializer.validated_data.get('default', False)
        old_default = instance.default

        instance = serializer.save()

        if default and not old_default:
            rate_coefficient = serializer.validated_data['rate_coefficient']
            rcm_type = serializer.validated_data['type']
            rate_coefficient.rate_coefficient_modifiers.filter(
                type=rcm_type, default=True
            ).exclude(pk=instance.pk).update(default=False)
        elif not default and old_default:
            instance.default = True
            instance.save()
