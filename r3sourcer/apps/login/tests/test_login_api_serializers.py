import pytest

from r3sourcer.apps.login.api.serializers import LoginSerializer


@pytest.mark.django_db
class TestLoginSerializer:

    def login_data(self, username):
        return {
            'username': username,
            'password': 'test1234',
        }

    def test_login_with_valid_email(self):
        login_data = self.login_data('test@test.tt')
        serializer = LoginSerializer(data=login_data)

        assert serializer.is_valid()

    def test_login_with_valid_phone(self):
        login_data = self.login_data('+12345678901')
        serializer = LoginSerializer(data=login_data)

        assert serializer.is_valid()

    def test_login_with_invalid_email(self):
        login_data = self.login_data('test.tt')
        serializer = LoginSerializer(data=login_data)

        assert not serializer.is_valid()

    def test_login_with_invalid_phone(self):
        login_data = self.login_data('42')
        serializer = LoginSerializer(data=login_data)

        assert not serializer.is_valid()

    def test_login_without_password(self):
        serializer = LoginSerializer(data={'username': 'test@test.tt'})

        assert serializer.is_valid()
