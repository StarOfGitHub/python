import pytest

from django.contrib.contenttypes.models import ContentType

from r3sourcer.apps.core import models
from r3sourcer.apps.core.utils import form_builder as form_builder_utils


@pytest.mark.django_db
class TestModelStorageHelperCls:
    """
    Testing r3sourcer.apps.core.utils.form_storage helper classes.

    """

    def test_simple_field(self):
        name, value = 'test_name', 'test value'
        simple_field = form_builder_utils.SimpleFieldHelper(name, value)
        assert simple_field.name == name
        assert simple_field.value == value

        with pytest.raises(AssertionError):
            form_builder_utils.SimpleFieldHelper('test-invalid-name', value)

        with pytest.raises(AssertionError):
            form_builder_utils.SimpleFieldHelper('0test', value)

        with pytest.raises(AssertionError):
            form_builder_utils.SimpleFieldHelper('-test', value)

    def test_related_field(self):
        value = 'test value'
        related_field = form_builder_utils.RelatedFieldHelper(models.CompanyContact, 'contact__first_name', value)

        assert related_field.value is None
        assert related_field.name == 'contact'
        assert 'first_name' in related_field.simple_fields
        assert related_field.simple_fields['first_name'].value == value

        with pytest.raises(AssertionError):
            related_field.process_field(value)

    def test_storage_helper(self):
        job_title = 'Software Developer'
        storage_helper = form_builder_utils.StorageHelper(models.CompanyContact, {
            'job_title': job_title,
            'contact__first_name': 'first name',
            'contact__last_name': 'last name',
            'contact__email': 'test@example.com',
            'contact__phone_mobile': '+79998887766'
        })
        storage_helper.process_fields()
        storage_helper.validate()

        instance = storage_helper.create_instance()
        assert isinstance(instance, models.CompanyContact)
        assert instance.job_title == job_title

        with pytest.raises(AssertionError) as exc:
            storage_helper.create_instance()

        assert str(exc.value) == 'Instance already created'

    def test_separate_lookup_method(self):
        contact_field = 'contact'
        first_name_field = 'first_name'
        test_field_name = form_builder_utils.StorageHelper.join_lookup_names(contact_field, first_name_field)
        field, lookup_field = form_builder_utils.StorageHelper.separate_lookup_name(test_field_name)
        assert field == contact_field
        assert lookup_field == first_name_field

        assert form_builder_utils.StorageHelper.separate_lookup_name('test_field_name') == ('test_field_name', '')
