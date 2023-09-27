import json
import mock
import pytest

from django.conf import settings
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import force_authenticate

from r3sourcer.apps.company_settings.models import CompanySettings, MYOBAccount
from r3sourcer.apps.company_settings.views import CompanyGroupListView, CompanyGroupCreateView
from r3sourcer.apps.company_settings.models import GlobalPermission, MYOBSettings
from r3sourcer.apps.core.models import User, CompanyContact, CompanyContactRelationship, InvoiceRule
from r3sourcer.apps.hr.models import PayslipRule
from r3sourcer.apps.myob.models import MYOBCompanyFile, MYOBCompanyFileToken, MYOBAuthData


class TestCompanySettingsView:
    def _get_company_settings(self, client, company, user, invoice_rule, payslip_rule, myob_account):
        company_settings = company.company_settings
        company_settings.logo = '/logo/url'
        company_settings.color_scheme = 'color_scheme'
        company_settings.font = 'font'
        company_settings.forwarding_number = '+12345678901'
        company_settings.save()
        url = reverse('company_settings')
        client.force_login(user)
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['payslip_rule']['id'] == str(payslip_rule.id)
        assert response.data['payslip_rule']['period'] == payslip_rule.period
        assert response.data['company_settings']['forwarding_number'] == company_settings.forwarding_number
        assert response.data['company_settings']['color_scheme'] == company_settings.color_scheme
        assert response.data['company_settings']['font'] == company_settings.font
        assert response.data['company_settings']['id'] == str(company_settings.id)
        assert response.data['company_settings']['logo'] == company_settings.logo.url
        assert response.data['invoice_rule']['separation_rule'] == invoice_rule.separation_rule
        assert response.data['invoice_rule']['show_candidate_name'] == invoice_rule.show_candidate_name
        assert response.data['invoice_rule']['id'] == str(invoice_rule.id)
        assert response.data['invoice_rule']['period'] == invoice_rule.period
        assert response.data['invoice_rule']['starting_number'] == invoice_rule.starting_number
        assert response.data['invoice_rule']['serial_number'] == invoice_rule.serial_number

    def test_get_company_settings_as_manager(self, client, company, user, invoice_rule, payslip_rule, myob_account):
        company_contact = user.contact.company_contact.first()
        company_contact.role = 'manager'
        company_contact.save()
        CompanyContactRelationship.objects.create(
            company_contact=company_contact,
            company=company
        )
        assert user.is_manager()
        self._get_company_settings(client, company, user, invoice_rule, payslip_rule, myob_account)

    def test_get_company_settings_as_client(self, client, company, user, invoice_rule, payslip_rule, myob_account, ):
        company_contact = user.contact.company_contact.first()
        company_contact.role = 'client'
        company_contact.save()
        CompanyContactRelationship.objects.create(
            company_contact=company_contact,
            company=company
        )
        assert user.is_client()
        self._get_company_settings(client, company, user, invoice_rule, payslip_rule, myob_account)

    def test_get_company_settings_as_candidate(
        self, client, company, user_sec, invoice_rule, payslip_rule, myob_account, candidate_contact_sec,
        candidate_rel_sec
    ):
        assert user_sec.is_candidate()
        self._get_company_settings(client, company, user_sec, invoice_rule, payslip_rule, myob_account)

    def test_get_company_settings_as_unknown_role(self, user, client):
        url = reverse('company_settings')
        client.force_login(user)
        response = client.get(url)

        assert response.json()['errors']['detail'] == "Unknown user's role."

    def test_get_company_settings_as_user_without_company(self, primary_contact, client):
        url = reverse('company_settings')
        client.force_login(primary_contact.contact.user)
        response = client.get(url)

        assert response.json()['errors']['detail'] == 'User has no relation to any company.'

    def test_update_company_settings(self, client, company, user, invoice_rule, payslip_rule, company_contact_rel):
        data = {
            'payslip_rule': {
                'period': 'fortnightly'
            },
            'company_settings': {
                'font': 'new_font'
            },
            'invoice_rule': {
                'period': 'fortnightly',
                'starting_number': 9999,
                'serial_number': '1NEW',
            },
        }
        url = reverse('company_settings')
        client.force_login(user)
        response = client.post(url, data=json.dumps(data), content_type='application/json')
        payslip_rule_new = PayslipRule.objects.get(id=payslip_rule.id)
        invoice_rule_new = InvoiceRule.objects.get(id=invoice_rule.id)
        company_settings_new = CompanySettings.objects.get(id=company.company_settings.id)

        assert response.status_code == status.HTTP_200_OK
        assert invoice_rule.period != invoice_rule_new.period
        assert payslip_rule.period != payslip_rule_new.period
        assert company.company_settings.font != company_settings_new.font
        assert invoice_rule_new.period == data['invoice_rule']['period']
        assert invoice_rule_new.serial_number == data['invoice_rule']['serial_number']
        assert invoice_rule_new.starting_number == data['invoice_rule']['starting_number']
        assert payslip_rule_new.period == data['payslip_rule']['period']
        assert company_settings_new.font == data['company_settings']['font']


class TestCompanyFileAccountsView:
    def test_get_myob_account_list(self, client, user, company_file):
        account1 = MYOBAccount.objects.create(uid="d3edc1d7-7b31-437e-9fcd-000000000002",
                                              name='Business Bank Account',
                                              display_id='1-1120',
                                              classification="Asset",
                                              type='Bank',
                                              number='1120',
                                              description="Bank account",
                                              is_active=True,
                                              level=4,
                                              opening_balance=10000.00,
                                              current_balance=5000.00,
                                              is_header=False,
                                              uri="/GeneralLedger/Account/eb043b43-1d66-472b-a6ee-ad48def81b96",
                                              row_version="5548997690873872384",
                                              company_file=company_file)
        account2 = MYOBAccount.objects.create(uid="d3edc1d7-7b31-437e-9fcd-000000000003",
                                              name='Business Bank Account',
                                              display_id='1-1120',
                                              classification="Asset",
                                              type='Bank',
                                              number='1120',
                                              description="Bank account",
                                              is_active=True,
                                              level=4,
                                              opening_balance=10000.00,
                                              current_balance=5000.00,
                                              is_header=False,
                                              uri="/GeneralLedger/Account/eb043b43-1d66-472b-a6ee-ad48def81b96",
                                              row_version="5548997690873872384",
                                              company_file=company_file)
        url = reverse('company_file_accounts', kwargs={'id': company_file.cf_id})
        client.force_login(user)
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['myob_accounts'][1]['id'] == str(account1.id)
        assert response.data['myob_accounts'][1]['number'] == account1.number
        assert response.data['myob_accounts'][1]['name'] == account1.name
        assert response.data['myob_accounts'][1]['type'] == account1.type
        assert response.data['myob_accounts'][0]['id'] == str(account2.id)
        assert response.data['myob_accounts'][0]['number'] == account2.number
        assert response.data['myob_accounts'][0]['name'] == account2.name
        assert response.data['myob_accounts'][0]['type'] == account2.type


class TestMYOBAuthorizationView:
    @pytest.mark.django_db
    @mock.patch('r3sourcer.apps.company_settings.views.get_site_master_company')
    @mock.patch('r3sourcer.apps.myob.api.wrapper.MYOBAuth.retrieve_access_token')
    def test_authorization_success(self, mocked_function, mock_company, client, user, company):
        mocked_function.return_value = {
            'access_token': 'access_token',
            'refresh_token': 'refresh_token',
            'expires_in': 1000,
            'user': {
                'uid': 'uid',
                'username': 'username'
            }
        }
        mock_company.return_value = company
        data = {
            'api_key': 'qwe',
            'api_secret': 'api_secret',
            'redirect_uri': 'redirect_uri',
        }
        url = reverse('myob_authorization') + "?code=code"
        client.force_login(user)
        response = client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK

    def test_authorization_fail(self, client, user):
        data = {
            'api_key': 'qwe',
            'api_secret': 'api_secret',
            'redirect_uri': 'redirect_uri',
        }
        url = reverse('myob_authorization') + "?code=code"
        response = client.post(url, data=data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestUserGlobalPermissionListView:
    def test_get_user_permissions(self, client, user, group):
        permission = GlobalPermission.objects.create(name='permission_name', codename='permission_codename')
        permission2 = GlobalPermission.objects.create(name='permission_name2', codename='permission_codename2')
        user.user_permissions.add(permission, permission2)

        permission3 = GlobalPermission.objects.create(name='permission_name3', codename='permission_codename3')
        permission4 = GlobalPermission.objects.create(name='permission_name4', codename='permission_codename4')
        group.permissions.add(permission3, permission4)
        group.user_set.add(user)

        url = reverse('user_global_permission_list', kwargs={'id': user.id})
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['permission_list'][0]['id'] == permission.id
        assert response.data['permission_list'][0]['name'] == permission.name
        assert response.data['permission_list'][0]['codename'] == permission.codename
        assert response.data['permission_list'][1]['id'] == permission2.id
        assert response.data['permission_list'][1]['name'] == permission2.name
        assert response.data['permission_list'][1]['codename'] == permission2.codename
        assert response.data['group_permission_list'][0]['id'] == permission3.id
        assert response.data['group_permission_list'][0]['name'] == permission3.name
        assert response.data['group_permission_list'][0]['codename'] == permission3.codename
        assert response.data['group_permission_list'][1]['id'] == permission4.id
        assert response.data['group_permission_list'][1]['name'] == permission4.name
        assert response.data['group_permission_list'][1]['codename'] == permission4.codename


class TestGroupGlobalPermissionListView:
    def test_get_group_permissions(self, client, group):
        permission = GlobalPermission.objects.create(name='permission_name', codename='permission_codename')
        permission2 = GlobalPermission.objects.create(name='permission_name2', codename='permission_codename2')
        group.permissions.add(permission, permission2)
        url = reverse('group_global_permission_list', kwargs={'id': group.id})
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['permission_list'][0]['id'] == permission.id
        assert response.data['permission_list'][0]['name'] == permission.name
        assert response.data['permission_list'][0]['codename'] == permission.codename
        assert response.data['permission_list'][1]['id'] == permission2.id
        assert response.data['permission_list'][1]['name'] == permission2.name
        assert response.data['permission_list'][1]['codename'] == permission2.codename


class TestSetGroupGlobalPermissionView:
    def test_set_group_permission(self, client, group):
        permission = GlobalPermission.objects.create(name='permission_name', codename='permission_codename')
        permission2 = GlobalPermission.objects.create(name='permission_name2', codename='permission_codename2')
        url = reverse('set_group_global_permission', kwargs={'id': group.id})
        payload = {
            'permission_list': [permission.id, permission2.id]
        }
        response = client.post(url, data=json.dumps(payload), content_type="application/json")
        result_permissions = group.permissions.all()

        assert response.status_code == status.HTTP_200_OK
        assert result_permissions[0] == permission
        assert result_permissions[1] == permission2


class TestSetUserGlobalPermissionView:
    def test_set_user_permission(self, client, user):
        permission = GlobalPermission.objects.create(name='permission_name', codename='permission_codename')
        permission2 = GlobalPermission.objects.create(name='permission_name2', codename='permission_codename2')
        url = reverse('set_user_global_permission', kwargs={'id': user.id})
        payload = {
            'permission_list': [permission.id, permission2.id]
        }
        response = client.post(url, data=json.dumps(payload), content_type="application/json")
        result_permissions = user.user_permissions.all()

        assert response.status_code == status.HTTP_200_OK
        assert result_permissions[0] == permission
        assert result_permissions[1] == permission2


@pytest.mark.django_db
class TestGlobalPermissionListView:
    def test_get_permission_list(self, client):
        permission = GlobalPermission.objects.create(name='permission_name', codename='permission_codename')
        permission2 = GlobalPermission.objects.create(name='permission_name2', codename='permission_codename2')
        url = reverse('global_permission_list')
        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['permission_list'][0]['id'] == permission.id
        assert response.data['permission_list'][0]['name'] == permission.name
        assert response.data['permission_list'][0]['codename'] == permission.codename
        assert response.data['permission_list'][1]['id'] == permission2.id
        assert response.data['permission_list'][1]['name'] == permission2.name
        assert response.data['permission_list'][1]['codename'] == permission2.codename


class TestCompanyGroupListView:
    def test_list_company_group(self, group_with_permissions, rf, company, company_contact_rel):
        user = company.get_user()
        company.groups.add(group_with_permissions)
        url = reverse('company_group_list')
        request = rf.get(url)
        force_authenticate(request, user=user)
        response = CompanyGroupListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['results'][0]['id'] == group_with_permissions.id
        assert len(response.data['results'][0]['permissions']) == 2
        assert 'id' in response.data['results'][0]['permissions'][0]
        assert 'name' in response.data['results'][0]['permissions'][0]
        assert 'codename' in response.data['results'][0]['permissions'][0]


class TestAddUserToGroupView:
    def test_add_user_to_group(self, user, group, client):
        data = {
            'user_id': user.id
        }
        url = reverse('add_user_to_group', kwargs={'id': group.id})
        response = client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        assert user in group.user_set.all()


class TestRemoveUserFromGroupView:
    def test_remove_user_from_group(self, user, group, client):
        group.user_set.add(user)
        data = {
            'user_id': user.id
        }
        url = reverse('remove_user_from_group', kwargs={'id': group.id})
        response = client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        assert user not in group.user_set.all()


class TestCompanyGroupCreateView:
    def test_create_company_group(self, company, rf, company_contact_rel):
        user = company.get_user()
        data = {
            "name": 'group_name'
        }
        url = reverse('company_group_create')
        request = rf.post(url, data=data)
        force_authenticate(request, user=user)
        response = CompanyGroupCreateView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert company.groups.count() == 1
        assert company.groups.first().name == data['name']


class TestRevokeGroupGlobalPermissionView:
    def test_revoke_group_permission(self, group_with_permissions, client):
        permission_ids = group_with_permissions.permissions.all().values_list('id', flat=True)
        data = {
            "permission_list": list(permission_ids)
        }
        url = reverse('revoke_group_global_permission', kwargs={'id': group_with_permissions.id})
        response = client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        assert len(group_with_permissions.permissions.all()) == 0

    def test_empty_permission_list(self, group, client):
        data = {
            "permission_list": list()
        }
        url = reverse('revoke_group_global_permission', kwargs={'id': group.id})
        response = client.post(url, data=data)

        assert response.status_code == 400
        assert 'Ensure this field has at least 1 elements.' in response.data['errors']['permission_list']

    def test_nonexistent_permission(self, client, group):
        last_permission = GlobalPermission.objects.all().order_by('-id')[0]
        data = {
            "permission_list": [last_permission.id+1]
        }
        url = reverse('revoke_group_global_permission', kwargs={'id': group.id})
        response = client.post(url, data=data)

        assert response.status_code == 400
        assert 'Some permissions dont exist.' in response.data['errors']['permission_list']


class TestRevokeUserGlobalPermissionView:
    def test_revoke_user_permission(self, user, client):
        permission = GlobalPermission.objects.create(name='permission_name', codename='permission_codename')
        user.user_permissions.add(permission)
        permission_ids = user.user_permissions.all().values_list('id', flat=True)
        data = {
            "permission_list": list(permission_ids)
        }
        url = reverse('revoke_user_global_permission', kwargs={'id': user.id})
        response = client.post(url, data=data)

        assert response.status_code == status.HTTP_200_OK
        assert len(user.user_permissions.all()) == 0

    def test_empty_permission_list(self, user, client):
        data = {
            "permission_list": list()
        }
        url = reverse('revoke_user_global_permission', kwargs={'id': user.id})
        response = client.post(url, data=data)

        assert response.status_code == 400
        assert 'Ensure this field has at least 1 elements.' in response.data['errors']['permission_list']

    def test_nonexistent_permission(self, client, user):
        last_permission = GlobalPermission.objects.all().order_by('-id')[0]
        data = {
            "permission_list": [last_permission.id+1]
        }
        url = reverse('revoke_user_global_permission', kwargs={'id': user.id})
        response = client.post(url, data=data)

        assert response.status_code == 400
        assert 'Some permissions dont exist.' in response.data['errors']['permission_list']


class TestCompanyGroupDeleteView:
    def test_delete_group(self, group, client):
        group_id = group.id
        url = reverse('company_group_delete', kwargs={'id': group_id})
        response = client.get(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert Group.objects.filter(id=group_id).count() == 0


class TestCompanyUserListView:
    @pytest.mark.django_db
    def test_get_user_list(self, company, client, user, company_contact_rel):
        user2 = User.objects.create_user(email='test2@test.tt', phone_mobile='+12345678903', password='test1234')
        user3 = User.objects.create_user(email='test3@test.tt', phone_mobile='+12345678904', password='test1234')
        user2.contact.first_name = 'John'
        user2.contact.last_name = 'Doe'
        user2.contact.save()
        user3.contact.first_name = 'John'
        user3.contact.last_name = 'Doe'
        user3.contact.save()
        company_contact = CompanyContact.objects.create(contact=user.contact)
        company_contact2 = CompanyContact.objects.create(contact=user2.contact)
        company_contact3 = CompanyContact.objects.create(contact=user3.contact)
        CompanyContactRelationship.objects.create(company=company, company_contact=company_contact)
        CompanyContactRelationship.objects.create(company=company, company_contact=company_contact2)
        CompanyContactRelationship.objects.create(company=company, company_contact=company_contact3)

        url = reverse('company_users_list')
        client.force_login(company.primary_contact.contact.user)
        response = client.get(url)
        id_list = [x['id'] for x in response.data['user_list']]
        name_list = [x['name'] for x in response.data['user_list']]

        assert response.status_code == 200
        assert len(response.data['user_list']) == 3
        assert str(user.id) in id_list
        assert str(user2.id) in id_list
        assert str(user3.id) in id_list
        assert user.get_full_name() in name_list
        assert user2.get_full_name() in name_list
        assert user3.get_full_name() in name_list


class TestUserGroupListView:
    def test_get_groups_of_user(self, client, user):
        group1 = Group.objects.create(name='group1')
        group2 = Group.objects.create(name='group2')
        user.groups.add(group1, group2)
        url = reverse('user_group_list', kwargs={'id': user.id})
        client.force_login(user)
        response = client.get(url)

        assert response.data['results'][0]['id'] == group1.id
        assert response.data['results'][0]['name'] == group1.name
        assert response.data['results'][1]['id'] == group2.id
        assert response.data['results'][1]['name'] == group2.name


class TestUserCompanyFilesView:
    def test_company_file_list(self, client, user, company, company_contact_rel):
        auth_data = MYOBAuthData.objects.create(client_id='client_id',
                                                client_secret='client_secret',
                                                access_token='access_token',
                                                refresh_token='refresh_token',
                                                myob_user_uid='myob_user_uid',
                                                myob_user_username='myob_user_username',
                                                expires_in=1000,
                                                expires_at=timezone.now())
        company_file = MYOBCompanyFile.objects.create(cf_id='cf_id',
                                                      cf_uri='cf_uri',
                                                      cf_name='cf_name')
        MYOBCompanyFileToken.objects.create(company_file=company_file,
                                            auth_data=auth_data,
                                            company=company,
                                            cf_token='cf_token')
        url = reverse('user_company_files')
        client.force_login(user)
        response = client.get(url)

        assert len(response.data['company_files']) == 1
        assert response.data['company_files'][0]['id'] == str(company_file.id)
        assert response.data['company_files'][0]['uri'] == company_file.cf_uri
        assert response.data['company_files'][0]['name'] == company_file.cf_name
        assert response.data['company_files'][0]['authenticated'] == company_file.authenticated


class TestRefreshCompanyFilesView:
    @mock.patch('r3sourcer.apps.myob.api.wrapper.MYOBClient.get_company_files')
    def test_refresh_company_files(self, get_company_files, client, user, company, company_file_token, company_contact_rel):
        get_company_files.return_value = [{'Uri': 'https://ar2.api.myob.com/accountright/d12357c7-1065-451f-8657-0ca8c825b2f7', 'Country': 'AU', 'CheckedOutDate': None, 'ProductVersion': '2017.2', 'ProductLevel': {'Code': 30, 'Name': 'Plus'}, 'SerialNumber': '618909727781', 'LibraryPath': 'TS Workforce Pty Ltd', 'LauncherId': '878263e8-cb1e-49f9-a138-a74f21bef5c9', 'Name': 'TS Workforce Pty Ltd', 'CheckedOutBy': None, 'Id': 'd12357c7-1065-451f-8657-0ca8c825b2f7'}]
        company_file_count = MYOBCompanyFile.objects.count()
        company_file_token_count = MYOBCompanyFileToken.objects.count()
        last_refreshed = company.myob_settings.company_files_last_refreshed
        client.force_login(user)
        url = reverse('refresh_company_files')
        client.get(url)

        assert MYOBCompanyFile.objects.count() == company_file_count + 1
        assert MYOBCompanyFileToken.objects.count() == company_file_token_count + 1
        assert last_refreshed != MYOBSettings.objects.get(id=company.myob_settings.id).company_files_last_refreshed


class TestCheckCompanyFilesView:
    @mock.patch('r3sourcer.apps.myob.api.wrapper.MYOBClient.check_company_file')
    def test_check_company_file(self, check_company_file, client, user, company, company_file_token, company_contact_rel):
        check_company_file.return_value = True
        company_file_id = company_file_token.company_file.cf_id
        url = reverse('check_company_files')
        payload = {
            'id': company_file_id,
            'username': '',
            'password': ''
        }
        client.force_login(user)
        client.post(url, data=json.dumps(payload), content_type="application/json")

        assert check_company_file.called
        assert MYOBCompanyFile.objects.get(cf_id=company_file_token.company_file.cf_id).authenticated


class TestRefreshMYOBAccountsView:
    @mock.patch('r3sourcer.apps.myob.api.wrapper.MYOBClient.get_accounts')
    def test_myob_settings(self, get_accounts, user, client, company_file_token, company_contact_rel):
        mocked_response = mock.Mock()
        mocked_response.json.return_value = {'NextPageLink': None, 'Count': 1, 'Items': [{'TaxCode': None, 'OpeningBalance': 0.0, 'Classification': 'Asset', 'URI': 'https://ar1.api.myob.com/accountright/30f3396c-02e9-4a86-99e6-3bb2e832cb3d/GeneralLedger/Account/e7cd2a56-d8f6-44a5-b5bc-979010d4bef0', 'LastReconciledDate': None, 'BankingDetails': None, 'Description': '', 'DisplayID': '1-1100', 'RowVersion': '7437976259579084800', 'Level': 3, 'UID': 'e7cd2a56-d8f6-44a5-b5bc-979010d4bef0', 'Number': 1100, 'Type': 'OtherAsset', 'CurrentBalance': -141162.67, 'IsHeader': True, 'IsActive': True, 'ParentAccount': {'URI': 'https://ar1.api.myob.com/accountright/30f3396c-02e9-4a86-99e6-3bb2e832cb3d/GeneralLedger/Account/285f93c9-14ba-458c-a7f5-7819ddf2e12a', 'Name': 'Current Assets', 'DisplayID': '1-1000', 'UID': '285f93c9-14ba-458c-a7f5-7819ddf2e12a'}, 'Name': 'Bank Accounts'}]}
        get_accounts.return_value = mocked_response
        company_file_token.company_file.authenticated = True
        company_file_token.company_file.save()
        initial_account_count = MYOBAccount.objects.count()
        myob_settings = company_file_token.company.myob_settings
        last_refreshed = myob_settings.payroll_accounts_last_refreshed
        url = reverse('refresh_myob_accounts')
        client.force_login(user)
        client.get(url)

        assert MYOBAccount.objects.count() == initial_account_count + 1
        assert last_refreshed != MYOBSettings.objects.get(id=myob_settings.id).payroll_accounts_last_refreshed


class TestMYOBSettingsView:
    def test_myob_settings_get(self, user, client, primary_contact, company, myob_account, company_contact_rel):
        company_file = MYOBCompanyFile.objects.create(
            cf_id='id',
            cf_uri='uri',
            cf_name='name'
        )
        company.myob_settings.invoice_activity_account = myob_account
        company.myob_settings.invoice_company_file = company_file
        company.myob_settings.timesheet_company_file = company_file
        company.myob_settings.save()

        url = reverse('myob_settings')
        client.force_login(user)
        response = client.get(url).json()

        assert response['myob_settings']['timesheet_company_file']['id'] == str(company_file.id)
        assert response['myob_settings']['invoice_company_file']['id'] == str(company_file.id)
        assert response['myob_settings']['invoice_activity_account']['id'] == str(myob_account.id)

    def test_myob_settings_post(self, user, client, primary_contact, company, company_contact_rel):
        now = timezone.now()
        company_file = MYOBCompanyFile.objects.create(
            cf_id='d3edc1d7-7b31-437e-9fcd-000000000008',
            cf_uri='uri',
            cf_name='name'
        )
        account = MYOBAccount.objects.create(uid="d3edc1d7-7b31-437e-9fcd-000000000002",
                                             name='Business Bank Account',
                                             display_id='1-1120',
                                             classification="Asset",
                                             type='Bank',
                                             number='1120',
                                             description="Bank account",
                                             is_active=True,
                                             level=4,
                                             opening_balance=10000.00,
                                             current_balance=5000.00,
                                             is_header=False,
                                             uri="/GeneralLedger/Account/eb043b43-1d66-472b-a6ee-ad48def81b96",
                                             row_version="5548997690873872384",
                                             company_file=company_file)
        data = {
            'invoice_activity_account': {"id": str(account.id)},
            'invoice_company_file': {"id": str(company_file.cf_id)},
            'timesheet_company_file': {"id": str(company_file.cf_id)},
            'payroll_accounts_last_refreshed': str(now),
            'company_files_last_refreshed': str(now),
        }
        url = reverse('myob_settings')
        client.force_login(user)
        client.post(url, data=json.dumps(data), content_type='application/json')
        myob_settings = MYOBSettings.objects.get(id=company.myob_settings.id)

        assert myob_settings.invoice_activity_account == account
        assert myob_settings.invoice_company_file == company_file
        assert myob_settings.timesheet_company_file == company_file
        assert myob_settings.payroll_accounts_last_refreshed == now
        assert myob_settings.company_files_last_refreshed == now


class TestMYOBAuthDataListView:
    @mock.patch('r3sourcer.apps.company_settings.views.get_site_master_company')
    def test_get(self, mock_company, user, client, company):
        mock_company.return_value = company

        auth_data = MYOBAuthData.objects.create(
            client_id='client_id1',
            client_secret='client_secret',
            access_token='access_token',
            refresh_token='refresh_token',
            myob_user_uid='myob_user_uid',
            myob_user_username='myob_user_username',
            expires_in=1,
            user=user,
            company=company
        )
        auth_data2 = MYOBAuthData.objects.create(
            client_id='client_id2',
            client_secret='client_secret',
            access_token='access_token',
            refresh_token='refresh_token',
            myob_user_uid='myob_user_uid',
            myob_user_username='myob_user_username2',
            expires_in=1,
            user=user,
            company=company
        )

        url = reverse('auth_data')
        client.force_login(user)
        response = client.get(url).json()

        assert len(response['auth_data_list']) == 2
        assert response['auth_data_list'][0]['myob_user_username'] == auth_data2.myob_user_username
        assert response['auth_data_list'][1]['myob_user_username'] == auth_data.myob_user_username


class TestMYOBAuthDataDeleteView:
    def test_delete(self, user, client):
        auth_data = MYOBAuthData.objects.create(
            client_id='client_id1',
            client_secret='client_secret',
            access_token='access_token',
            refresh_token='refresh_token',
            myob_user_uid='myob_user_uid',
            myob_user_username='myob_user_username',
            expires_in=1,
            user=user
        )

        url = reverse('auth_data_delete', kwargs={'id': auth_data.id})
        client.force_login(user)
        response = client.delete(url)

        assert response.status_code == 204
        assert MYOBAuthData.objects.all().count() == 0


class TestMYOBAPIKeyView:
    def test_get(self, client, user):
        url = reverse('myob_api_key')
        client.force_login(user)
        response = client.get(url).json()

        assert response['api_key'] == settings.MYOB_APP['api_key']
