from datetime import datetime

import pytz
from django.utils import timezone

import freezegun
import pytest

from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.candidate import models as candidate_models
from r3sourcer.apps.email_interface import models


@pytest.fixture
def user(db):
    return core_models.User.objects.create_user(
        email='candidate_contact@test.ee', phone_mobile='+12345678904',
        password='test2345'
    )

@pytest.fixture
def contact_candidate(db, user):
    return user.contact

@pytest.fixture
def candidate_contact(db, contact_candidate):
    return candidate_models.CandidateContact.objects.create(
        contact=contact_candidate
    )

@pytest.fixture
def user_primary(db):
    return core_models.User.objects.create_user(
        email='test3@test.tt', phone_mobile='+12345678903',
        password='test2345'
    )

@pytest.fixture
def contact_primary(db, user_primary):
    return user_primary.contact

@pytest.fixture
def company_contact_primary(db, contact_primary):
    return core_models.CompanyContact.objects.create(
        contact=contact_primary
    )


@pytest.fixture
def master_company(db, company_contact_primary):
    return core_models.Company.objects.create(
        name='Master',
        business_id='123',
        registered_for_gst=True,
        type=core_models.Company.COMPANY_TYPES.master,
        timesheet_approval_scheme=core_models.Company.TIMESHEET_APPROVAL_SCHEME.PIN,
        primary_contact=company_contact_primary
    )

@pytest.fixture
def email_template(master_company):
    lang, _ = core_models.Language.objects.get_or_create(alpha_2='en', name='English')
    return models.EmailTemplate.objects.create(
        name='Email Template',
        type=models.EmailTemplate.EMAIL,
        slug="email-template",
        message_text_template='template',
        subject_template='subject',
        language=lang,
        company=master_company
    )


@pytest.fixture
@freezegun.freeze_time(datetime(2017, 1, 1))
def fake_email():
    now = datetime.now(pytz.utc)
    return models.EmailMessage.objects.create(
        state=models.EmailMessage.STATE_CHOICES.CREATED,
        sent_at=now,
        from_email='test@test.tt',
        subject='subject',
        created_at=now,
        to_addresses='test1@test.tt'
    )


@pytest.fixture
def fake_email_text_body(fake_email):
    return models.EmailBody.objects.create(
        content='test',
        message=fake_email
    )


@pytest.fixture
def fake_email_html_body(fake_email):
    return models.EmailBody.objects.create(
        content='test',
        message=fake_email,
        type=models.HTML_CONTENT_TYPE
    )


@pytest.fixture
def default_email_template():
    return models.DefaultEmailTemplate.objects.create(
        name="Test Email Template",
        slug="test-email-template",
        subject_template="Test subject",
        language_id="en",
        message_text_template="template"
    )
