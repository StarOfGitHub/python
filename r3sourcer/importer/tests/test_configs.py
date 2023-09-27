import mock

from r3sourcer.importer.configs import BaseConfig, ContactConfig

from r3sourcer.apps.core.models import User


class ConfigTest(BaseConfig):
    pass


class TestBaseConfig:

    def test_override(self):
        conf_class = ConfigTest.override(model='test')

        assert conf_class is not ConfigTest
        assert issubclass(conf_class, ConfigTest)
        assert conf_class.model == 'test'


class TestContactConfig:

    def test_prepare_data(self):
        row = {
            'user_id': 'id', 'email': 'email', 'phone_mobile': 'phone_mobile'
        }
        res = ContactConfig.prepare_data(row)

        assert row['email'] == res['email']
        assert row['phone_mobile'] == res['phone_mobile']

    def test_prepare_data_email_empty(self):
        row = {
            'user_id': 'id', 'email': '', 'phone_mobile': 'phone_mobile'
        }
        res = ContactConfig.prepare_data(row)

        assert res['email'] is None
        assert row['phone_mobile'] == res['phone_mobile']

    def test_prepare_data_phone_empty(self):
        row = {
            'user_id': 'id', 'email': 'email', 'phone_mobile': ''
        }
        res = ContactConfig.prepare_data(row)

        assert row['email'] == res['email']
        assert res['phone_mobile'] is None

    @mock.patch.object(User, 'objects', new_callable=mock.PropertyMock())
    def test_prepare_data_user_id_empty(self, mock_objects):
        row = {
            'user_id': None, 'email': 'email', 'phone_mobile': ''
        }
        res = ContactConfig.prepare_data(row)

        assert row['email'] == res['email']
        assert res['phone_mobile'] is None
