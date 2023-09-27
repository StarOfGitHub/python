import datetime

import pytz
from infi.clickhouse_orm.database import Database
from django.conf import settings

from r3sourcer.apps.logger.models import LogHistory, TRANSACTION_TYPES


class TestLogHistory:
    logger_db = None

    @classmethod
    def setup_class(cls):
        cls.logger_db = Database(settings.LOGGER_DB,
                                 db_url="http://{}:{}/".format(settings.LOGGER_HOST, settings.LOGGER_PORT),
                                 username=settings.LOGGER_USER,
                                 password=settings.LOGGER_PASSWORD)
        cls.logger_db.create_table(LogHistory)

    @classmethod
    def teardown_class(cls):
        cls.logger_db.drop_table(LogHistory)

    def test_defaults(self):
        instance = LogHistory()
        assert instance.transaction_type == TRANSACTION_TYPES.update
        assert instance.old_value == ''
        assert instance.new_value == ''

    def test_assignment(self):
        kwargs = dict(
            date=datetime.date.today(),
            updated_at=int(round(datetime.datetime.now(tz=pytz.utc).timestamp() * 1000)),
            updated_by='test_user',
            transaction_type=TRANSACTION_TYPES.create,
            model='Test',
            field='name',
            new_value='test name'
        )
        instance = LogHistory(**kwargs)
        for name, value in kwargs.items():
            assert kwargs[name] == getattr(instance, name)

    def test_logger_db_insert(self):
        log = LogHistory(updated_by='test_user',
                         date=datetime.date.today(),
                         updated_at=int(round(datetime.datetime.now(tz=pytz.utc).timestamp() * 1000)),
                         transaction_type=TRANSACTION_TYPES.create,
                         model='Test',
                         field='name',
                         new_value='test name'
                         )
        self.logger_db.insert([log])
        assert self.logger_db.count(LogHistory, "updated_by = 'test_user'") == 1
        log_from_table = list(self.logger_db.select("SELECT * from $table order by updated_at", LogHistory))[0]
        assert log_from_table.model == 'Test'
        assert log_from_table.field == 'name'
