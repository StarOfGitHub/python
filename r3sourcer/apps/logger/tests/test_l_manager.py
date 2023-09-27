from datetime import timedelta, datetime

import freezegun
import pytest
import pytz

from django.utils import timezone
from django.conf import settings as dj_settings
from r3sourcer.apps.logger.manager import get_endless_logger, EndlessLogger, ClickHouseLogger
from r3sourcer.apps.logger.models import LogHistory


tz = pytz.timezone(dj_settings.TIME_ZONE)


def test_get_endless_logger():
    logger = get_endless_logger()
    assert isinstance(logger, EndlessLogger)


class TestEndlessLogger:
    @classmethod
    def setup_class(cls):
        cls.logger = EndlessLogger()

    def test_log_create_instance(self, test_instance):
        with pytest.raises(NotImplementedError):
            self.logger.log_create_instance(test_instance, None)

    def test_log_update_instance(self, test_instance):
        with pytest.raises(NotImplementedError):
            self.logger.log_update_instance(test_instance, None, test_instance)

    def test_log_delete_instance(self, test_instance):
        with pytest.raises(NotImplementedError):
            self.logger.log_delete_instance(test_instance, None, test_instance)

    def test_log_update_field(self):
        with pytest.raises(NotImplementedError):
            self.logger.log_update_field("name", None, new_value='New Name', old_value='Old Name')

    def test_get_object_history(self, test_model):
        with pytest.raises(NotImplementedError):
            self.logger.get_object_history(test_model, "id", by_user=None, from_date=None, to_date=None, desc=False)

    def test_get_object_changes(self, test_model):
        with pytest.raises(NotImplementedError):
            self.logger.get_object_changes(test_model, "id", "1490191182117")


@pytest.mark.usefixtures("test_instance")
class TestClickhouseLogger:
    logger = None

    @classmethod
    def setup_class(cls):
        cls.logger = ClickHouseLogger()

    @classmethod
    def teardown_class(cls):
        cls.logger.logger_database.drop_database()

    def test_get_general_fields(self, test_instance):
        fields = self.logger.get_general_fields(test_instance, 'create')
        assert fields["model"] == "{}.{}".format(test_instance.__class__.__module__, test_instance.__class__.__name__)
        assert fields["transaction_type"] == 'create'
        assert fields["object_id"] == str(4)

    def test_log_create_instance(self, test_instance):
        general_logger_fields = self.logger.get_general_fields(test_instance, 'create')
        self.logger.log_create_instance(test_instance, general_logger_fields, None)
        assert self.logger.logger_database.count(LogHistory) == 2
        test_instance.id = None
        test_instance.save()
        general_logger_fields = self.logger.get_general_fields(test_instance, 'create')
        self.logger.log_create_instance(test_instance, general_logger_fields, None)
        assert self.logger.logger_database.count(LogHistory) == 4

    def test_log_update_instance(self, test_instance):
        general_logger_fields = self.logger.get_general_fields(test_instance, 'update')
        import copy
        old_instance = copy.deepcopy(test_instance)
        test_instance.name = "New Name"
        self.logger.log_update_instance(test_instance, general_logger_fields, old_instance)
        assert self.logger.logger_database.count(LogHistory, conditions="transaction_type='update'") == 1

        query = "SELECT old_value, new_value FROM $table " \
                "where model='{}.{}' and object_id='{}' and transaction_type='update' "\
            .format(test_instance.__class__.__module__, test_instance.__class__.__name__, test_instance.id)
        for item in self.logger.logger_database.select(query, LogHistory):
            assert item.new_value == test_instance.name
            assert item.old_value == old_instance.name

    def test_log_delete_instance(self, test_instance):
        general_logger_fields = self.logger.get_general_fields(test_instance, 'delete')
        assert self.logger.logger_database.count(LogHistory, conditions="transaction_type='delete'") == 0
        self.logger.log_delete_instance(test_instance, general_logger_fields, test_instance)
        assert self.logger.logger_database.count(LogHistory, conditions="transaction_type='delete'") == 2
        query = "SELECT old_value, new_value FROM $table " \
                "where model='{}.{}' and object_id='{}' and transaction_type='delete' " \
            .format(test_instance.__class__.__module__, test_instance.__class__.__name__, test_instance.id)

        for item in self.logger.logger_database.select(query, LogHistory):
            assert item.new_value == ''
            assert item.old_value in [str(test_instance.id), str(test_instance.name)]

    def test_log_instance_change_as_create(self, test_model):
        new_instance = test_model.objects.create(name='test name 2', id=3)
        count = self.logger.logger_database.count(LogHistory)
        self.logger.log_instance_change(new_instance, old_instance=None, transaction_type='create')
        assert self.logger.logger_database.count(LogHistory) == count + 2

    def test_log_update_field(self, test_instance):
        general_logger_fields = self.logger.get_general_fields(test_instance, 'update')
        count = self.logger.logger_database.count(LogHistory, conditions="transaction_type='update'")
        self.logger.log_update_field("name", general_logger_fields, new_value='Name', old_value='Old name')
        assert self.logger.logger_database.count(LogHistory, conditions="transaction_type='update'") == count + 1
        query = "SELECT old_value, new_value, updated_at FROM $table " \
                "where model='{}.{}' and object_id='{}' and transaction_type='update' and new_value='Name' " \
                "order by updated_at desc " \
                "limit 1"\
            .format(test_instance.__class__.__module__, test_instance.__class__.__name__, test_instance.id)
        for item in self.logger.logger_database.select(query, LogHistory):
            assert item.old_value == "Old name"

    def test_get_object_history_without_additional_params(self, test_model):
        new_instance = test_model.objects.create(name='For history test', id=4)
        general_logger_fields = self.logger.get_general_fields(new_instance, 'create')
        self.logger.log_create_instance(new_instance, general_logger_fields, None)
        history = self.logger.get_object_history(test_model, new_instance.id)
        assert len(history) == 1
        assert "create" in history[0].values()

        general_logger_fields = self.logger.get_general_fields(new_instance, 'update')
        self.logger.log_update_field("name", general_logger_fields,
                                     old_value='For history test',
                                     new_value='For history test 2')
        history = self.logger.get_object_history(test_model, new_instance.id)
        assert len(history) == 2

    def test_get_object_history_filtered_by_user(self, test_instance, user):
        general_logger_fields = self.logger.get_general_fields(test_instance, 'update')
        self.logger.log_update_field("name", general_logger_fields,
                                     old_value='some name',
                                     new_value='updated name')
        history = self.logger.get_object_history(test_instance.__class__, test_instance.id, by_user=user)
        for item in history:
            assert int(item['by']['id']) == 1
            assert item['by']['name'] == str(user)

    @freezegun.freeze_time(tz.localize(datetime(2017, 1, 1, 7)))
    def test_get_object_history_filtered_by_date(self, test_model):
        new_instance = test_model.objects.create(name='Dates range test', id=5)

        week_ago = timezone.now() - timedelta(days=7)
        three_days_ago = timezone.now() - timedelta(days=3)
        # logging of creation
        general_logger_fields = {
            'updated_by': str(None),
            'date': week_ago.date(),
            'updated_at': int(round(week_ago.timestamp() * 1000)),
            'model': "{}.{}".format(new_instance.__class__.__module__, new_instance.__class__.__name__),
            'object_id': str(new_instance.id),
            'transaction_type': "create"
        }
        self.logger.log_create_instance(new_instance, general_logger_fields)

        # first update logging
        general_logger_fields['date'] = three_days_ago.date()
        general_logger_fields['updated_at'] = int(round(three_days_ago.timestamp() * 1000))
        general_logger_fields['transaction_type'] = "update"

        self.logger.log_update_field("name", general_logger_fields,
                                     old_value='Dates range test',
                                     new_value='Dates range test 2')
        # second update logging
        now = timezone.now()
        general_logger_fields['date'] = now.date()
        general_logger_fields['updated_at'] = int(round(now.timestamp() * 1000))

        self.logger.log_update_field("name", general_logger_fields,
                                     old_value='Dates range test 2',
                                     new_value='Dates range test 3')

        history = self.logger.get_object_history(new_instance.__class__, new_instance.id)
        assert len(history) == 3
        # TODO: Fix timezone
        history = self.logger.get_object_history(new_instance.__class__, new_instance.id,
                                                 from_date=timezone.now())
        assert len(history) == 1
        history = self.logger.get_object_history(new_instance.__class__, new_instance.id,
                                                 from_date=week_ago.date(),
                                                 to_date=datetime.combine(three_days_ago.date(), datetime.max.time()))
        assert len(history) == 2

    def test_get_object_history_ordering(self, test_model):
        new_instance = test_model.objects.create(name='For ordering history test', id=6)
        general_logger_fields = self.logger.get_general_fields(new_instance, 'create')
        self.logger.log_create_instance(new_instance, general_logger_fields, None)

        general_logger_fields = self.logger.get_general_fields(new_instance, 'update')
        self.logger.log_update_field("name", general_logger_fields,
                                     old_value='For ordering history test',
                                     new_value='For ordering history test 2')
        history = self.logger.get_object_history(test_model, new_instance.id, desc=False)

        assert history[0]["transaction_type"] == "create"
        history = self.logger.get_object_history(test_model, new_instance.id, desc=True)
        assert history[0]["transaction_type"] == "update"

    def test_get_object_changes(self, test_model):
        new_instance = test_model.objects.create(name='Field test', id=7)
        general_logger_fields = self.logger.get_general_fields(new_instance, 'create')
        self.logger.log_create_instance(new_instance, general_logger_fields, None)

        history = self.logger.get_object_history(test_model, new_instance.id)
        result = self.logger.get_object_changes(new_instance.__class__, new_instance.id, history[0]["timestamp"])
        assert result["updated_at"] == history[0]["timestamp"]
        assert result["transaction_type"] == "create"
        assert len(result["fields"]) == 2
        for field in result["fields"]:
            assert field["new_value"] == str(getattr(new_instance, field["field"]))
