from rest_framework import viewsets, mixins, permissions
from rest_framework.response import Response

from r3sourcer.apps.core.models import ContactBankAccount
from .serializers import ContactBankAccountSerializer


class ContactBankAccountViewSet(mixins.ListModelMixin,
                                mixins.RetrieveModelMixin,
                                mixins.CreateModelMixin,
                                mixins.DestroyModelMixin,
                                viewsets.GenericViewSet):
    queryset = ContactBankAccount.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContactBankAccountSerializer

    def get_queryset(self):
        qs = self.queryset.filter(
            contact_id=self.kwargs['contact_id']
        )
        return qs

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

