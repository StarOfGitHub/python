from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from django.conf import settings
from r3sourcer.apps.acceptance_tests.models import AcceptanceTestRelationship, AcceptanceTest, \
    AcceptanceTestQuestionPicture
from r3sourcer.apps.acceptance_tests.api.serializers import AcceptanceTestSerializerAll, \
    AcceptanceTestQuestionPictureSerializerAll
from r3sourcer.apps.core.api.viewsets import BaseApiViewset
from r3sourcer.apps.core.utils.companies import get_site_master_company


class AcceptanceTestViewset(BaseApiViewset):

    def perform_create(self, serializer):
        instance = serializer.save()

        master_company = get_site_master_company(request=self.request)

        AcceptanceTestRelationship.objects.create(acceptance_test=instance, company=master_company)

    @action(methods=['get'], detail=False, permission_classes=(AllowAny,))
    def all(self, request, *args, **kwargs):
        queryset = AcceptanceTest.objects.all()
        serializer = AcceptanceTestSerializerAll(queryset, many=True)
        return Response(serializer.data)


class AcceptanceTestQuestionPictureViewset(BaseApiViewset):

    def perform_create(self, serializer):
        question_id = serializer.validated_data['acceptance_test_question']
        picture_count = AcceptanceTestQuestionPicture.objects.filter(acceptance_test_question_id=question_id).count()
        if picture_count >= settings.MAXIMUM_ACCEPTANCE_TEST_PICTURES:
            raise ValidationError('Too many pictures')
        serializer.save()

    @action(methods=['get'], detail=False, permission_classes=(AllowAny,))
    def all(self, request, *args, **kwargs):
        queryset = AcceptanceTestQuestionPicture.objects.all()
        serializer = AcceptanceTestQuestionPictureSerializerAll(queryset, many=True)
        return Response(serializer.data)
