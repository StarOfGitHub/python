from datetime import datetime, time, timedelta, date

import freezegun
import pytest
from freezegun import freeze_time

from pytz import timezone

from django.conf import settings as dj_settings
from rest_framework.exceptions import ValidationError

from r3sourcer.apps.hr.api.serializers.timesheet import TimeSheetSerializer
from r3sourcer.apps.hr.api.serializers.job import JobSerializer, ShiftSerializer
from r3sourcer.apps.hr.models import Shift, ShiftDate
from r3sourcer.helpers.datetimes import utc_now

tz = timezone(dj_settings.TIME_ZONE)


class TestTimeSheetSerializer:

    @pytest.fixture
    def serializer(self):
        return TimeSheetSerializer()

    def test_get_company(self, serializer, timesheet, regular_company):
        res = serializer.get_company(timesheet)

        assert res == {'id': regular_company.id, '__str__': str(regular_company), 'supervisor_approved_scheme': 'BASIC'}

    def test_get_company_none(self, serializer, timesheet):
        res = serializer.get_company(None)

        assert res is None

    def test_get_jobsite(self, serializer, timesheet, jobsite):
        res = serializer.get_jobsite(timesheet)

        assert res == {
            'id': jobsite.id,
            'address': {
                'id': jobsite.address.id,
                '__str__': str(jobsite.address),
            },
            '__str__': str(jobsite),
        }

    def test_get_jobsite_none(self, serializer, timesheet):
        res = serializer.get_jobsite(None)

        assert res is None

    def test_get_position(self, serializer, timesheet, skill):
        res = serializer.get_position(timesheet)

        assert res == {'id': skill.id, '__str__': str(skill), 'translations': []}

    def test_get_position_none(self, serializer, timesheet):
        res = serializer.get_position(None)

        assert res is None

    def test_save_null_dates(self, timesheet_with_break):
        with freeze_time("2017-01-02 0:00:00", tz_offset=0):
            data = {
                "shift_started_at": utc_now().replace(hour=8, minute=0),
                "shift_ended_at": utc_now().replace(hour=8, minute=0) + timedelta(hours=8),
                "break_started_at": None,
                "break_ended_at": None
            }

        serializer = TimeSheetSerializer(timesheet_with_break, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        timesheet_with_break.refresh_from_db()

        assert timesheet_with_break.shift_started_at is not None
        assert timesheet_with_break.break_started_at is None
        assert timesheet_with_break.break_ended_at is None


@pytest.mark.django_db
class TestJobSerializer:

    @pytest.fixture
    def serializer(self):
        return JobSerializer()

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 7)))
    def test_get_todays_timesheets(self, timesheet, job, serializer):
        res = serializer.get_todays_timesheets(job)

        assert res == '0% / 0% / 0%'

    def test_get_todays_timesheets_no_timesheet(self, job, serializer):
        res = serializer.get_todays_timesheets(job)

        assert res == '-'


@pytest.mark.django_db
class TestShiftSerializer:

    @pytest.fixture
    def serializer(self):
        return ShiftSerializer()

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 2, 8, 00)))
    def test_success_validate(self, job, serializer, shift, cancelled_jo, shift_date):
        data = {
            'date': shift_date.pk,
            'time': time(hour=8, minute=30)
        }
        res = serializer.validate(data)

        assert res == {
            'date': shift_date.pk,
            'time': time(hour=8, minute=30)
        }

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 2, 8, 00)))
    def test_fail_validate(self, job, serializer, accepted_jo, shift_date):
        validated_data = {
            'date': shift_date.pk,
            'time': time(hour=8, minute=30)
        }

        with pytest.raises(ValidationError) as excinfo:
            serializer.validate(validated_data)

        assert "Shift time must be unique" in str(excinfo.value)

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 2, 8, 00)))
    def test_success_validate_on_update(self, job, shift, cancelled_jo, shift_date):
        new_shift_date = ShiftDate.objects.create(
            job=job,
            shift_date=date(2017, 1, 3)
        )
        new_shift = Shift.objects.create(
            date=new_shift_date,
            time=time(hour=8, minute=30)
        )
        serializer = ShiftSerializer(new_shift, data={
            'date': shift_date.pk,
            'time': time(hour=8, minute=00)
        })
        res = serializer.is_valid(raise_exception=True)

        assert res is True

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 2, 8, 00)))
    def test_fail_validate_on_update(self, job, accepted_jo, shift_date):
        new_shift = Shift.objects.create(
            date=shift_date,
            time=time(hour=19, minute=30)
        )
        serializer = ShiftSerializer(new_shift, data={
            'date': shift_date.pk,
            'time': time(hour=8, minute=30)
        })

        with pytest.raises(ValidationError) as excinfo:
            serializer.is_valid(raise_exception=True)

        assert "Shift time must be unique" in str(excinfo.value)
