from datetime import timedelta, datetime, date, time
from decimal import Decimal

import pytest

from django.utils import timezone
from freezegun import freeze_time

# from r3sourcer.apps.hr.payment.base import BasePaymentService, calc_worked_delta
from r3sourcer.apps.hr.payment.base import BasePaymentService


hour_1 = timedelta(hours=1)


@pytest.mark.django_db
class TestInvoiceService:

    @pytest.fixture
    def service(self):
        return BasePaymentService()

    # def test_calc_worked_delta(self, timesheet):
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8)
    #
    # def test_calc_worked_delta_no_ended(self, timesheet):
    #     timesheet.shift_ended_at = None
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta()
    #
    # @freeze_time(datetime(2017, 1, 1))
    # def test_calc_worked_delta_ended_lt_started(self, timesheet):
    #     timesheet.shift_ended_at = timezone.make_aware(
    #         datetime.combine(date.today(), time(3, 30))
    #     )
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8)
    #
    # def test_calc_worked_delta_no_break(self, timesheet):
    #     timesheet.break_started_at = None
    #     timesheet.break_ended_at = None
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8, minutes=30)
    #
    # @freeze_time(datetime(2017, 1, 1))
    # def test_calc_worked_delta_break_date_lt_started(self, timesheet):
    #     timesheet.break_started_at = timezone.make_aware(
    #         datetime.combine(date.today() - timedelta(days=1), time(12, 0))
    #     )
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8)
    #
    # @freeze_time(datetime(2017, 1, 1))
    # def test_calc_worked_delta_break_started_lt_started(self, timesheet):
    #     timesheet.break_started_at = timezone.make_aware(
    #         datetime.combine(date.today(), time(0, 0))
    #     )
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8)
    #
    # @freeze_time(datetime(2017, 1, 1))
    # def test_calc_worked_delta_break_ended_lt_started(self, timesheet):
    #     timesheet.break_ended_at = timezone.make_aware(
    #         datetime.combine(date.today(), time(0, 30))
    #     )
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8)
    #
    # def test_calc_worked_delta_break_started_gt_ended(self, timesheet):
    #     timesheet.break_started_at = timesheet.shift_ended_at + hour_1
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8, minutes=30)
    #
    # def test_calc_worked_delta_break_ended_gt_ended(self, timesheet):
    #     timesheet.break_ended_at = timesheet.shift_ended_at + hour_1
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8, minutes=30)
    #
    # def test_calc_worked_delta_break_ended_gt_break_started(self, timesheet):
    #     timesheet.break_ended_at = timesheet.break_started_at - hour_1
    #
    #     res = calc_worked_delta(timesheet)
    #
    #     assert res == timedelta(hours=8, minutes=30)

    def test_get_timesheets(self, timesheet_approved, service):

        res = service._get_timesheets(None)

        assert res.count() == 1
        assert res[0] == timesheet_approved

    def test_get_timesheets_not_approved(self, timesheet, service):

        res = service._get_timesheets(None)

        assert res.count() == 0

    @freeze_time(datetime(2017, 1, 2))
    def test_get_timesheets_not_date(self, timesheet_approved, service):

        res = service._get_timesheets(None, timezone.now())

        assert res.count() == 0

    def test_get_timesheets_candidate(self, timesheet_approved, service,
                                      candidate_contact):

        res = service._get_timesheets(None, candidate=candidate_contact)

        assert res.count() == 1

    def test_lines_iter(self, service, price_list_rate, rate_coefficient,
                        skill):

        coeffs_hours = [
            {
                'coefficient': rate_coefficient,
                'hours': timedelta(hours=1),
            },
            {'coefficient': 'base', 'hours': timedelta(hours=7)},
        ]

        res = list(service.lines_iter(
            coeffs_hours, skill, price_list_rate.hourly_rate
        ))

        assert len(res) == 2
        assert res[0]['rate'] == Decimal(20)
        assert res[1]['rate'] == Decimal(10)

    def test_lines_iter_allowance(self, service, price_list_rate,
                                  allowance_rate_coefficient, skill):

        coeffs_hours = [
            {
                'coefficient': allowance_rate_coefficient,
                'hours': timedelta(hours=1),
            },
            {'coefficient': 'base', 'hours': timedelta(hours=7)},
        ]

        res = list(service.lines_iter(
            coeffs_hours, skill, price_list_rate.hourly_rate
        ))

        assert len(res) == 2
        assert res[0]['rate'] == Decimal(10)
        assert res[1]['rate'] == Decimal(10)

    def test_lines_iter_no_coeffs_hours(self, service, price_list_rate,
                                        rate_coefficient, skill):

        coeffs_hours = []

        res = list(service.lines_iter(
            coeffs_hours, skill, price_list_rate.hourly_rate
        ))

        assert len(res) == 0
