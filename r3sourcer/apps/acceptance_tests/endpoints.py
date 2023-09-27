from r3sourcer.apps.acceptance_tests.api import filters, serializers, viewsets
from r3sourcer.apps.core.api.router import router
from r3sourcer.apps.core.api.endpoints import ApiEndpoint

from . import models


class AcceptanceTestEndpoint(ApiEndpoint):

    model = models.AcceptanceTest
    filter_class = filters.AcceptanceTestFilter
    serializer = serializers.AcceptanceTestSerializer
    base_viewset = viewsets.AcceptanceTestViewset

    search_fields = ('test_name', )


class AcceptanceTestQuestionPictureEndpoint(ApiEndpoint):
    model = models.AcceptanceTestQuestionPicture
    base_viewset = viewsets.AcceptanceTestQuestionPictureViewset


class AcceptanceTestWorkflowNodeEndpoint(ApiEndpoint):

    model = models.AcceptanceTestWorkflowNode
    filter_class = filters.AcceptanceTestWorkflowNodeFilter
    serializer = serializers.AcceptanceTestWorkflowNodeSerializer


class WorkflowObjectAnswerEndpoint(ApiEndpoint):

    model = models.WorkflowObjectAnswer
    serializer = serializers.WorkflowObjectAnswerSerializer


router.register(endpoint=AcceptanceTestEndpoint())
router.register(models.AcceptanceTestQuestion)
router.register(endpoint=AcceptanceTestQuestionPictureEndpoint())
router.register(models.AcceptanceTestAnswer)
router.register(models.AcceptanceTestSkill)
router.register(models.AcceptanceTestIndustry)
router.register(models.AcceptanceTestTag)
router.register(endpoint=AcceptanceTestWorkflowNodeEndpoint())
router.register(endpoint=WorkflowObjectAnswerEndpoint())
