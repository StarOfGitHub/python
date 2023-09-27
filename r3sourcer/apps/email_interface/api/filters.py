from django_filters.rest_framework import FilterSet
from r3sourcer.apps.core_adapter.filters import DateRangeFilter

from r3sourcer.apps.email_interface.models import EmailMessage


class EmailMessageFilter(FilterSet):

    created_at = DateRangeFilter(distinct=True)

    class Meta:
        model = EmailMessage
        fields = ['state', 'template', 'created_at']
