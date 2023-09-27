from datetime import timedelta

import pytest

from r3sourcer.apps.pricing.utils.utils import format_timedelta


test_data = (
    (timedelta(hours=1), True, '1h'),
    (timedelta(hours=1, minutes=42), True, '1h 42min'),
    (timedelta(hours=1, minutes=42, seconds=8), True, '1h 42min 8s'),
    (timedelta(minutes=42), True, '42min'),
    (timedelta(minutes=42, seconds=8), True, '42min 8s'),
    (timedelta(seconds=8), True, '8s'),
    (timedelta(hours=1, minutes=42, seconds=8), False, '1h 42min'),
    (timedelta(minutes=42, seconds=8), False, '42min'),
    (timedelta(seconds=8), False, ''),
)


class TestFormatTimedelta:

    @pytest.mark.parametrize(['time_delta', 'with_seconds', 'res'], test_data)
    def test_format_timedelta_only_hours(self, time_delta, with_seconds, res):
        assert format_timedelta(time_delta, with_seconds) == res
