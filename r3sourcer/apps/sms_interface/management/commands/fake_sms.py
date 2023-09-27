import logging
from argparse import RawTextHelpFormatter

from django.core.management.base import BaseCommand, CommandError

from r3sourcer.apps.core.models import Contact
from r3sourcer.apps.sms_interface.helpers import get_phone_number
from r3sourcer.apps.sms_interface.models import SMSMessage
from r3sourcer.helpers.datetimes import utc_now

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def create_parser(self, *args, **kwargs):
        parser = super(Command, self).create_parser(*args, **kwargs)
        parser.formatter_class = RawTextHelpFormatter
        return parser

    def add_arguments(self, parser):
        parser.add_argument(
            '--from_number',
            dest='from_number', default=None,
            help='Specifies the sender number.',
        )
        parser.add_argument(
            '--text',
            dest='text', default=None,
            help='Specifies the message to send.',
        )
        parser.add_argument(
            '--noinput', '--no-input',
            action='store_false', dest='interactive', default=True,
            help=(
                'Tells Django to NOT prompt the user for input of any kind. '
                'You must use --text with --noinput, along with an option for '
                'any other required field.'
            ),
        )
        parser.add_argument(
            '--to_number',
            dest='to_number', default=None,
            help='Specifies the receiver number.',
        )

    def handle(self, *args, **options):
        self.stdout.write("Manually sending fake message")

        from_number = options['from_number']
        text = options['text']

        if options['interactive']:
            from_number = input("Enter sender number: ")  # pragma: no cover

        if not from_number:
            raise CommandError("Sender number cannot be empty")

        if not Contact.objects.filter(phone_mobile=from_number).exists():
            raise CommandError("Contact doesn't exists with `{}` number".format(from_number))

        contact = Contact.objects.get(phone_mobile=from_number)

        to_number = options['to_number']
        if to_number is None:
            phone_number = get_phone_number()
            to_number = phone_number and phone_number.phone_number

        self.stdout.write("Using phone number: {}".format(to_number))
        self.stdout.write("From: {}".format(contact))

        if options['interactive']:
            text = input("Enter text message: ")  # pragma: no cover

        sent_at = utc_now()
        self.stdout.write("Sent fake sms:")
        self.stdout.write("Numbers: {} => {}".format(from_number, to_number))
        self.stdout.write("Sent at: {}".format(sent_at))
        self.stdout.write("Text: {}".format(text))

        sms = SMSMessage(
                type=SMSMessage.TYPE_CHOICES.RECEIVED,
                is_fake=True,
                text=text,
                created_at=sent_at,
                sent_at=sent_at,
                from_number=from_number,
                to_number=to_number,
                status=SMSMessage.STATUS_CHOICES.RECEIVED
        )
        sms.sid = 'FAKE_{}'.format(sms.id)
        sms.save()
        self.stdout.write("Fake SMS message sent: {}".format(sms.id))
