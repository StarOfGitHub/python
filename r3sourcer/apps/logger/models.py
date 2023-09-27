from enum import Enum

from infi.clickhouse_orm import fields, engines
from infi.clickhouse_orm.models import Model

TRANSACTION_TYPES = Enum('transaction_type', 'create update delete')


class LogHistory(Model):
    model = fields.StringField()
    field = fields.StringField()
    object_id = fields.StringField()
    old_value = fields.StringField()
    new_value = fields.StringField()
    updated_by = fields.StringField()
    updated_at = fields.UInt64Field()
    transaction_type = fields.Enum8Field(TRANSACTION_TYPES, default=TRANSACTION_TYPES.update)
    date = fields.DateField()

    engine = engines.MergeTree('date', ('updated_by', 'object_id'))


class LocationHistory(Model):
    model = fields.StringField()
    name = fields.NullableField(fields.StringField())
    object_id = fields.StringField()
    timesheet_id = fields.NullableField(fields.StringField())
    latitude = fields.Float32Field()
    longitude = fields.Float32Field()
    log_at = fields.DateTimeField()
    date = fields.DateField()

    engine = engines.MergeTree('date', ('object_id',))
