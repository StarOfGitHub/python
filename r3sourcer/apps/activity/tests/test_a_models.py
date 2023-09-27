import pytest

from celery import schedules
from django.conf import settings
from django.utils import timezone
from django.utils.formats import date_format

from freezegun import freeze_time
from redbeat import RedBeatSchedulerEntry

from r3sourcer.apps.core.service import factory

from r3sourcer.apps.activity.models import ActivityDate


@pytest.mark.django_db
class TestActivityModels:

    def test_related_entity(self, primary_activity, primary_contact):
        factored_name = 'PrimaryContact'
        factory.register(factored_name, type(primary_contact))

        primary_activity.entity_object = primary_contact
        assert primary_activity.entity_object
        assert primary_activity.get_related_entity() == primary_contact
        assert primary_activity.entity_object_id == primary_contact.id
        assert primary_activity.entity_object_name == factored_name

    @freeze_time('2200, 1, 2')
    def test_overdue_activity(self, primary_activity):
        assert primary_activity.get_overdue()

    @freeze_time('2017-01-02')
    def test_not_overdue_activity1(self, primary_activity):
        assert not primary_activity.get_overdue()

    @freeze_time('2017-01-01 00:00')
    def test_not_overdue_activity2(self, primary_activity):
        assert not primary_activity.get_overdue()

    def test_get_duration(self, primary_activity):
        assert primary_activity.get_duration().days == 4

    def test_activity_dates(self, activity_date):

        assert activity_date.activity is None

        activity_date.occur()

        assert activity_date.activity is not None
        assert activity_date.activity.template == activity_date.activity_repeat.activity.template
        assert activity_date.is_occurred()
        assert activity_date.status == ActivityDate.STATUS_CHOICES.OCCURRED
        assert not activity_date.error_text

    def test_already_occurred(self, activity_date):

        assert activity_date.activity is None

        activity_date.occur()

        assert activity_date.is_occurred()
        assert activity_date.status == ActivityDate.STATUS_CHOICES.OCCURRED

        with pytest.raises(AssertionError) as exc_info:
            activity_date.occur()

        assert exc_info.match(r'.*Activity date already occurred.*')
        assert activity_date.is_occurred()
        assert activity_date.status == ActivityDate.STATUS_CHOICES.OCCURRED

    def test_not_occurred_activity_date(self, activity_date):

        assert activity_date.activity is None
        assert not activity_date.is_occurred()
        assert not activity_date.activity
        assert activity_date.status == ActivityDate.STATUS_CHOICES.WAITING

    def test_repeater_schedule_interval(self, repeater_interval1):

        assert repeater_interval1.activity

        task = repeater_interval1.create_periodic_task()

        assert task
        assert isinstance(task, RedBeatSchedulerEntry)

    def test_repeater_interval(self, repeater_interval2):

        assert repeater_interval2.activity

        task = repeater_interval2.create_periodic_task()

        assert task
        assert isinstance(task, schedules.schedule)
        every_seconds = timezone.timedelta(minutes=repeater_interval2.minute)
        assert task.run_every == every_seconds

    def test_repeater_schedule(self, repeater_schedule):

        assert repeater_schedule.activity

        task = repeater_schedule.create_periodic_task()

        assert task
        assert isinstance(task, schedules.crontab)
        assert task.hour == {repeater_schedule.hour}
        assert task.minute == {repeater_schedule.minute}

    def test_activity_str(self, primary_activity):
        result_str = '{} - {}: {}'.format(
            date_format(timezone.localtime(primary_activity.starts_at), settings.DATETIME_FORMAT),
            date_format(timezone.localtime(primary_activity.ends_at), settings.DATETIME_FORMAT),
            primary_activity.template.name
        )
        assert str(primary_activity) == result_str

    # TODO: fix test
    # def test_fixed_repeater(self, activity_repeater):

    #     activity_repeater.activate()
    #     assert activity_repeater.periodic_task is None

    # TODO: fix test
    # def test_celery_task_activate(self, repeater_interval1):

    #     repeater_interval1.activate()
    #     assert isinstance(repeater_interval1.periodic_task, PeriodicTask)

    # TODO: fix test
    # def test_celery_task_deactivate(self, repeater_interval1):

    #     repeater_interval1.activate()

    #     repeater_interval1.deactivate()
    #     assert repeater_interval1.periodic_task is None

    #     repeater_interval1.refresh_from_db()
    #     assert repeater_interval1.periodic_task is None

    # TODO: fix test
    # def test_create_celery_task_method_ret(self, repeater_interval1):

    #     assert isinstance(repeater_interval1.create_tasks(), PeriodicTask)

    # TODO: fix test
    # def test_create_celery_task_method_db(self, repeater_interval1):

    #     repeater_interval1.create_tasks()

    #     with pytest.raises(app_exceptions.PeriodicTaskAlreadyExists) as exc_info:
    #         repeater_interval1.create_tasks()

    #     assert exc_info.match(r'.*Periodic task already exists*.')
