import pytest

from r3sourcer.apps.sms_interface.helpers import get_sms, get_phone_number
from r3sourcer.apps.sms_interface.models import PhoneNumber


class TestHelpers:

    def test_get_sms(self, contact, twilio_account, phone_number):
        sms_message = get_sms(
            from_number=phone_number.phone_number,
            to_number=contact.phone_mobile,
            text='test message',
        )

        assert sms_message is not None

    def test_get_sms_without_to_number_fails(self):
        with pytest.raises(AssertionError):
            get_sms(
                from_number='+12345678901',
                to_number=None,
                text='test message',
            )

    def test_get_sms_without_text_fails(self, contact):
        with pytest.raises(AssertionError):
            get_sms(
                from_number='+12345678901',
                to_number=contact.phone_mobile,
                text=None,
            )

    def test_sms_text_reply_timeout(self, contact, twilio_account, phone_number):
        sms_message = get_sms(
            from_number=phone_number.phone_number,
            to_number=contact.phone_mobile,
            text='test message',
            reply_timeout=1,
        )

        assert sms_message.reply_timeout == 1

    def test_sms_text_delivery_timeout(self, contact, twilio_account, phone_number):
        sms_message = get_sms(
            from_number=phone_number.phone_number,
            to_number=contact.phone_mobile,
            text='test message',
            delivery_timeout=1,
        )

        assert sms_message.delivery_timeout == 1

    def test_get_phone_number(self, company):
        number = PhoneNumber.objects.create(
            company=company,
            phone_number='+12345678901',
            sid='test'
        )

        phone_number = get_phone_number(company)

        assert number == phone_number

    def test_get_phone_number_does_not_exist(self, company):
        PhoneNumber.objects.all().delete()
        phone_number = get_phone_number(company)

        assert phone_number is None

    def test_get_phone_number_company_none(self, company):
        number = PhoneNumber.objects.create(
            company=company,
            phone_number='+12345678901',
            sid='test'
        )
        phone_number = get_phone_number()

        assert number == phone_number
