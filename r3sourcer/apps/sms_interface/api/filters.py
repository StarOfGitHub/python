from django_filters.rest_framework import FilterSet

from r3sourcer.apps.core_adapter.filters import DateRangeFilter
from r3sourcer.apps.sms_interface.models import SMSMessage, SMSRelatedObject


class SMSMessageFilter(FilterSet):

    created_at = DateRangeFilter(distinct=True)

    class Meta:
        model = SMSMessage
        fields = ['type', 'status', 'template', 'created_at', 'check_reply', 'is_fake']


class SMSRelatedObjectFilter(FilterSet):

    class Meta:
        model = SMSRelatedObject
        fields = ['sms']
