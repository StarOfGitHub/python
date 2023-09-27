from datetime import date, datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.formats import date_format
from infi.clickhouse_orm.database import Database
from infi.clickhouse_orm.fields import DateTimeField

from .models import LogHistory
from .utils import get_current_user, get_field_value, format_range
from ...helpers.datetimes import utc_now


def get_endless_logger():
    return ClickHouseLogger()


class EndlessLogger(object):
    def log_instance_change(self, instance, old_instance=None, user=None, transaction_type='update'):
        """
        Logs changes of the instance
        :param instance: instance
        :param old_instance: old instance if exists
        :param transaction_type: type of the transaction operation
        """
        if transaction_type == 'create' and isinstance(instance, get_user_model())\
                and instance.email == settings.SYSTEM_USER:
            return
        general_logger_fields = self.get_general_fields(instance, transaction_type, user)
        method_name = "log_{}_instance".format(transaction_type)
        getattr(self, method_name)(instance, general_logger_fields, old_instance)

    def log_create_instance(self, instance, general_logger_fields, old_instance=None):
        raise NotImplementedError

    def log_update_instance(self, instance, general_logger_fields, old_instance):
        raise NotImplementedError

    def log_delete_instance(self, instance, general_logger_fields, old_instance):
        raise NotImplementedError

    def log_update_field(self, field_name, general_logger_fields, new_value='', old_value=''):
        """
         Logs changes of the one field
         :param field_name: name of the field
         :param general_logger_fields: dictionary of the general field settings
         :param new_value: new value of the field
         :param old_value: old value of the field
         """
        raise NotImplementedError

    def get_general_fields(self, instance, transaction_type, user=None):
        """
        Generates dictionary with general fields for instance logging
        """
        current_user = get_current_user()
        general_logger_fields = {
            'updated_by': user if user else str(current_user.id if current_user else None),
            'date': date.today(),
            'updated_at': int(round(utc_now().timestamp() * 1000)),
            'model': "{}.{}".format(instance.__class__.__module__, instance.__class__.__name__),
            'object_id': str(instance.id) if hasattr(instance, 'id') else '',
            'transaction_type': transaction_type
        }
        return general_logger_fields

    def get_object_history(self, model, object_id=None, by_user=None, from_date=None, to_date=None, desc=True,
                           offset=0, limit=None):
        """
        Gets history of the model or object and return it in structured view
        :param model: model of the object
        :param object_id: id of the object for retrieving
        :param by_user: id of the user who has changed the object
        :param from_date: from date of the changes
        :param to_date: to date of the changes
        :param desc: ordering of the result
        :param offset: offset for result searching
        :param limit: amount of rows for retrieving
        :rtype: list
        :return: :list: [{
                    "at": "",
                    "by": "",
                    "transaction_type": "",
                    "timestamp": "",
                    "object_id": "*optional",
                    "diff": [{
                        "field": "",
                        "old_val": "",
                        "new_val": ""
                        },
                        ...
                    ]},
                    ...
                ]
        """
        raise NotImplementedError

    def get_object_changes(self, model, object_id, timestamp):
        """
        Gets state of the object by timestamp
        :param model: model of the object
        :param object_id: id of the object for retrieving
        :param timestamp: timestamp for retrieving
        :return: :dict: {
            "updated_by": "user_id",
            "updated_at": timestamp,
            "transaction_type": "update",
            "fields": [{
                "field": "field_name", "old_value": "some value", "new_value": "some value",
                ...
                }]
            }
        :rtype: dict
        """
        raise NotImplementedError

    def get_history_for_fields(self, model, object_id, fields):
        """
        Gets history of field's changes of the object. Sorted by update time DESC
        :param model: model of the object
        :param object_id: id of the object for retrieving
        :param fields: list of field to get history
        :return: :dict: {
            field: [
                {
                    "updated_by": "user_id",
                    "updated_at": timestamp,
                    "transaction_type": "update",
                    "old_value": "some value",
                    "new_value": "some value",
                }, ...
            ],
            another_field: [...],
            ...
        }
        :rtype: dict
        """
        raise NotImplementedError

    def get_recent_field_change(self, model, object_id, field):
        """
        Gets the most recent change of the field
        :param model: model of the object
        :param object_id: id of the object for retrieving
        :param fields: list of field to get history
        :return: :dict: {
            "updated_by": "user_id",
            "updated_at": timestamp,
            "transaction_type": "update",
            "old_value": "some value",
            "new_value": "some value",
        }
        :rtype: dict
        """
        history = self.get_history_for_fields(model, object_id, [field]).get(field, [])
        return history[0] if len(history) > 0 else {}


class ClickHouseLogger(EndlessLogger):
    def __init__(self):
        self.logger_database = Database(settings.LOGGER_DB,
                                        db_url="http://{}:{}/".format(settings.LOGGER_HOST, settings.LOGGER_PORT),
                                        username=settings.LOGGER_USER,
                                        password=settings.LOGGER_PASSWORD)
        self.logger_database.migrate('r3sourcer.apps.logger.clickhouse_migrations')

    @staticmethod
    def date_to_db_representation(date_value):
        """
        Converts date value to int which contains timestamp * 1000
        """
        datetime_field = DateTimeField()
        return int(round(datetime_field.to_python(date_value, True).timestamp() * 1000))

    def log_create_instance(self, instance, general_logger_fields, old_instance=None):
        """
        Logs object creation
        :param instance: instance
        :param general_logger_fields: dictionary of the fields for logging
        :param old_instance: old instance of object
        """
        log_array = []
        for field in instance._meta.local_fields:
            log = LogHistory(
                field=field.name,
                new_value=str(get_field_value(instance, field)),
                **general_logger_fields
            )
            log_array.append(log)
        self.logger_database.insert(log_array)

    def log_update_instance(self, instance, general_logger_fields, old_instance):
        """
        Logs object create
        :param instance: instance
        :param general_logger_fields: dictionary of the fields for logging
        :param old_instance: old instance of object
        """
        log_array = []
        for field in instance._meta.local_fields:
            if getattr(instance, field.name) != getattr(old_instance, field.name):
                log = LogHistory(
                    field=field.name,
                    new_value=str(get_field_value(instance, field)),
                    old_value=str(get_field_value(old_instance, field)),
                    **general_logger_fields
                )
                log_array.append(log)
        self.logger_database.insert(log_array)

    def log_delete_instance(self, instance, general_logger_fields, old_instance):
        """
        Logs object deletion
        :param instance: instance if exists
        :param general_logger_fields: dictionary of the fields for logging
        :param old_instance: old instance of object if exists
        """
        log_array = []
        general_logger_fields['object_id'] = str(old_instance.id)
        for field in instance._meta.local_fields:
            log = LogHistory(
                field=field.name,
                old_value=str(get_field_value(old_instance, field)),
                **general_logger_fields
            )
            log_array.append(log)
        self.logger_database.insert(log_array)

    def log_update_field(self, field_name, general_logger_fields, new_value='', old_value=''):
        """
        Logs changes of the one field to the ClickHouse db
        :param field_name: name of the field
        :param general_logger_fields: dictionary of the general field settings
        :param new_value: new value of the field
        :param old_value: old value of the field
        """
        log = LogHistory(
            field=field_name,
            new_value=str(new_value),
            old_value=str(old_value),
            **general_logger_fields
        )
        self.logger_database.insert([log])

    def get_object_history(self, model, object_id=None, by_user=None, from_date=None, to_date=None, desc=True,
                           offset=0, limit=None):
        """
        Gets history of the model or object from ClickHouse db and returns it in structured view
        """
        query = "SELECT object_id, updated_at, updated_by, field, new_value, old_value, transaction_type " \
                "FROM $table " \
                "WHERE model='{}.{}' "\
            .format(model.__module__, model.__name__)
        if object_id:
            query = "{} and object_id='{}'".format(query, object_id)

        if by_user:
            query = "{} and updated_by='{}'".format(query, by_user.id)

        if from_date:
            query = "{} and updated_at>={}".format(query, self.date_to_db_representation(from_date))

        if to_date:
            query = "{} and updated_at<={}".format(query, self.date_to_db_representation(to_date))

        query = "{} ORDER BY updated_at {} ".format(query, "desc" if desc else '')
        if limit:
            query = "{} LIMIT {}, {}".format(query, offset, limit)
        return self._convert_query_result_to_dictionary(self.logger_database.select(query, LogHistory),
                                                        include_object_id=not object_id)

    def _convert_query_result_to_dictionary(self, query_result, include_object_id=False):
        """
        Convert db query result to human readable view
        :param query_result: result of the query
        :param include_object_id: shows if object_id parameter must be included in dictionary
        """
        result_array = []
        item_counter = 0
        starting_transaction_type = ''
        timestamp = ''
        item_dictionary = None
        diff = []
        for item in query_result:
            if item_counter > 0 \
                    and timestamp != item.updated_at \
                    or item.transaction_type.name != starting_transaction_type:

                if item_dictionary:
                    item_dictionary["diff"] = diff
                    result_array.append(item_dictionary)
                    diff = []
                    item_dictionary = None

            if not item_dictionary:
                updated = date_format(datetime.utcfromtimestamp(item.updated_at / 1000), settings.DATETIME_FORMAT)

                try:
                    updated_by = get_user_model().objects.get(pk=item.updated_by)
                except Exception:
                    updated_by = ""

                item_dictionary = {
                    "transaction_type": item.transaction_type.name,
                    "by": {"id": item.updated_by, "name": str(updated_by)},
                    "at": updated,
                    "timestamp": item.updated_at,
                }
                if include_object_id:
                    item_dictionary["object_id"] = item.object_id

            diff.append({
                "field": item.field,
                "old_val": item.old_value,
                "new_val": item.new_value,
            })

            timestamp = item.updated_at
            starting_transaction_type = item.transaction_type.name
            item_counter += 1

        if item_dictionary:
            item_dictionary["diff"] = diff
            result_array.append(item_dictionary)
        return result_array

    def get_object_changes(self, model, object_id, timestamp):
        query = "SELECT * FROM $table " \
                "WHERE model='{}.{}' and object_id='{}' and updated_at={}" \
            .format(model.__module__, model.__name__, object_id, timestamp)
        object_state = {}
        data = list(self.logger_database.select(query, LogHistory))
        if data and len(data) > 0:
            object_state["updated_at"] = data[0].updated_at
            object_state["updated_by"] = data[0].updated_by
            object_state["transaction_type"] = data[0].transaction_type.name
            object_state["fields"] = []

        for item in data:
            field_info = {"field": item.field, "old_value": item.old_value, "new_value": item.new_value}
            object_state["fields"].append(field_info)
        return object_state

    def get_result_length(self, model, object_id=None, by_user=None, from_date=None, to_date=None):
        conditions = "model='{}.{}' ".format(model.__module__, model.__name__)
        if object_id:
            conditions = "{} and object_id='{}'".format(conditions, object_id)

        if by_user:
            conditions = "{} and updated_by='{}'".format(conditions, by_user.id)

        if from_date:
            conditions = "{} and updated_at>={}".format(conditions, self.date_to_db_representation(from_date))

        if to_date:
            conditions = "{} and updated_at<={}".format(conditions, self.date_to_db_representation(to_date))
        return self.logger_database.count(LogHistory, conditions)

    def get_log_queryset(self):
        return LogHistory.objects_in(self.logger_database)

    def get_history_object_ids(self, model, field, new_value, ids=None,
                               old_value=None, transaction_types=None):
        filter_kwargs = {
            'field': field,
            'new_value': new_value,
        }

        if ids:
            filter_kwargs['object_id__in'] = format_range(ids)

        if old_value is not None:
            filter_kwargs['old_value='] = old_value

        if transaction_types:
            if isinstance(transaction_types, (tuple, list)):
                transaction_types = format_range(transaction_types)

            filter_kwargs['transaction_type'] = transaction_types

        # TODO: fix aggregation (attribute error: infi.clickhouse_orm.query.QuerySet)
        res = self.get_log_queryset().filter(**filter_kwargs).only(
            'object_id'
        )  # .aggregate('object_id', num='count()')
        return [log.object_id for log in res]

    def _get_fields_history_qs(self, model, object_id, fields, transaction_type=None, order_by=None):
        if not isinstance(fields, (list, tuple)):
            fields = [fields]

        model = '%s.%s' % (model.__module__, model.__name__)

        query_set = self.get_log_queryset().filter(
            model=model, object_id=str(object_id), field__in=fields
        )

        if transaction_type is not None:
            query_set = query_set.filter(transaction_type=transaction_type)

        return query_set.order_by(order_by) if order_by is not None else query_set

    def _map_field_history(self, log_object):
        updated_at = datetime.utcfromtimestamp(log_object.updated_at / 1000)

        return {
            'updated_by': log_object.updated_by,
            'updated_at': updated_at,
            'transaction_type': log_object.transaction_type.name,
            'old_value': log_object.old_value,
            'new_value': log_object.new_value,
        }

    def get_history_for_fields(self, model, object_id, fields):
        fields_history = {}

        if not fields:
            return fields_history

        log_qs = self._get_fields_history_qs(model, object_id, fields, order_by='-updated_at')

        for log_object in log_qs:
            field_history = fields_history.get(log_object.field, [])
            field_history.append(self._map_field_history(log_object))
            fields_history[log_object.field] = field_history

        return fields_history

    def get_recent_field_change(self, model, object_id, field, transaction_type=None):
        log_qs = self._get_fields_history_qs(
            model, object_id, [field],
            order_by='-updated_at',
            transaction_type=transaction_type
        )

        return self._map_field_history(log_qs[0]) if log_qs.count() > 0 else {}
