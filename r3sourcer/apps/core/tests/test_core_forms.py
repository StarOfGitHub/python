import pytest

from r3sourcer.apps.core.forms import CoreAdminAuthenticationForm


@pytest.mark.django_db
class TestCoreAdminAuthenticationForm:

    def test_staff_valid_auth_email(self, superuser):
        form = CoreAdminAuthenticationForm(data={
            'username': 'test@test.tt',
            'password': 'test1234'
        })

        assert form.is_valid()

    def test_staff_valid_auth_phone(self, superuser):
        form = CoreAdminAuthenticationForm(data={
            'username': '+12345678901',
            'password': 'test1234'
        })

        assert form.is_valid()

    def test_non_staff_user_admin_auth_errors(self, user):
        form = CoreAdminAuthenticationForm(data={
            'username': 'test@test.tt',
            'password': 'test1234'
        })

        assert not form.is_valid()

    def test_admin_auth_without_password(self, superuser):
        form = CoreAdminAuthenticationForm(data={
            'username': 'test@test.tt'
        })

        assert not form.is_valid()

    def test_admin_auth_without_email_and_phone(self, superuser):
        form = CoreAdminAuthenticationForm()

        assert not form.is_valid()

    def test_admin_auth_wrong_email_format(self, superuser):
        form = CoreAdminAuthenticationForm(data={
            'username': 'test.tt'
        })

        assert not form.is_valid()

    def test_admin_auth_wrong_number_format(self, superuser):
        form = CoreAdminAuthenticationForm(data={
            'username': '+1234'
        })

        assert not form.is_valid()

    def test_admin_auth_not_registered_user(self, superuser):
        form = CoreAdminAuthenticationForm(data={
            'username': 'test1@test.tt',
            'password': 'test1234'
        })

        assert not form.is_valid()
