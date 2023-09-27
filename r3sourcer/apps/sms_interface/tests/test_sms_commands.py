import pytest

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.six import StringIO

from r3sourcer.apps.sms_interface.models import SMSMessage, PhoneNumber


@pytest.mark.django_db
class TestFakeSMSCommands:

    @pytest.fixture
    def out(self):
        return StringIO()

    @pytest.fixture
    def fake_sms(self, contact):
        return SMSMessage.objects.create(
            from_number=contact.phone_mobile,
            to_number='+12345678903',
            text='fake message',
            is_fake=True,
            sid='test_sid'
        )

    @pytest.fixture
    def phone_number(self, company):
        return PhoneNumber.objects.create(
            company=company,
            phone_number='+12345678901',
            sid='test'
        )

    def test_clear_fake_sms(self, fake_sms):
        call_command('clear_fake_sms')

        assert not SMSMessage.objects.all().exists()

    def test_create_fake_sms(self, contact, phone_number, out):
        call_command('fake_sms', '--noinput', from_number='+12345678901',
                     text='test', stdout=out)

        sms_message = SMSMessage.objects.filter(from_number='+12345678901').first()

        assert sms_message is not None
        assert sms_message.to_number == phone_number.phone_number

    def test_create_fake_sms_with_default_to_number(self, contact,
                                                    phone_number, out):
        call_command('fake_sms', '--noinput', text='test',
                     to_number=phone_number.phone_number,
                     from_number='+12345678901', stdout=out)

        sms_message = SMSMessage.objects.filter(
            from_number='+12345678901'
        ).first()

        assert sms_message is not None
        assert sms_message.text == 'test'

    def test_create_fake_sms_without_from_number_error(self, contact,
                                                       phone_number, out):
        with pytest.raises(CommandError):
            call_command('fake_sms', '--noinput', text='test',
                         stdout=out)
