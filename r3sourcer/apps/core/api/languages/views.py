from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, permissions
from rest_framework.filters import SearchFilter

from r3sourcer.apps.core.api.languages.serializers import LanguageSerializer
from r3sourcer.apps.core.models import Language


class LanguageViewSet(mixins.ListModelMixin,
                      viewsets.GenericViewSet):
    queryset = Language.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LanguageSerializer
    filter_backends = [SearchFilter]
    search_fields = ['alpha_2', 'name']
