import binascii
import copy

import pytest
import pytz
from django.core.files.base import ContentFile
from django.utils import timezone
from r3sourcer.apps.core.models import Company, CompanyContact, Contact, User

from r3sourcer.apps.activity.models import Activity, ActivityDate, ActivityRepeat, ActivityTemplate


@pytest.fixture
def activity_template(db):
    return ActivityTemplate.objects.create(
        name='test',
        type=ActivityTemplate.TYPE_CHOICES.ACTIVITY,
        subject_template='text content',
        message_text_template='html content'
    )


@pytest.fixture
def primary_activity(db, activity_template, primary_user):
    return Activity.objects.create(
        template=activity_template,
        contact=primary_user.contact,
        starts_at=timezone.datetime(2017, 1, 1, 12, 0).replace(tzinfo=pytz.UTC),
        ends_at=timezone.datetime(2017, 1, 5, 12, 0).replace(tzinfo=pytz.UTC)
    )


@pytest.fixture
def secondary_activity(db, activity_template, secondary_user):
    return Activity.objects.create(
        template=activity_template,
        contact=secondary_user.contact,
        starts_at=timezone.datetime(2017, 1, 1, 12, 0).replace(tzinfo=pytz.UTC),
        ends_at=timezone.datetime(2017, 1, 5, 12, 0).replace(tzinfo=pytz.UTC)
    )


@pytest.fixture
def activity_repeater(db, faker, primary_activity):
    return ActivityRepeat.objects.create(
        repeat_type=ActivityRepeat.REPEAT_CHOICES.FIXED,
        activity=primary_activity
    )


@pytest.fixture
def repeater_interval1(db, primary_activity):
    return ActivityRepeat.objects.create(
        repeat_type=ActivityRepeat.REPEAT_CHOICES.INTERVAL,
        base_type=ActivityRepeat.PERIODIC_TYPE.secondly,
        every=60,
        activity=primary_activity
    )


@pytest.fixture
def repeater_interval2(db, primary_activity):
    return ActivityRepeat.objects.create(
        repeat_type=ActivityRepeat.REPEAT_CHOICES.SCHEDULE,
        base_type=ActivityRepeat.PERIODIC_TYPE.minutely,
        every=60,
        activity=primary_activity
    )


@pytest.fixture
def repeater_schedule(db, primary_activity):
    return ActivityRepeat.objects.create(
        repeat_type=ActivityRepeat.REPEAT_CHOICES.SCHEDULE,
        base_type=ActivityRepeat.PERIODIC_TYPE.daily,
        hour=10,
        minute=10,
        activity=primary_activity
    )


@pytest.fixture
def activity_date(db, faker, activity_repeater):
    return ActivityDate.objects.create(
        activity_repeat=activity_repeater,
        occur_at=timezone.datetime(2017, 1, 2, 12, 0).replace(tzinfo=pytz.UTC)
    )


@pytest.fixture
def primary_user(db, faker):
    return User.objects.create_user(
        password=faker.password(),
        email='primary@test.tt', phone_mobile='+12345678921'
    )


@pytest.fixture
def secondary_user(db, faker):
    return User.objects.create_user(
        password=faker.password(),
        email='secondary@test.tt', phone_mobile='+12345678922'
    )


@pytest.fixture
def manager(db, manager_data):
    return Contact.objects.create(**manager_data)


@pytest.fixture
def secondary_contact(db, secondary_contact_data):
    return Contact.objects.create(**secondary_contact_data)


@pytest.fixture
def primary_contact(db, manager):
    return CompanyContact.objects.create(contact=manager)


@pytest.fixture
def company(db, primary_contact):
    return Company.objects.create(
        name='Company',
        business_id='111',
        registered_for_gst=True,
        primary_contact=primary_contact,
        type=Company.COMPANY_TYPES.master,
    )


@pytest.fixture
def manager_data(faker, picture):
    return dict(
        title='Mr.',
        # user=primary_user,
        first_name=faker.first_name(),
        last_name=faker.last_name(),
        email=faker.email(),
        phone_mobile='+41789272696',
        gender=Contact._meta.get_field('gender').choices[0][0],
        marital_status=Contact.MARITAL_STATUS_CHOICES.Single,
        birthday=faker.date_time_this_year().date(),
        spouse_name=faker.name(),
        children=0,
        is_available=faker.boolean(),
        picture=copy.deepcopy(picture),
    )


@pytest.fixture
def secondary_contact_data(faker, picture):
    return dict(
        title='Mr.',
        first_name=faker.first_name(),
        last_name=faker.last_name(),
        email=faker.email(),
        phone_mobile='+41789272697',
        gender=Contact._meta.get_field('gender').choices[0][0],
        marital_status=Contact.MARITAL_STATUS_CHOICES.Single,
        birthday=faker.date_time_this_year().date(),
        spouse_name=faker.name(),
        children=0,
        is_available=faker.boolean(),
        picture=copy.deepcopy(picture),
    )


@pytest.fixture
def picture(faker):
    # See: http://stackoverflow.com/a/30290754
    sequence = binascii.unhexlify(
        'FFD8FFE000104A46494600010101004800480000FFDB004300FFFFFFFFFFFFFFFFFFFF'
        'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF'
        'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFC2000B080001000101011100FFC400'
        '14100100000000000000000000000000000000FFDA0008010100013F10')
    return ContentFile(bytes(sequence), faker.file_name(extension='jpg'))


@pytest.fixture
def related_activity(db, activity_template, primary_user):
    return Activity.objects.create(
        template=activity_template,
        contact=primary_user.contact,
        starts_at=timezone.datetime(2017, 1, 1, 12, 0).replace(tzinfo=pytz.UTC),
        ends_at=timezone.datetime(2017, 1, 5, 12, 0).replace(tzinfo=pytz.UTC),
        entity_object_id=primary_user.id,
        entity_object_name=primary_user.__class__.__name__
    )
