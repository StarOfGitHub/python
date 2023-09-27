import datetime

import binascii
import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.utils import timezone
from freezegun import freeze_time
from unittest.mock import patch

from r3sourcer.apps.core.models import WorkflowNode, Workflow

from r3sourcer.apps.candidate import models as candidate_models
from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.skills.models import Skill, SkillName
from r3sourcer.apps.pricing import models as pricing_models
from r3sourcer.apps.sms_interface import models as sms_models
from r3sourcer.helpers.datetimes import utc_now, utc_tomorrow


@pytest.fixture
def user(db):
    return core_models.User.objects.create_user(
        email='test@test.tt', phone_mobile='+12345678901',
        password='test1234'
    )


@pytest.fixture
def user_another(db):
    return core_models.User.objects.create_user(
        email='test2@test.tt', phone_mobile='+12345678902',
        password='test2345'
    )


@pytest.fixture
def user_primary(db):
    return core_models.User.objects.create_user(
        email='test3@test.tt', phone_mobile='+12345678903',
        password='test2345'
    )


@pytest.fixture
def contact_data():
    return dict(
        title='Mr.',
        first_name='John',
        last_name='Connor',
        email='test@test.tt',
        phone_mobile='+12345678901'
    )


@pytest.fixture
def contact_data_another():
    return dict(
        title='Ms.',
        first_name='Sarah',
        last_name='Connor',
        email='test2@test.tt',
        phone_mobile='+12345678902'
    )


@pytest.fixture
def contact(db, user, contact_data):
    contact = user.contact
    keys = ('title', 'first_name', 'last_name', 'email', 'phone_mobile')
    for key in keys:
        setattr(contact, key, contact_data[key])
    return contact


@pytest.fixture
def contact_another(db, user_another, contact_data_another):
    contact = user_another.contact
    keys = ('title', 'first_name', 'last_name', 'email', 'phone_mobile')
    for key in keys:
        setattr(contact, key, contact_data_another[key])
    return contact


@pytest.fixture
def contact_primary(db, user_primary):
    return user_primary.contact


@pytest.fixture
def candidate_contact(db, contact):
    candidate = candidate_models.CandidateContact.objects.create(
        contact=contact
    )
    hr_models.CandidateScore.objects.create(candidate_contact=candidate, skill_score=4, average_score=4)
    # content_type = ContentType.objects.get_for_model(candidate_models.CandidateContact)
    # w, _ = Workflow.objects.get_or_create(
    #     name='test',
    #     model=content_type
    # )
    # n, _ = WorkflowNode.objects.get_or_create(
    #     number=70,
    #     workflow=w,
    # )
    # core_models.WorkflowObject.objects.create(
    #     state=n,
    #     active=True,
    #     object_id=candidate.pk
    # )
    return candidate


@pytest.fixture
def candidate_contact_second(db, contact_another):
    candidate = candidate_models.CandidateContact.objects.create(
        contact=contact_another
    )
    hr_models.CandidateScore.objects.create(candidate_contact=candidate, skill_score=4, average_score=4)
    content_type = ContentType.objects.get_for_model(candidate_models.CandidateContact)
    w, _ = Workflow.objects.get_or_create(
        name='test',
        model = content_type
    )
    n, _ = WorkflowNode.objects.get_or_create(
        number=70,
        workflow=w,
    )
    core_models.WorkflowObject.objects.create(
        state=n,
        active=True,
        object_id=candidate.pk
    )
    return candidate


@pytest.fixture
def company_contact(db, contact):
    return core_models.CompanyContact.objects.create(
        contact=contact,
        pin_code='1234'
    )


@pytest.fixture
def company_contact_another(db, contact_another):
    return core_models.CompanyContact.objects.create(
        contact=contact_another
    )


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
def regular_company(db):
    return core_models.Company.objects.create(
        name='Regular',
        business_id='321',
        registered_for_gst=True,
        type=core_models.Company.COMPANY_TYPES.regular
    )


@pytest.fixture
def second_regular_company(db):
    return core_models.Company.objects.create(
        name='Second Regular',
        business_id='4321',
        registered_for_gst=True,
        type=core_models.Company.COMPANY_TYPES.regular
    )


@pytest.fixture
def industry(db):
    return pricing_models.Industry.objects.create(type='test')


@pytest.fixture
def jobsite(db, master_company, company_contact, industry, address, regular_company):
    return hr_models.Jobsite.objects.create(
        industry=industry,
        master_company=master_company,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=7),
        primary_contact=company_contact,
        address=address,
        regular_company=regular_company,
    )

@pytest.fixture
def another_jobsite(db, master_company, company_contact, industry, address, second_regular_company):
    return hr_models.Jobsite.objects.create(
        industry=industry,
        master_company=master_company,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=7),
        primary_contact=company_contact,
        address=address,
        regular_company=second_regular_company,
    )


@pytest.fixture
@patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address',
       return_value=(42, 42))
def address(db):
    country, _ = core_models.Country.objects.get_or_create(name='Australia', code2='AU')
    state = core_models.Region.objects.create(name='test', country=country)
    city = core_models.City.objects.create(name='city', country=country)
    return core_models.Address.objects.create(
        street_address="test street",
        postal_code="123456",
        city=city,
        state=state
    )


@pytest.fixture
def skill_name(db, industry):
    return SkillName.objects.create(name="Driver", industry=industry)


@pytest.fixture
def skill(db, skill_name, master_company):
    return Skill.objects.create(
        name=skill_name,
        carrier_list_reserve=2,
        short_name="Drv",
        active=False,
        company=master_company
    )


@pytest.fixture
def job(db, master_company, regular_company, jobsite, skill):
    return hr_models.Job.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
        jobsite=jobsite,
        position=skill,
        published=True,
        workers=2
    )


@pytest.fixture
def shift_date(db, job):
    return hr_models.ShiftDate.objects.create(
        job=job,
        shift_date=datetime.date(2017, 1, 2)
    )


@pytest.fixture
def shift(db, shift_date):
    return hr_models.Shift.objects.create(
        date=shift_date,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def shift_date_second(db, job):
    return hr_models.ShiftDate.objects.create(
        job=job,
        shift_date=datetime.date(2017, 1, 3)
    )


@pytest.fixture
def shift_second(db, shift_date_second):
    return hr_models.Shift.objects.create(
        date=shift_date_second,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def job_offer(mock_check, db, shift, candidate_contact):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift,
        candidate_contact=candidate_contact
    )

    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)

    return job_offer


@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def job_offer_second(mock_check, db, shift_second, candidate_contact_second):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_second,
        candidate_contact=candidate_contact_second
    )

    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)

    return job_offer


@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def accepted_jo(mock_check, db, shift, candidate_contact):
    return hr_models.JobOffer.objects.create(
        shift=shift,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.accepted
    )


@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def cancelled_jo(mock_check, db, shift, candidate_contact):
    return hr_models.JobOffer.objects.create(
        shift=shift,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.cancelled
    )


@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def job_offer_yesterday(mock_check, db, job, candidate_contact):
    shift_date_yesterday = hr_models.ShiftDate.objects.create(
        job=job,
        shift_date=datetime.date(2017, 1, 1)
    )
    shift_yesterday = hr_models.Shift.objects.create(
        date=shift_date_yesterday,
        time=datetime.time(hour=8, minute=30)
    )

    return hr_models.JobOffer.objects.create(
        shift=shift_yesterday,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.accepted
    )


@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def job_offer_tomorrow(mock_check, db, job, candidate_contact):
    shift_date_tomorrow = hr_models.ShiftDate.objects.create(
        job=job,
        shift_date=datetime.date(2017, 1, 3)
    )
    shift_tomorrow = hr_models.Shift.objects.create(
        date=shift_date_tomorrow,
        time=datetime.time(hour=8, minute=30)
    )

    return hr_models.JobOffer.objects.create(
        shift=shift_tomorrow,
        candidate_contact=candidate_contact
    )


@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def job_offer_tomorrow_night(mock_check, db, job, candidate_contact):
    shift_date_tomorrow = hr_models.ShiftDate.objects.create(
        job=job,
        shift_date=datetime.date(2017, 1, 3)
    )
    shift_tomorrow = hr_models.Shift.objects.create(
        date=shift_date_tomorrow,
        time=datetime.time(hour=19, minute=0)
    )

    return hr_models.JobOffer.objects.create(
        shift=shift_tomorrow,
        candidate_contact=candidate_contact
    )


@pytest.fixture
@freeze_time(datetime.datetime(2017, 1, 1))
def timesheet(db, job_offer, company_contact):
    return hr_models.TimeSheet.objects.create(
        job_offer=job_offer,
        supervisor=company_contact
    )


@pytest.fixture
@freeze_time(datetime.datetime(2017, 1, 1))
def timesheet_approved(db, job_offer, company_contact):
    return hr_models.TimeSheet.objects.create(
        job_offer=job_offer,
        supervisor=company_contact,
        supervisor_approved_at=timezone.now(),
        candidate_submitted_at=timezone.now(),
        going_to_work_confirmation=True,
    )


@pytest.fixture
@freeze_time(datetime.datetime(2017, 1, 2))
def timesheet_tomorrow(db, job_offer, company_contact):
    return hr_models.TimeSheet.objects.create(
        job_offer=job_offer,
        supervisor=company_contact
    )


@pytest.fixture
def timesheet_issue(db, timesheet, company_contact):
    return hr_models.TimeSheetIssue.objects.create(
        time_sheet=timesheet,
        subject='subject',
        description='description',
        supervisor=company_contact
    )


@pytest.fixture
@freeze_time(datetime.datetime(2017, 1, 2))
def timesheet_with_break(db, job_offer, company_contact):
    return hr_models.TimeSheet.objects.create(
        job_offer=job_offer,
        supervisor=company_contact,
        shift_started_at=utc_now().replace(hour=8, minute=0),
        shift_ended_at=utc_now().replace(hour=8, minute=0) + datetime.timedelta(hours=8),
        break_started_at=utc_now().replace(hour=8, minute=0) + datetime.timedelta(hours=4),
        break_ended_at=utc_now().replace(hour=8, minute=0) + datetime.timedelta(hours=4, minutes=30),
    )


@pytest.fixture
@freeze_time(datetime.datetime(2017, 1, 1))
def carrier_list(db, candidate_contact, job_offer):
    return hr_models.CarrierList.objects.create(
        candidate_contact=candidate_contact,
        job_offer=job_offer,
        target_date=utc_tomorrow()
    )


@pytest.fixture
def black_list(master_company, candidate_contact):
    return hr_models.BlackList.objects.create(
        company=master_company,
        candidate_contact=candidate_contact
    )


@pytest.fixture
def favourite_list(company_contact, candidate_contact):
    return hr_models.FavouriteList.objects.create(
        company_contact=company_contact,
        candidate_contact=candidate_contact
    )


@pytest.fixture
def company_rel(db, master_company, regular_company, company_contact):
    return core_models.CompanyRel.objects.create(
        master_company=master_company,
        regular_company=regular_company,
        manager=company_contact
    )


@pytest.fixture
def company_contact_rel(db, regular_company, company_contact):
    return core_models.CompanyContactRelationship.objects.create(
        company=regular_company,
        company_contact=company_contact
    )


@pytest.fixture
def picture(faker):
    # See: http://stackoverflow.com/a/30290754
    sequence = binascii.unhexlify(
        'FFD8FFE000104A46494600010101004800480000FFDB004300FFFFFFFFFFFFFFFFFFF'
        'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF'
        'FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFC2000B080001000101011100FFC'
        '40014100100000000000000000000000000000000FFDA0008010100013F10')
    return ContentFile(bytes(sequence), faker.file_name(extension='jpg'))


@pytest.fixture
def price_list(db, master_company):
    return pricing_models.PriceList.objects.create(
        company=master_company,
        valid_from=timezone.datetime(2017, 1, 1, 12, 0)
    )


@pytest.fixture
def price_list_rate(db, price_list, skill):
    return pricing_models.PriceListRate.objects.create(
        price_list=price_list,
        skill=skill,
        hourly_rate=10,
    )


@pytest.fixture
def invoice_rule_master_company(db, master_company):
    return core_models.InvoiceRule.objects.create(
        company=master_company,
    )


@pytest.fixture
def invoice_rule_company(db, regular_company):
    return core_models.InvoiceRule.objects.create(
        company=regular_company,
    )


@pytest.fixture
def payslip_rule_master_company(db, master_company):
    return hr_models.PayslipRule.objects.create(
        company=master_company,
    )


@pytest.fixture
def payslip_rule_company(db, regular_company):
    return hr_models.PayslipRule.objects.create(
        company=regular_company,
    )


@pytest.fixture
def rate_coefficient(db, industry):
    coeff = pricing_models.RateCoefficient.objects.create(name='test', industry=industry)
    pricing_models.RateCoefficientModifier.objects.create(
        type=pricing_models.RateCoefficientModifier.TYPE_CHOICES.company,
        rate_coefficient=coeff,
        multiplier=2,
    )

    return coeff


@pytest.fixture
def allowance_rate_coefficient(db, industry):
    coeff = pricing_models.RateCoefficient.objects.create(name='test', industry=industry)
    pricing_models.RateCoefficientModifier.objects.create(
        type=pricing_models.RateCoefficientModifier.TYPE_CHOICES.company,
        rate_coefficient=coeff,
        fixed_override=10,
    )
    rule = pricing_models.AllowanceWorkRule.objects.create(allowance_description='Travel')
    pricing_models.DynamicCoefficientRule.objects.create(
        rate_coefficient=coeff,
        rule=rule,
    )

    return coeff


@pytest.fixture
@freeze_time(datetime.datetime(2017, 1, 1))
def invoice(db, master_company, regular_company):
    return core_models.Invoice.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
    )


@pytest.fixture
def vat():
    country, _ = core_models.Country.objects.get_or_create(name='Australia', code2='AU')
    return core_models.VAT.objects.get_or_create(
        country=country,
        name='GST',
        defaults={
            'rate': 0.1,
            'start_date': datetime.date(2017, 1, 1),
        }
    )[0]


@pytest.fixture
def fake_sms(contact):
    return sms_models.SMSMessage.objects.create(
        from_number=contact.phone_mobile,
        to_number='+12345678901',
        text='fake',
        sid='FAKE_test',
    )


@pytest.fixture
def jobtag1(job):
    tag1 = core_models.Tag.objects.create(name='Tag1')
    return hr_models.JobTag.objects.create(
        job=job,
        tag=tag1
    )


@pytest.fixture
def jobtag2(job):
    tag2 = core_models.Tag.objects.create(name='Tag2')
    return hr_models.JobTag.objects.create(
        job=job,
        tag=tag2
    )

# fixtures for job fulfillment tests
@pytest.fixture
def skill_name1(db, industry):
    return SkillName.objects.create(name="Skill1", industry=industry)


@pytest.fixture
def skill1(db, skill_name1, master_company):
    return Skill.objects.create(
        name=skill_name1,
        carrier_list_reserve=2,
        short_name="Skl1",
        active=False,
        company=master_company
    )


@pytest.fixture
def skill_name2(db, industry):
    return SkillName.objects.create(name="Skill2", industry=industry)


@pytest.fixture
def skill2(db, skill_name2, master_company):
    return Skill.objects.create(
        name=skill_name2,
        carrier_list_reserve=2,
        short_name="Skl2",
        active=False,
        company=master_company
    )


@pytest.fixture
def skill_name3(db, industry):
    return SkillName.objects.create(name="Skill3", industry=industry)


@pytest.fixture
def skill3(db, skill_name3, master_company):
    return Skill.objects.create(
        name=skill_name3,
        carrier_list_reserve=2,
        short_name="Skl3",
        active=False,
        company=master_company
    )


@pytest.fixture
def job_with_filled_not_accepted_shifts(master_company, regular_company, jobsite, skill1):
    return hr_models.Job.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
        jobsite=jobsite,
        position=skill1,
        published=True,
        workers=1
    )


@pytest.fixture
def shift_date_filled_not_accepted(job_with_filled_not_accepted_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_filled_not_accepted_shifts,
        shift_date=datetime.date(2017, 1, 2)
    )


@pytest.fixture
def shift_filled_not_accepted(shift_date_filled_not_accepted):
    return hr_models.Shift.objects.create(
        date=shift_date_filled_not_accepted,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def job_offer_undefined(candidate_contact, shift_filled_not_accepted):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_filled_not_accepted,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.undefined
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer


@pytest.fixture
def shift_date_filled_accepted(job_with_filled_not_accepted_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_filled_not_accepted_shifts,
        shift_date=datetime.date(2017, 1, 3)
    )


@pytest.fixture
def shift_filled_accepted(shift_date_filled_accepted):
    return hr_models.Shift.objects.create(
        date=shift_date_filled_accepted,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def job_offer_accepted(candidate_contact_second, shift_filled_not_accepted):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_filled_not_accepted,
        candidate_contact=candidate_contact_second,
        status=hr_models.JobOffer.STATUS_CHOICES.accepted
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer


#### filled_and_declined
@pytest.fixture
def shift_date_filled_notaccepted(job_with_filled_and_declined_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_filled_and_declined_shifts,
        shift_date=datetime.date(2017, 1, 4)
    )


@pytest.fixture
def shift_filled_notaccepted(shift_date_filled_notaccepted):
    return hr_models.Shift.objects.create(
        date=shift_date_filled_notaccepted,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def job_with_filled_and_declined_shifts(master_company, regular_company, candidate_contact, jobsite, skill2):
    return hr_models.Job.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
        jobsite=jobsite,
        position=skill2,
        published=True,
        workers=1
    )


@pytest.fixture
def job_offer_first_declined(candidate_contact, shift_filled_notaccepted):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_filled_notaccepted,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.cancelled
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer


@pytest.fixture
def job_offer_second_declined(candidate_contact, shift_filled_notaccepted):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_filled_notaccepted,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.cancelled
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer


@pytest.fixture
def job_with_accepted_shifts(master_company, regular_company, jobsite, skill):
    return hr_models.Job.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
        jobsite=jobsite,
        position=skill,
        published=True,
        workers=1
    )


@pytest.fixture
def shift_date_accepted(job_with_accepted_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_accepted_shifts,
        shift_date=datetime.date(2017, 1, 3)
    )


@pytest.fixture
def shift_accepted(shift_date_accepted):
    return hr_models.Shift.objects.create(
        date=shift_date_accepted,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def job_offer_yetanother_accepted(candidate_contact, shift_accepted):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_accepted,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.accepted
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer


@pytest.fixture
def job_with_declined_shifts(master_company, regular_company, jobsite, skill):
    return hr_models.Job.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
        jobsite=jobsite,
        position=skill,
        published=True,
        workers=1
    )


@pytest.fixture
def shift_date_declined(job_with_declined_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_declined_shifts,
        shift_date=datetime.date(2017, 1, 3)
    )


@pytest.fixture
def shift_declined(shift_date_declined):
    return hr_models.Shift.objects.create(
        date=shift_date_declined,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def job_offer_declined(candidate_contact, shift_declined):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_declined,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.cancelled
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer

# for TestJobViewset.test_fillin_partially_available()

@pytest.fixture
def job_with_four_shifts(master_company, regular_company, jobsite, skill):
    return hr_models.Job.objects.create(
        provider_company=master_company,
        customer_company=regular_company,
        jobsite=jobsite,
        position=skill,
        published=True,
        workers=1
    )


@pytest.fixture
def another_job_with_one_shift(master_company, second_regular_company, another_jobsite, skill):
    return hr_models.Job.objects.create(
        provider_company=master_company,
        customer_company=second_regular_company,
        jobsite=another_jobsite,
        position=skill,
        published=True,
        workers=1
    )


@pytest.fixture
def shift_date_first(job_with_four_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_four_shifts,
        shift_date=datetime.date(2017, 1, 1)
    )


@pytest.fixture
def shift_first(shift_date_first):
    return hr_models.Shift.objects.create(
        date=shift_date_first,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def shift_date_second(job_with_four_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_four_shifts,
        shift_date=datetime.date(2017, 1, 2)
    )


@pytest.fixture
def shift_second(shift_date_second):
    return hr_models.Shift.objects.create(
        date=shift_date_second,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def shift_date_third(job_with_four_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_four_shifts,
        shift_date=datetime.date(2017, 1, 3)
    )


@pytest.fixture
def shift_third(shift_date_third):
    return hr_models.Shift.objects.create(
        date=shift_date_third,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def shift_date_fourth(job_with_four_shifts):
    return hr_models.ShiftDate.objects.create(
        job=job_with_four_shifts,
        shift_date=datetime.date(2017, 1, 4)
    )


@pytest.fixture
def shift_fourth(shift_date_fourth):
    return hr_models.Shift.objects.create(
        date=shift_date_fourth,
        time=datetime.time(hour=8, minute=30)
    )


@pytest.fixture
def shift_date_fifth(another_job_with_one_shift):
    return hr_models.ShiftDate.objects.create(
        job=another_job_with_one_shift,
        shift_date=datetime.date(2017, 1, 4)
    )


@pytest.fixture
def shift_fifth(shift_date_fifth):
    return hr_models.Shift.objects.create(
        date=shift_date_fifth,
        time=datetime.time(hour=8, minute=30)
    )

@pytest.fixture
def skill_rel(skill, candidate_contact):
    return candidate_models.SkillRel.objects.create(
        skill=skill,
        candidate_contact=candidate_contact,
        score=4,
    )

@pytest.fixture
def skill_rel_second(skill, candidate_contact_second):
    return candidate_models.SkillRel.objects.create(
        skill=skill,
        candidate_contact=candidate_contact_second,
        score=4,
    )

@pytest.fixture
def candidate_rel(master_company, candidate_contact):
    return candidate_models.CandidateRel.objects.create(
        master_company=master_company,
        candidate_contact=candidate_contact,
        active=True,
    )

@pytest.fixture
def candidate_rel_second(master_company, candidate_contact_second):
    return candidate_models.CandidateRel.objects.create(
        master_company=master_company,
        candidate_contact=candidate_contact_second,
        active=True,
    )


@pytest.fixture
def job_offer_for_candidate(candidate_contact, shift_first):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_first,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.accepted
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer


@pytest.fixture
def job_offer_for_candidate_fifth_shift(candidate_contact, shift_fifth):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift_fifth,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.accepted
    )
    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)
    return job_offer
