import os

import mock
import pytest

from _pytest.compat import NoneType, STRING_TYPES
from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from freezegun import freeze_time

from r3sourcer.apps.core.models import (
    User, CompanyContact, BankAccount, CompanyAddress, ContactUnavailability,
    CompanyTradeReference, Note, Tag, InvoiceLine, FileStorage, Contact,
    Company, CompanyLocalization, Invoice, WorkflowNode,
    Workflow, SiteCompany, CompanyRel, CompanyContactRelationship
)


@pytest.mark.django_db
class TestUser:

    def test_create_user_with_email(self):
        email = 'test@test.tt'
        user = User.objects.create_user(
            email=email, password='test1234'
        )

        assert user.id is not None
        assert not user.is_superuser
        assert not user.is_staff
        assert user.contact.email == 'test@test.tt'

    def test_create_user_with_phone_number(self):
        phone_mobile = '+12345678901'
        user = User.objects.create_user(
            phone_mobile=phone_mobile, password='test1234'
        )

        assert user.id is not None
        assert not user.is_superuser
        assert not user.is_staff
        assert user.contact.phone_mobile == phone_mobile

    def test_create_user_with_email_and_phone_number(self):
        phone_mobile = '+12345678901'
        email = 'test@test.tt'
        user = User.objects.create_user(
            phone_mobile=phone_mobile, email=email, password='test1234', is_staff=True
        )

        assert user.id is not None
        assert not user.is_superuser
        assert not user.is_staff
        assert user.contact.phone_mobile == phone_mobile
        assert user.contact.email == email

    def test_create_superuser_with_email(self):
        email = 'test@test.tt'
        user = User.objects.create_superuser(
            email=email, password='test1234'
        )

        assert user.id is not None
        assert user.is_superuser
        assert user.is_staff
        assert user.contact.email == 'test@test.tt'

    def test_create_user_without_email_and_phone_number(self):
        with pytest.raises(ValueError):
            User.objects.create_user(
                password='test1234'
            )

    def test_user_str(self, user):
        assert str(user) == str(user.contact)

    def test_user_get_short_name(self, user):
        assert user.get_short_name() == str(user)

    def test_get_company_as_manager(self, user, primary_contact, company):
        company_contact = user.contact.company_contact.first()
        company_contact.role = 'manager'
        company_contact.save()
        CompanyContactRelationship.objects.create(
            company_contact=company_contact,
            company=company
        )
        assert user.is_manager()
        assert user.company == company

    def test_get_company_as_client(self, user, company):
        company_contact = user.contact.company_contact.first()
        company_contact.role = 'client'
        company_contact.save()
        CompanyContactRelationship.objects.create(
            company_contact=company_contact,
            company=company
        )
        assert user.is_client()
        assert user.company == company

    def test_get_company_as_candidate(self, user_sec, candidate_contact_sec, candidate_rel_sec, company):
        assert user_sec.is_candidate()
        assert user_sec.company == company

    def test_user_track_login(self, user):
        assert user.last_login is None
        user.track_login()
        assert user.last_login is not None


@pytest.mark.django_db
class TestContact:

    @pytest.fixture
    def unavalability(self, contact):
        from_date = date(2017, 1, 2)
        to_date = date(2017, 1, 8)
        return ContactUnavailability.objects.create(
            unavailable_from=from_date,
            unavailable_until=to_date,
            contact=contact
        )

    def test_contact_availability(self, contact):
        contact.is_available = True

        assert contact.get_availability()

    def test_contact_unavailability(self, contact):
        contact.is_available = False

        assert not contact.get_availability()

    @freeze_time(date(2017, 1, 2))
    def test_contact_unavailability_start(self, contact, unavalability):
        assert not contact.get_availability()

    @freeze_time(date(2017, 1, 8))
    def test_contact_unavailability_end(self, contact, unavalability):
        assert not contact.get_availability()

    @freeze_time(date(2017, 1, 10))
    def test_contact_today_out_of_unavailability_range(self, contact, unavalability):
        assert contact.get_availability()

    def test_is_company_contact_successfully(self, staff_user, staff_relationship):
        assert staff_user.contact.is_company_contact()

    def test_is_company_contact_unsuccessfully(self, contact):
        assert not contact.is_company_contact()

    def test_get_company_contact_by_company_successfully(self, staff_user, company,
                                                         staff_company_contact, staff_relationship):
        assert staff_user.contact.get_company_contact_by_company(company) == staff_company_contact

    def test_get_company_contact_by_company_none(self, staff_user, company,
                                                 staff_company_contact):
        assert not staff_user.contact.get_company_contact_by_company(company) == staff_company_contact
        assert staff_user.contact.get_company_contact_by_company(company) is None

    def test_is_master_related_successfully(self, staff_user, staff_relationship):
        assert staff_user.contact.is_master_related()

    def test_is_master_related_unsuccessfully(self, staff_user):
        assert not staff_user.contact.is_master_related()


@pytest.mark.django_db
class TestAddress:

    def test_address_str(self, address):
        address_str = 'street0 \n1110 city\nAustralia'
        assert str(address) == address_str

    def test_address_full(self, address):
        full_address = 'street0,\ncity 1110 test,\nAustralia'
        assert str(address.get_full_address()) == full_address

    def test_address_short(self, address):
        short_address = 'street0, city, 1110 test'
        assert str(address.get_address()) == short_address

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
    def test_set_address_coordinates(self, mock_fetch, address):
        address.fetch_geo_coord()

        assert address.latitude == 42
        assert address.longitude == 42

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
    def test_change_address_and_update_coordinates(self, mock_fetch, address):
        address.street_address = 'street 1'
        address.save()

        assert address.latitude == 42
        assert address.longitude == 42


@pytest.mark.django_db
class TestCompanyContact:

    def test_company_contact_str(self, user):
        contact = user.contact
        company_contact = CompanyContact(job_title='Tester', contact=contact)
        result = 'Tester {}'.format(contact)

        assert str(company_contact) == result

    def test_get_master_company(self, staff_company_contact, staff_relationship):
        assert staff_relationship.company in staff_company_contact.get_master_company()


@pytest.mark.django_db
class TestBankAccount:

    def test_bank_account_str(self):
        bank_account = BankAccount(bank_name='Bank',
                                   bank_account_name='Tester',
                                   bsb='111111',
                                   account_number='1234567890')

        assert str(bank_account) == 'Bank: Tester'


@pytest.mark.django_db
class TestCompany:

    def test_is_primary_contact_assigned(self, company):
        assert company.is_primary_contact_assigned()

    def test_is_primary_contact_not_assigned(self, company):
        company.primary_contact = None
        assert not company.is_primary_contact_assigned()

    def test_is_business_id_set(self, company):
        assert company.is_business_id_set()

    def test_is_business_id_not_set(self, company):
        company.business_id = None
        assert not company.is_business_id_set()

        company.business_id = ''
        assert not company.is_business_id_set()

    def test_get_contact(self, company, contact):
        company_manager_contact = company.get_contact()
        assert company_manager_contact is not None
        assert company_manager_contact == contact

    def test_get_contact_manager_does_not_set(self, company):
        company.primary_contact = None
        assert company.get_contact() is None

    def test_get_user(self, company, user):
        company_manager_user = company.get_user()
        assert company_manager_user is not None
        assert company_manager_user == user

    def test_get_user_manager_does_not_set(self, company):
        company.primary_contact = None
        assert company.get_user() is None

    def test_get_hq_address(self, company, address):
        company_address = CompanyAddress.objects.create(
            company=company, address=address, hq=True
        )
        company_hq_address = company.get_hq_address()

        assert company_hq_address is not None
        assert company_hq_address == company_address

    def test_get_not_existing_hq_address(self, company, address):
        assert company.get_hq_address() is None

    def test_get_master_company_for_master(self, company):
        assert len(company.get_master_company()) == 1
        assert company in company.get_master_company()

    def test_get_master_company_for_regular(self, company, company_rel):
        assert len(company_rel.regular_company.get_master_company()) == 1
        assert company in company_rel.regular_company.get_master_company()

    def test_get_master_company_for_regular_recursively(self, company, primary_manager, company_rel):
        regular_company = Company.objects.create(
            name='RegCompany2',
            business_id='222',
            registered_for_gst=True
        )

        CompanyRel.objects.create(
            master_company=company_rel.regular_company,
            regular_company=regular_company,
            manager=primary_manager
        )

        assert len(regular_company.get_master_company()) == 1
        assert company in regular_company.get_master_company()
        assert company_rel.regular_company not in regular_company.get_master_company()

    def test_get_master_company_for_regular_returns_multiple(self, company, primary_manager, company_rel):
        master_company = Company.objects.create(
            name='MasterCompany2',
            business_id='222',
            registered_for_gst=True,
            type=Company.COMPANY_TYPES.master
        )

        CompanyRel.objects.create(
            master_company=master_company,
            regular_company=company_rel.regular_company,
            manager=primary_manager
        )

        master_companies = company_rel.regular_company.get_master_company()
        assert len(master_companies) == 2
        assert company in master_companies
        assert master_company in master_companies

    def test_get_regular_companies_none(self, company):
        assert len(company.get_regular_companies()) == 0

    def test_get_regular_companies_not_none(self, company, company_rel):
        reg_companies = company.get_regular_companies()
        assert len(reg_companies) == 1
        assert company_rel.regular_company in reg_companies

    def test_get_country_code(self, company, hq_company_address):
        assert company.get_country_code() == 'AU'

    def test_default_get_country_code(self, company):
        assert company.get_country_code() == 'EE'

    def test_get_active_workers(self, company_regular, timesheet_approved, timesheet_second_approved):
        assert company_regular.active_workers() == 2

    def test_get_active_workers_with_inactive(self, company_regular, timesheet_approved, timesheet_second_approved, timesheet_second_approval_pending):
        assert company_regular.active_workers() == 2

    def test_get_active_workers_with_other_offer(self, company_regular, company_other, timesheet_approved, timesheet_other_approved):
        assert company_regular.active_workers() == 1
        assert company_other.active_workers() == 1

    def test_get_active_workers_ids_with_inactive(self, company_regular, timesheet_approved, timesheet_second_approval_pending):
        assert len(company_regular.get_active_workers_ids()) == 2

    def test_get_active_workers_ids_without_timesheets(self, company):
        assert len(company.get_active_workers_ids()) == 0

    def test_get_active_workers_ids_with_other_(self, company_other):
        assert len(company_other.get_active_workers_ids()) == 0

    def test_get_active_workers_ids(self, company_regular, timesheet_approved, timesheet_second_approval_pending):
        active_workers = company_regular.get_active_workers_ids()
        assert timesheet_approved.job_offer.candidate_contact.id in list(active_workers)
        assert timesheet_second_approval_pending.job_offer.candidate_contact.id in list(active_workers)
        assert len(active_workers) == 2

@pytest.mark.django_db
class TestCompanyAddress:

    def test_first_address_for_company_should_be_hq(self, company, addresses):
        CompanyAddress.objects.create(
            company=company, address=addresses[0]
        )

        hq_address = company.get_hq_address()

        assert hq_address is not None

    def test_only_one_hq_address_for_company(self, company, addresses):
        CompanyAddress.objects.create(
            company=company, address=addresses[0], hq=True
        )
        second_address = CompanyAddress.objects.create(
            company=company, address=addresses[1], hq=True
        )

        assert company.company_addresses.filter(hq=True).count() == 1
        assert company.get_hq_address() == second_address

    def test_change_hq_address_for_company(self, company, addresses):
        first_address = CompanyAddress.objects.create(
            company=company, address=addresses[0], hq=True
        )
        second_address = CompanyAddress.objects.create(
            company=company, address=addresses[1], hq=False
        )

        assert company.company_addresses.filter(hq=True).count() == 1
        assert company.get_hq_address() == first_address

        second_address.hq = True
        second_address.save()

        assert company.company_addresses.filter(hq=True).count() == 1
        assert company.get_hq_address() == second_address

    def test_get_master_company(self, company, addresses):
        ca = CompanyAddress.objects.create(
            company=company, address=addresses[0], hq=True
        )
        assert company in ca.get_master_company()


@pytest.mark.django_db
class TestFileStorage:
    @pytest.fixture
    def content_file(self):
        """Dummy file object for file tests"""
        return ContentFile('Hello, World!!', 'my_file.txt')

    def check_content_validation(self, owner, content_file, pattern):
        # Creating sample FileStorage instance with owner and file specified and save it in database
        file_storage = FileStorage()
        file_storage.owner = owner
        file_storage.content.save(content_file.name, content_file)

        # Check file saved to expected location
        path = os.path.join(settings.BASE_DIR, pattern.format(owner=owner, filename=content_file.name))
        assert file_storage.content.path == path

    def test_contact_files(self, content_file):
        """Test contacts files in file storage are using correct path"""
        contact = Contact(email='test42@test.tt')
        contact.save()
        self.check_content_validation(contact, content_file, 'var/www/media/contacts/{owner.id}/{filename}')

    def test_company_files(self, content_file):
        """Test company files in file storage are using correct path"""
        company = Company()
        company.save()
        self.check_content_validation(company, content_file, 'var/www/media/companies/{owner.id}/{filename}')

    def test_files_without_owner(self, content_file):
        """Test exception is raised when file assigned without file holder"""
        file_storage = FileStorage()
        with pytest.raises(NotImplementedError):
            file_storage.content.save(content_file.name, content_file)

    def test_files_with_wrong_owner(self, content_file, address):
        file_storage = FileStorage()
        file_storage.owner = address
        with pytest.raises(NotImplementedError):
            file_storage.content.save(content_file.name, content_file)


@pytest.mark.django_db
class TestCompanyTradeReference:
    def test_company_trade_reference_str(self, company):
        reference = CompanyTradeReference()
        reference.company = company
        reference.referral_company_name = 'aaa'
        assert str(reference) == _('{} from {}').format(reference.company.name, reference.referral_company_name)


@pytest.mark.django_db
class TestNote:
    def test_note_str(self, company):
        note = Note()
        note.object = company
        assert str(note) == '{} {}'.format(str(note.content_type), _("Note"))


@pytest.mark.django_db
class TestTag:
    def test_tag_str(self):
        tag = Tag()
        assert str(tag) == str(tag.name)

    # def test_original_active_tracked(self):
    #     tag = Tag.add_root(active=True)
    #     tag.active = False
    #     assert tag._Tag__original_active != tag.active
    #     tag.candidate_tags = dict()
    #     tag.save()
    #     assert tag._Tag__original_active == tag.active
    #     assert tag.candidate_tags == dict(verified_by=None)


@pytest.mark.django_db
class TestInvoiceLine:

    @freeze_time(datetime(2017, 1, 1))
    def test_invoice_line_str(self, company, invoice):
        line = InvoiceLine()
        line.invoice = invoice
        # TODO: Fix timezone
        line.date = datetime.now().date()
        assert str(line) == '{}: 01/01/2017'.format(str(line.invoice))


@pytest.mark.django_db
class TestCompanyLocalization:

    def test_country_metadata(self):
        metadata = CompanyLocalization.get_company_metadata('NZ')
        self.check_metadata_format(metadata)

    def test_default_metadata(self):
        metadata = CompanyLocalization.get_company_metadata()
        self.check_metadata_format(metadata)

    def test_partial_metadata(self, kr_localization):
        metadata = CompanyLocalization.get_company_metadata('KR')
        self.check_metadata_format(metadata)

    def check_metadata_format(self, metadata):
        assert 'business_id' in metadata
        assert 'tax_number' in metadata
        for value in metadata.values():
            assert 'active' in value
            assert isinstance(value['active'], bool)
            assert 'verbose_value' in value
            assert isinstance(value['verbose_value'], (STRING_TYPES, NoneType))
            assert 'help_text' in value
            assert isinstance(value['help_text'], (STRING_TYPES, NoneType))


@pytest.mark.django_db
class TestOrder:

    def test_order_creation(self, order):
        assert str(order) == "{}, {}".format(order.provider_company, order.customer_company)
        assert order.get_provider() == order.provider_company
        assert order.get_customer() == order.customer_company


@pytest.mark.django_db
class TestSiteCompany:
    def test_site_company_str(self, company, site):
        sc = SiteCompany(company=company, site=site)
        assert str(sc) == "{}: {}".format(site, company)

    def test_get_master_company(self, company, site):
        sc = SiteCompany(company=company, site=site)
        assert company in sc.get_master_company()


@pytest.mark.django_db
class TestCompanyContactRelationship:
    def test_get_closest_company_equal_to_master(self, company, staff_relationship):
        assert staff_relationship.get_closest_company() == company
        assert company in staff_relationship.get_master_company()

    def test_get_closest_company_equal_to_regular(self, staff_company_contact, company_rel):
        staff_relationship = CompanyContactRelationship.objects.create(
            company_contact=staff_company_contact,
            company=company_rel.regular_company,
        )

        assert staff_relationship.get_closest_company() == company_rel.regular_company
        assert company_rel.regular_company not in staff_relationship.get_master_company()
        assert company_rel.master_company in staff_relationship.get_master_company()

    def test_get_closest_company_expired(self, staff_relationship):
        # TODO: Fix timezone
        staff_relationship.termination_date = timezone.now() - timedelta(days=1)
        staff_relationship.save()
        assert staff_relationship.get_closest_company() is None


@pytest.mark.django_db
class TestInvoice:
    def test_invoice_number(self, company, company_regular):
        invoice_rule = company_regular.invoice_rules.first()
        invoice_rule.serial_number = 'TST'
        invoice_rule.starting_number = 100
        invoice_rule.save()

        invoice = Invoice.objects.create(
            provider_company=company,
            customer_company=company_regular,
            total_with_tax=20,
            total=15,
            tax=5,
            myob_number='test'
        )
        assert invoice.number == '00001'

    def test_invoice_number_without_serial_number(self, company, company_regular):
        invoice_rule = company_regular.invoice_rules.first()
        invoice_rule.serial_number = ''
        invoice_rule.starting_number = 100
        invoice_rule.save()

        invoice = Invoice.objects.create(
            provider_company=company,
            customer_company=company_regular,
            total_with_tax=20,
            total=15,
            tax=5,
            myob_number='test'
        )
        assert invoice.number == '00001'


class TestTemplateMessage:
    def test_template_message_str(self, email_test_message_template):
        assert str(email_test_message_template) == "Test template"

    def test_compile(self, email_test_message_template, user):
        params = {
            "user": user,
            "domain": "test.com"
        }

        result = email_test_message_template.compile(**params)
        assert result["id"] == email_test_message_template.id
        assert result["subject"] == "Hello from test.com"
        assert result["html"] == "Hello {}".format(user.email)

    def test_compile_string(self, email_test_message_template):
        params = {
            "user": "New user"
        }
        compiled, = email_test_message_template.compile_string(
            email_test_message_template.message_text_template,
            **params
        )
        assert compiled == "Hello New user"

    def test_get_dict_values(self, email_test_message_template, user):
        params = {
            "user": user
        }
        values_dict = email_test_message_template.get_dict_values(
            params, *[email_test_message_template.message_html_template])
        assert "user__email" in values_dict.keys()
        assert values_dict["user__email"] == user.email


@pytest.mark.django_db
class TestWorkflowNode:

    def _get_company(self):
        return Company.objects.get(name='New C')

    def get_node(self, number):
        return WorkflowNode.objects.get(number=number)

    @pytest.fixture
    def workflow_obj(self, workflow_ct):
        return Workflow.objects.get(name="test_workflow", model=workflow_ct)

    @mock.patch('r3sourcer.apps.core.models.core.get_default_company')
    def test_validate_node(self, mock_default_company, company):
        mock_default_company.return_value = self._get_company()

        assert WorkflowNode.validate_node(
            10, None, company, True, {}, True, None
        ) is None

    @mock.patch('r3sourcer.apps.core.models.core.get_default_company')
    def test_validate_node_default_company(self, mock_default_company):
        mock_default_company.return_value = self._get_company()

        assert WorkflowNode.validate_node(
            10, None, self._get_company(), True, {}, True, None
        ) is None

    @mock.patch('r3sourcer.apps.core.models.core.get_default_company')
    def test_validate_node_system_node_deactivate(self, mock_default_company,
                                                  company, workflow_obj):
        mock_default_company.return_value = self._get_company()

        with pytest.raises(ValidationError):
            WorkflowNode.validate_node(
                10, workflow_obj, company, False, {}, True, None
            )

    @mock.patch('r3sourcer.apps.core.models.core.get_default_company')
    def test_validate_node_system_node_rules(self, mock_default_company,
                                             company, workflow_obj):
        mock_default_company.return_value = self._get_company()

        with pytest.raises(ValidationError):
            WorkflowNode.validate_node(
                10, workflow_obj, company, True, {}, True, None
            )

    @mock.patch('r3sourcer.apps.core.models.core.get_default_company')
    def test_validate_node_change_number(self, mock_default_company,
                                         company, workflow_obj):
        mock_default_company.return_value = self._get_company()

        node = self.get_node(10)

        with pytest.raises(ValidationError):
            WorkflowNode.validate_node(
                20, workflow_obj, company, True, node.rules, False, node.id
            )

    @mock.patch('r3sourcer.apps.core.models.core.get_default_company')
    def test_validate_node_number_is_used(self, mock_default_company,
                                          workflow_obj):
        mock_default_company.return_value = self._get_company()

        node = self.get_node(10)

        with pytest.raises(ValidationError):
            WorkflowNode.validate_node(
                20, workflow_obj, self._get_company(), True, node.rules, False, node.id
            )
