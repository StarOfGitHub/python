from rest_framework import viewsets, mixins, permissions
from rest_framework.generics import get_object_or_404

from r3sourcer.apps.core.models import BankAccountLayout
from .serializers import BankAccountLayoutSerializer


class BankAccountLayoutViewSet(mixins.ListModelMixin,
                               viewsets.GenericViewSet):
    queryset = BankAccountLayout.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankAccountLayoutSerializer
    lookup_url_kwarg = 'country_id'

    def get_queryset(self):
        qs = self.queryset
        if self.kwargs.get(self.lookup_url_kwarg):
            qs = qs.filter(countries__country_id=self.kwargs[self.lookup_url_kwarg].upper())
        return qs
