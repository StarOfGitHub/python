from django.conf import settings
from django.conf.urls import url
from django.contrib import admin
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import ugettext_lazy as _

from r3sourcer.apps.core_utils.filters import DatePeriodRangeAdminFilter
from r3sourcer.apps.sms_interface.models import SMSMessage

from .models import TwilioCredential, TwilioSMSMessage, TwilioPhoneNumber, TwilioAccount


class AdminAllReadOnlyFields(admin.ModelAdmin):
    def get_change_admin_url(self, obj):
        url = reverse(
            'admin:{app}_{model}_change'.format(
                app=obj._meta.app_label,
                model=obj._meta.model_name,
            ),
            args=[obj.id]
        )
        return '{name} <a href="{url}">(follow the link)</a>'.format(url=url, name=obj)

    def get_readonly_fields(self, request, obj=None):
        fields = list()
        for item in self.fieldsets:
            for field in item[1]['fields']:
                if isinstance(field, str):
                    fields.append(field)
                else:
                    fields.extend(field)
        return fields


class TwilioCredentialAdmin(admin.ModelAdmin):
    model = TwilioCredential
    extra = 0
    max_num = 1

    fieldsets = (
        (_("Credentials"), {
            'fields': ['sid', 'auth_token', ('parse_from_date', 'last_sync')]
        }),
        (_("Company"), {
            'fields': ['company']
        }),
        (_("Timeouts"), {
            'fields': [('reply_timeout', 'delivery_timeout')]
        })
    )

    readonly_fields = ('last_sync',)


class TwilioSMSMessageAdmin(AdminAllReadOnlyFields):
    search_fields = ('sid', 'from_number', 'to_number')
    list_display = ('sid', 'from_number', 'to_number', 'status',
                    'sent_at', 'get_delivered_received_datetime')
    readonly_fields = ('get_delivered_received_datetime',)
    list_display_links = list_display
    list_filter = (
        'type', 'status',
        ('sent_at', DatePeriodRangeAdminFilter),
        'check_reply', 'is_fake'
    )
    fieldsets = (
        (_("Main info"), {
            'fields': [('from_number', 'to_number'), 'text', ('type', 'status'),
                       ('sent_at', 'created_at', 'get_account_link'),
                       ('reply_timeout', 'delivery_timeout', 'error_code', 'error_message'),
                       ('get_resend_link',),
                       ]
        }),
    )

    def get_resend_link(self, obj):
        if not obj.is_delivered():
            reversed_url = reverse('admin:twilio_smsmessage_resend', args=[obj.id])
            return '<a href="{url}">{title}</a>'.format(
                url=reversed_url, title=_("Resend sms") if settings.ENABLED_TWILIO_WORKING \
                    else _("Resend debug sms")
            )
        return '-'

    get_resend_link.short_description = _("Resend")
    get_resend_link.allow_tags = True

    def get_account_link(self, obj):
        return obj.twillio_account.credential.owner

    get_account_link.short_description = _("Account")

    def get_delivered_received_datetime(self, obj):
        if obj.type == SMSMessage.TYPE_CHOICES.SENT:
            if obj.status == SMSMessage.STATUS_CHOICES.DELIVERED:
                return obj.updated_at
        if obj.type == SMSMessage.TYPE_CHOICES.RECEIVED:
            return obj.updated_at

    get_delivered_received_datetime.short_description = _("Delivered at/ Received at")

    def get_urls(self):
        urls = super(TwilioSMSMessageAdmin, self).get_urls()
        return [url(r'^(?P<object_id>.+)/resend/$', self.admin_site.admin_view(self.resend_failed_view),
                    name='twilio_smsmessage_resend'), ] + urls

    def resend_failed_view(self, reqeust, object_id):
        obj = get_object_or_404(self.model, pk=object_id)
        success = obj.resend()
        if success:
            self.message_user(reqeust, _("Sms successfully resent"))
        else:
            self.message_user(reqeust, _("Sms message wasn't resent"), messages.ERROR)

        reverse_url = 'admin:{app}_{model}_change'.format(
            app=obj._meta.app_label,
            model=obj._meta.model_name,
        )

        return redirect(reverse_url, obj.id)

    class Media:
        css = {
            'all': ('font-awesome/css/font-awesome.css',)
        }


class TwilioPhoneNumberAdmin(admin.ModelAdmin):

    list_display = ('phone_number', 'company', 'is_default', 'sms_enabled', 'voice_enabled')
    list_filter = ('company', 'is_default')
    readonly_fields = ('phone_number', 'friendly_name', 'sms_enabled', 'mms_enabled', 'voice_enabled')


admin.site.register(TwilioPhoneNumber, TwilioPhoneNumberAdmin)
admin.site.register(TwilioCredential, TwilioCredentialAdmin)
admin.site.register(TwilioSMSMessage, TwilioSMSMessageAdmin)
admin.site.register(TwilioAccount)
