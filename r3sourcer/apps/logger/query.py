import importlib

from django.conf import settings
from django.db import models

from .utils import get_field_value_by_field_name


def get_logger_queryset(self):
    queryset_class = getattr(settings, 'QUERYSET_CLASS', None)

    if queryset_class is not None:
        class_name = queryset_class.split('.')[-1]
        QuerySetClass = getattr(importlib.import_module(queryset_class.rsplit('.', 1)[0]), class_name)
    else:
        QuerySetClass = LoggerQuerySet

    return QuerySetClass(self.model, using=self._db)


class LoggerQuerySet(models.QuerySet):
    def bulk_create(self, objs, batch_size=None):
        """
        Bulk create with logging of the objects' fields which were created
        """
        real_objects = None
        model = None
        old_ids = []
        if objs and len(objs) > 0:
            model = objs[0].__class__
            old_ids = list(model.objects.all().values_list('id', flat=True))

        objs = super().bulk_create(objs, batch_size)

        if objs and len(objs) > 0:
            real_objects = model.objects.exclude(id__in=old_ids)

        if real_objects:
            from .main import endless_logger
            for obj in real_objects:
                endless_logger.log_instance_change(obj, transaction_type='create')
        return objs

    def update(self, **kwargs):
        """
        Bulk update with logging of the objects' fields which were updated
        """
        old_values = []
        for elem in self:
            old_values.append(elem)

        from .main import endless_logger
        rows = super().update(**kwargs)
        for elem in old_values:
            general_logger_fields = endless_logger.get_general_fields(elem, 'update')
            for field_name, field_value in kwargs.items():
                endless_logger.log_update_field(field_name, general_logger_fields,
                                                new_value=field_value,
                                                old_value=get_field_value_by_field_name(elem, field_name))
        return rows

    def delete(self):
        """
        Bulk deletion with logging of the objects' ids which were deleted
        """
        old_values = []
        for elem in self:
            old_values.append(elem)

        from .main import endless_logger
        deleted, _rows_count = super().delete()
        for elem in old_values:
            general_logger_fields = endless_logger.get_general_fields(elem, 'delete')
            endless_logger.log_update_field('id', general_logger_fields,
                                            old_value=elem.id)

        return deleted, _rows_count
