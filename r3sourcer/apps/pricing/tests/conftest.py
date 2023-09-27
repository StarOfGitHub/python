from datetime import timedelta, time, date

import pytest

from r3sourcer.apps.core.models import Company
from r3sourcer.apps.pricing.models import (
    WeekdayWorkRule, OvertimeWorkRule, TimeOfDayWorkRule, AllowanceWorkRule,
    RateCoefficient, RateCoefficientModifier, Industry, PriceList, PriceListRateCoefficient,
    PriceListRate, RateCoefficientRel
)
from r3sourcer.apps.skills.models import Skill, SkillName


@pytest.fixture
def company(db):
    return Company.objects.create(
        name='Company',
        business_id='111',
        registered_for_gst=True,
        type=Company.COMPANY_TYPES.master,
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
def monday_rule(db):
    return WeekdayWorkRule.objects.create(weekday_monday=True)


@pytest.fixture
def overtime_rule(db):
    return OvertimeWorkRule.objects.create(
        overtime_hours_from=timedelta(hours=1),
        overtime_hours_to=timedelta(hours=2),
    )


@pytest.fixture
def overtime_4_rule(db):
    return OvertimeWorkRule.objects.create(
        overtime_hours_from=timedelta(hours=0),
        overtime_hours_to=timedelta(hours=4),
    )


@pytest.fixture
def day_time_rule(db):
    return TimeOfDayWorkRule.objects.create(
        time_start=time(hour=8),
        time_end=time(hour=18),
    )


@pytest.fixture
def night_time_rule(db):
    return TimeOfDayWorkRule.objects.create(
        time_start=time(hour=18),
        time_end=time(hour=6),
    )


@pytest.fixture
def allowance_rule(db):
    return AllowanceWorkRule.objects.create(allowance_description='Travel')


@pytest.fixture
def rate_coefficient(db, industry, company):
    coeff = RateCoefficient.objects.create(name='test', industry=industry)
    RateCoefficientModifier.objects.create(
        type=RateCoefficientModifier.TYPE_CHOICES.candidate,
        rate_coefficient=coeff,
        multiplier=2,
    )
    RateCoefficientRel.objects.create(rate_coefficient=coeff, company=company)

    return coeff


@pytest.fixture
def rate_coefficient_another(db, industry, company):
    coeff = RateCoefficient.objects.create(name='test 1', industry=industry)
    RateCoefficientModifier.objects.create(
        type=RateCoefficientModifier.TYPE_CHOICES.candidate,
        rate_coefficient=coeff,
        multiplier=1.5,
    )
    RateCoefficientRel.objects.create(rate_coefficient=coeff, company=company)

    return coeff


@pytest.fixture
def rate_coefficient_company(db, industry, company):
    coeff = RateCoefficient.objects.create(name='test company', industry=industry)
    RateCoefficientModifier.objects.create(
        type=RateCoefficientModifier.TYPE_CHOICES.company,
        rate_coefficient=coeff,
        multiplier=2,
    )
    RateCoefficientRel.objects.create(rate_coefficient=coeff, company=company)

    return coeff


@pytest.fixture
def rate_coefficient_company_another(db, industry, company):
    coeff = RateCoefficient.objects.create(name='test company 1.5', industry=industry)
    RateCoefficientModifier.objects.create(
        type=RateCoefficientModifier.TYPE_CHOICES.company,
        rate_coefficient=coeff,
        multiplier=1.5,
    )
    RateCoefficientRel.objects.create(rate_coefficient=coeff, company=company)

    return coeff


@pytest.fixture
def price_list(db, company):
    return PriceList.objects.create(
        company=company,
        valid_from=date(2017, 1, 1)
    )


@pytest.fixture
def price_list_rate_coefficient(db, price_list, rate_coefficient_company):
    return PriceListRateCoefficient.objects.create(
        price_list=price_list,
        rate_coefficient=rate_coefficient_company,
    )


@pytest.fixture
def price_list_rate(db, price_list, skill):
    return PriceListRate.objects.create(
        price_list=price_list,
        skill=skill,
        hourly_rate=10
    )
