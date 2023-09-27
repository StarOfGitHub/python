from django.db import IntegrityError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, mixins, permissions, filters
from rest_framework.generics import get_object_or_404

from r3sourcer.apps.core.models import CompanyLanguage
from r3sourcer.helpers.api.responses import Custom409
from .serializers import CompanyLanguageSerializer


class CompanyLanguageViewSet(mixins.ListModelMixin,
                             mixins.CreateModelMixin,
                             mixins.UpdateModelMixin,
                             mixins.DestroyModelMixin,
                             viewsets.GenericViewSet):
    queryset = CompanyLanguage.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CompanyLanguageSerializer
    lookup_url_kwarg = 'language_id'
    search_fields = ['language__alpha_2', 'language__name']
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)

    def get_queryset(self):
        qs = self.queryset.filter(
            company_id=self.kwargs['company_id']
        )
        if self.kwargs.get(self.lookup_url_kwarg):
            qs = qs.filter(**{self.lookup_url_kwarg: self.kwargs[self.lookup_url_kwarg]})
        return qs

    def get_object(self):
        return get_object_or_404(self.get_queryset())

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, args, kwargs)
        except IntegrityError as e:
            raise Custom409(e)
        return response
