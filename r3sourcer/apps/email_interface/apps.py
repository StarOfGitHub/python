from django.apps import AppConfig


class EmailInterfaceConfig(AppConfig):
    name = 'r3sourcer.apps.email_interface'

    def ready(self):
        from r3sourcer.apps.core.service import factory
        from r3sourcer.apps.email_interface.utils import get_email_service

        factory.register('email_interface', get_email_service())
