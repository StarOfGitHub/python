from django.utils.translation import ugettext_lazy as _
from r3sourcer.apps.core.api.router import router

from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from r3sourcer.apps.core_logger.models import LoggerModel, LoggerDiffModel
from r3sourcer.apps.core_logger.viewsets import LoggerViewset, LoggerDiffViewset

from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.core.api.serializers import ApiBaseSerializer
from r3sourcer.apps.core.api.viewsets import BaseApiViewset
from r3sourcer.apps.core.utils.text import format_lazy

from r3sourcer.apps.core_adapter.constants import FIELD_DATETIME
from r3sourcer.apps.core_adapter.utils import api_reverse_lazy


class LoggerEndpoint(ApiEndpoint):
    model = LoggerModel
    base_viewset = LoggerViewset
    base_serializer = ApiBaseSerializer
    ordering_fields = []


class LoggerDiffEndpoint(ApiEndpoint):
    model = LoggerDiffModel
    base_viewset = LoggerDiffViewset
    base_serializer = ApiBaseSerializer
    ordering_fields = []


@action(methods=['get'], detail=False)
def log(self, request, *args, **kwargs):
    serializer_class = self.get_serializer_class()
    model = serializer_class.Meta.model

    if not hasattr(model, 'use_logger') or not model.use_logger:
        raise NotFound()

    data = LoggerViewset.get_logs(model)

    page = self.paginate_queryset(data)
    if page is not None:
        return self.get_paginated_response(page)
    return Response(data)


BaseApiViewset.log = log


router.register(endpoint=LoggerEndpoint(), url='log')
router.register(endpoint=LoggerDiffEndpoint(), url='log/(?P<model>.+)/(?P<obj_id>.+)')
