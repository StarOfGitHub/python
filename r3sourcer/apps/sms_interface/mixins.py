import json
from datetime import datetime

import jwt

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import Http404
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import get_list_or_404
from django import forms
from model_utils import Choices
from oauth2_provider_jwt.utils import decode_jwt

from r3sourcer.helpers.models.abs import TemplateMessage


class DeadlineCheckingMixin(models.Model):
    """
    Deadline mixin.
    Adding deadline fields for checking messages.
    """

    reply_timeout = models.IntegerField(
        default=settings.REPLY_TIMEOUT_SMS,
        verbose_name=_("Reply timeout"),
        help_text=_("Minutes"),
    )
    delivery_timeout = models.IntegerField(
        default=settings.DELIVERY_TIMEOUT_SMS,
        verbose_name=_("Delivery timeout"),
        help_text=_("Minutes"),
    )

    class Meta:
        abstract = True


class TokenRequiredMixin(object):
    def dispatch(self, request, *args, **kwargs):
        from r3sourcer.apps.core.models import User
        token = request.GET.get('token')
        if not token:
            raise PermissionDenied

        try:
            payload = decode_jwt(token)
            self.user = User.objects.get(id=payload['user_id'])
        except (jwt.PyJWTError, User.DoesNotExist):
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)


class MessageViewBase(object):
    uri_param_key = 'param_tpl'
    recipient_key = 'recipient'

    SENDER_CHOICES = Choices(
        ('self', _("From self")),
        ('responsible', _("From person responsible")),
    )

    def get_sender_choices(self):
        raise NotImplemented

    @property
    def recipient_field(self):
        """
        Required field: `get_recipient` or `get_recipient_value`
        """
        raise NotImplementedError

    def get_model_object(self, model_name, object_id):
        """
        :param model_name: string app_label.model_name
        :param object_id: string (uuid)
        :return: app_label.model_name instance
        """
        try:
            return apps.get_model(model_name).objects.get(id=object_id)
        except Exception:
            return object_id

    def get_extra_params(self, recipient):
        """
        Get all requirements from recipient instance:
         - recruitee contact
         - client contact
         - client, account
        """
        default_kwargs = {}
        return default_kwargs

    def get_url_params(self):
        """
        Return arguments from GET params.
        For example:
            - for uri_param_key_crm_core__contact=ID return {'contact': crm_core.Contact.get(id=UUID)}
            - for uri_param_key_starts_at=10.01.2010 return {'starts_at': '10.01.2010'}
        """

        values = {}
        for key, value in self.request.GET.dict().items():
            if key.startswith(self.uri_param_key):
                _key = key[10:]
                if key.count('__') == 1:
                    instance = self.get_model_object(_key.replace('__', '.'), value)
                    if isinstance(instance, models.Model):
                        values.setdefault(_key[_key.index('__') + 2:], instance)
                    else:
                        values.setdefault(_key, instance)
                else:
                    values.setdefault(_key, value)
        return values

    def get_json_params(self, json_dict):

        def get_object(ct_id, object_id):
            model_class = ContentType.objects.get(pk=ct_id).model_class()
            return model_class.objects.filter(pk=object_id).last()

        def parse_date(dt_str):
            return datetime.strptime(dt_str, '%d/%m/%Y')

        def parse_datetime(dtm_str):
            return datetime.strptime(dtm_str, '%d/%m/%Y %H:%M')

        base_types = {
            'date': parse_date,
            'datetime': parse_datetime,
            'row': lambda x: x,
            'object': get_object
        }

        result_dict = {}

        for key, (type_value, values) in json_dict.items():
            handler = base_types[type_value]
            result_dict.setdefault(key, handler(*values))
        return result_dict

    def get_origin_params(self):
        """
        Get url origin params:
        """
        return dict(filter(lambda key: key[0].startswith(self.uri_param_key), self.request.GET.dict().items()))

    def get_recipient_value(self):
        """
        Return recipient value from GET params
        """
        return self.request.GET.getlist(self.recipient_key) or self.request.GET.getlist('%s[]' % self.recipient_key)

    def get_recipient_field_value(self):
        """
        Return recipient phone number or email field value
        """
        return getattr(self.get_recipients(), self.recipient_field, None)

    def get_recipient_list(self):
        """
        Return contacts recipient by recipient_field (email, phone_mobile)
        """
        from r3sourcer.apps.core.models import Contact
        recipients = self.get_recipient_value()

        if recipients:
            return get_list_or_404(Contact, **{'%s__in' % self.recipient_field: recipients})

        return Contact.objects.filter(phone_mobile__isnull=False)

    def get_recipient_id(self):
        return self.request.POST.getlist('recipient_id', None) or self.request.POST.getlist('recipient_id[]', None)

    def get_recipients(self):
        """
        Return contact recipient by recipient_field (email, phone_mobile)
        """
        from r3sourcer.apps.core.models import Contact
        recipients = self.get_recipient_value()
        if self.request.method == 'POST':
            # get recipient by recipient_id
            return get_list_or_404(Contact,
                                   models.Q(**{'%s__in' % self.recipient_field: recipients}) |
                                   models.Q(pk__in=self.get_recipient_id()))

        contacts = Contact.objects.filter(**{'%s__in' % self.recipient_field: recipients})
        if not recipients or contacts.exists():
            return contacts
        raise Http404(_("No such contact"))

    @property
    def sender_value_field(self):
        raise NotImplementedError

    def get_sender(self):
        raise NotImplementedError

    def get_sender_value(self):
        value = getattr(self.get_sender(), self.sender_value_field, None)
        if callable(value):
            return value()  # for methods
        return value


class MessageView(MessageViewBase, TokenRequiredMixin):
    """
    Would be use in sms and email dialog views
    """

    ERROR_SENDING_MESSAGE = _("Error sending message '%s' for %s: %s")

    template_key = 'template_id'

    initial_keys = [
        'recipient',
        'reply_deadline',
        'delivery_deadline',
        'body'
    ]

    form_context_keys = [
        'extra_title'
    ]

    UNAVAILABLE_TEXT_MESSAGE = _("Service is not allowed")
    SUCCESS_SENDING = _("Your message was successfully sent to %s: %s")

    def get_form_class(self):
        """
        Extending class form with sender field
        """

        class ExtendedMessageForm(self.form_class):
            sender_user = forms.ChoiceField(choices=self.get_sender_choices, label=_("Sender"))

        ExtendedMessageForm.base_fields.move_to_end('sender_user', last=False)
        return ExtendedMessageForm

    @property
    def message_type(self):
        raise NotImplementedError

    def get_initial(self):
        initial = super(MessageView, self).get_initial()
        for key in self.initial_keys:
            if key in self.request.GET:
                initial.update({key: self.request.GET.get(key)})
        template = self.get_template()
        if template:
            initial.update({'body': template.message_text_template})
            initial.update({'subject': template.subject_template})
        return initial

    def get_context_data(self, **kwargs):
        context = super(MessageView, self).get_context_data(**kwargs)
        for key in self.form_context_keys:
            if key in self.request.GET:
                context.update({key: self.request.GET.get(key)})
        context.update({
            'message_type': self.message_type,
            'recipient': self.get_recipients(),
            'recipients': self.get_recipient_list(),
            'recipient_value': self.get_recipient_value(),
            'is_allowed': self.is_allowed(),
            'allowed_message_info': self.UNAVAILABLE_TEXT_MESSAGE,
            'template_params': json.dumps(self.get_origin_params())
        })
        return context

    def is_allowed(self):
        """
        Checking allowed modal service for current contact
        """
        allowed = self.request.GET.get('allowed', 'true') == 'true'
        return allowed or bool(self.get_recipient_value())  # and bool(self.get_sender_value())

    def get_template(self):
        if self.template_key in self.request.GET:
            try:
                return TemplateMessage.objects.get(id=self.request.GET.get(self.template_key))
            except TemplateMessage.DoesNotExist:
                pass

    def get_success_url(self):
        return self.request.path + "?" + self.request.META['QUERY_STRING']
