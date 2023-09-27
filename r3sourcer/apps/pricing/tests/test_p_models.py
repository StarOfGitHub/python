import pytest
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from r3sourcer.apps.core.models import Company
from r3sourcer.apps.pricing.models import (
    Industry, PriceList, PriceListRate, RateCoefficientGroup, RateCoefficient,
    RateCoefficientModifier, DynamicCoefficientRule,
)
from r3sourcer.apps.skills.models import Skill, SkillName


industry_fake = Industry(type='test')
company_f = Company(name='company', fake_wf=True)
skill_name = SkillName(name='skill', industry=industry_fake)
skill_f = Skill(name=skill_name, company=company_f)
rate_coeff_fake = RateCoefficient(name='coefficient')


str_test_data = [
    (industry_fake, 'test'),
    (PriceList(company=Company(name='company', fake_wf=True), valid_from=date(2017, 1, 1)),
        'company: 01/01/2017'),
    (PriceList(company=Company(name='company', fake_wf=True), valid_from=date(2017, 1, 1),
               valid_until=date(2017, 2, 1)),
        'company: 01/01/2017 - 01/02/2017'),
    (PriceListRate(default_rate=1.23), 'skill: $1.23/h'),
    (RateCoefficientGroup(name='group'), 'group'),
    (rate_coeff_fake, 'coefficient'),
    (RateCoefficientModifier(rate_coefficient=rate_coeff_fake,
                             fixed_override=1.23), 'coefficient: $1.23/h'),
    (RateCoefficientModifier(rate_coefficient=rate_coeff_fake,
                             multiplier=1.23, fixed_addition=2.34),
        'coefficient: *1.23+2.34'),
]


@pytest.mark.django_db
class TestStr:

    @pytest.mark.parametrize(['obj', 'str_result'], str_test_data)
    def test_str(self, obj, str_result):
        assert str(obj) == str_result

    def test_dynamic_coeff_str(self):
        ct = ContentType.objects.get_by_natural_key(
            'pricing', 'industry'
        )
        obj = DynamicCoefficientRule(rate_coefficient=rate_coeff_fake,
                                     rule_type=ct)

        assert str(obj) == 'coefficient: Industry'


@pytest.mark.django_db
class TestDynamicCoefficientRule:

    def test_save(self, rate_coefficient, monday_rule):
        obj = DynamicCoefficientRule(
            rate_coefficient=rate_coefficient,
            rule=monday_rule,
        )

        obj.save()

        assert obj.priority == 10

    def test_save_priority(self, rate_coefficient, monday_rule):
        obj = DynamicCoefficientRule(
            priority=20,
            rate_coefficient=rate_coefficient,
            rule=monday_rule,
        )

        obj.save()

        assert obj.priority == 20

    def test_save_manual_priority(self, rate_coefficient, monday_rule):
        obj = DynamicCoefficientRule(
            priority=20,
            rate_coefficient=rate_coefficient,
            rule=monday_rule,
        )

        obj.save()

        obj.priority = 0
        obj.save()

        assert obj.priority == 0


class TestRateCoefficientModifier:

    def test_calc(self):
        mod = RateCoefficientModifier(multiplier=1, fixed_addition=1)

        assert mod.calc(1) == 2

    def test_calc_fixed_override(self):
        mod = RateCoefficientModifier(fixed_override=1)

        assert mod.calc(1) == 1


class TestPriceListRate:
    @pytest.mark.django_db
    def test_default_rate(self, skill, price_list, skill_name, company):
        base_rate1 = PriceListRate.objects.create(
            skill=skill, price_list=price_list, hourly_rate=20, default_rate=True
        )
        base_rate2 = PriceListRate.objects.create(
            skill=skill, price_list=price_list, default_rate=True, hourly_rate=30
        )

        assert not PriceListRate.objects.get(pk=str(base_rate1.pk)).default_rate
        assert PriceListRate.objects.get(pk=str(base_rate2.pk)).default_rate

        skill2 = Skill.objects.create(
            name=skill_name, company=company, carrier_list_reserve=2, short_name="Drv", active=False
        )
        base_rate3 = PriceListRate.objects.create(
            skill=skill2, price_list=price_list, hourly_rate=20, default_rate=False
        )
        base_rate4 = PriceListRate.objects.create(
            skill=skill2, price_list=price_list, default_rate=False, hourly_rate=30
        )

        assert base_rate3.default_rate
        assert not base_rate4.default_rate

    def test_clean(self, skill, price_list):
        skill.price_list_lower_rate_limit = 30
        skill.price_list_upper_rate_limit = 50
        skill.price_list_default_rate = 40
        skill.save()

        price_list_rate = PriceListRate.objects.create(
            skill=skill,
            price_list=price_list,
            default_rate=True
        )

        assert price_list_rate.hourly_rate == skill.price_list_default_rate

        with pytest.raises(ValidationError):
            PriceListRate.objects.create(
                skill=skill,
                price_list=price_list,
                default_rate=True,
                hourly_rate=10
            )

        with pytest.raises(ValidationError):
            PriceListRate.objects.create(
                skill=skill,
                price_list=price_list,
                default_rate=True,
                hourly_rate=100
            )
