"""
Management utility to create superusers.
"""
import uuid

from django.contrib.auth.management.commands.createsuperuser import Command as SuperUserCommand


class Command(SuperUserCommand):

    def handle(self, *args, **options):
        options[self.UserModel.USERNAME_FIELD] = uuid.uuid4()
        super(Command, self).handle(*args, **options)
