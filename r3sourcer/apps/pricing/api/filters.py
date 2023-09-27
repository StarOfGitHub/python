from django.db.models import Q
from django_filters import UUIDFilter
from django_filters.rest_framework import FilterSet

from r3sourcer.apps.pricing import models


class PriceListRateFilter(FilterSet):
    price_list = UUIDFilter(method='filter_price_list')

    class Meta:
        model = models.PriceListRate
        fields = ['worktype']

    def filter_price_list(self, queryset, name, value):
        qs = queryset.filter(price_list=value)

        # Actually the skills must be beforehand. Add the exception handler in cases
        # when the skills happened to be deleted.
        exclude_list = []
        for price_list_rate in qs.all():
            if price_list_rate.worktype.skill:
                continue

            if price_list_rate.worktype.skill_name:
                from r3sourcer.apps.skills.models import Skill
                skills = Skill.objects.filter(name=price_list_rate.worktype.skill_name,
                                              company=price_list_rate.price_list.company)
                if skills.exists():
                    continue

            exclude_list.append(price_list_rate.id)

        qs = qs.exclude(id__in=exclude_list)
        return qs


class RateCoefficientModifierFilter(FilterSet):

    class Meta:
        model = models.RateCoefficientModifier
        fields = ['rate_coefficient', 'type', 'default']


class PriceListFilter(FilterSet):

    class Meta:
        model = models.PriceList
        fields = ['company']


class IndustryFilter(FilterSet):

    class Meta:
        model = models.Industry
        fields = ['company']


class RateCoefficientFilter(FilterSet):

    class Meta:
        model = models.RateCoefficient
        fields = ['industry']
