import mock

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django_mock_queries.query import MockSet, MockModel, MagicMock

from r3sourcer.apps.core.mixins import GenerateAuthTokenMixin


class MockTokenModel(GenerateAuthTokenMixin, MockModel):
    class DoesNotExist(ObjectDoesNotExist):
        pass


qs = MockSet()
MockTokenModel.objects = qs

try:
    qs.get(Q())
except TypeError:
    def get(*args, **attrs):
        results = qs.filter(*args, **attrs)
        if not results.exists():
            raise MockTokenModel.DoesNotExist()
        else:
            return results[0]

    qs.get = MagicMock(side_effect=get)


class TestGenerateTokenMixin:

    @mock.patch('r3sourcer.apps.core.mixins.get_random_string', return_value='1'*8)
    def test_generate_unique_token_empty_qs(self, mock_rand_str):
        token = MockTokenModel.generate_auth_token()

        assert token == '1'*8

    @mock.patch('r3sourcer.apps.core.mixins.get_random_string', return_value='1'*8)
    def test_generate_unique_token_token_not_empty_qs(self, mock_rand_str):
        MockTokenModel.objects.add(MockTokenModel(mock_name='login1', auth_token='12345678', auth=''))
        token = MockTokenModel.generate_auth_token()
        MockTokenModel.objects.clear()

        assert token == '1'*8

    @mock.patch('r3sourcer.apps.core.mixins.get_random_string', side_effect=['1'*8, '2'*8])
    def test_generate_unique_token_exists_qs(self, mock_rand_str):
        MockTokenModel.objects.add(MockTokenModel(mock_name='login 2', auth_token='1'*8, auth=''))
        token = MockTokenModel.generate_auth_token()
        MockTokenModel.objects.clear()

        assert token == '2'*8

    @mock.patch('r3sourcer.apps.core.mixins.get_random_string', return_value='1'*8)
    def test_generate_unique_token_multiple_fields(self, mock_rand_str):
        token = MockTokenModel.generate_auth_token(token_field_names=['auth_token', 'auth'])

        assert token == '1'*8

    @mock.patch('r3sourcer.apps.core.mixins.get_random_string', side_effect=['1'*8, '2'*8, '3'*8])
    def test_generate_unique_token_exists_qs_multiple_fields(self, mock_rand_str):
        MockTokenModel.objects.add(MockTokenModel(mock_name='active user', auth_token='1'*8, auth='2'*8))
        token = MockTokenModel.generate_auth_token(token_field_names=['auth_token', 'auth'])
        MockTokenModel.objects.clear()

        assert token == '3'*8
