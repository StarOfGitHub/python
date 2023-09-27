import pytest

from django.utils import timezone

from r3sourcer.apps.core.models import User, Company, CompanyContact, Language
from r3sourcer.apps.candidate.models import CandidateContact

from r3sourcer.apps.sms_interface.models import SMSMessage, SMSTemplate
from r3sourcer.apps.twilio.models import TwilioAccount, TwilioCredential, TwilioPhoneNumber


@pytest.fixture
def user_1(db):
    return User.objects.create_user(
        email='candidate_contact@test.ee', phone_mobile='+12345678900',
        password='test1234'
    )

@pytest.fixture
def contact_1(db, user_1):
    return user_1.contact

@pytest.fixture
def candidate_contact(db, contact_1):
    return CandidateContact.objects.create(
        contact=contact_1
    )

@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='test@test.tt', phone_mobile='+12345678901',
        password='test1234'
    )


@pytest.fixture
def contact(db, user):
    return user.contact


@pytest.fixture
def primary_contact(db, contact):
    return CompanyContact.objects.create(contact=contact)


@pytest.fixture
def company(db, primary_contact):
    return Company.objects.create(
        name='Company',
        business_id='111',
        registered_for_gst=True,
        primary_contact=primary_contact,
        type=Company.COMPANY_TYPES.master,
        sms_enabled=True,
    )


@pytest.fixture
def fake_sms(contact):
    return SMSMessage(
        from_number=contact.phone_mobile,
        to_number='+12345678901',
        text='fake',
        sid='FAKE_test',
    )


@pytest.fixture
def sms_template(company):
    lang, _ = Language.objects.get_or_create(alpha_2='en', name='English')
    return SMSTemplate.objects.create(
        name='SMS Template',
        slug='sms-template',
        type=SMSTemplate.SMS,
        message_text_template='template',
        company=company,
        language=lang,
    )


@pytest.fixture
def twilio_credentials(db, company):
    return TwilioCredential.objects.create(
        company=company,
        sid='sid',
        auth_token='auth_token',
    )


@pytest.fixture
def twilio_account(db, twilio_credentials, phone_number):
    return TwilioAccount.objects.create(
        credential=twilio_credentials,
        sid='sid2',
        phone_numbers=[phone_number]
    )


@pytest.fixture
def phone_number(db, company):
    return TwilioPhoneNumber.objects.create(
        sid='sid',
        phone_number='+123456789',
        company=company
    )


@pytest.fixture
def admin(db):
    user = User.objects.create_user(
        email='test2@test.tt', phone_mobile='+12345679999',
        password='test1234', is_staff=True, is_superuser=True
    )
    user.is_staff = True
    user.is_superuser = True
    user.save()
    return user


@pytest.fixture
def sms_message(db, company):
    return SMSMessage.objects.create(
        text='sms text',
        from_number='+123456789',
        to_number='+123456789',
        check_delivered=True,
        sent_at=timezone.now(),
        type=SMSMessage.TYPE_CHOICES.SENT,
        company=company,
        segments=1
    )
