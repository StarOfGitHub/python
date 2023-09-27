from django.apps import AppConfig


class LoginConfig(AppConfig):
    name = 'r3sourcer.apps.login'

    def ready(self):
        from r3sourcer.apps.core.service import factory
        from r3sourcer.apps.login.services import LoginService

        factory.register('login', LoginService)
