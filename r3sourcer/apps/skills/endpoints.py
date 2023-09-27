from rest_framework import permissions

from r3sourcer.apps.core.api.router import router
from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.skills import models
from r3sourcer.apps.skills.api import filters as skills_filters, serializers as skill_serializer, viewsets as skill_viewset


class SkillEndpoint(ApiEndpoint):

    model = models.Skill
    filter_class = skills_filters.SkillFilter
    serializer = skill_serializer.SkillSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly, )
    search_fields = ('name__name', 'name__translations__value')


class EmploymentClassificationEndpoint(ApiEndpoint):

    model = models.EmploymentClassification
    search_fields = ('name', )
    serializer_fields = ('id', 'name', )


class SkillBaseRateEndpoint(ApiEndpoint):
    model = models.SkillBaseRate
    serializer = skill_serializer.SkillBaseRateSerializer
    filter_class = skills_filters.SkillBaseRateFilter
    search_fields = ('skill__name__name', 'skill__name__translations__value')


class SkillTagEndpoint(ApiEndpoint):
    model = models.SkillTag
    filter_class = skills_filters.SkillTagFilter
    serializer = skill_serializer.SkillTagSerializer
    search_fields = ('skill__name__name', 'tag__name', 'skill__name__translations__value')


class SkillNameEndpoint(ApiEndpoint):

    model = models.SkillName
    base_viewset = skill_viewset.SkillNameViewSet
    filter_class = skills_filters.SkillNameFilter
    serializer = skill_serializer.SkillNameSerializer
    search_fields = ('name', 'translations__value')


class SkillRateRangeEndpoint(ApiEndpoint):

    model = models.SkillRateRange
    base_viewset = skill_viewset.SkillRateRangeViewSet
    filter_class = skills_filters.SkillRateRangeFilter
    serializer = skill_serializer.SkillRateRangeSerializer
    search_fields = ('skill__name__name', 'worktype__name', 'skill__name__translations__value')


class WorkTypeEndpoint(ApiEndpoint):

    model = models.WorkType
    base_viewset = skill_viewset.WorkTypeViewSet
    filter_class = skills_filters.WorkTypeFilter
    serializer = skill_serializer.WorkTypeSerializer
    search_fields = ('skill_name__name', 'name', 'skill_name__translations__value')


router.register(endpoint=SkillNameEndpoint())
router.register(endpoint=SkillEndpoint())
router.register(endpoint=SkillBaseRateEndpoint())
router.register(endpoint=EmploymentClassificationEndpoint())
router.register(endpoint=SkillTagEndpoint())
router.register(endpoint=SkillRateRangeEndpoint())
router.register(endpoint=WorkTypeEndpoint())
