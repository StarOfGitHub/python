import logging

from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from twilio.base.exceptions import TwilioRestException

from r3sourcer.apps.core.api.viewsets import BaseApiViewset
from r3sourcer.apps.core.utils.companies import get_site_master_company
from r3sourcer.apps.twilio import models
from r3sourcer.apps.twilio.api.serializers import TwilioPhoneNumberSerializer


logger = logging.getLogger(__name__)


class TwilioPhoneNumberViewset(BaseApiViewset):

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.distinct('phone_number')

    def create(self, request, *args, **kwargs):
        sid = self.request.data.get('sid')

        if not sid:
            raise exceptions.ValidationError(_('Twilio phone number SID is invalid'))

        twilio_client = self._get_twilio_client()

        try:
            remote_phone = twilio_client.incoming_phone_numbers(sid).fetch()
        except TwilioRestException as e:
            logger.exception(e)
            raise exceptions.ValidationError(_('Twilio phone number SID is invalid'))

        company = get_site_master_company(request=self.request)
        twilio_phone = models.TwilioPhoneNumber.fetch_remote(remote_phone, company)

        serializer = TwilioPhoneNumberSerializer(twilio_phone)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _get_twilio_client(self):
        twilio_account = models.TwilioAccount.objects.filter(
            status=models.TwilioAccount.STATUS_CHOICES.ACTIVE
        ).first()

        if not twilio_account:
            raise exceptions.NotFound()

        return twilio_account.client

    @action(methods=['get'], detail=False)
    def available(self, *args, **kwargs):
        country_code = self.request.query_params.get('country_code', 'AU')
        page_size = int(self.request.query_params.get('page_size', 10))

        twilio_client = self._get_twilio_client()

        phone_number_objs = twilio_client.api.available_phone_numbers(country_code).mobile.stream(
            page_size=page_size
        )
        phone_numbers = [
            models.TwilioPhoneNumber.dict_from_object(phone_number_obj, is_new=True)
            for phone_number_obj in phone_number_objs
        ]
        return Response(TwilioPhoneNumberSerializer(phone_numbers, many=True).data)

    @action(methods=['post'], detail=False)
    def purchase(self, *args, **kwargs):
        phone_number = self.request.data.get('phone_number')

        if not phone_number:
            raise exceptions.ValidationError(_('Phone number is invalid'))

        twilio_client = self._get_twilio_client()
        try:
            remote_phone = twilio_client.incoming_phone_numbers.create(phone_number=phone_number)
        except TwilioRestException as e:
            logger.exception(e)
            raise exceptions.ValidationError(_('Cannot purchase phone number. Please try later.'))

        company = get_site_master_company(request=self.request)
        models.TwilioPhoneNumber.fetch_remote(remote_phone, company)

        return Response({'status': 'success'})
