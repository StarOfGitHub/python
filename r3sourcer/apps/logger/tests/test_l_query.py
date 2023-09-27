from r3sourcer.apps.logger.manager import ClickHouseLogger
from r3sourcer.apps.logger.models import LogHistory, TRANSACTION_TYPES
from r3sourcer.apps.logger.query import get_logger_queryset
from r3sourcer.apps.logger.tests.conftest import NameModel


class TestLoggerQuerySet:
    logger = None

    @classmethod
    def setup_class(cls):
        cls.logger = ClickHouseLogger()
        import types
        cls.test_model = NameModel
        cls.test_model.objects.get_queryset = types.MethodType(get_logger_queryset, cls.test_model.objects)

    @classmethod
    def teardown_class(cls):
        cls.logger.logger_database.drop_database()

    def test_bulk_create(self, db):
        objects = self.test_model.objects.bulk_create([NameModel(name='n1'), NameModel(name='n2')])
        assert len(objects) == 2
        assert self.logger.logger_database.count(LogHistory, conditions="transaction_type='create'") == 4

        query = "SELECT * FROM $table " \
                "where model='{}.{}'".format(NameModel.__module__, NameModel.__name__)

        for item in self.logger.logger_database.select(query, LogHistory):
            assert item.object_id == str(1) or str(2)
            assert item.old_value == ''
            assert item.transaction_type == TRANSACTION_TYPES.create

    def test_update(self, db):
        self.test_model.objects.create(name='n3')
        rows = self.test_model.objects.filter(name='n3').update(name='n4')
        assert self.logger.logger_database.count(LogHistory, conditions="transaction_type='update'") == rows

    def test_delete(self, db):
        old_id = self.test_model.objects.create(name='n3').id
        old_deleted_value = self.logger.logger_database.count(LogHistory, conditions="transaction_type='delete'")
        deleted, _rows_count = self.test_model.objects.filter(name='n3').delete()
        assert self.logger.logger_database.count(LogHistory,
                                                 conditions="transaction_type='delete'") == old_deleted_value + deleted

        query = "SELECT * FROM $table " \
                "where model='{}.{}' and transaction_type='delete' and object_id='{}'".format(
            NameModel.__module__, NameModel.__name__, old_id)

        for item in self.logger.logger_database.select(query, LogHistory):
            assert str(old_id) == item.old_value
