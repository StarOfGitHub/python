from unittest import skip

import pytest

from r3sourcer.apps.skills.models import EmploymentClassification, Skill, SkillBaseRate, SkillName
from r3sourcer.apps.pricing.models import Industry
from r3sourcer.apps.core.models import Company


industry_fake = Industry(type='test')
company_f = Company(name='company', fake_wf=True)
skill_name = SkillName(name='test', industry=industry_fake)
skill_name_f = SkillName(name='t', industry=industry_fake)
str_test_data = [
    (EmploymentClassification(name='test'), 'test'),
    (Skill(name=skill_name, company=company_f), 'company - test'),
    (SkillBaseRate(skill=Skill(name=skill_name_f, company=company_f), hourly_rate=1.23), 'company - t $1.23/h'),
]


class TestStr:
    @pytest.mark.parametrize(['obj', 'str_result'], str_test_data)
    def test_str(self, obj, str_result):
        assert str(obj) == str_result


class TestSkillBaseRate:
    @pytest.mark.django_db
    def test_default_rate(self, skill, skill_name, skill_name_plumber, company):
        base_rate1 = SkillBaseRate.objects.create(skill=skill, hourly_rate=1, default_rate=True)
        base_rate2 = SkillBaseRate.objects.create(skill=skill, hourly_rate=2, default_rate=True)

        assert not SkillBaseRate.objects.get(pk=str(base_rate1.pk)).default_rate
        assert SkillBaseRate.objects.get(pk=str(base_rate2.pk)).default_rate

        skill2 = Skill.objects.create(
            name=skill_name_plumber, company=company, carrier_list_reserve=2, short_name="Plmb", active=False
        )
        base_rate3 = SkillBaseRate.objects.create(skill=skill2, hourly_rate=20, default_rate=False)
        base_rate4 = SkillBaseRate.objects.create(skill=skill2, hourly_rate=30, default_rate=False)

        assert base_rate3.default_rate
        assert not base_rate4.default_rate

    def test_set_default_rate(self, skill):
        base_rate1 = SkillBaseRate.objects.create(skill=skill, hourly_rate=1, default_rate=True)
        base_rate2 = SkillBaseRate.objects.create(skill=skill, hourly_rate=2, default_rate=False)
        base_rate2.default_rate = True
        base_rate2.save()

        assert SkillBaseRate.objects.get(pk=base_rate1.pk).default_rate is False
        assert SkillBaseRate.objects.get(pk=base_rate2.pk).default_rate is True


class TestSkill:
    def test_validation_success(self, price_list, skill_name_plumber, company):
        skill = Skill.objects.create(
            name=skill_name_plumber, carrier_list_reserve=2, short_name="Drv", active=False, company=company,
        )
        skill.active = True
        skill.save()

        assert skill.active

    @skip("Fix this")
    def test_validation_fail(self, skill):
        SkillBaseRate.objects.create(skill=skill, hourly_rate=20, default_rate=True)
        skill.active = True

        with pytest.raises(Exception) as excinfo:
            skill.save()

        error = "Skill can't be active. It doesn't have default price list rate and defalut base rate."
        assert excinfo.value.messages[0] == error
