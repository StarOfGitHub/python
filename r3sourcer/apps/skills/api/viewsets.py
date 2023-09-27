from django.db.models import Q

from r3sourcer.apps.core.api import viewsets as core_viewsets
from r3sourcer.apps.skills.models import Skill, SkillRateRange
from r3sourcer.apps.pricing.models import PriceListRate
from r3sourcer.apps.core.models import Company
from r3sourcer.apps.core.utils.companies import get_site_master_company


class SkillNameViewSet(core_viewsets.BaseApiViewset):

    def get_queryset(self):
        qs = super().get_queryset()
        company = get_site_master_company()
        qs = qs.filter(
            industry__in=company.industries.all(),
            skills__company=company,
        )
        if self.request.query_params.get('ordering'):
            ordering = self.request.query_params.get('ordering')
            qs = qs.order_by(*ordering.split(','))
        else:
            qs = qs.order_by('name')

        return qs

    def _filter_list(self):
        if not hasattr(self, '_map_skill'):
            map_skill = dict()
            company = get_site_master_company()
            for skill in Skill.objects.filter(name__industry__in=company.industries.all(),
                                              company=company).select_related('name'):
                map_skill.update({skill.name.name: skill})
            self._map_skill = map_skill

        return self._map_skill


class WorkTypeViewSet(core_viewsets.BaseApiViewset):

    def get_queryset(self):
        qs = super().get_queryset()

        priced = self.request.query_params.get('priced', False) in ['true', '1']
        limited = self.request.query_params.get('limited', False) in ['true', '1']
        try:
            company = Company.objects.get(pk=self.request.query_params.get('company'))
        except:
            company = get_site_master_company()
        industries = company.industries.all()
        qs = qs.filter(Q(skill_name__industry__in=industries) |
                       Q(skill__company=company))
        if priced:
            # limit skill activities which have Price_list_rate
            price_list_rates = PriceListRate.objects.filter(price_list__company=company) \
                                                    .values_list('pk', flat=True)
            qs = qs.filter(price_list_rates__in=price_list_rates)

        if limited:
            # limit skill activities which have skill_rate_range
            rate_ranges_exists = SkillRateRange.objects.filter(skill__company=company.get_closest_master_company())
            qs = qs.filter(skill_rate_ranges__in=rate_ranges_exists)

        if self.request.query_params.get('ordering'):
            ordering = self.request.query_params.get('ordering')
            qs = qs.order_by(*ordering.split(','))
        else:
            qs = qs.order_by('name')

        return qs


class SkillRateRangeViewSet(core_viewsets.BaseApiViewset):

    def get_queryset(self):
        qs = super().get_queryset()
        company = get_site_master_company()
        qs = qs.filter(
            skill__name__industry__in=company.industries.all(),
        )
        if self.request.query_params.get('ordering'):
            ordering = self.request.query_params.get('ordering')
            qs = qs.order_by(*ordering.split(','))
        else:
            qs = qs.order_by('skill')

        return qs
