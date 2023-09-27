import datetime

import mock
import pytest
from freezegun import freeze_time
from mock import patch, PropertyMock, MagicMock
from pytz import timezone

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils.formats import date_format
from django.utils.timezone import localtime, make_aware
from django_mock_queries.query import MockSet, MockModel

from r3sourcer.apps.hr.models import (
    TimeSheet, JobsiteUnavailability, CandidateEvaluation, JobOffer, ShiftDate, TimeSheetIssue, BlackList,
    FavouriteList, Job, CarrierList, Shift, JobOfferSMS, NOT_FULFILLED, FULFILLED, LIKELY_FULFILLED, IRRELEVANT
)
from r3sourcer.helpers.datetimes import utc_tomorrow
from r3sourcer.helpers.models.abs.timezone_models import TimeZone
from r3sourcer.apps.hr.models import TimeSheet


tz = timezone(settings.TIME_ZONE)


@pytest.mark.django_db
class TestJobsite:
    def test_get_site_name_without_address(self, jobsite):
        jobsite.address = None
        assert jobsite.get_site_name() == str(jobsite.master_company)

    def test_get_site_name_with_address(self, jobsite):
        street_address = jobsite.address.street_address
        assert street_address in jobsite.get_site_name()

    def test_get_availability_successful(self, jobsite):
        JobsiteUnavailability.objects.create(
            jobsite=jobsite,
            unavailable_from=datetime.date.today() + datetime.timedelta(days=4)
        )
        assert jobsite.get_availability() == jobsite.is_available
        assert jobsite.get_availability()

    def test_get_availability_unsuccessful(self, jobsite):
        today = datetime.date.today()
        JobsiteUnavailability.objects.create(
            jobsite=jobsite,
            unavailable_from=today,
            unavailable_until=today + datetime.timedelta(days=2)
        )
        assert not jobsite.get_availability()

    def test_get_duration(self, jobsite):
        assert jobsite.get_duration() == datetime.timedelta(7)

    def test_is_address_set_successful(self, jobsite):
        assert jobsite.is_address_set()

    def test_is_address_set_unsuccessful(self, jobsite):
        jobsite.address = None
        assert not jobsite.is_address_set()

    def test_get_address_none(self, jobsite):
        jobsite.address = None
        assert jobsite.get_address() is None

    def test_get_address_with_result(self, jobsite, address):
        assert jobsite.get_address() == address

    def test_is_supervisor_set_true(self, jobsite):
        assert jobsite.is_supervisor_set()

    def test_is_supervisor_set_false(self, jobsite):
        jobsite.primary_contact = None
        assert not jobsite.is_supervisor_set()

    @freeze_time(datetime.datetime(2017, 1, 1))
    def test_save_not_changed_primary_contact(self, jobsite, job_offer,
                                              company_contact,
                                              timesheet_tomorrow):
        jobsite.save()

        ts = TimeSheet.objects.filter(
            job_offer__in=[job_offer],
            shift_started_at__date__gte=datetime.date.today() + datetime.timedelta(days=1)
        ).first()

        assert ts.supervisor == company_contact

    @freeze_time(datetime.datetime(2017, 1, 1))
    def test_save_changed_primary_contact(self, jobsite, job_offer,
                                          company_contact_another,
                                          timesheet_tomorrow):
        jobsite.primary_contact = company_contact_another
        jobsite.save()

        ts = TimeSheet.objects.filter(
            job_offer__in=[job_offer],
            shift_started_at__date__gte=datetime.date.today() + datetime.timedelta(days=1)
        ).first()

        assert ts.supervisor == company_contact_another

    def test_get_closest_company(self, jobsite, master_company):
        assert jobsite.get_closest_company() == master_company


@pytest.mark.django_db
class TestJob:

    def test_get_title(self, job, jobsite, skill):
        assert str(jobsite) in str(job)
        assert str(skill) in str(job)

    def test_get_job_offers(self, job, job_offer):
        assert job.get_job_offers().count() == 1

    def test_get_total_bookings_count(self, job, job_offer):
        assert job.get_total_bookings_count() == 1

    @freeze_time(datetime.datetime(2017, 1, 2))
    def test_is_fulfilled_irrelevant(self, job):
        assert job.is_fulfilled() == IRRELEVANT

    @freeze_time(datetime.datetime(2017, 1, 2))
    def test_is_fulfilled_and_accepted(self, job_with_accepted_shifts, shift_accepted, job_offer_yetanother_accepted):
        assert job_with_accepted_shifts.is_fulfilled() == FULFILLED

    @freeze_time(datetime.datetime(2017, 1, 2))
    def test_is_fulfilled_likely_fullfilled(self, job_with_filled_not_accepted_shifts, shift_filled_accepted,
                                       shift_filled_not_accepted, job_offer_undefined, job_offer_accepted):
        assert job_with_filled_not_accepted_shifts.is_fulfilled() == LIKELY_FULFILLED

    @freeze_time(datetime.datetime(2017, 1, 2))
    def test_is_fulfilled_not_fullfilled(self, job_with_declined_shifts, shift_declined,job_offer_declined):
        assert job_with_declined_shifts.is_fulfilled() == NOT_FULFILLED

    @freeze_time(datetime.datetime(2017, 1, 1))
    def test_is_fulfilled_declined(self, job_with_filled_and_declined_shifts, shift_filled_notaccepted,
                                   job_offer_first_declined, job_offer_second_declined):
        assert job_with_filled_and_declined_shifts.is_fulfilled() == NOT_FULFILLED

    #####
    # OLD LOGIC TESTS (remove them if logic is accepted)
    # ###

    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=FULFILLED)
    # def test_is_fulfilled_fulfilled(self, mock_sd_fulfilled, job, shift_date):
    #     assert job.is_fulfilled() == FULFILLED
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=LIKELY_FULFILLED)
    # def test_is_fulfilled_sd_likely_fulfilled(self, mock_sd_fulfilled, job,
    #                                           shift_date):
    #     assert job.is_fulfilled() == LIKELY_FULFILLED
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=IRRELEVANT)
    # def test_is_fulfilled_sd_irrelevant(self, mock_sd_fulfilled, job, shift_date):
    #     assert job.is_fulfilled() == IRRELEVANT
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=NOT_FULFILLED)
    # @patch.object(ShiftDate, 'job_offers', new_callable=PropertyMock)
    # def test_is_fulfilled_sd_not_fulfilled_jo_not_exists(self, mock_jos, mock_sd_fulfilled, job, shift_date):
    #     mock_jos.return_value.exists.return_value = False
    #
    #     assert job.is_fulfilled() == NOT_FULFILLED
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=NOT_FULFILLED)
    # @patch.object(ShiftDate, 'job_offers', new_callable=PropertyMock)
    # def test_is_fulfilled_sd_not_fulfilled_no_unaccepted_jos(self, mock_jos, mock_sd_fulfilled, job, shift_date):
    #     mock_jos.return_value = MockSet(
    #         MockModel(status=JobOffer.STATUS_CHOICES.accepted)
    #     )
    #
    #     assert job.is_fulfilled() == LIKELY_FULFILLED
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=NOT_FULFILLED)
    # def test_is_fulfilled_sd_not_fulfilled_accepted_ts(self, mock_sd_fulfilled, job, job_offer, shift_date):
    #     TimeSheet.objects.create(
    #         job_offer=job_offer,
    #         going_to_work_confirmation=True
    #     )
    #
    #     assert job.is_fulfilled() == LIKELY_FULFILLED
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=NOT_FULFILLED)
    # def test_is_fulfilled_sd_not_fulfilled_no_accepted_ts(self, mock_sd_fulfilled, job, shift_date, timesheet):
    #
    #     assert job.is_fulfilled() == NOT_FULFILLED
    #
    # @freeze_time(datetime.datetime(2017, 1, 2))
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=FULFILLED)
    # def test_is_fulfilled_today_fulfilled(self, mock_fulfilled, job, shift_date):
    #     assert job.is_fulfilled_today() == FULFILLED
    #
    # @freeze_time(datetime.datetime(2017, 1, 2))
    # def test_is_fulfilled_today_no_sd_today(self, job):
    #     assert job.is_fulfilled_today() == IRRELEVANT
    #
    # @freeze_time(datetime.datetime(2017, 1, 2))
    # @patch.object(Job, 'is_fulfilled', return_value=NOT_FULFILLED)
    # def test_can_fillin_not_fulfilled(self, mock_sd_fulfilled, job):
    #     assert job.can_fillin()
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(Job, 'is_fulfilled', return_value=FULFILLED)
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=NOT_FULFILLED)
    # def test_can_fillin_future_sd_not_fulfilled(self, mock_fulfilled, mock_sd_fulfilled, job, job_offer):
    #     assert job.can_fillin()
    #
    # @freeze_time(datetime.datetime(2017, 1, 1))
    # @patch.object(Job, 'is_fulfilled', return_value=FULFILLED)
    # @patch.object(ShiftDate, 'is_fulfilled', return_value=FULFILLED)
    # def test_can_fillin_future_sd_fulfilled(self, mock_fulfilled, mock_sd_fulfilled, job, job_offer):
    #     assert not job.can_fillin()

    #####
    # END
    # ###


@pytest.mark.django_db
class TestShiftDate:
    def test_str(self, shift_date):
        assert str(shift_date) == date_format(shift_date.shift_date, settings.DATE_FORMAT)

    def test_job_offers(self, shift_date, job_offer):
        assert shift_date.job_offers.count() == 1
        assert job_offer in shift_date.job_offers

    def test_is_fulfilled(self, shift_date, shift):
        assert shift_date.is_fulfilled() == NOT_FULFILLED

    @patch.object(JobOffer, 'check_job_quota', return_value=True)
    def test_is_fulfilled_true(self, mock_check, shift_date, shift, candidate_contact):
        JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact,
            status=JobOffer.STATUS_CHOICES.accepted,
        )
        shift_date.workers = 1

        assert shift_date.is_fulfilled() == FULFILLED


@pytest.mark.django_db
class TestShift:
    def test_str(self, shift):
        assert str(shift) == date_format(
            datetime.datetime.combine(shift.date.shift_date, shift.time),
            settings.DATETIME_FORMAT
        )

    def test_get_job(self, shift, job):
        assert shift.job == job

    def test_is_fulfilled(self, shift):
        assert shift.is_fulfilled() == NOT_FULFILLED

    @patch.object(JobOffer, 'check_job_quota', return_value=True)
    def test_is_fulfilled_true(self, mock_check, shift, candidate_contact):
        JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact,
            status=JobOffer.STATUS_CHOICES.accepted,
        )
        shift.workers = 1

        assert shift.is_fulfilled() == FULFILLED


@pytest.mark.django_db
class TestTimesheet:

    def test_str(self, timesheet):
        assert str(timesheet) == '2017-01-01 07:00:00+00:00 None None'

    def test_str_candidate_submitted(self, timesheet):
        timesheet.candidate_submitted_at = make_aware(
            datetime.datetime(2017, 1, 1, 18, 0)
        )
        assert str(timesheet) == '2017-01-01 07:00:00+00:00 2017-01-01 18:00:00+00:00 None'

    def test_str_supervisor_approved(self, timesheet):
        timesheet.candidate_submitted_at = make_aware(
            datetime.datetime(2017, 1, 1, 18, 0)
        )
        timesheet.supervisor_approved_at = make_aware(
            datetime.datetime(2017, 1, 1, 20, 0)
        )
        res = '2017-01-01 07:00:00+00:00 2017-01-01 18:00:00+00:00 2017-01-01 20:00:00+00:00'
        assert str(timesheet) == res

    def test_get_job_offer(self, timesheet, job_offer):
        assert timesheet.get_job_offer() == job_offer

    @patch.object(TimeSheet, '_send_placement_acceptance_sms')
    def test_get_or_create_for_job_offer_accepted(self, mock_acceptance, job_offer_tomorrow):
        res = TimeSheet.get_or_create_for_job_offer_accepted(
            job_offer_tomorrow
        )
        assert res.job_offer == job_offer_tomorrow

    @patch.object(TimeSheet, '_send_placement_acceptance_sms')
    @patch.object(TimeSheet, 'objects', new_callable=PropertyMock)
    def test_get_or_create_for_job_offer_accepted_exists(self, mock_objects, mock_acceptance, job_offer):
        mock_objects.return_value.get_or_create.side_effect = IntegrityError
        mock_objects.return_value.update_or_create.return_value = (
            MockModel(job_offer=job_offer), True
        )

        res = TimeSheet.get_or_create_for_job_offer_accepted(job_offer)
        assert res.job_offer == job_offer

    def test_get_closest_company(self, timesheet, master_company):
        assert timesheet.get_closest_company() == master_company

    @patch.object(TimeSheet, 'is_allowed', return_value=True)
    @patch.object(TimeSheet, 'create_state')
    def test_save_just_added(self, mock_create, mock_allowed, job_offer, company_contact):
        TimeSheet.objects.create(
            job_offer=job_offer,
            supervisor=company_contact
        )

        assert mock_create.called

    @patch.object(TimeSheet, 'create_state')
    def test_save_not_just_added(self, mock_create, timesheet):
        timesheet.save()

        assert not mock_create.called

    def test_supervisor_signature_path(self, timesheet):
        res = timesheet.supervisor_signature_path('test.sig')

        assert res == 'timesheets/signature/{}.sig'.format(timesheet.id)


@pytest.mark.django_db
class TestJobOffer:
    def test_str(self, job_offer):
        assert str(job_offer) == date_format(
            localtime(job_offer.created_at), settings.DATETIME_FORMAT)

    def test_get_job(self, job_offer, job):
        assert job_offer.job == job

    @pytest.mark.parametrize('jo,expected', [
        (JobOffer(status=JobOffer.STATUS_CHOICES.accepted), True),
        (JobOffer(status=JobOffer.STATUS_CHOICES.cancelled), False),
        (JobOffer(status=JobOffer.STATUS_CHOICES.undefined), False)
    ])
    def test_is_accepted(self, jo, expected):
        assert jo.is_accepted() == expected

    def test_is_first(self, job_offer):
        assert job_offer.is_first()

    def test_is_first_false(self, job_offer_yesterday, job_offer):
        assert not job_offer.is_first()

    def test_is_recurring(self, job_offer_yesterday, job_offer):
        assert job_offer.is_recurring()

    def test_is_recurring_false(self, job_offer):
        assert not job_offer.is_recurring()

    def test_get_future_offers(self, job_offer_tomorrow, job_offer):

        assert job_offer.get_future_offers().count() == 1
        assert not job_offer.is_recurring()

    def test_get_future_offers_no_offers(self, job_offer):
        assert job_offer.get_future_offers().count() == 0

    def test_start_time(self, job_offer):
        res = make_aware(datetime.datetime(2017, 1, 2, 8, 30))
        assert job_offer.start_time == res

    def test_move_candidate_to_carrier_list(self, job_offer):
        job_offer.move_candidate_to_carrier_list()

        assert CarrierList.objects.all().count() == 1

        cl = CarrierList.objects.filter(
            candidate_contact=job_offer.candidate_contact, target_date=job_offer.start_time
        ).first()

        assert cl is not None
        assert cl.referral_job_offer == job_offer

    def test_move_candidate_to_carrier_list_new_offer(self, job_offer):
        job_offer.move_candidate_to_carrier_list(True)

        assert CarrierList.objects.all().count() == 1

        cl = CarrierList.objects.filter(
            candidate_contact=job_offer.candidate_contact, target_date=job_offer.start_time
        ).first()

        assert cl is not None
        assert cl.job_offer == job_offer

    def test_move_candidate_to_carrier_list_exists(self, job_offer, carrier_list):
        job_offer.move_candidate_to_carrier_list()

        assert CarrierList.objects.all().count() == 1

        cl = CarrierList.objects.filter(
            candidate_contact=job_offer.candidate_contact, target_date=job_offer.start_time
        ).first()

        assert cl is not None
        assert cl.target_date == job_offer.shift.date.shift_date

    def test_move_candidate_to_carrier_list_confirmed(self, job_offer):
        job_offer.move_candidate_to_carrier_list(confirmed_available=True)

        assert CarrierList.objects.all().count() == 1

        cl = CarrierList.objects.filter(
            candidate_contact=job_offer.candidate_contact, target_date=job_offer.start_time
        ).first()

        assert cl is not None
        assert cl.confirmed_available

    @patch.object(JobOffer, 'check_job_quota', return_value=True)
    def test_process_sms_reply_positive(self, mock_check, job_offer, fake_sms):
        job_offer.process_sms_reply(None, fake_sms, True)

        assert job_offer.status == JobOffer.STATUS_CHOICES.accepted

    def test_process_sms_reply_negative(self, job_offer, fake_sms):
        job_offer.process_sms_reply(None, fake_sms, False)

        assert job_offer.status == JobOffer.STATUS_CHOICES.cancelled

    @freeze_time(tz.localize(datetime.datetime(2017, 1, 2, 9)))
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_shift_started_2h_less(self, mock_task, shift, candidate_contact):
        jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        eta = tz.localize(datetime.datetime(2017, 1, 2, 9, 0, 10))

        assert jo.scheduled_sms_datetime == eta
        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_called_with(args=[jo.id], eta=eta)

    @freeze_time(tz.localize(datetime.datetime(2017, 1, 2, 11)))
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_shift_started_2h_more(self, mock_task, shift, candidate_contact):
        JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_not_called()

    @freeze_time(tz.localize(datetime.datetime(2017, 1, 2, 11)))
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_shift_eta_less_than_now(self, mock_task, shift_date, candidate_contact):
        shift = Shift.objects.create(
            date=shift_date,
            time=datetime.time(hour=12, minute=30)
        )
        jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        eta = tz.localize(datetime.datetime(2017, 1, 2, 11, 0, 10))

        assert jo.scheduled_sms_datetime == eta
        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_called_with(args=[jo.id], eta=eta)

    @freeze_time(tz.localize(datetime.datetime(2017, 1, 2, 9)))
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_shift_eta_less_than_90min_to_shift(self, mock_task, shift_date, candidate_contact):
        shift = Shift.objects.create(
            date=shift_date,
            time=datetime.time(hour=10, minute=0)
        )
        jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        eta = tz.localize(datetime.datetime(2017, 1, 2, 9, 0, 10))

        assert jo.scheduled_sms_datetime == eta
        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_called_with(args=[jo.id], eta=eta)

    @freeze_time(tz.localize(datetime.datetime(2016, 12, 31, 9)))
    @patch.object(JobOffer, 'has_future_accepted_jo', return_value=False)
    @patch.object(JobOffer, 'has_previous_jo', return_value=False)
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_has_no_offers_future_less_than_4day(
        self, mock_task, mock_prev_jo, mock_future_jo, shift, candidate_contact
    ):
        jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        eta = tz.localize(datetime.datetime(2016, 12, 31, 9, 0, 10))

        assert jo.scheduled_sms_datetime == eta
        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_called_with(args=[jo.id], eta=eta)

    @freeze_time(tz.localize(datetime.datetime(2016, 12, 31, 9)))
    @patch.object(JobOffer, 'has_future_accepted_jo', return_value=True)
    @patch.object(JobOffer, 'has_previous_jo', return_value=False)
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_has_offers_future_less_than_4day(
        self, mock_task, mock_prev_jo, mock_future_jo, shift, candidate_contact
    ):
        jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        eta = tz.localize(datetime.datetime(2017, 1, 1, 10, 0, 0))

        assert jo.scheduled_sms_datetime == eta
        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_called_with(args=[jo.id], eta=eta)

    @freeze_time(tz.localize(datetime.datetime(2016, 12, 31, 9)))
    @patch.object(JobOffer, 'has_future_accepted_jo', return_value=False)
    @patch.object(JobOffer, 'has_previous_jo', return_value=True)
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_has_prev_offers_future_less_than_4day(
        self, mock_task, mock_prev_jo, mock_future_jo, shift, candidate_contact
    ):
        jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        eta = tz.localize(datetime.datetime(2017, 1, 1, 10, 0, 0))

        assert jo.scheduled_sms_datetime == eta
        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_called_with(args=[jo.id], eta=eta)

    @freeze_time(tz.localize(datetime.datetime(2016, 12, 25, 9)))
    @patch.object(JobOffer, 'has_future_accepted_jo', return_value=False)
    @patch.object(JobOffer, 'has_previous_jo', return_value=False)
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_just_added_has_prev_offers_future_more_than_4day(
        self, mock_task, mock_prev_jo, mock_future_jo, shift, candidate_contact
    ):
        jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact
        )

        eta = tz.localize(datetime.datetime(2017, 1, 1, 10, 0, 0))

        assert jo.scheduled_sms_datetime == eta
        mock_task.get_jo_sms_sending_task.return_value.apply_async.assert_called_with(args=[jo.id], eta=eta)

    def test_check_job_quota(self, job_offer):
        res = job_offer.check_job_quota(True)

        assert res
        assert job_offer.status == JobOffer.STATUS_CHOICES.accepted

    @patch.object(JobOffer, 'move_candidate_to_carrier_list')
    def test_check_job_quota_cancelled(self, mock_move, job_offer):
        job_offer.status = JobOffer.STATUS_CHOICES.cancelled
        res = job_offer.check_job_quota(True)

        assert not res
        assert job_offer.status == JobOffer.STATUS_CHOICES.cancelled

    @patch.object(JobOffer, 'move_candidate_to_carrier_list')
    def test_check_job_quota_has_accepted_gt_workers(self, mock_move, accepted_jo, job_offer):
        res = job_offer.check_job_quota(True)

        assert not res
        assert job_offer.status == JobOffer.STATUS_CHOICES.cancelled

    @freeze_time(tz.localize(datetime.datetime(2017, 1, 2, 6)))
    @patch.object(JobOffer, 'move_candidate_to_carrier_list')
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_check_job_quota_has_accepted_gt_workers_gt_now(
        self, mock_task, mock_move, accepted_jo, job_offer
    ):
        res = job_offer.check_job_quota(True)

        assert not res
        assert job_offer.status == JobOffer.STATUS_CHOICES.cancelled
        mock_task.send_jo_rejection.assert_called_with(job_offer)

    @freeze_time(tz.localize(datetime.datetime(2017, 1, 2, 6)))
    @patch.object(TimeSheet, 'get_or_create_for_job_offer_accepted')
    @patch.object(JobOffer, 'move_candidate_to_carrier_list')
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_check_job_quota_has_accepted_gt_workers_gt_now_with_sms_sent(
        self, mock_task, mock_move, mock_create_timesheet, shift, candidate_contact, job_offer, fake_sms
    ):
        accepted_jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact,
            status=JobOffer.STATUS_CHOICES.accepted,
        )
        JobOfferSMS.objects.create(job_offer=accepted_jo, offer_sent_by_sms=fake_sms)

        res = job_offer.check_job_quota(True)

        assert not res
        assert job_offer.status == JobOffer.STATUS_CHOICES.cancelled
        mock_task.send_jo_rejection.assert_called_with(job_offer)

    @freeze_time(tz.localize(datetime.datetime(2017, 1, 2, 6)))
    @patch.object(TimeSheet, 'get_or_create_for_job_offer_accepted')
    @patch.object(JobOffer, 'move_candidate_to_carrier_list')
    @patch('r3sourcer.apps.hr.models.hr_utils')
    def test_check_job_quota_has_accepted_gt_workers_gt_now_with_sms_sent_self(
        self, mock_task, mock_move, mock_create_timesheet, shift, candidate_contact, fake_sms
    ):
        accepted_jo = JobOffer.objects.create(
            shift=shift,
            candidate_contact=candidate_contact,
            status=JobOffer.STATUS_CHOICES.accepted,
        )
        JobOfferSMS.objects.create(job_offer=accepted_jo, offer_sent_by_sms=fake_sms)

        res = accepted_jo.check_job_quota(True)

        assert not res
        assert accepted_jo.status == JobOffer.STATUS_CHOICES.cancelled
        mock_task.send_jo_rejection.assert_called_with(accepted_jo)

    def test_check_job_quota_not_initial(self, job_offer):
        assert job_offer.check_job_quota(False)


class TestTimeSheetIssue:

    def test_str(self, timesheet):
        timesheet_issue = TimeSheetIssue(time_sheet=timesheet, subject='test')
        assert str(timesheet_issue) == '01/01/2017 07:00 AM  : test'

    def test_get_closest_company(self, timesheet_issue, master_company):
        assert timesheet_issue.get_closest_company() == master_company


@pytest.mark.django_db
class TestCarrierList:

    def test_str(self, carrier_list, candidate_contact):
        assert str(carrier_list) == '{}: {}'.format(
            candidate_contact,
            date_format(carrier_list.target_date, settings.DATE_FORMAT)
        )

    def test_confirm(self, carrier_list):
        assert not carrier_list.confirmed_available
        carrier_list.confirm()
        assert carrier_list.confirmed_available

    def test_deny(self, carrier_list):
        carrier_list.confirmed_available = True
        assert carrier_list.confirmed_available
        carrier_list.deny()
        assert not carrier_list.confirmed_available

    @mock.patch('r3sourcer.apps.hr.tasks.send_carrier_list_offer_sms.apply_async')
    def test_sending_offer_after_saving(self, mocked_send, candidate_contact, job_offer, skill1):
        carrier_list = CarrierList.objects.create(
            candidate_contact=candidate_contact,
            skill=skill1,
            target_date=utc_tomorrow()
        )
        mocked_send.assert_called_once_with(args=[carrier_list.id], countdown=5)


@pytest.mark.django_db
class TestCandidateEvaluation:
    @pytest.mark.parametrize('evaluation,expected', [
        (CandidateEvaluation(was_on_time=True), 0.5),
        (CandidateEvaluation(was_on_time=True, evaluation_score=1), 1),
        (CandidateEvaluation(was_on_time=True, evaluation_score=2), 1.5),
        (CandidateEvaluation(was_on_time=True, evaluation_score=3), 2),
        (CandidateEvaluation(was_on_time=True, evaluation_score=4), 2.5),
        (CandidateEvaluation(was_on_time=True, evaluation_score=5), 3),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True), 1),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             evaluation_score=1), 1.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             evaluation_score=5), 3.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True), 1.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True, met_expectations=True), 2),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True, met_expectations=True,
                             representation=True), 2.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True, met_expectations=True,
                             representation=True,
                             evaluation_score=5), 5),
        (CandidateEvaluation(evaluation_score=5), 0),
        (CandidateEvaluation(evaluation_score=0), 0),
    ])
    def test_get_rating(self, evaluation, expected):
        assert evaluation.get_rating() == expected

    @pytest.mark.parametrize('evaluation,expected', [
        (CandidateEvaluation(was_on_time=True), 0.5),
        (CandidateEvaluation(was_on_time=True, evaluation_score=1), 1),
        (CandidateEvaluation(was_on_time=True, evaluation_score=2), 1.5),
        (CandidateEvaluation(was_on_time=True, evaluation_score=3), 2),
        (CandidateEvaluation(was_on_time=True, evaluation_score=4), 2.5),
        (CandidateEvaluation(was_on_time=True, evaluation_score=5), 3),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True), 1),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             evaluation_score=1), 1.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             evaluation_score=5), 3.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True), 1.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True, met_expectations=True), 2),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True, met_expectations=True,
                             representation=True), 2.5),
        (CandidateEvaluation(was_on_time=True, had_ppe_and_tickets=True,
                             was_motivated=True, met_expectations=True,
                             representation=True,
                             evaluation_score=5), 5),
        (CandidateEvaluation(evaluation_score=5), 2.5),
        (CandidateEvaluation(evaluation_score=0), 0),
    ])
    def test_single_evaluation_average(self, evaluation, expected):
        assert evaluation.single_evaluation_average() == expected


@pytest.mark.django_db
class TestBlackList:

    def test_str(self, black_list, master_company, candidate_contact):
        assert str(black_list) == '{}: {}'.format(master_company, candidate_contact)

    def test_save_set_jobsite(self, black_list, timesheet, jobsite,
                              company_contact):
        black_list.timesheet = timesheet
        black_list.company_contact = company_contact
        black_list.clean()
        black_list.save()

        assert black_list.jobsite == jobsite

    def test_save_set_supervisor(self, black_list, timesheet, jobsite,
                                 company_contact):
        black_list.timesheet = timesheet
        black_list.jobsite = jobsite
        black_list.clean()
        black_list.save()

        assert black_list.company_contact == company_contact

    @patch.object(BlackList, 'objects', new_callable=PropertyMock)
    def test_clean(self, mock_objects, black_list):
        mock_objects.return_value.filter.return_value = MockSet(MockModel())

        with pytest.raises(ValidationError):
            black_list.clean()


@pytest.mark.django_db
class TestFavouriteList:

    def test_str(self, favourite_list, company_contact, candidate_contact):
        assert str(favourite_list) == '{}: {}'.format(company_contact, candidate_contact)

    def test_save_set_company(self, favourite_list, jobsite, master_company):
        favourite_list.jobsite = jobsite
        favourite_list.clean()
        favourite_list.save()

        assert favourite_list.company == master_company

    def test_save_set_jobsite(self, favourite_list, job, jobsite, master_company):
        favourite_list.job = job
        favourite_list.clean()
        favourite_list.save()

        assert favourite_list.jobsite == jobsite
        assert favourite_list.company == master_company

    @patch.object(FavouriteList, 'objects', new_callable=PropertyMock)
    def test_clean(self, mock_objects, favourite_list):
        mock_objects.return_value.filter.return_value = MockSet(MockModel())

        with pytest.raises(ValidationError):
            favourite_list.clean()
