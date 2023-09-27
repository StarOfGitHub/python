import logging

from django.core.management.base import BaseCommand

from r3sourcer.apps.sms_interface.models import SMSMessage


logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        self.stdout.write("Fake messages ({}) have been cleared!".format(
            SMSMessage.objects.filter(is_fake=True).delete()[0])
        )
