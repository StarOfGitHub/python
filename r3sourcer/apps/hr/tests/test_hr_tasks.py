import uuid

from datetime import datetime

import freezegun
import mock
import pytest

from django.conf import settings as dj_settings

from pytz import timezone

from r3sourcer.apps.hr import tasks as hr_tasks, models as hr_models

tz = timezone(dj_settings.TIME_ZONE)


@pytest.mark.django_db
class TestVOTasks:

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 7)))
    @mock.patch('r3sourcer.apps.hr.tasks.get_sms_service')
    def test_send_job_offer_sms(self, mock_sms_service, job_offer):
        hr_tasks.send_job_offer(job_offer, 'job-offer-1st')

        assert mock_sms_service.return_value.send_tpl.called

    @mock.patch('r3sourcer.apps.hr.tasks.get_sms_service', side_effect=ImportError)
    def test_send_job_offer_sms_no_sms_service(self, mock_sms_service, job_offer):
        hr_tasks.send_job_offer(job_offer, 'tpl')

        assert not mock_sms_service.return_value.send_tpl.called

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 2, 9)))
    @mock.patch('r3sourcer.apps.hr.tasks.get_sms_service')
    def test_send_job_offer_sms_asap(self, mock_sms_service, job_offer):
        hr_tasks.send_job_offer(job_offer, 'tpl')

        assert mock_sms_service.return_value.send_tpl.called

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 7)))
    @mock.patch('r3sourcer.apps.hr.tasks.get_sms_service')
    def test_send_job_offer_sms_action_sent(self, mock_sms_service, job_offer, fake_sms):
        mock_sms_service.return_value.send_tpl.return_value = fake_sms

        hr_tasks.send_job_offer(job_offer, 'tpl', action_sent='offer_sent_by_sms')

        assert mock_sms_service.return_value.send_tpl.called
        assert job_offer.scheduled_sms_datetime is None
        assert job_offer.job_offer_smses.exists()

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 18, 0)))
    @mock.patch.object(hr_models.JobOffer, 'has_timesheets_with_going_work_unset_or_timeout', return_value=True)
    @mock.patch('r3sourcer.apps.hr.tasks.send_job_offer')
    def test_send_or_schedule_job_offer_sms(self, mock_send_sms, mock_jo_ts_unset, job_offer):
        hr_tasks.send_or_schedule_job_offer(
            job_offer.id, mock.MagicMock(), action_sent='offer_sent_by_sms'
        )

        assert mock_send_sms.called

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 7)))
    @mock.patch.object(hr_models.JobOffer, 'has_timesheets_with_going_work_unset_or_timeout', return_value=True)
    @mock.patch('r3sourcer.apps.hr.tasks.send_job_offer')
    def test_send_or_schedule_job_offer_sms_rescheduled(self, mock_send_sms, mock_jo_ts_unset, job_offer):
        task_mock = mock.MagicMock()
        hr_tasks.send_or_schedule_job_offer(job_offer.id, task_mock, action_sent='offer_sent_by_sms')

        assert task_mock.apply_async.called

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 14, 30)))
    @mock.patch.object(hr_models.JobOffer, 'has_timesheets_with_going_work_unset_or_timeout', return_value=True)
    @mock.patch('r3sourcer.apps.hr.tasks.send_job_offer')
    def test_send_or_schedule_job_offer_sms_reschedule_from_16_to_17(
        self, mock_send_sms, mock_jo_ts_unset, job_offer
    ):
        task_mock = mock.MagicMock()
        hr_tasks.send_or_schedule_job_offer(job_offer.id, task_mock, action_sent='offer_sent_by_sms')

        assert task_mock.apply_async.called

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 7)))
    @mock.patch.object(hr_models.JobOffer, 'has_timesheets_with_going_work_unset_or_timeout', return_value=True)
    @mock.patch('r3sourcer.apps.hr.tasks.send_job_offer')
    def test_send_or_schedule_job_offer_sms_no_task(self, mock_send_sms, mock_jo_ts_unset, job_offer):
        hr_tasks.send_or_schedule_job_offer(job_offer.id, action_sent='offer_sent_by_sms')

        assert not mock_send_sms.apply_async.called

    @freezegun.freeze_time(tz.localize(datetime(2016, 1, 1, 7)))
    @mock.patch.object(hr_models.JobOffer, 'has_timesheets_with_going_work_unset_or_timeout', return_value=False)
    def test_send_or_schedule_job_offer_sms_future_night_shift(
        self, mock_jo_ts_unset, job_offer_tomorrow_night
    ):
        task_mock = mock.MagicMock()
        hr_tasks.send_or_schedule_job_offer(
            job_offer_tomorrow_night.id, task_mock, action_sent='offer_sent_by_sms'
        )

        assert task_mock.apply_async.called

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 2, 7)))
    @mock.patch.object(hr_models.JobOffer, 'has_timesheets_with_going_work_unset_or_timeout', return_value=False)
    @mock.patch('r3sourcer.apps.hr.tasks.send_job_offer')
    def test_send_or_schedule_job_offer_sms_today_shift(self, mock_send_sms, mock_jo_ts_unset, job_offer):
        hr_tasks.send_or_schedule_job_offer(job_offer.id, action_sent='offer_sent_by_sms')

        assert mock_send_sms.called

    @mock.patch('r3sourcer.apps.hr.tasks.logger', new_callable=mock.PropertyMock())
    def test_send_or_schedule_job_offer_no_jo(self, mock_logger):
        hr_tasks.send_or_schedule_job_offer(uuid.uuid4(), action_sent='offer_sent_by_sms')

        assert mock_logger.error.called

    @mock.patch('r3sourcer.apps.hr.tasks.logger', new_callable=mock.PropertyMock())
    def test_send_or_schedule_job_offer_already_accepted(self, mock_logger, accepted_jo):
        hr_tasks.send_or_schedule_job_offer(accepted_jo.id, action_sent='offer_sent_by_sms')

        assert mock_logger.info.called

    @mock.patch('r3sourcer.apps.hr.tasks.send_job_offer')
    @mock.patch('r3sourcer.apps.hr.tasks.logger', new_callable=mock.PropertyMock())
    def test_send_or_schedule_job_offer_already_cancelled(self, mock_logger, mock_send, cancelled_jo):
        hr_tasks.send_or_schedule_job_offer(cancelled_jo.id, action_sent='offer_sent_by_sms')

        assert mock_send.called

    @mock.patch('r3sourcer.apps.hr.tasks.send_or_schedule_job_offer')
    def test_send_jo_confirmation(self, mock_send, job_offer):
        hr_tasks.send_jo_confirmation(job_offer.id)

        mock_send.assert_called_with(
            job_offer.id, hr_tasks.send_jo_confirmation,
            tpl_id='job-offer-1st', action_sent='offer_sent_by_sms'
        )

    @mock.patch('r3sourcer.apps.hr.tasks.send_or_schedule_job_offer')
    def test_send_recurring_jo_confirmation(self, mock_send, job_offer):
        hr_tasks.send_recurring_jo_confirmation(job_offer.id)

        mock_send.assert_called_with(
            job_offer.id, hr_tasks.send_recurring_jo_confirmation,
            tpl_id='job-offer-recurring', action_sent='offer_sent_by_sms'
        )
