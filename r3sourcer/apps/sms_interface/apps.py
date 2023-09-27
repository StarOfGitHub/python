from django.apps import AppConfig


class SMSInterfaceConfig(AppConfig):
    name = 'r3sourcer.apps.sms_interface'

    def ready(self):
        from r3sourcer.apps.core.service import factory
        from r3sourcer.apps.sms_interface.utils import get_sms_service

        factory.register('sms_interface', get_sms_service())
