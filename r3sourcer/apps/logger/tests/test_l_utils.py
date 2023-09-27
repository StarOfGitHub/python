from r3sourcer.apps.logger.manager import ClickHouseLogger
from r3sourcer.apps.logger.utils import get_field_value, get_field_value_by_field_name


class TestUtils:
    logger = None

    @classmethod
    def setup_class(cls):
        cls.logger = ClickHouseLogger()

    @classmethod
    def teardown_class(cls):
        cls.logger.logger_database.drop_database()

    def test_get_field_value_general_field(self, db, test_instance, test_model_for_autodiscover):
        instance = test_model_for_autodiscover.objects.create(name="Model", rel=test_instance)
        assert instance.name == get_field_value(instance, instance.__class__._meta.get_field("name"))

    def test_get_field_value_foreign_key_field(self, db, test_instance, test_model_for_autodiscover):
        instance = test_model_for_autodiscover.objects.create(name="Model", rel=test_instance)
        assert test_instance.id == get_field_value(instance, instance.__class__._meta.get_field("rel"))

    def test_get_field_value_by_field_name(self, db, test_instance):
        assert test_instance.name == get_field_value_by_field_name(test_instance, "name")
