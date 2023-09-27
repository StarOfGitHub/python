import pytest

from r3sourcer.apps.login.models import TokenLogin


@pytest.mark.django_db
class TestTokenLogin:

    def test_generate_auth_token_on_create(self, token_login):
        assert token_login.auth_token == '1'*8

    def test_get_auth_url(self, token_login):
        assert token_login.auth_url == '/login/11111111'

    def test_token_login_str(self, token_login, contact):
        assert str(token_login) == 'Token Login {}'.format(str(contact))

    def test_token_login_sms_type(self, contact):
        token_login = TokenLogin.objects.create(contact=contact, type=TokenLogin.TYPES.sms)

        assert token_login.type == TokenLogin.TYPES.sms
        assert len(token_login.auth_token) == TokenLogin.TYPE_TO_LEN_MAPPING[TokenLogin.TYPES.sms]

    def test_token_login_email_type(self, contact):
        token_login = TokenLogin.objects.create(contact=contact, type=TokenLogin.TYPES.email)

        assert token_login.type == TokenLogin.TYPES.email
        assert len(token_login.auth_token) == TokenLogin.TYPE_TO_LEN_MAPPING[TokenLogin.TYPES.email]
