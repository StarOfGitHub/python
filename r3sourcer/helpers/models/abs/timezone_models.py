from datetime import datetime, timedelta

import pytz
from django.db import models
from django.utils.functional import cached_property
from django_mock_queries.constants import ObjectDoesNotExist

from r3sourcer.helpers.datetimes import datetime2timezone, geo_time_zone, tz2utc, utc2local


class TimeZone(models.Model):
    class Meta:
        abstract = True

    @property
    def geo(self):
        raise NotImplementedError

    @cached_property
    def tz(self):
        try:
            coord = self.geo
        except ObjectDoesNotExist:
            coord = -0.118092, 51.509865
        return geo_time_zone(*coord)

    @property
    def timezone(self):
        return self.tz.zone

    @property
    def today_tz(self):
        return self.now_tz.date()

    @property
    def tomorrow_tz(self):
        return self.now_tz + timedelta(days=1)

    @property
    def tomorrow_utc(self):
        return self.now_utc + timedelta(days=1)

    @property
    def in_two_weeks_utc(self):
        return self.now_utc + timedelta(days=14)

    @property
    def today_utc(self):
        return self.now_utc.date()

    @property
    def now_tz(self):
        return datetime.now(self.tz)

    @property
    def now_utc(self):
        return datetime.now(pytz.utc)

    def utc2local(self, dt):
        if dt is not None:
            return utc2local(dt, self.tz)

    @classmethod
    def local2utc(cls, dt):
        return tz2utc(dt)

    def dt2utc(self, dt):
        return datetime2timezone(dt, pytz.utc)

    def dt2local(self, dt):
        return datetime2timezone(dt, self.tz)
