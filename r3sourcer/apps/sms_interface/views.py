from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SMSTemplate
from .mixins import MessageViewBase
from .serializers import TemplateBodySerializer, ContentTypeSerializer, TemplateSerializer, \
    SMSMessageSerializer, SMSErrorSerializer
from r3sourcer.apps.core.models import Company
from r3sourcer.apps.sms_interface.models import SMSMessage
from r3sourcer.apps.sms_interface.serializers import ModelObjectSerializer


class TemplateCompileView(MessageViewBase, APIView):

    recipient_field = 'phone_mobile'
    sender_value_field = 'get_phone'
    message_type = 'sms'

    def post(self, request, *args, **kwargs):
        serializer = TemplateBodySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        compiled_messages = []
        for recipient in self.get_recipients():
            params = self.get_url_params()
            params.update(**self.get_extra_params(recipient))
            params.update(**self.get_json_params(serializer.validated_data['params']))
            compiled_messages.append(
                SMSTemplate.compile_string(serializer.validated_data['body'], **params)[0]
            )
        return Response({'body': compiled_messages})


class ContentTypeListView(generics.ListAPIView):

    pagination_class = None
    queryset = ContentType.objects.filter(app_label__in=[
        'core',
        'crm_core',
        'crm_hr',
        'candidate'
    ])
    serializer_class = ContentTypeSerializer


class SearchObjects(generics.ListAPIView):

    serializer_class = ModelObjectSerializer

    def get_queryset(self):
        model_class= ContentType.objects.get(pk=self.kwargs['ct']).model_class()

        data = self.request.GET.get('q', '')
        if hasattr(model_class, 'get_search_lookup'):
            lookup = model_class.get_search_lookup(data)
        else:
            lookup = Q(pk__icontains=data)

        return model_class.objects.filter(lookup)


class TemplateSMSMessageListView(generics.ListAPIView):

    pagination_class = None
    queryset = SMSTemplate.objects.filter(type=SMSTemplate.SMS)
    serializer_class = TemplateSerializer


class SMSMessageListView(generics.ListAPIView):
    serializer_class = SMSMessageSerializer

    def get_queryset(self):
        queryset = SMSMessage.objects.filter(type='SENT')
        company_id = self.request.GET.get('company_id', None)

        if company_id:
            company = get_object_or_404(Company, id=company_id)
            queryset = queryset.filter(company=company)

        return queryset


class ErrorSMSMessageListView(generics.ListAPIView):
    serializer_class = SMSErrorSerializer

    def get_queryset(self):
        queryset = SMSMessage.objects.filter(error_code__in=["No Funds", "SMS disabled"])
        company_id = self.request.GET.get('company_id', None)

        if company_id:
            company = get_object_or_404(Company, id=company_id)
            queryset = queryset.filter(company=company)

        return queryset