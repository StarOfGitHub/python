import os

from django.core.management.base import BaseCommand, CommandError

from r3sourcer.apps.core.models import User
from r3sourcer.apps.company_settings.models import GlobalPermission


class Command(BaseCommand):
    """
    Grants all GlobalPermissions to a given user.
    """
    def add_arguments(self, parser):
        parser.add_argument('user_id', type=str)

    def handle(self, *args, **kwargs):
        user_id = kwargs['user_id']

        try:
            user = User.objects.get(id=user_id)
        except:
            raise CommandError("User with id: %s was not found." % user_id)

        permission_list = GlobalPermission.objects.all()
        user.user_permissions.add(*permission_list)

        self.stdout.write("Permissions granted")
