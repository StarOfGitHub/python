import pytest
from datetime import timedelta, time, date, datetime

from django.utils.translation import ugettext_lazy as _
from django.utils import timezone
from freezegun import freeze_time

from r3sourcer.apps.pricing.models import (
    WeekdayWorkRule, OvertimeWorkRule, TimeOfDayWorkRule, AllowanceWorkRule,
    WorkRuleMixin,
)
from r3sourcer.apps.pricing.exceptions import RateNotApplicable


str_test_data = [
    (WeekdayWorkRule(weekday_monday=True), _('Rule for: mon')),
    (OvertimeWorkRule(overtime_hours_from=timedelta(hours=1)),
        _('Overtime: from 1h')),
    (OvertimeWorkRule(overtime_hours_from=timedelta(hours=1),
                      overtime_hours_to=timedelta(hours=2)),
        _('Overtime: from 1h to 2h')),
    (TimeOfDayWorkRule(time_start=time(hour=18),
                       time_end=time(hour=6)),
        _('Time of Day: 06:00 PM - 06:00 AM')),
    (AllowanceWorkRule(allowance_description='Travel'),
        _('Allowance: Travel')),
]


class TestStr:

    @pytest.mark.parametrize(['obj', 'str_result'], str_test_data)
    def test_str(self, obj, str_result):
        assert str(obj) == str_result


@pytest.mark.django_db
class TestorkRuleMixin:

    def test_get_hours(self):
        obj = WorkRuleMixin()

        with pytest.raises(NotImplementedError):
            obj.calc_hours(None, None)


class TestWeekdayWorkRule:

    @freeze_time(date(2017, 1, 2))
    def test_get_hours(self):
        obj = WeekdayWorkRule(weekday_monday=True)

        res = obj.calc_hours(timezone.now(), timedelta(hours=1))

        assert res == timedelta()

    @freeze_time(date(2017, 1, 1))
    def test_get_hours_not_applied(self):
        obj = WeekdayWorkRule(weekday_monday=True)

        with pytest.raises(RateNotApplicable):
            obj.calc_hours(timezone.now(), timedelta(hours=1))


class TestOvertimeWorkRule:

    def test_get_hours(self):
        obj = OvertimeWorkRule(overtime_hours_from=timedelta(hours=1),
                               overtime_hours_to=timedelta(hours=2))

        res = obj.calc_hours(timezone.now(), timedelta(hours=2))

        assert res == timedelta(hours=1)

    def test_get_hours_gt_worked(self):
        obj = OvertimeWorkRule(overtime_hours_from=timedelta(hours=1),
                               overtime_hours_to=timedelta(hours=2))

        res = obj.calc_hours(timezone.now(), timedelta(hours=4))

        assert res == timedelta(hours=1)

    def test_get_hours_not_applied(self):
        obj = OvertimeWorkRule(overtime_hours_from=timedelta(hours=1),
                               overtime_hours_to=timedelta(hours=2))

        res = obj.calc_hours(timezone.now(), timedelta(hours=1))

        assert res == timedelta()


@pytest.mark.django_db
class TestTimeOfDayWorkRule:

    @freeze_time(datetime(2017, 1, 1, 7, 0))
    def test_get_hours(self, settings):
        settings.TIME_ZONE = 'UTC'
        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=2))

        assert res == timedelta(hours=2)

    @freeze_time(datetime(2017, 1, 1, 7, 0))
    def test_get_hours_gt_ended(self, settings):
        settings.TIME_ZONE = 'UTC'
        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=4))

        assert res == timedelta(hours=3)

    @freeze_time(datetime(2017, 1, 1, 5, 0))
    def test_get_hours_started_lt(self, settings):
        settings.TIME_ZONE = 'UTC'
        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=4))

        assert res == timedelta(hours=3)

    @freeze_time(datetime(2017, 1, 1, 5, 0))
    def test_get_hours_started_lt_ended_gt(self, settings):
        settings.TIME_ZONE = 'UTC'
        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=6))

        assert res == timedelta(hours=4)

    @freeze_time(datetime(2017, 1, 1, 9, 0))
    def test_get_hours_started_gt_ended_gt(self, settings):
        settings.TIME_ZONE = 'UTC'
        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=8))

        res = obj.calc_hours(timezone.now(), timedelta(hours=1))

        assert res == timedelta()

    @freeze_time(datetime(2017, 1, 1, 5, 0))
    def test_get_hours_started_lt_ended_lt(self, settings):
        settings.TIME_ZONE = 'UTC'
        obj = TimeOfDayWorkRule(time_start=time(hour=8),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=1))

        assert res == timedelta()

    @freeze_time(datetime(2017, 1, 1, 4, 0))
    def test_get_hours_worked_zero(self, settings):
        settings.TIME_ZONE = 'UTC'
        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=2))

        assert res == timedelta()

    @freeze_time(datetime(2017, 1, 1, 7, 0))
    def test_get_hours_break(self, settings):
        settings.TIME_ZONE = 'UTC'

        break_start = timezone.make_aware(datetime(2017, 1, 1, 7, 30))
        break_end = timezone.make_aware(datetime(2017, 1, 1, 8, 30))

        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=11))

        res = obj.calc_hours(timezone.now(), timedelta(hours=2), break_start,
                             break_end)

        assert res == timedelta(hours=2)

    @freeze_time(datetime(2017, 1, 1, 7, 0))
    def test_get_hours_break_ended_gt(self, settings):
        settings.TIME_ZONE = 'UTC'

        break_start = timezone.make_aware(datetime(2017, 1, 1, 9, 30))
        break_end = timezone.make_aware(datetime(2017, 1, 1, 10, 30))

        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=4), break_start,
                             break_end)

        assert res == timedelta(hours=2, minutes=30)

    @freeze_time(datetime(2017, 1, 1, 5, 0))
    def test_get_hours_break_started_lt_ended_in(self, settings):
        settings.TIME_ZONE = 'UTC'

        break_start = timezone.make_aware(datetime(2017, 1, 1, 5, 30))
        break_end = timezone.make_aware(datetime(2017, 1, 1, 6, 30))

        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=4), break_start,
                             break_end)

        assert res == timedelta(hours=3, minutes=30)

    @freeze_time(datetime(2017, 1, 1, 5, 0))
    def test_get_hours_break_started_lt_ended_gt(self, settings):
        settings.TIME_ZONE = 'UTC'

        break_start = timezone.make_aware(datetime(2017, 1, 1, 5, 30))
        break_end = timezone.make_aware(datetime(2017, 1, 1, 7, 30))

        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=7))

        res = obj.calc_hours(timezone.now(), timedelta(hours=3), break_start,
                             break_end)

        assert res == timedelta()

    @freeze_time(datetime(2017, 1, 1, 18, 0))
    def test_get_hours_night_shift(self, settings):
        settings.TIME_ZONE = 'UTC'

        obj = TimeOfDayWorkRule(time_start=time(hour=18),
                                time_end=time(hour=6))

        res = obj.calc_hours(timezone.now(), timedelta(hours=2))

        assert res == timedelta(hours=2)

    @freeze_time(datetime(2017, 1, 1, 5, 0))
    def test_get_hours_break_started_gt_ended_gt(self, settings):
        settings.TIME_ZONE = 'UTC'

        break_start = timezone.make_aware(datetime(2017, 1, 1, 7, 30))
        break_end = timezone.make_aware(datetime(2017, 1, 1, 8, 30))

        obj = TimeOfDayWorkRule(time_start=time(hour=6),
                                time_end=time(hour=7))

        res = obj.calc_hours(timezone.now(), timedelta(hours=3), break_start,
                             break_end)

        assert res == timedelta(hours=1)

    @freeze_time(datetime(2017, 1, 1, 7, 0))
    def test_get_hours_break_started_lt_ended_lt(self, settings):
        settings.TIME_ZONE = 'UTC'

        break_start = timezone.make_aware(datetime(2017, 1, 1, 7, 30))
        break_end = timezone.make_aware(datetime(2017, 1, 1, 8, 30))

        obj = TimeOfDayWorkRule(time_start=time(hour=9),
                                time_end=time(hour=10))

        res = obj.calc_hours(timezone.now(), timedelta(hours=3), break_start,
                             break_end)

        assert res == timedelta(hours=1)


class TestAllowanceWorkRule:

    def test_get_hours(self):
        obj = AllowanceWorkRule()

        res = obj.calc_hours(timezone.now(), timedelta(hours=2))

        assert res == timedelta(hours=-1)
