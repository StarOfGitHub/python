from r3sourcer.apps.core.api.router import router

from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.sms_interface import models as sms_models
from r3sourcer.apps.sms_interface.api import serializers as sms_serializers, filters, viewsets
from r3sourcer.apps.sms_interface.api.serializers import SMSTemplateSerializer


class SMSMessageApiEndpoint(ApiEndpoint):

    model = sms_models.SMSMessage
    serializer = sms_serializers.SMSMessageSerializer
    base_viewset = viewsets.SMSMessageViewset
    filter_class = filters.SMSMessageFilter

    search_fields = ('from_number', 'to_number', 'text')


class SMSRelatedObjectEndpoint(ApiEndpoint):

    model = sms_models.SMSRelatedObject
    filter_class = filters.SMSRelatedObjectFilter


class SMSLogEndpoint(ApiEndpoint):

    model = sms_models.SMSMessage
    serializer = sms_serializers.SMSLogSerializer
    filter_class = filters.SMSMessageFilter
    base_viewset = viewsets.SMSLogViewset

    search_fields = ('from_number', 'to_number', 'sid')


class SMSTemplateEndpoint(ApiEndpoint):

    model = sms_models.SMSTemplate
    base_viewset = viewsets.SMSMessageTemplateViewset
    serializer = SMSTemplateSerializer


router.register(endpoint=SMSMessageApiEndpoint())
router.register(endpoint=SMSRelatedObjectEndpoint())
router.register(endpoint=SMSTemplateEndpoint())
router.register(endpoint=SMSLogEndpoint(), url='sms-interface/smslogs')
