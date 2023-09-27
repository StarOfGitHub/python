import logging

from rest_framework import viewsets, mixins, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from r3sourcer.apps.core.api.viewsets import BaseApiViewset
from r3sourcer.apps.email_interface.models import EmailTemplate

logger = logging.getLogger(__name__)


class EmailMessageViewset(BaseApiViewset):
    ordering = ('-created_at',)


class EmailMessageTemplateViewset(mixins.ListModelMixin,
                                  mixins.CreateModelMixin,
                                  mixins.UpdateModelMixin,
                                  mixins.DestroyModelMixin,
                                  mixins.RetrieveModelMixin,
                                  viewsets.GenericViewSet):
    queryset = EmailTemplate.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(
            company_id=self.request.user.company.id
        )

    def perform_create(self, serializer):
        serializer.save(company_id=self.request.user.company.id)

    @action(methods=['get'], detail=False)
    def slugs(self, request):
        slugs = EmailTemplate.objects.order_by('slug').distinct('slug').values_list('slug', flat=True)
        return Response({
            "slugs": slugs
        })
