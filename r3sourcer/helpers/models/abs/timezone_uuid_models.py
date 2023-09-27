from .timezone_models import TimeZone
from .uuid_models import UUIDModel


class TimeZoneUUIDModel(TimeZone, UUIDModel):
    class Meta:
        abstract = True

    @property
    def geo(self):
        raise NotImplementedError

    @property
    def created_at_tz(self):
        return self.utc2local(self.created_at)

    @property
    def updated_at_tz(self):
        return self.utc2local(self.updated_at)

    @property
    def created_at_utc(self):
        return self.created_at

    @property
    def updated_at_utc(self):
        return self.updated_at
