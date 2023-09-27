import calendar
from datetime import timedelta

from celery import schedules
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _
from model_utils.choices import Choices
from redbeat import RedBeatSchedulerEntry

from r3sourcer import ref
from r3sourcer.apps.activity.exceptions import PeriodNameError
from r3sourcer.apps.activity.fields import FactoryLookupField
from r3sourcer.helpers.models.abs import TemplateMessage, UUIDModel, TimeZoneUUIDModel
from r3sourcer.apps.core.service import FactoryException, factory
from r3sourcer.celeryapp import app as celery_app


class Activity(TimeZoneUUIDModel):

    PRIORITY_CHOICES = Choices(
        (1, 'BOTTOM_PRIORITY', _("Bottom")),
        (2, 'LOW_PRIORITY', _("Low")),
        (3, 'NORMAL_PRIORITY', _("Normal")),
        (4, 'HIGH_PRIORITY', _("High")),
        (5, 'TOP_PRIORITY', _("Top"))
    )

    STATUS_CHOICES = Choices(
        (None, 'NEW', _("New")),
        (False, 'SEEN', _("SEEN")),
        (True, 'DONE', _("Done")),
    )

    DEFAULT_PRIORITY = PRIORITY_CHOICES.NORMAL_PRIORITY

    UNRELATED_TYPE = None

    priority = models.SmallIntegerField(
        _("Priority"),
        default=DEFAULT_PRIORITY,
        choices=PRIORITY_CHOICES
    )

    entity_object_id = models.UUIDField(
        _("Related entity id"),
        default=None,
        null=True,
        editable=False
    )

    entity_object_name = models.CharField(
        _("object name"),
        max_length=128,
        default='',
        editable=False
    )

    entity_object = FactoryLookupField('entity_object_name', 'entity_object_id')

    contact = models.ForeignKey(
        'core.Contact',
        verbose_name=_("Contact"),
        on_delete=models.CASCADE
    )

    starts_at = ref.DTField(_("Starts at"))
    ends_at = ref.DTField(_("Ends at"))

    done = models.NullBooleanField(
        _("Done"),
        default=STATUS_CHOICES.NEW,
        choices=STATUS_CHOICES
    )

    template = models.ForeignKey(
        'activity.ActivityTemplate',
        verbose_name=_("Template"),
        on_delete=models.CASCADE
    )

    involved_contacts = models.ManyToManyField(
        'core.Contact',
        related_name="involved_in_activities",
        verbose_name=_("Involved Contacts"),
        blank=True
    )

    @property
    def geo(self):
        raise NotImplementedError

    @property
    def starts_at_tz(self):
        return self.utc2local(self.starts_at)

    @property
    def starts_at_utc(self):
        return self.starts_at

    @property
    def ends_at_tz(self):
        return self.utc2local(self.ends_at)

    @property
    def ends_at_utc(self):
        return self.ends_at

    def __str__(self):
        _starts_at = date_format(self.starts_at, settings.DATETIME_FORMAT)
        _ends_at = date_format(self.ends_at, settings.DATETIME_FORMAT)
        if self.starts_at and self.ends_at and self.starts_at.date() == self.ends_at.date():
            if self.starts_at.date() == self.now_utc.date():
                return self.template.name

            return '{}: {}'.format(_starts_at, self.template.name)
        return '{} - {}: {}'.format(_starts_at, _ends_at, self.template.name)

    class Meta:
        verbose_name = _("Activity")
        verbose_name_plural = _("Activities")

    def get_duration(self):
        return self.ends_at - self.starts_at

    def get_related_entity(self):
        try:
            return factory.get_instance_class(self.entity_object_name, fail_fast=True).objects.get(
                pk=self.entity_object_id
            )
        except (FactoryException, models.ObjectDoesNotExist):
            return None

    def render(self):
        """
        Render activity template

        :return text: str Rendered template text
        """

        raise NotImplementedError

    def get_overdue(self):
        return self.ends_at < self.now_utc and not self.done

    def save(self, *args, **kwargs):
        if not self.starts_at:
            self.starts_at = self.now_utc
        super().save(*args, **kwargs)


class ActivityDate(TimeZoneUUIDModel):

    STATUS_CHOICES = Choices(
        (True, 'OCCURRED', _("Occurred")),
        (False, 'FAIL', _("Fail")),
        (None, 'WAITING', _("Waiting for occur")),
    )

    DEFAULT_STATUS_CHOICES = STATUS_CHOICES.WAITING

    occur_at = ref.DTField(_("Occur at"))

    activity_repeat = models.ForeignKey(
        'activity.ActivityRepeat',
        related_name='repeat_dates',
        verbose_name=_("Activity repeater"),
        on_delete=models.PROTECT
    )

    activity = models.ForeignKey(
        'activity.Activity',
        default=None,
        blank=True,
        null=True,
        related_name='occur_dates',
        on_delete=models.PROTECT
    )

    status = models.NullBooleanField(
        _("Status"),
        default=DEFAULT_STATUS_CHOICES,
        choices=STATUS_CHOICES
    )

    error_text = models.TextField(
        _("Error occurred details"),
        default="",
        blank=True
    )

    @property
    def geo(self):
        raise NotImplementedError

    @property
    def occur_at_tz(self):
        return self.utc2local(self.occur_at)

    @property
    def occur_at_utc(self):
        return self.occur_at

    def __str__(self):
        return str(self.occur_at)

    def is_occurred(self):
        return self.status != self.STATUS_CHOICES.WAITING

    def occur(self):
        assert not self.is_occurred(), "Activity date already occurred"
        try:
            self.activity = self.activity_repeat.occur()
            self.status = self.STATUS_CHOICES.OCCURRED
        except Exception as e:
            self.error_text = str(e)
            self.status = self.STATUS_CHOICES.FAIL
        self.save()

    class Meta:
        verbose_name = _("Activity schedule date")
        verbose_name_plural = _("Activity schedule dates")


class ActivityRepeat(TimeZoneUUIDModel):
    TASK_KEY = 'periodic_task:{}'
    TASK_NAME = 'activity.tasks.activity_handler'

    REPEAT_CHOICES = Choices(
        ('FIXED', _("Fixed")),
        ('INTERVAL', _("Interval")),
        ('SCHEDULE', _("Schedule")),
    )
    DEFAULT_REPEAT_CHOICE = REPEAT_CHOICES.FIXED

    PERIODIC_TYPE = Choices(
        ('monthly', _("Monthly")),
        ('weekly', _("Weekly")),
        ('daily', _("Daily")),
        ('hourly', _("Hourly")),
        ('minutely', _("Minutely")),
        ('secondly', _("Secondly"))
    )
    DEFAULT_PERIODIC_TYPE = PERIODIC_TYPE.daily

    CRON_CHOICES = {
        'MONTH': map(lambda x: (x[0], _(x[1])), enumerate(filter(bool, calendar.month_name))),
        'DAY': Choices(
            (0, 'NONE', _("Undefined")),
            *map(lambda x: (x[0] + 1, x[1]), enumerate(map(_, calendar.day_name)))
        ),
        'DAY_OF_MONTH': map(lambda x: (x, x), range(32)),
        'HOUR': Choices(
            *enumerate(map(lambda x: '{} {}'.format((x % 12) or 12, 'AM' if x < 12 else 'PM'), range(24)))
        ),
        'MINUTE': map(lambda x: (x, x), range(60))
    }

    DEFAULT_CRON_CHOICES = {
        'MONTH': 0,
        'DAY': 0,
        'DAY_OF_MONTH': 0,
        'HOUR': 0,
        'MINUTE': 0
    }

    repeat_type = models.CharField(
        _("Repeat type"),
        max_length=16,
        choices=REPEAT_CHOICES,
        default=DEFAULT_REPEAT_CHOICE
    )

    activity = models.ForeignKey(
        'activity.Activity',
        default=None,
        verbose_name=_("Activity"),
        on_delete=models.CASCADE
    )

    started_at = ref.DTField(_("Started at"))

    base_type = models.CharField(
        _("Schedule type"),
        max_length=16,
        choices=PERIODIC_TYPE,
        default=DEFAULT_PERIODIC_TYPE
    )

    every = models.IntegerField(
        _("Every"),
        default=0
    )

    month_of_year = models.IntegerField(
        _("Month of Year"),
        choices=CRON_CHOICES['MONTH'],
        default=DEFAULT_CRON_CHOICES['MONTH']
    )

    day_of_week = models.IntegerField(
        _("Weekday"),
        choices=CRON_CHOICES['DAY'],
        default=DEFAULT_CRON_CHOICES['DAY']
    )

    day_of_month = models.IntegerField(
        _("Day of month"),
        choices=CRON_CHOICES['DAY_OF_MONTH'],
        default=DEFAULT_CRON_CHOICES['DAY_OF_MONTH']
    )

    hour = models.IntegerField(
        _("Hour"),
        choices=CRON_CHOICES['HOUR'],
        default=DEFAULT_CRON_CHOICES['HOUR']
    )

    minute = models.IntegerField(
        _("Minute"),
        choices=CRON_CHOICES['MINUTE'],
        default=DEFAULT_CRON_CHOICES['MINUTE']
    )

    occurred_activities = models.ManyToManyField(
        'activity.Activity',
        related_name='repeaters',
        editable=False
    )

    tas_key = models.CharField(
        verbose_name=_("Task key"),
        max_length=512,
        default=''
    )

    @property
    def geo(self):
        raise NotImplementedError

    @property
    def started_at_tz(self):
        return self.utc2local(self.started_at)

    @property
    def started_at_utc(self):
        return self.started_at

    def __str__(self):
        if self.activity and self.activity.entity_object_name:
            return '{}: {}'.format(self.activity.entity_object_name,
                                   self.activity.template.name)

        return '{}: {}'.format(self.get_repeat_type_display(),
                               self.activity.template)

    def occur(self):
        activity = self.activity
        new_activity = Activity.objects.create(
            contact=self.activity.contact,
            template_id=self.activity.template_id,
            priority=activity.priority,
            entity_object_id=activity.entity_object_id,
            entity_object_name=activity.entity_object_name,
            ends_at=self.now_utc + (activity.ends_at - activity.starts_at),
        )
        self.occurred_activities.add(new_activity)
        return new_activity

    def create_periodic_task(self):
        if not self.repeat_type:
            return

        f_dict = {}

        if self.repeat_type == self.REPEAT_CHOICES.INTERVAL:
            if self.base_type == self.PERIODIC_TYPE.monthly:
                period = 'days'
                value = self.every * 30
            elif self.base_type == self.PERIODIC_TYPE.weekly:
                period = 'days'
                value = self.every * 7
            elif self.base_type == self.PERIODIC_TYPE.daily:
                period = 'days'
                value = self.every
            elif self.base_type == self.PERIODIC_TYPE.hourly:
                period = 'hours'
                value = self.every
            elif self.base_type == self.PERIODIC_TYPE.minutely:
                period = 'minutes'
                value = self.every
            elif self.base_type == self.PERIODIC_TYPE.secondly:
                period = 'seconds'
                value = self.every
            else:
                raise PeriodNameError(_("Incorrect period name"))
            entry = RedBeatSchedulerEntry(
                self.TASK_KEY.format(self.TASK_NAME),
                self.TASK_NAME,
                schedules.schedule(timedelta(**{period: value})),
                app=celery_app
            )
            self.tas_key = entry.key
            self.save(update_fields=['tas_key'])
            return entry

        if self.base_type == self.PERIODIC_TYPE.monthly:
            f_dict['day_of_month'] = self.day_of_month or '*'
            f_dict['hour'] = self.hour
            f_dict['minute'] = self.minute or '*'

        if self.base_type == self.PERIODIC_TYPE.weekly:
            f_dict['day_of_week'] = self.day_of_week or '*'
            f_dict['hour'] = self.hour
            f_dict['minute'] = self.minute or '*'

        if self.base_type == self.PERIODIC_TYPE.daily:
            f_dict['hour'] = self.hour
            f_dict['minute'] = self.minute or '*'

        if self.base_type == self.PERIODIC_TYPE.hourly:
            f_dict['minute'] = self.minute if self.minute else 1

        if self.base_type == self.PERIODIC_TYPE.minutely:
            f_dict = {
                'period': 'minutes',
                'every': self.minute
            }

        # TODO: return schedule
        if self.base_type in [self.PERIODIC_TYPE.secondly,
                              self.PERIODIC_TYPE.minutely]:
            # return IntervalSchedule(**f_dict)
            return schedules.schedule(timedelta(minutes=f_dict['every']))

        return schedules.crontab(**f_dict)

    def deactivate(self):
        """ Deactivate all activity tasks """
        periodic_task = self.periodic_task
        if periodic_task:
            self.periodic_task = None
            periodic_task.delete()

    def activate(self):
        """ Deactivate all activity tasks """
        self.deactivate()
        self.create_tasks()

    def create_tasks(self):
        if self.repeat_type in [self.REPEAT_CHOICES.INTERVAL, self.REPEAT_CHOICES.SCHEDULE]:
            # TODO: create tasks
            # if self.periodic_task:
            #     raise PeriodicTaskAlreadyExists(_("Periodic task already exists"))

            # s_or_i = self.create_periodic_task()
            # values = dict(
            #     task=self.TASK_NAME,
            #     name='Activity repeater ({}): {}'.format(self.id, self.activity.template.name),
            #     args=json.dumps([str(self.id)]),
            #     enabled=False
            # )

            # s_or_i.save()
            # if isinstance(s_or_i, CrontabSchedule):
            #     values['crontab'] = s_or_i
            # else:
            #     values['interval'] = s_or_i
            # self.periodic_task = PeriodicTask.objects.create(**values)
            # PeriodicTasks.changed(self.periodic_task)
            # self.save(update_fields=['periodic_task_id'])
            # return self.periodic_task
            pass

    def clean(self):
        """
        Validate schedule type

        """
        if self.repeat_type == self.REPEAT_CHOICES.SCHEDULE and \
                self.base_type == self.PERIODIC_TYPE.secondly:
            raise ValidationError({"repeat_type": _("Incorrect type: use `Interval`"),
                                   'base_type': _("Incorrect schedule")})

        if self.repeat_type == self.REPEAT_CHOICES.SCHEDULE and \
                self.base_type == self.PERIODIC_TYPE.minutely:
            raise ValidationError({"repeat_type": _("Incorrect type: use `Interval`"),
                                   'base_type': _("Incorrect schedule")})

    class Meta:
        verbose_name = _("Activity repeat")
        verbose_name_plural = _("Activity repeat")

    def save(self, *args, **kwargs):
        if not self.started_at:
            self.started_at = self.now_utc
        super().save(*args, **kwargs)


class ActivityTemplate(TemplateMessage):
    TYPE_CHOICES = Choices(
        ('ACTIVITY', _("Activity"))
    )

    DEFAULT_TYPE = TYPE_CHOICES.ACTIVITY

    type = models.CharField(
        max_length=8,
        choices=TYPE_CHOICES,
        default=DEFAULT_TYPE,
        verbose_name=_("Type")
    )

    class Meta:
        verbose_name = _("Activity template")
        verbose_name_plural = _("Activity templates")
        ordering = ['name']
