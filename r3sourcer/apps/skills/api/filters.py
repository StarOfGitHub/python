from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django_filters import UUIDFilter
from django_filters.rest_framework import FilterSet, BooleanFilter

from r3sourcer.apps.skills import models as skills_models
from r3sourcer.apps.candidate.models import CandidateContact


class SkillFilter(FilterSet):
    priced = BooleanFilter(method='filter_by_priced')
    exclude = UUIDFilter(method='exclude_by_candidate')
    exclude_pricelist = UUIDFilter(method='exclude_by_pricelist')
    industry = UUIDFilter(method='filter_by_industry')
    # active = BooleanFilter(method='filter_by_active')

    class Meta:
        model = skills_models.Skill
        fields = ['company']

    def filter_by_priced(self, queryset, name, value):
        if value:
            return queryset.filter(id__in=[skill.id for skill in queryset if skill.is_priced()])
        else:
            return queryset

    def exclude_by_candidate(self, queryset, name, value):
        return queryset.filter(active=True).exclude(
            candidate_skills__candidate_contact_id=value
        )

    def exclude_by_pricelist(self, queryset, name, value):
        return queryset.exclude(
            price_list_rates__price_list_id=value
        )

    def filter_by_industry(self, queryset, name, value):
        return queryset.filter(name__industry=value).distinct()

    # def filter_by_active(self, queryset, name, value):
    #     return queryset.filter(active=value)


class SkillBaseRateFilter(FilterSet):
    candidate_skill = UUIDFilter(method='filter_candidate_skill')

    class Meta:
        model = skills_models.SkillBaseRate
        fields = ['candidate_skill', 'skill']

    def filter_candidate_skill(self, queryset, name, value):
        return queryset.filter(skill__candidate_skills=value).distinct()


class SkillTagFilter(FilterSet):

    class Meta:
        model = skills_models.SkillTag
        fields = ['tag', 'skill', 'tag__confidential']


class SkillNameFilter(FilterSet):
    exclude_company = UUIDFilter(method='exclude_by_company')
    active = BooleanFilter(method='filter_by_active')

    class Meta:
        model = skills_models.SkillName
        fields = ['industry']

    def exclude_by_company(self, queryset, name, value):
        return queryset.exclude(
            skills__company=value
        )

    def filter_by_active(self, queryset, name, value):
        if value:
            return queryset.filter(
                skills__active=value,
                skills__company=self.request.user.company
            )
        else:
            return queryset.filter(
                skills__active=value,
            )


class SkillRateRangeFilter(FilterSet):

    class Meta:
        model = skills_models.SkillRateRange
        fields = ['skill', 'worktype']


class WorkTypeFilter(FilterSet):
    skill = UUIDFilter(method='filter_skill')
    candidate_contact = UUIDFilter(method='filter_candidate_contact')

    class Meta:
        model = skills_models.WorkType
        fields = ['skill_name', 'skill']

    def filter_skill(self, queryset, name, value):
        try:
            skill = skills_models.Skill.objects.get(pk=value)
        except:
            skill = None
        queryset = queryset.filter(
            Q(skill_name=skill.name) |
            Q(skill__name=skill.name)
        )
        return queryset

    def filter_candidate_contact(self, queryset, name, value):
        try:
            candidat_contact = CandidateContact.objects.get(pk=value)
        except ObjectDoesNotExist:
            candidat_contact = None
        skill_rel_ids = candidat_contact.candidate_skills.values_list('id', flat=True)
        queryset = queryset.filter(skill_rates__skill_rel_id__in=skill_rel_ids)
        return queryset
