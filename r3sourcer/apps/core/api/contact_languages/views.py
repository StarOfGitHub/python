from django.db import IntegrityError
from rest_framework import viewsets, mixins, permissions
from rest_framework.generics import get_object_or_404

from r3sourcer.apps.core.api.contact_languages.serializers import ContactLanguageSerializer
from r3sourcer.apps.core.models.core import ContactLanguage
from r3sourcer.helpers.api.responses import Custom409


class ContactLanguageViewSet(mixins.ListModelMixin,
                             mixins.CreateModelMixin,
                             mixins.UpdateModelMixin,
                             mixins.DestroyModelMixin,
                             viewsets.GenericViewSet):
    queryset = ContactLanguage.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContactLanguageSerializer
    lookup_url_kwarg = 'language_id'

    def get_queryset(self):
        qs = self.queryset.filter(
            contact_id=self.kwargs['contact_id']
        )
        if self.kwargs.get(self.lookup_url_kwarg):
            qs = qs.filter(**{self.lookup_url_kwarg: self.kwargs[self.lookup_url_kwarg]})
        return qs

    def get_object(self):
        return get_object_or_404(self.get_queryset())

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, args, kwargs)
        except IntegrityError:
            raise Custom409("Contact language already exists")
        return response

