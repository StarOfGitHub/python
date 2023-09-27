from django.db.models import Q

from django_filters import UUIDFilter, CharFilter
from django_filters.rest_framework import FilterSet

from r3sourcer.apps.acceptance_tests import models


class AcceptanceTestFilter(FilterSet):

    skill = UUIDFilter(method='filter_skill')
    tag = UUIDFilter(method='filter_tag')
    industry = UUIDFilter(method='filter_industry')
    type = CharFilter(method='filter_type')

    class Meta:
        model = models.AcceptanceTest
        fields = ['skill', 'tag', 'industry', 'type']

    def filter_skill(self, queryset, name, value):
        return queryset.filter(acceptance_tests_skills__skill=value)

    def filter_tag(self, queryset, name, value):
        return queryset.filter(acceptance_tests_tags__tag=value)

    def filter_industry(self, queryset, name, value):
        return queryset.filter(acceptance_tests_industries__industry=value)

    def filter_type(self, queryset, name, value):
        if value == 'skill':
            qry = Q(acceptance_tests_skills__isnull=False)
        elif value == 'tag':
            qry = Q(acceptance_tests_tags__isnull=False)
        elif value == 'industry':
            qry = Q(acceptance_tests_industries__isnull=False)
        else:
            qry = Q(
                acceptance_tests_skills__isnull=True,
                acceptance_tests_tags__isnull=True,
                acceptance_tests_industries__isnull=True,
            )
        return queryset.filter(qry).distinct()


class AcceptanceTestWorkflowNodeFilter(FilterSet):

    class Meta:
        model = models.AcceptanceTestWorkflowNode
        fields = ['company_workflow_node']
