import pytest

from r3sourcer.apps.core.fields import ContactLookupField
from r3sourcer.apps.core.models import Contact, User


@pytest.mark.django_db
class TestContactLookup:

    @pytest.fixture
    def field(self):
        return ContactLookupField(lookup_model=Contact)

    def test_contact_attrs_getter(self):
        user = User()
        user.contact = Contact(email='test@test.tt')
        email = User.__dict__['email'].__get__(user, User)

        assert email == 'test@test.tt'

    def test_contact_attrs_getter_on_none_instance(self):
        email = User.__dict__['email'].__get__(None, User)

        assert type(email) == ContactLookupField

    def test_contact_attrs_setter_on_none_instance(self):
        res = User.__dict__['email'].__set__(None, 'test@test.tt')

        assert res is None

    def test_contact_attrs_setter(self):
        user = User()
        user.email = 'test@test.tt'

        assert user.email == 'test@test.tt'

    def test_clean(self, field, user):
        field.lookup_field = Contact._meta.get_field('email')
        cleaned_value = field.clean('test@test.tt', user)

        assert cleaned_value == 'test@test.tt'

    def test_clean_on_none(self, field):
        field.lookup_field = Contact._meta.get_field('email')
        cleaned_value = field.clean('test@test.tt', None)

        assert cleaned_value == 'test@test.tt'

    def test_get_default_on_none(self, field):
        assert field.get_default() is None

    def test_get_default(self, field):
        field.lookup_field = Contact._meta.get_field('email')
        assert field.get_default() is None
