import mock

from django.db.models import Q

from r3sourcer.apps.core.managers import TagManager
from r3sourcer.apps.core.models import Tag, CompanyContact, Contact, Address


class TestManagers(object):
    def test_tag_manager_active(self):
        manager = TagManager()
        manager.model = Tag
        assert str(manager.active().query) == str(
            manager.get_queryset().filter(active=True).query
        )


class TestAbstractObjectOwnerManager:
    def test_companycontact_owned_by_company(self, staff_company_contact,
                                             staff_relationship, company):
        result = CompanyContact.objects.owned_by(company)
        assert result.count() == 1
        assert result.filter(id=staff_company_contact.id).exists()

    def test_contact_owned_by_company(self, staff_company_contact,
                                      staff_relationship, company):
        result = Contact.objects.owned_by(company)
        assert result.count() == 1
        assert result.filter(id=staff_company_contact.contact.id).exists()

    def test_address_owned_by_contact(self, contact, contact_address):
        result = Address.objects.owned_by(contact)
        assert result.count() == 1

    def test_companycontact_owned_by_contact(self, contact, primary_contact):
        result = CompanyContact.objects.owned_by(contact)
        assert result.count() == 1

    @mock.patch.object(Address.objects, 'get_lookups', return_value=[])
    def test_owned_by_with_passable(self, mock_lookups, contact, contact_address):
        mock_passable = mock.PropertyMock(return_value=[Contact])
        type(Address.objects).passed_models = mock_passable

        result = Address.objects.owned_by(contact)
        assert result.count() == 1

    def test_get_lookups(self, contact, address):
        lookups = Contact.objects.get_lookups(address)

        assert len(lookups) == 1
        assert lookups[0].children == Q(address=address).children

    def test_get_lookups_with_path(self, contact, address):
        lookups = Contact.objects.get_lookups(address.country)

        assert len(lookups) == 4
