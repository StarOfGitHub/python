from datetime import datetime, timedelta, time

from django.conf import settings
from django.db import models
from django.utils.formats import time_format
from django.utils.translation import ugettext_lazy as _

from r3sourcer.helpers.models.abs import UUIDModel
from ..utils.utils import format_timedelta
from ..exceptions import RateNotApplicable


WEEKDAY_MAP = {
    0: 'monday',
    1: 'tuesday',
    2: 'wednesday',
    3: 'thursday',
    4: 'friday',
    5: 'saturday',
    6: 'sunday',
}


class WorkRuleMixin(models.Model):

    default_priority = 0

    class Meta:
        abstract = True

    def calc_hours(self, start_datetime, worked_hours, break_started=None,
                   break_ended=None):
        raise NotImplementedError


class AllowanceMixin(WorkRuleMixin):

    class Meta:
        abstract = True

    def __str__(self):
        return str(_('Allowance: {}'.format(self.allowance_description or 'yes')))

    def calc_hours(self, start_datetime, worked_hours, break_started=None,
                   break_ended=None):
        return timedelta(hours=-1)


class WeekdayWorkRule(WorkRuleMixin, UUIDModel):
    """
    Used for weekday
    """

    default_priority = 10

    weekday_monday = models.BooleanField(
        verbose_name=_('Monday'),
        default=False
    )

    weekday_tuesday = models.BooleanField(
        verbose_name=_('Tuesday'),
        default=False
    )

    weekday_wednesday = models.BooleanField(
        verbose_name=_('Wednesday'),
        default=False
    )

    weekday_thursday = models.BooleanField(
        verbose_name=_('Thursday'),
        default=False
    )

    weekday_friday = models.BooleanField(
        verbose_name=_('Friday'),
        default=False
    )

    weekday_saturday = models.BooleanField(
        verbose_name=_('Saturday'),
        default=False
    )

    weekday_sunday = models.BooleanField(
        verbose_name=_('Sunday'),
        default=False
    )

    weekday_bank_holiday = models.BooleanField(
        verbose_name=_('Bank Holiday'),
        default=False
    )

    class Meta:
        verbose_name = _('Weekday Work Rule')
        verbose_name_plural = _('Weekday Work Rules')

    def __str__(self):
        weekday_list = (
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday',
            'sunday', 'bank_holiday'
        )
        weekday_str = ', '.join([
            wd[:3] for wd in weekday_list if getattr(self, 'weekday_%s' % wd)
        ])
        return str(_('Rule for: {}'.format(weekday_str)))

    def calc_hours(self, start_datetime, worked_hours, break_started=None,
                   break_ended=None):
        weekday = WEEKDAY_MAP[
            start_datetime.weekday()
        ]

        if not getattr(self, 'weekday_' + weekday):
            raise RateNotApplicable()

        return timedelta()


class OvertimeWorkRule(WorkRuleMixin, UUIDModel):
    """
    Used for overtime
    """

    default_priority = 20

    overtime_hours_from = models.DurationField(
        verbose_name=_('Lower Overtime Hours Threshold'),
        default=timedelta,
        help_text=_('Format: (HH:MM:SS)')
    )

    overtime_hours_to = models.DurationField(
        verbose_name=_('Upper Overtime Hours Threshold'),
        default=timedelta,
        help_text=_('Format: (HH:MM:SS)')
    )

    class Meta:
        verbose_name = _('Overtime Work Rule')
        verbose_name_plural = _('Overtime Work Rules')

    def __str__(self):
        overtime_str = format_timedelta(self.overtime_hours_from)
        if self.overtime_hours_to > timedelta():
            overtime_str = '{} to {}'.format(
                overtime_str,
                format_timedelta(self.overtime_hours_to)
            )
        return str(_('Overtime: from {}'.format(overtime_str)))

    def calc_hours(self, start_datetime, worked_hours, break_started=None,
                   break_ended=None):
        # if overtime in available range
        if self.overtime_hours_from < worked_hours <= self.overtime_hours_to:
            worked_delta = worked_hours - self.overtime_hours_from

        # if overtime more then hours_to (more than max)
        elif worked_hours > self.overtime_hours_to:
            worked_delta = self.overtime_hours_to - self.overtime_hours_from
        else:
            worked_delta = timedelta()
        return worked_delta


class TimeOfDayWorkRule(WorkRuleMixin, UUIDModel):
    """
    Used for time of day
    """

    time_start = models.TimeField(
        verbose_name=_("Time From"),
        default=time(hour=18)
    )

    time_end = models.TimeField(
        verbose_name=_("Time To"),
        default=time(hour=6)
    )

    class Meta:
        verbose_name = _('Time of Day Work Rule')
        verbose_name_plural = _('Time of Day Work Rules')

    def __str__(self):
        times_str = '{} - {}'.format(
            time_format(self.time_start, settings.TIME_FORMAT),
            time_format(self.time_end, settings.TIME_FORMAT),
        )
        return str(_('Time of Day: {}'.format(times_str)))

    @property
    def default_priority(self):
        if self.time_start > self.time_end:
            return 35
        return 30

    def calc_hours(self, start_datetime, worked_hours, break_started=None,
                   break_ended=None):
        break_delta = timedelta()
        if break_started and break_ended:
            break_delta = break_ended - break_started

        worked_delta = timedelta()

        # calc started_at and ended_at for time sheet
        start_date = start_datetime.date()
        ended = start_datetime + worked_hours + break_delta

        # get rate start time
        rate_start = datetime.combine(start_date, self.time_start).replace(tzinfo=start_datetime.tzinfo)

        # calc rate started_at and ended_at
        if self.time_end < self.time_start:
            rate_end = datetime.combine(start_date + timedelta(days=1),
                                        self.time_end).replace(tzinfo=start_datetime.tzinfo)
        else:
            rate_end = datetime.combine(start_date, self.time_end).replace(tzinfo=start_datetime.tzinfo)

        # calc break timedelta
        break_delta = timedelta()
        if break_started and break_ended:
            # if break started in rate time range
            if rate_start <= break_started <= rate_end:
                # if break ended in rate time range
                if break_ended <= rate_end:
                    break_delta = break_ended - break_started
                else:
                    break_delta = rate_end - break_started
            elif break_started < rate_start:
                if rate_start <= break_ended <= rate_end:
                    break_delta = break_ended - rate_start
                elif break_ended > rate_end:
                    break_delta = rate_end - rate_start

        # if started at in rate time range
        if rate_start <= start_datetime <= rate_end:
            if ended <= rate_end:
                worked_delta = ended - start_datetime
            else:
                worked_delta = rate_end - start_datetime
        elif start_datetime < rate_start:
            if rate_start <= ended <= rate_end:
                worked_delta = ended - rate_start
            elif ended > rate_end:
                worked_delta = rate_end - rate_start

        if worked_delta.seconds > 0:
            worked_delta = worked_delta - break_delta

        return worked_delta


class AllowanceWorkRule(AllowanceMixin, UUIDModel):
    """
    Used for allowances
    """

    default_priority = 50

    allowance_description = models.TextField(
        max_length=255,
        blank=True,
        verbose_name=_("Allowance Description"),
        help_text=_("Examples: Travel Allowance, Waiting Hours, etc.")
    )

    class Meta:
        verbose_name = _('Allowance Work Rule')
        verbose_name_plural = _('Allowance Work Rules')


__all__ = [
    'WorkRuleMixin', 'AllowanceMixin', 'WeekdayWorkRule', 'OvertimeWorkRule',
    'TimeOfDayWorkRule', 'AllowanceWorkRule',
]

all_rules = [rule.lower() for rule in __all__]
