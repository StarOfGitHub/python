import os

from django.core.management.base import BaseCommand, CommandError

from r3sourcer.apps.core.models import User
from r3sourcer.apps.company_settings.models import GlobalPermission


class Command(BaseCommand):
    """
    Grants GlobalPermissions to a company contacts.
    Get model name argument
    """
    def add_arguments(self, parser):
        parser.add_argument('model', type=str)

    def handle(self, *args, **kwargs):
        model = kwargs['model']

        permission_list = GlobalPermission.objects.filter(name__icontains=model)
        print('Permissions ', permission_list, 'added for users:')

        users = User.objects.all()
        for user in users:
            if hasattr(user, 'contact') and user.contact.company_contact.exists():
                user.user_permissions.add(*permission_list)
                print(user)

        self.stdout.write("Permissions granted")
