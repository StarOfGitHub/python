import datetime

import pytest

from unittest.mock import patch

from r3sourcer.apps.core.models import (
    User, Company, CompanyContact, CompanyContactRelationship, Country, Region, City, Address,
    CompanyAddress, Language, VAT,
)
from r3sourcer.apps.email_interface.models import DefaultEmailTemplate
from r3sourcer.apps.hr.models import Shift, ShiftDate, Job, Jobsite
from r3sourcer.apps.skills.models import Skill, SkillName
from r3sourcer.apps.pricing.models import Industry
from r3sourcer.apps.billing.models import Payment, Subscription, SubscriptionType, SMSBalanceLimits


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
        business_id='123',
        registered_for_gst=True,
        type=Company.COMPANY_TYPES.master,
        primary_contact=primary_contact
    )


@pytest.fixture
def relationship(db, company, primary_contact):
    return CompanyContactRelationship.objects.create(
        company_contact=primary_contact,
        company=company,
    )


@pytest.fixture
def master_company(db, primary_contact):
    return Company.objects.create(
        name='Master',
        business_id='123',
        registered_for_gst=True,
        type=Company.COMPANY_TYPES.master,
        timesheet_approval_scheme=Company.TIMESHEET_APPROVAL_SCHEME.PIN,
        primary_contact=primary_contact
    )


@pytest.fixture
def regular_company(db):
    return Company.objects.create(
        name='Regular',
        business_id='321',
        registered_for_gst=True,
        type=Company.COMPANY_TYPES.regular
    )


@pytest.fixture
def industry(db):
    return Industry.objects.create(type='test')


@pytest.fixture
def skill_name(db, industry):
    return SkillName.objects.create(name="Driver", industry=industry)


@pytest.fixture
def skill(db, skill_name, company):
    return Skill.objects.create(
        name=skill_name,
        carrier_list_reserve=2,
        short_name="Drv",
        active=False,
        company=company
    )


@pytest.fixture
def company_contact(db, contact):
    return CompanyContact.objects.create(
        contact=contact,
        pin_code='1234'
    )


@pytest.fixture
def country(db):
    country, _ = Country.objects.get_or_create(name='Australia', code2='AU')
    return country

@pytest.fixture
@patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
def address(db, country):
    state = Region.objects.create(name='test', country=country)
    city = City.objects.create(name='city', country=country)
    return Address.objects.create(
        street_address="test street",
        postal_code="123456",
        city=city,
        state=state
    )


@pytest.fixture
def company_address(db, address, company):
    return CompanyAddress.objects.create(
        company=company,
        address=address,
        hq=True
    )


@pytest.fixture
def jobsite(db, master_company, company_contact, industry, address, regular_company):
    return Jobsite.objects.create(
        industry=industry,
        master_company=master_company,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=7),
        primary_contact=company_contact,
        address=address,
        regular_company=regular_company,
    )


@pytest.fixture
def job(db, master_company, regular_company, jobsite, skill):
    return Job.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
        jobsite=jobsite,
        position=skill,
        published=True
    )


@pytest.fixture
def shift_date(db, job):
    return ShiftDate.objects.create(
        job=job,
        shift_date=datetime.date.today()
    )


@pytest.fixture
def shift(db, shift_date):
    return Shift.objects.create(
        date=shift_date,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def payment(db, company):
    return Payment.objects.create(
        company=company,
        type=Payment.PAYMENT_TYPES.sms,
        amount=100,
        status='done',
        stripe_id='stripeid'
    )


@pytest.fixture
def subscription_type_monthly(db):
    return SubscriptionType.objects.create(
        type='monthly',
        step_change_val=7,
        employess_total_num=10,
        max_employess_num=1005,
        start_range=5,
        start_range_price_monthly=10,
    )


@pytest.fixture
def subscription_type_annual(db):
    return SubscriptionType.objects.create(
        type='annual',
        step_change_val=7,
        employess_total_num=10,
        max_employess_num=1005,
        start_range=5,
        start_range_price_annual=10,
    )


@pytest.fixture
def subscription(db, company, subscription_type_monthly):
    return Subscription.objects.create(
        company=company,
        name='Subscription',
        subscription_type=subscription_type_monthly,
        price=100,
        worker_count=10,
        active=True,
        status='active',
        subscription_id='sub_J5Za0mDguqlu5C'
    )


@pytest.fixture
def company_contact_rel(db, primary_contact, company):
    return CompanyContactRelationship.objects.create(
        company_contact=primary_contact,
        company=company
    )


@pytest.fixture
def canceled_subscription(db, company, subscription_type_monthly):
    return Subscription.objects.create(
        company=company,
        name='Subscription',
        subscription_type=subscription_type_monthly,
        price=100,
        worker_count=10,
        active=False,
        status='canceled',
        subscription_id='sub_J5Za0mDguqlu5C'
    )


@pytest.fixture
def language(db):
    language, _ = Language.objects.get_or_create(alpha_2="en")
    return language


@pytest.fixture
def low_balance_limit(db, language):
    template, _ = DefaultEmailTemplate.objects.get_or_create(slug="sms-balance-low", language=language)
    limit, created = SMSBalanceLimits.objects.get_or_create(name="Low", low_balance_limit=20, email_template=template)
    return limit


@pytest.fixture
def ran_out_balance_limit(db, language):
    template, _ = DefaultEmailTemplate.objects.get_or_create(slug="sms-balance-ran-out", language=language)
    limit, _ = SMSBalanceLimits.objects.get_or_create(name="Ran out", low_balance_limit=0, email_template=template)
    return limit


@pytest.fixture
def vat(db, country):
    vat, _ = VAT.objects.get_or_create(
        country=country,
        stripe_id='stripe_id',
        rate=0.1,
        start_date=datetime.date(2021, 1, 1)
    )
    return vat
