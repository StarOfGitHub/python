from django.conf import settings
from infi.clickhouse_orm.database import Database

from .models import LocationHistory
from ...helpers.datetimes import utc_now


class LocationLogger():

    def __init__(self):
        self.logger_database = Database(
            settings.LOGGER_DB, db_url="http://{}:{}/".format(settings.LOGGER_HOST, settings.LOGGER_PORT),
            username=settings.LOGGER_USER, password=settings.LOGGER_PASSWORD
        )
        self.logger_database.migrate('r3sourcer.apps.logger.clickhouse_migrations')

    def _map_location_log(self, log_instance):
        return {
            'model': log_instance.model,
            'object_id': log_instance.object_id,
            'name': log_instance.name,
            'latitude': log_instance.latitude,
            'longitude': log_instance.longitude,
            'log_at': log_instance.log_at,
            'timesheet_id': log_instance.timesheet_id,
        }

    def get_location_queryset(self):
        return LocationHistory.objects_in(self.logger_database)

    def log_instance_location(self, instance, latitude, longitude, timesheet_id=None, name=None, log_at=None):
        if log_at is None:
            log_at = utc_now()

        log = LocationHistory(
            model=instance._meta.label,
            name=name and str(name),
            object_id=str(instance.pk),
            timesheet_id=timesheet_id and str(timesheet_id),
            latitude=latitude,
            longitude=longitude,
            log_at=log_at,
            date=utc_now().date()
        )
        self.logger_database.insert([log])

    def fetch_location_history(self, instance, **kwargs):
        page_num = kwargs.pop('page_num', 1)
        page_size = kwargs.pop('page_size', 10)

        kwargs['object_id'] = str(instance.pk)

        if 'timesheet_id' in kwargs and kwargs.get('timesheet_id') is None:
            del kwargs['timesheet_id']

        qs = self.get_location_queryset().filter(**kwargs).order_by('-log_at')

        if page_size < 0:
            page_size = qs.count()
            if not page_size:
                page_size = 10
        qs = qs.paginate(
            page_num=page_num, page_size=page_size
        )

        return {
            'results': [self._map_location_log(log) for log in qs.objects],
            'count': qs.number_of_objects,
        }

    def fetch_location_candidates(self, instances=None, **kwargs):
        page_num = kwargs.pop('page_num', 1)
        page_size = kwargs.pop('page_size', 100)

        if instances:
            final_qs = []
            qs_ids = [i.object_id for i in self.get_location_queryset().filter(timesheet_id__in=[str(i) for i in instances]).only('object_id').distinct()]
            for id in qs_ids:
                qs = self.get_location_queryset().filter(object_id=id, timesheet_id__in=[str(i) for i in instances]).order_by('-log_at')
                qs = qs.paginate(
                    page_num=1, page_size=1
                    )
                final_qs.extend(qs.objects)

            return {
                'results': [self._map_location_log(log) for log in final_qs],
                'count': len(final_qs),
            }
        else:
            if kwargs.get('return_all'):
                final_qs = []
                qs_ids = [i.object_id for i in self.get_location_queryset().only('object_id').distinct()]
                for id in qs_ids:
                    qs = self.get_location_queryset().filter(object_id=id).exclude(timesheet_id='').order_by('-log_at')
                    qs = qs.paginate(
                        page_num=1, page_size=1
                        )
                    final_qs.extend(qs.objects)

                return {
                    'results': [self._map_location_log(log) for log in final_qs],
                    'count': len(final_qs),
                    }
            else:
                return {
                    'results': [],
                    'count': 0,
                    }
