import mock
import pytest

from django.contrib import auth
from django.urls import reverse
from rest_framework import status

from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import Contact, CompanyContact, CompanyContactRelationship
from r3sourcer.apps.login.models import TokenLogin
from r3sourcer.apps.login.api.viewsets import AuthViewSet


@pytest.mark.django_db
class TestLoginResource:
    @mock.patch('r3sourcer.apps.candidate.models.get_site_master_company')
    @mock.patch('r3sourcer.apps.candidate.models.CandidateContact.get_active_states')
    def test_restore_session_contact_type(self, get_active_states, mock_company, client, user, token_login, company):
        mocked_value = mock.Mock()
        mocked_value.score = 1
        mocked_value.get_score = mock.Mock(return_value=1)
        get_active_states.return_value = [mocked_value]
        mock_company.return_value = company

        client.get(reverse('api:auth-login-by-token', kwargs={'auth_token': token_login.auth_token}))
        company_contact = CompanyContact.objects.create(
            contact=user.contact, role=CompanyContact.ROLE_CHOICES[CompanyContact.MANAGER]
        )
        company_contact_rel = CompanyContactRelationship.objects.create(
            company=company, company_contact=company_contact
        )
        url = reverse('api:auth-restore-session')
        response1 = client.get(url)
        company_contact.role = CompanyContact.ROLE_CHOICES[CompanyContact.CLIENT]
        company_contact.save()
        response2 = client.get(url)
        company_contact_rel.delete()
        company_contact.delete()
        CandidateContact.objects.create(contact=user.contact)
        response3 = client.get(url)

        assert response1.json()['data']['contact']['contact_type'] == 'Manager'
        assert response2.json()['data']['contact']['contact_type'] == 'Client'
        assert response3.json()['data']['contact']['contact_type'] == 'candidate'

    def test_cannot_put_to_login(self, client, user):
        response = client.put(reverse('api:auth-login'))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_cannot_patch_to_login(self, client, user):
        response = client.patch(reverse('api:auth-login'))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_cannot_delete_to_login(self, client, user):
        response = client.delete(reverse('api:auth-login'))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    @mock.patch.object(AuthViewSet, 'is_login_allowed', return_value=(True, None))
    def test_user_email_login_success(self, mock_login_allowed, client, user):
        response = client.post(reverse('api:auth-login'),
                               data={'username': user.email, 'password': 'test1234'})

        assert response.json()['status'] == 'success'
        assert response.status_code == status.HTTP_200_OK

        auth_user = auth.get_user(client)
        assert auth_user == user
        assert auth_user.is_authenticated

    @mock.patch.object(AuthViewSet, 'is_login_allowed', return_value=(True, None))
    def test_user_mobile_phone_login_success(self, mock_login_allowed, client, user):
        response = client.post(reverse('api:auth-login'),
                               data={'username': user.phone_mobile, 'password': 'test1234'})

        assert response.json()['status'] == 'success'
        assert response.status_code == status.HTTP_200_OK

        auth_user = auth.get_user(client)
        assert auth_user == user
        assert auth_user.is_authenticated

    def test_user_login_email_not_exists(self, client):
        response = client.post(reverse('api:auth-login'),
                               data={'username': 'test42@test.tt', 'password': 'test1234'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_user_login_phone_not_exists(self, client):
        response = client.post(reverse('api:auth-login'),
                               data={'username': '+12345654321', 'password': 'test1234'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @mock.patch.object(AuthViewSet, 'is_login_allowed', return_value=(True, None))
    def test_user_already_logged_in(self, mock_login_allowed, client, user, superuser):
        client.post(
            reverse('api:auth-login'),
            data={'username': user.phone_mobile, 'password': 'test1234'}
        )

        client.post(
            reverse('api:auth-login'),
            data={'username': superuser.email, 'password': 'test4242'}
        )

        auth_user = auth.get_user(client)
        assert auth_user == superuser
        assert auth_user.is_authenticated

    def test_token_login_success(self, client, user, token_login):
        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login.auth_token}
        ))

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['data']['redirect_to'] == token_login.redirect_to

        auth_user = auth.get_user(client)
        assert auth_user == user
        assert auth_user.is_authenticated

    def test_token_login_user_not_found(self, client):
        contact = Contact.objects.create(email='test2@test.tt', phone_mobile='+12345678902')
        contact.user = None
        contact.save(update_fields=['user'])
        token_login = TokenLogin.objects.create(contact=contact)

        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login.auth_token}
        ))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_token_used_twice_login_forbidden(self, client, user, token_login):
        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login.auth_token}
        ))

        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login.auth_token}
        ))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_login_logged_in_user(self, client, contact, token_login):
        token_login_another = TokenLogin.objects.create(contact=contact)

        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login.auth_token}
        ))

        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login_another.auth_token}
        ))

        assert response.status_code == status.HTTP_200_OK

        auth_user = auth.get_user(client)
        assert auth_user == contact.user
        assert auth_user.is_authenticated

    def test_token_login_logged_in_another_user(self, client, contact, superuser, token_login):
        contact_another = superuser.contact
        token_login_another = TokenLogin.objects.create(contact=contact_another)

        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login.auth_token}
        ))

        response = client.get(reverse(
            'api:auth-login-by-token',
            kwargs={'auth_token': token_login_another.auth_token}
        ))

        assert response.status_code == status.HTTP_200_OK

        auth_user = auth.get_user(client)
        assert auth_user == superuser
        assert auth_user.is_authenticated

    @mock.patch('r3sourcer.apps.login.api.viewsets.send_login_message')
    def test_login_without_password_send_sms_message(self, mock_send_message, client, user):
        client.post(reverse('api:auth-login'),
                    data={'username': user.phone_mobile})

        assert mock_send_message.called

    @mock.patch('r3sourcer.apps.login.api.viewsets.send_login_message')
    def test_login_without_password_send_email_message(self, mock_send_message, client, user):
        client.post(reverse('api:auth-login'),
                    data={'username': user.email})

        assert mock_send_message.called

    def test_login_without_password_user_not_found(self, client, user):
        response = client.post(reverse('api:auth-login'),
                               data={'username': 'test2@test.tt'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_email_wrong_password_(self, client, user):
        response = client.post(reverse('api:auth-login'),
                               data={'username': user.email, 'password': '1'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_phone_wrong_password_(self, client, user):
        response = client.post(reverse('api:auth-login'),
                               data={'username': user.phone_mobile, 'password': '1'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogoutResource:

    def test_user_logout_success(self, client, user):
        client.post(reverse('api:auth-login'),
                    data={'username': user.email, 'password': 'test1234'})

        client.post(reverse('api:auth-logout'))

        auth_user = auth.get_user(client)
        assert not auth_user.is_authenticated

    def test_anonymous_user_logout_success(self, client, user):
        client.post(reverse('api:auth-logout'))

        auth_user = auth.get_user(client)
        assert not auth_user.is_authenticated
