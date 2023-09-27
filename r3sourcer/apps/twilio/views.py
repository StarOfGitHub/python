import logging

from django.contrib import messages
from django.http import HttpResponse
from django.views.generic import FormView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property

from r3sourcer.apps.sms_interface.mixins import MessageView
from r3sourcer.apps.sms_interface.tasks import fetch_remote_sms, parse_sms_response
from r3sourcer.apps.twilio.forms import SMSForm
from r3sourcer.apps.twilio.services import TwilioSMSService


logger = logging.getLogger(__name__)


@method_decorator(xframe_options_exempt, name='dispatch')
class SMSDialogTemplateView(MessageView, FormView):

    form_class = SMSForm
    template_name = "base-message-template.html"

    sender_value_field = 'get_phone'
    recipient_field = 'phone_mobile'
    message_type = 'sms'

    @cached_property
    def get_sender_choices(self):

        phones = TwilioSMSService.get_sender_phones(self.user.contact)
        choices = []

        for phone in phones:
            item = (str(phone.id), "{company} {phone_number}".format(
                company=phone.company, phone_number=phone.phone_number
            ))
            choices.append(item)

        return choices

    def get_sender(self):
        sender = self.request.POST['sender_user']
        return TwilioSMSService.get_sender_phones(self.user.contact).get(id=sender)

    def form_valid(self, form):
        for recipient in self.get_recipients():
            params = self.get_url_params()
            params.update(self.get_extra_params(recipient))
            params.update(self.get_json_params(form.cleaned_data['params']))
            sender_contact = self.get_sender()
            try:
                TwilioSMSService().send(
                        to_number=recipient.phone_mobile,
                        text=form.cleaned_data['body'],
                        from_number=sender_contact.phone_number,
                        related_obj=recipient,
                        sender_contact=self.user.contact,
                        **params
                )
            except Exception as e:
                messages.add_message(self.request, messages.ERROR, self.ERROR_SENDING_MESSAGE % (
                    e, recipient, recipient.phone_mobile))
            else:
                messages.add_message(self.request, messages.SUCCESS, self.SUCCESS_SENDING % (
                    recipient, recipient.phone_mobile))
        return super(SMSDialogTemplateView, self).form_valid(form)


@csrf_exempt
def callback(request, **kwargs):
    data = request.POST
    logger.info('Twilio request data: {}'.format(data))
    if data.get('From') and data.get('Body') and data.get('Body').strip().lower() == 'yes':
        parse_sms_response.delay(data.get('From'))
    fetch_remote_sms.delay()
    return HttpResponse('<Response></Response>', content_type='text/xml')
