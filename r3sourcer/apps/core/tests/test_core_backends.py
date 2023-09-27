import pytest

from r3sourcer.apps.core.backends import ContactBackend
from r3sourcer.apps.core.models import User


@pytest.mark.django_db
class TestContactBackend:

    @pytest.fixture
    def backend(self):
        return ContactBackend()

    def test_user_authenticate_by_email(self, user, backend):
        auth_user = backend.authenticate('test@test.tt', 'test1234')

        assert auth_user == user

    def test_user_authenticate_by_phone(self, user, backend):
        auth_user = backend.authenticate('+12345678901', 'test1234')

        assert auth_user == user

    def test_user_does_not_exists(self, backend):
        auth_user = backend.authenticate('fake@test.tt', 'test1234')

        assert auth_user is None

    def test_user_auth_without_password(self, backend):
        auth_user = backend.authenticate('fake@test.tt')

        assert auth_user is None

    def test_user_get_login_value_email(self, backend):
        value = backend.get_login_value(User, email='test@test.tt')

        assert value == 'test@test.tt'

    def test_user_get_login_value_phone(self, backend):
        value = backend.get_login_value(User, phone_mobile='+12345678901')

        assert value == '+12345678901'

    def test_user_get_login_value_unknown_field(self, backend):
        value = backend.get_login_value(User, phone='+12345678901')

        assert value is None

    def test_user_authenticate_by_email_param(self, user, backend):
        auth_user = backend.authenticate(email='test@test.tt', password='test1234')

        assert auth_user == user
