from datetime import date, datetime
from unittest import skip

import pytest
from freezegun import freeze_time

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


class TestSkillManager:

    @freeze_time('2021, 1, 2')
    def test_filtered_for_carrier_list(self, skill_painter_active, skill_rel_1, skill_rel_2, skill_rel_3,
                                       carrier_list_1, carrier_list_2, carrier_list_4):
        target_dt = datetime.now()
        skills = Skill.objects.filtered_for_carrier_list(target_date_and_time=target_dt)

        assert len(skills) == 1

    @freeze_time('2021, 1, 2')
    def test_filtered_inactive_skill(self, skill_rel_4, carrier_list_4):
        target_dt = datetime.now()
        skills = Skill.objects.filtered_for_carrier_list(target_date_and_time=target_dt)

        assert len(skills) == 0

    @freeze_time('2021, 1, 2')
    def test_filtered_for_carrier_list_with_accepted_offer(self, job_offer_accepted):
        target_dt = datetime.now()
        skills = Skill.objects.filtered_for_carrier_list(target_date_and_time=target_dt)

        assert len(skills) == 0

    @freeze_time('2021, 1, 2')
    def test_filtered_for_carrier_list_without_confirmation(self, skill_rel_2, carrier_list_2):
        target_dt = datetime.now()
        skills = Skill.objects.filtered_for_carrier_list(target_date_and_time=target_dt)

        assert len(skills) == 0

    @freeze_time('2021, 1, 2')
    def test_filtered_for_carrier_list_with_zero_reserved(self, carrier_list_5):
        target_dt = datetime.now()
        skills = Skill.objects.filtered_for_carrier_list(target_date_and_time=target_dt)

        assert len(skills) == 0
