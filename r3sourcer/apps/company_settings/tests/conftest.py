import pytest

from django.contrib.auth.models import Group

from r3sourcer.apps.candidate.models import CandidateContact, CandidateRel
from r3sourcer.apps.company_settings.models import MYOBAccount, GlobalPermission
from r3sourcer.apps.core.models import InvoiceRule, User, Company, CompanyContact, CompanyContactRelationship
from r3sourcer.apps.hr.models import PayslipRule
from r3sourcer.apps.myob.models import MYOBCompanyFileToken, MYOBCompanyFile, MYOBAuthData


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='test@test.tt', phone_mobile='+12345678901',
        password='test1234'
    )


@pytest.fixture
def user_sec(db):
    return User.objects.create_user(
        email='test_sec@test.tt', phone_mobile='+12345678902',
        password='test1234'
    )


@pytest.fixture
def contact(db, user):
    return user.contact


@pytest.fixture
def contact_sec(db, user_sec):
    return user_sec.contact


@pytest.fixture
def primary_contact(db, contact):
    return CompanyContact.objects.create(contact=contact)


@pytest.fixture
def company(db, primary_contact):
    return Company.objects.create(
        name='Company',
        business_id='123',
        registered_for_gst=True,
        type=Company.COMPANY_TYPES.master,
        primary_contact=primary_contact
    )


@pytest.fixture
def group(db):
    return Group.objects.create(name='test_group')


@pytest.fixture
def group_with_permissions(db, group):
    permission = GlobalPermission.objects.create(name='permission_name', codename='permission_codename')
    permission2 = GlobalPermission.objects.create(name='permission_name2', codename='permission_codename2')
    group.permissions.add(permission, permission2)
    return group


@pytest.fixture
def permission_get(db):
    return GlobalPermission.objects.create(name='permission_get', codename='permission_get')


@pytest.fixture
def permission_post(db):
    return GlobalPermission.objects.create(name='permission_post', codename='permission_post')


@pytest.fixture
def permission_patch(db):
    return GlobalPermission.objects.create(name='permission_patch', codename='permission_patch')


@pytest.fixture
def permission_delete(db):
    return GlobalPermission.objects.create(name='permission_delete', codename='permission_delete')


@pytest.fixture
def payslip_rule(db, company):
    company.payslip_rules.all().delete()

    return PayslipRule.objects.create(
        company=company,
        comment='comment',
    )


@pytest.fixture
def invoice_rule(db, company):
    company.invoice_rules.all().delete()

    return InvoiceRule.objects.create(
        company=company,
        serial_number='TEST',
        starting_number=100,
        comment='comment',
        notice='notice'
    )


@pytest.fixture
def myob_account(db, company_file):
    return MYOBAccount.objects.create(
        uid="d3edc1d7-7b31-437e-9fcd-000000000001",
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
        company_file=company_file
    )


@pytest.fixture
def company_file(db):
    return MYOBCompanyFile.objects.create(
        cf_id='cf_id',
        cf_uri='cf_uri',
        cf_name='cf_name'
    )


@pytest.fixture
def auth_data(db, user):
    return MYOBAuthData.objects.create(
        client_id='client_id',
        client_secret='client_secret',
        access_token='access_token',
        refresh_token='refresh_token',
        myob_user_uid='myob_user_uid',
        myob_user_username='myob_user_username',
        expires_in=1000,
        user=user
    )


@pytest.fixture
def company_file_token(db, company_file, auth_data, company):
    return MYOBCompanyFileToken.objects.create(
        company_file=company_file,
        auth_data=auth_data,
        company=company,
        cf_token='cf_token'
    )


@pytest.fixture
def candidate_contact(db, contact):
    return CandidateContact.objects.create(
        contact=contact
    )


@pytest.fixture
def candidate_contact_sec(db, contact_sec):
    return CandidateContact.objects.create(
        contact=contact_sec
    )


@pytest.fixture
def candidate_rel(db, candidate_contact, company, primary_contact):
    return CandidateRel.objects.create(
        candidate_contact=candidate_contact,
        master_company=company,
        company_contact=primary_contact,
    )


@pytest.fixture
def candidate_rel_sec(db, candidate_contact_sec, company, primary_contact):
    return CandidateRel.objects.create(
        candidate_contact=candidate_contact_sec,
        master_company=company,
        company_contact=primary_contact,
    )


@pytest.fixture
def company_contact_rel(db, primary_contact, company):
    return CompanyContactRelationship.objects.create(
        company_contact=primary_contact,
        company=company
    )
