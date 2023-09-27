from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from django.utils import timezone

from r3sourcer.apps.core.models import Company
from r3sourcer.apps.pricing.models import (
    DynamicCoefficientRule, RateCoefficientModifier, Industry,
)
from r3sourcer.apps.pricing.services import CoefficientService


rates_calc = CoefficientService()


@pytest.mark.django_db
class TestCoefficientRates:

    def add_rule(self, rate_coefficient, rule):
        DynamicCoefficientRule.objects.create(
            rate_coefficient=rate_coefficient,
            rule=rule,
            used=True,
        )

    def calc_res(self, worked_hours=None):
        break_start = timezone.make_aware(datetime(2017, 1, 2, 13, 00))
        break_end = timezone.make_aware(datetime(2017, 1, 2, 14, 00))
        company = Company.objects.get(name='Company')

        return rates_calc.calc(
            company, Industry.objects.get(type='test'),
            RateCoefficientModifier.TYPE_CHOICES.candidate,
            timezone.now(), worked_hours or timedelta(hours=8),
            break_start, break_end
        )

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_monday_rule(self, settings, rate_coefficient, monday_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, monday_rule)
        res = self.calc_res()

        assert len(res) == 1
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=8)

    @freeze_time(datetime(2017, 1, 1, 8, 30))
    def test_calc_not_applicable(self, settings, rate_coefficient, monday_rule, industry, company):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, monday_rule)

        res = rates_calc.calc(
            company, industry, RateCoefficientModifier.TYPE_CHOICES.candidate,
            timezone.now(), timedelta(hours=8)
        )

        assert len(res) == 1

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_overtime(self, settings, rate_coefficient, overtime_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, overtime_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)

    @freeze_time(datetime(2017, 1, 2, 7, 30))
    def test_calc_overtime_not_applied(self, settings, rate_coefficient, overtime_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, overtime_rule)
        res = self.calc_res(timedelta(hours=1))

        assert len(res) == 1
        assert res[0]['coefficient'] == 'base'

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_overtime_for_monday(self, settings, rate_coefficient, monday_rule, overtime_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, overtime_rule)
        self.add_rule(rate_coefficient, monday_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(hours=7)

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_overtime_for_time_monday(
        self, settings, rate_coefficient, monday_rule, overtime_rule, day_time_rule
    ):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, overtime_rule)
        self.add_rule(rate_coefficient, monday_rule)
        self.add_rule(rate_coefficient, day_time_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(hours=7)

    @freeze_time(datetime(2017, 1, 2, 5, 30))
    def test_calc_overtime_for_time_monday_part(
        self, settings, rate_coefficient, monday_rule, overtime_rule, day_time_rule
    ):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, overtime_rule)
        self.add_rule(rate_coefficient, monday_rule)
        self.add_rule(rate_coefficient, day_time_rule)
        res = self.calc_res(timedelta(hours=3))

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(minutes=30)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(hours=2, minutes=30)

    @freeze_time(datetime(2017, 1, 2, 9, 30))
    def test_calc_for_time_monday(self, settings, rate_coefficient, monday_rule, day_time_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, monday_rule)
        self.add_rule(rate_coefficient, day_time_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=7, minutes=30)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(minutes=30)

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_allowance(self, settings, rate_coefficient, allowance_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, allowance_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(hours=8)

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_allowance_for_time(self, settings, rate_coefficient, allowance_rule, day_time_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, allowance_rule)
        self.add_rule(rate_coefficient, day_time_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(hours=8)

    @freeze_time(datetime(2017, 1, 2, 9, 30))
    def test_calc_allowance_for_night_time(self, settings, rate_coefficient, overtime_rule, night_time_rule):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, overtime_rule)
        self.add_rule(rate_coefficient, night_time_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(minutes=30)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(hours=7, minutes=30)

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_two_coeff(
        self, settings, rate_coefficient, rate_coefficient_another, overtime_rule, monday_rule, allowance_rule
    ):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, allowance_rule)
        self.add_rule(rate_coefficient, monday_rule)

        self.add_rule(rate_coefficient_another, overtime_rule)
        self.add_rule(rate_coefficient_another, monday_rule)
        res = self.calc_res()

        assert len(res) == 3
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)
        assert res[1]['coefficient'] == rate_coefficient_another
        assert res[1]['hours'] == timedelta(hours=1)
        assert res[2]['coefficient'] == 'base'
        assert res[2]['hours'] == timedelta(hours=7)

    @freeze_time(datetime(2017, 1, 2, 10, 30))
    def test_calc_two_coeff_night(
        self, settings, rate_coefficient, overtime_rule, rate_coefficient_another, overtime_4_rule, monday_rule,
        night_time_rule, day_time_rule
    ):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient_another, night_time_rule)
        self.add_rule(rate_coefficient_another, overtime_4_rule)
        self.add_rule(rate_coefficient_another, monday_rule)

        self.add_rule(rate_coefficient, overtime_rule)
        self.add_rule(rate_coefficient, day_time_rule)
        self.add_rule(rate_coefficient, monday_rule)

        res = self.calc_res()

        assert len(res) == 3
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)
        assert res[1]['coefficient'] == rate_coefficient_another
        assert res[1]['hours'] == timedelta(minutes=30)
        assert res[2]['coefficient'] == 'base'
        assert res[2]['hours'] == timedelta(hours=6, minutes=30)

    @freeze_time(datetime(2017, 1, 2, 8, 30))
    def test_calc_two_coeff_night_not_applied(
        self, settings, rate_coefficient, overtime_rule, rate_coefficient_another, monday_rule, night_time_rule,
        day_time_rule
    ):
        settings.TIME_ZONE = 'UTC'

        self.add_rule(rate_coefficient, day_time_rule)
        self.add_rule(rate_coefficient, overtime_rule)
        self.add_rule(rate_coefficient, monday_rule)

        self.add_rule(rate_coefficient_another, overtime_rule)
        self.add_rule(rate_coefficient_another, night_time_rule)
        self.add_rule(rate_coefficient_another, monday_rule)
        res = self.calc_res()

        assert len(res) == 2
        assert res[0]['coefficient'] == rate_coefficient
        assert res[0]['hours'] == timedelta(hours=1)
        assert res[1]['coefficient'] == 'base'
        assert res[1]['hours'] == timedelta(hours=7)
