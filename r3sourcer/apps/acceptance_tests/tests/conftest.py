import datetime
import pytest

from r3sourcer.apps.acceptance_tests import models
from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.pricing.models import Industry
from r3sourcer.apps.skills.models import Skill, SkillName


@pytest.fixture
def user(db):
    return core_models.User.objects.create_user(
        email='test@test.tt', phone_mobile='+12345678901',
        password='test1234'
    )


@pytest.fixture
def contact(db, user):
    return user.contact


@pytest.fixture
def primary_contact(db, contact):
    return core_models.CompanyContact.objects.create(contact=contact)


@pytest.fixture
def company(db, primary_contact):
    return core_models.Company.objects.create(
        name='Company',
        business_id='123',
        registered_for_gst=True,
        type=core_models.Company.COMPANY_TYPES.master,
        primary_contact=primary_contact
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
def acceptance_test(db):
    return models.AcceptanceTest.objects.create(
        test_name='test',
        valid_from=datetime.date(2017, 1, 1),
        valid_until=datetime.date(2018, 1, 1),
        is_active=True
    )


@pytest.fixture
def question(db, acceptance_test):
    return models.AcceptanceTestQuestion.objects.create(
        acceptance_test=acceptance_test,
        question='question',
        order=1
    )


@pytest.fixture
def answer(db, question):
    return models.AcceptanceTestAnswer.objects.create(
        acceptance_test_question=question,
        answer='answer',
        order=0,
        is_correct=True,
        score=5
    )


@pytest.fixture
def answer_wrong(db, question):
    return models.AcceptanceTestAnswer.objects.create(
        acceptance_test_question=question,
        answer='answer wrong',
        order=0,
        is_correct=False
    )


@pytest.fixture
def excluded_question(db, acceptance_test):
    return models.AcceptanceTestQuestion.objects.create(
        acceptance_test=acceptance_test,
        question='question2',
        order=2,
        exclude_from_score=True
    )


@pytest.fixture
def excluded_question_answer(db, question):
    return models.AcceptanceTestAnswer.objects.create(
        acceptance_test_question=question,
        answer='answer',
        order=0,
        is_correct=True
    )


@pytest.fixture
def acceptance_test_skill(db, acceptance_test, skill):
    return models.AcceptanceTestSkill.objects.create(
        acceptance_test=acceptance_test,
        skill=skill
    )
