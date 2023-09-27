from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from r3sourcer.apps.candidate.models import CandidateContact, SkillRel
from r3sourcer.apps.core.models import Company, User
from r3sourcer.apps.hr.models import CarrierList, CandidateScore, JobOffer, Shift, ShiftDate, Job, Jobsite
from r3sourcer.apps.pricing.models import PriceList, Industry
from r3sourcer.apps.skills.models import Skill, SkillName


@pytest.fixture
def industry(db):
    return Industry.objects.create(type='test')


@pytest.fixture
def company(db):
    return Company.objects.create(
        name='Company',
        business_id='111',
        registered_for_gst=True,
        type=Company.COMPANY_TYPES.master,
    )


@pytest.fixture
def skill_name(db, industry):
    return SkillName.objects.create(name="Driver", industry=industry)


@pytest.fixture
def skill_name_plumber(db, industry):
    return SkillName.objects.create(name="Plumber", industry=industry)


@pytest.fixture
def skill_name_painter(db, industry):
    return SkillName.objects.create(name="Painter", industry=industry)


@pytest.fixture
def skill_name_carpenter(db, industry):
    return SkillName.objects.create(name="Carpenter", industry=industry)


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
def skill_plumber(db, skill_name_plumber, company):
    return Skill.objects.create(
        name=skill_name_plumber,
        carrier_list_reserve=2,
        short_name="Plmb",
        active=False,
        company=company
    )


@pytest.fixture
def skill_painter_active(db, skill_name_painter, company):
    return Skill.objects.create(
        name=skill_name_painter,
        carrier_list_reserve=2,
        short_name="Pnt",
        active=True,
        company=company
    )


@pytest.fixture
def skill_carpenter_no_reserve_active(db, skill_name_carpenter, company):
    return Skill.objects.create(
        name=skill_name_carpenter,
        carrier_list_reserve=0,
        short_name="Crt",
        active=True,
        company=company
    )


@pytest.fixture
def price_list(db, company):
    return PriceList.objects.create(
        company=company,
        valid_from=date(2017, 1, 1)
    )


@pytest.fixture
def user_1(db):
    return User.objects.create_user(
        email='candidate_contact@test.ee', phone_mobile='+12345678901',
        password='test1234'
    )


@pytest.fixture
def user_2(db):
    return User.objects.create_user(
        email='candidate_contact2@test.ee', phone_mobile='+12345678902',
        password='test1234'
    )


@pytest.fixture
def user_3(db):
    return User.objects.create_user(
        email='candidate_contact3@test.ee', phone_mobile='+12345678903',
        password='test1234'
    )


@pytest.fixture
def user_4(db):
    return User.objects.create_user(
        email='candidate_contact4@test.ee', phone_mobile='+12345678904',
        password='test1234'
    )


@pytest.fixture
def contact_1(db, user_1):
    return user_1.contact


@pytest.fixture
def contact_2(db, user_2):
    return user_2.contact


@pytest.fixture
def contact_3(db, user_3):
    return user_3.contact


@pytest.fixture
def contact_4(db, user_4):
    return user_4.contact


@pytest.fixture
def candidate_contact_confirmed_in_carrier_list_without_jo(db, contact_1):
    return CandidateContact.objects.create(
        contact=contact_1
    )


@pytest.fixture
def candidate_contact_not_confirmed_in_carrier_list(db, contact_2):
    return CandidateContact.objects.create(
        contact=contact_2
    )


@pytest.fixture
def candidate_contact_confirmed_in_carrier_list_with_accepted_jo(db, contact_3):
    return CandidateContact.objects.create(
        contact=contact_3
    )


@pytest.fixture
def candidate_contact_confirmed_in_carrier_list_with_another_skill(db, contact_4):
    return CandidateContact.objects.create(
        contact=contact_4
    )


@pytest.fixture
def score_1(db, candidate_contact_confirmed_in_carrier_list_without_jo):
    return CandidateScore.objects.create(
        candidate_contact=candidate_contact_confirmed_in_carrier_list_without_jo
    )


@pytest.fixture
def score_2(db, candidate_contact_not_confirmed_in_carrier_list):
    return CandidateScore.objects.create(
        candidate_contact=candidate_contact_not_confirmed_in_carrier_list
    )


@pytest.fixture
def score_3(db, candidate_contact_confirmed_in_carrier_list_with_accepted_jo):
    return CandidateScore.objects.create(
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_accepted_jo
    )


@pytest.fixture
def score_4(db, candidate_contact_confirmed_in_carrier_list_with_another_skill):
    return CandidateScore.objects.create(
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_another_skill
    )


@pytest.fixture
def skill_rel_1(db, skill_painter_active, score_1, candidate_contact_confirmed_in_carrier_list_without_jo):
    return SkillRel.objects.create(
        skill=skill_painter_active,
        candidate_contact=candidate_contact_confirmed_in_carrier_list_without_jo
    )


@pytest.fixture
def skill_rel_2(db, skill_painter_active, score_2, candidate_contact_not_confirmed_in_carrier_list):
    return SkillRel.objects.create(
        skill=skill_painter_active,
        candidate_contact=candidate_contact_not_confirmed_in_carrier_list
    )


@pytest.fixture
def skill_rel_3(db, skill_painter_active, score_3, candidate_contact_confirmed_in_carrier_list_with_accepted_jo):
    return SkillRel.objects.create(
        skill=skill_painter_active,
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_accepted_jo
    )


@pytest.fixture
def skill_rel_4(db, skill_plumber, score_4, candidate_contact_confirmed_in_carrier_list_with_another_skill):
    return SkillRel.objects.create(
        skill=skill_plumber,
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_another_skill
    )


@pytest.fixture
@freeze_time('2021, 1, 2')
def carrier_list_1(db, skill_painter_active, candidate_contact_confirmed_in_carrier_list_without_jo):
    return CarrierList.objects.create(
        skill=skill_painter_active,
        confirmed_available=True,
        target_date=date.today(),
        candidate_contact=candidate_contact_confirmed_in_carrier_list_without_jo
    )


@pytest.fixture
@freeze_time('2021, 1, 2')
def carrier_list_2(db, skill_painter_active, candidate_contact_not_confirmed_in_carrier_list):
    return CarrierList.objects.create(
        skill=skill_painter_active,
        confirmed_available=False,
        target_date=date.today(),
        candidate_contact=candidate_contact_not_confirmed_in_carrier_list
    )


@pytest.fixture
@freeze_time('2021, 1, 2')
def carrier_list_3(db, skill_painter_active, candidate_contact_confirmed_in_carrier_list_with_accepted_jo):
    return CarrierList.objects.create(
        skill=skill_painter_active,
        confirmed_available=True,
        target_date=date.today(),
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_accepted_jo
    )


@pytest.fixture
@freeze_time('2021, 1, 2')
def carrier_list_4(db, skill_plumber, candidate_contact_confirmed_in_carrier_list_with_another_skill):
    return CarrierList.objects.create(
        skill=skill_plumber,
        confirmed_available=True,
        target_date=date.today(),
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_another_skill
    )


@pytest.fixture
@freeze_time('2021, 1, 2')
def carrier_list_5(db, skill_carpenter_no_reserve_active,
                   candidate_contact_confirmed_in_carrier_list_with_another_skill):
    return CarrierList.objects.create(
        skill=skill_carpenter_no_reserve_active,
        confirmed_available=True,
        target_date=date.today(),
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_another_skill
    )


@pytest.fixture
def jobsite(db, company, industry):
    return Jobsite.objects.create(
        industry=industry,
        master_company=company,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=7),
        regular_company=company,
    )


@pytest.fixture
@patch.object(Job, 'is_allowed', return_value=True)
def job(mocked_is_allowed, db, company, jobsite, skill_painter_active):
    return Job.objects.create(
        provider_company=company,
        customer_company=company,
        jobsite=jobsite,
        position=skill_painter_active,
        published=True,
        workers=2,
        fake_wf=True
    )


@pytest.fixture
@freeze_time('2021, 1, 2')
def shift_date(db, job):
    return ShiftDate.objects.create(
        job=job,
        shift_date=datetime.now().date()
    )


@pytest.fixture
def shift(db, shift_date):
    return Shift.objects.create(
        date=shift_date,
        time=time(hour=8, minute=30)
    )

@pytest.fixture
@patch.object(JobOffer, 'check_job_quota', return_value=True)
def job_offer_accepted(mock_check, db, shift, candidate_contact_confirmed_in_carrier_list_with_accepted_jo):
    return JobOffer.objects.create(
        shift=shift,
        candidate_contact=candidate_contact_confirmed_in_carrier_list_with_accepted_jo,
        status=JobOffer.STATUS_CHOICES.accepted
    )

