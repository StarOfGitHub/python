from rest_framework.permissions import AllowAny

from r3sourcer.apps.candidate.api.serializers import VisaTypeSerializer
from r3sourcer.apps.candidate.api.viewsets import VisaTypeViewset
from r3sourcer.apps.core.api.router import router

from r3sourcer.apps.core.api import endpoints as core_endpoints
from r3sourcer.apps.candidate import models as candidate_models
from r3sourcer.apps.candidate.api import viewsets as candidate_viewsets, filters as candidate_filters
from r3sourcer.apps.candidate.api import serializers as candidate_serializers


class CandidateContactEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.CandidateContact
    base_viewset = candidate_viewsets.CandidateContactViewset
    serializer = candidate_serializers.CandidateContactSerializer
    filter_class = candidate_filters.CandidateContactFilter

    search_fields = (
        'contact__title', 'contact__last_name', 'contact__first_name',
        'contact__address__city__search_names', 'contact__address__street_address',
        'contact__email', 'contact__phone_mobile',
    )


class SkillRelEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.SkillRel
    serializer = candidate_serializers.SkillRelSerializer
    filter_class = candidate_filters.SkillRelFilter


class SkillRateEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.SkillRate
    serializer = candidate_serializers.SkillRateSerializer
    filter_class = candidate_filters.SkillRateFilter


class TagRelEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.TagRel
    serializer = candidate_serializers.TagRelSerializer
    filter_class = candidate_filters.TagRelFilter
    permission_classes = [AllowAny]


class SubcontractorEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.Subcontractor
    base_viewset = candidate_viewsets.SubcontractorViewset
    serializer = candidate_serializers.SubcontractorSerializer


class SubcontractorCandidateRelationEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.SubcontractorCandidateRelation
    serializer = candidate_serializers.SubcontractorCandidateRelationSerializer


class SuperannuationFundEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.SuperannuationFund
    base_viewset = candidate_viewsets.SuperannuationFundViewset
    search_fields = ['product_name']
    serializer_fields = (
        'id', 'fund_name', 'abn', 'usi', 'product_name', 'contribution_restrictions', 'from_date', 'to_date'
    )


class VisaTypeEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.VisaType
    viewset = VisaTypeViewset


class CandidateLocationEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.CandidateContact
    base_viewset = candidate_viewsets.CandidateLocationViewset
    serializer_fields = ('id', )


class SkillRateCoefficientRelEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.SkillRateCoefficientRel


class FormalityEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.Formality
    base_viewset = candidate_viewsets.FormalityViewset
    serializer = candidate_serializers.FormalitySerializer
    filter_class = candidate_filters.FormalityFilter


class CandidateStatisticsEndpoint(core_endpoints.ApiEndpoint):

    model = candidate_models.CandidateContact
    base_viewset = candidate_viewsets.CandidateStatisticsViewset
    serializer = candidate_serializers.CandidateStatisticsSerializer


router.register(endpoint=VisaTypeEndpoint())
router.register(endpoint=SuperannuationFundEndpoint())
router.register(endpoint=CandidateContactEndpoint())
router.register(endpoint=SubcontractorEndpoint())
router.register(endpoint=SkillRateEndpoint())
router.register(endpoint=TagRelEndpoint())
router.register(endpoint=SkillRelEndpoint())
router.register(candidate_models.InterviewSchedule)
router.register(candidate_models.CandidateRel)
router.register(endpoint=SubcontractorCandidateRelationEndpoint())
router.register(endpoint=CandidateLocationEndpoint(), url='candidate/location')
router.register(endpoint=SkillRateCoefficientRelEndpoint())
router.register(endpoint=FormalityEndpoint())
router.register(endpoint=CandidateStatisticsEndpoint(), url='candidate/statistics')
