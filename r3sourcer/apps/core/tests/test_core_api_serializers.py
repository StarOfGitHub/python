import copy
import itertools
from datetime import date

import pytest

from mock import patch, MagicMock, PropertyMock
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.utils import timezone
from django_mock_queries.query import MockModel, MockSet
from freezegun import freeze_time
from rest_framework import serializers, exceptions, relations

from r3sourcer.apps.core.api.fields import ApiBaseRelatedField
from r3sourcer.apps.core.api.serializers import (
    ApiMethodFieldsMixin, ApiBaseModelSerializer, AddressSerializer,
    ContactSerializer, CompanySerializer, CompanyContactSerializer,
    UserSerializer, CompanyContactRegisterSerializer, MetaFields,
    ApiFieldsMixin, CompanyAddressSerializer, WorkflowNodeSerializer,
    WorkflowObjectSerializer, WorkflowTimelineSerializer,
    NavigationSerializer, TrialSerializer, CompanyContactRenderSerializer,
    RELATED_DIRECT, RELATED_FULL, RELATED_NONE,
)
from r3sourcer.apps.core.models import (
    City, Region, Contact, Company, User, CompanyContact, CompanyAddress,
    WorkflowObject, WorkflowNode, ExtranetNavigation
)
from r3sourcer.apps.core.workflow import (
    NEED_REQUIREMENTS, ALLOWED, NOT_ALLOWED
)


@pytest.fixture
def double_tuple_fields():
    return (
        ('field_d', 'view_name_d'),
        ('field_e', 'view_name_e'),
        ('field_f', 'view_name_f'),
    )


@pytest.fixture
def string_field_data():
    return tuple('abcdef')


class BaseTestSerializer(ApiBaseModelSerializer):

    class Meta:
        fields = '__all__'
        model = City
        related_fields = {
            'country': ('id', 'code2', 'continent', 'name')
        }


class AnotherBaseTestSerializer(ApiBaseModelSerializer):

    class Meta:
        fields = ('name', 'display_name', 'country', '__str__')
        model = City


class CompanyTestSerializer(ApiBaseModelSerializer):
    city = AnotherBaseTestSerializer(required=False)

    class Meta:
        fields = ('name', 'parent', 'city')
        model = Company
        related = RELATED_DIRECT


class TestBaseMetadata:

    def get_class(self):
        class MetaFieldsTestSerializer(BaseTestSerializer, metaclass=MetaFields):
            contact = ContactSerializer(required=False)

            class Meta:
                fields = (
                    'name', 'country',
                    {'contact': ('first_name', 'last_name', )}
                )

        return MetaFieldsTestSerializer

    def test_meta_fields(self):
        seializer_class = self.get_class()

        assert set(seializer_class.Meta.fields) == {'name', 'country', 'contact', '__str__'}

    def test_meta_related_fields(self):
        seializer_class = self.get_class()

        assert 'contact' in seializer_class.Meta.related_fields
        assert set(seializer_class.Meta.related_fields['contact']) == {'first_name', 'last_name'}

    def test_get_super_meta(self):
        metaclass = MetaFields

        meta = metaclass._get_super_meta((CompanyTestSerializer, ))
        assert meta is CompanyTestSerializer.Meta

    def test_inherit_parent_meta(self):
        seializer_class = self.get_class()

        assert BaseTestSerializer.Meta in seializer_class.Meta.__bases__

    def test_inherit_parent_model(self):
        seializer_class = self.get_class()

        assert BaseTestSerializer.Meta.model is seializer_class.Meta.model

    def test_meta_without_fields(self):
        class MetaFieldsTestSerializer(serializers.Serializer, metaclass=MetaFields):

            class Meta:
                fields = []

        assert MetaFieldsTestSerializer.Meta.fields == []


@pytest.mark.django_db
class TestApiMethodFieldsMixin:

    @pytest.fixture
    def tuple_3_field_data(self):
        return tuple((a, a, a) for a in 'abcdef')

    def get_method_fields_mixin(self, method_fields=(), fields=None, getter_fields=None):
        """
        Create class inheriting target mixin with attributes being set to given or default values.
        If getter_fields is given then get_method_fields is overridden too.
        """

        attrs = dict()
        attrs['method_fields'] = copy.copy(method_fields)
        attrs['fields'] = fields and copy.copy(fields) or dict()

        if getter_fields is not None:
            attrs['get_method_fields'] = lambda self: getter_fields

        return type('MyApiMethodFieldsMixin', (ApiMethodFieldsMixin,), attrs)

    def test_method_fields_not_used(self):
        """Expect method_fields not used directly"""

        mixin_cls = self.get_method_fields_mixin(
            method_fields=tuple('def'),
            fields=dict(),
            getter_fields=list('cd')
        )
        instance = mixin_cls()
        assert set(instance.fields.keys()) == set('cd')

    def test_get_method_fields_result(self):
        """Expect get_method_fields return method_fields by default"""

        fields = tuple('abc')

        mixin_cls = self.get_method_fields_mixin(
            method_fields=fields,
            fields=dict()
        )
        instance = mixin_cls()
        assert instance.get_method_fields() == fields

    def test_empty_method_fields(self):
        """Expect empty method_fields does not change fields"""

        fields = dict(a=serializers.CharField())
        mixin_cls = self.get_method_fields_mixin(
            method_fields=(),
            fields=fields
        )
        instance = mixin_cls()
        assert instance.fields == fields

    def test_triple_tuple_format_raise_exception(self, tuple_3_field_data):
        """Expect 3-item tuples format raises exception"""

        mixin_cls = self.get_method_fields_mixin(
            method_fields=tuple_3_field_data,
            fields=dict()
        )
        message = (
            'Field data {!r} not supported. '
            'Method fields can be declared as list or tuple of field name '
            'strings or 2-item tuples in form (field_name, method_name)'
        )
        with pytest.raises(Exception) as e:
            mixin_cls()
        assert e.value.args == (message.format(tuple_3_field_data[0]),)

    def test_double_tuple_supported(self, double_tuple_fields):
        """Expect 2-item tuples format supported"""

        mixin_cls = self.get_method_fields_mixin(
            method_fields=double_tuple_fields
        )
        instance = mixin_cls()
        field_class = serializers.SerializerMethodField
        fields = {
            field_name: field_class(method_name=method_name)
            for field_name, method_name in double_tuple_fields
        }
        assert instance.fields.keys() == fields.keys()
        assert all(isinstance(x, field_class) for x in instance.fields.values())

    def test_strings_supported(self, string_field_data):
        """Expect string-item tuples format supported"""

        field_class = serializers.SerializerMethodField
        fields = {
            field_name: field_class()
            for field_name in string_field_data
        }

        mixin_cls = self.get_method_fields_mixin(
            method_fields=string_field_data
        )
        instance = mixin_cls()
        assert instance.fields.keys() == fields.keys()
        assert all(isinstance(x, field_class) for x in instance.fields.values())


@pytest.mark.django_db
class TestApiFullRelatedFieldsMixin:

    @pytest.fixture
    def city_data(self, country):
        return {
            'name': 'Test',
            'display_name': 'Test',
            'country': str(country.id)
        }

    def test_related_object_field_base_field_type(self):
        serializer = AnotherBaseTestSerializer()

        assert isinstance(serializer.fields['country'], ApiBaseRelatedField)

    def test_related_object_field_serializer_field(self):
        serializer = BaseTestSerializer()

        assert isinstance(serializer.fields['country'], ApiBaseModelSerializer)

    def test_related_object_field_serializer_type(self, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_DIRECT
        serializer = BaseTestSerializer()

        assert isinstance(serializer.fields['country'], ApiBaseModelSerializer)
        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_related_object_as_dict(self, city, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_DIRECT
        serializer = BaseTestSerializer(city)
        data = serializer.data

        assert isinstance(data['country'], dict)
        assert 'code2' in data['country']
        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_related_object_related_fields(self, city):
        serializer = BaseTestSerializer(city)
        data = serializer.data

        assert set(data['country']) == {'id', 'code2', 'continent', '__str__', 'name'}

    def test_related_object_default(self, city):
        serializer = BaseTestSerializer(city)
        data = serializer.data

        assert set(data['region']) == {'id', 'name', '__str__'}

    def test_related_object_direct(self, city, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_DIRECT
        serializer = BaseTestSerializer(city)
        data = serializer.data

        assert 'country' in data['region']
        assert set(data['region']['country']) == {'id', 'name', '__str__'}
        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_related_object_full(self, city, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_FULL
        serializer = BaseTestSerializer(city)
        data = serializer.data

        assert 'country' in data['region']
        assert 'code2' in data['region']['country']
        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_related_fields(self, city, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_DIRECT
        serializer = BaseTestSerializer(city)
        data = serializer.data

        assert set(data['country']) == {'id', 'code2', 'continent', '__str__', 'name'}
        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_create_objects_with_related_fields_minimal(self, country, city_data):
        serializer = BaseTestSerializer(data=city_data)
        serializer.is_valid(raise_exception=True)

        instance = serializer.save()

        assert instance.name == city_data['name']

    def test_create_objects_with_related_fields_full(self, country, city_data, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_FULL
        serializer = BaseTestSerializer(data=city_data)

        assert serializer.is_valid()

        instance = serializer.save()

        assert instance.name == city_data['name']
        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_partial_update_objects_with_related_fields(self, city):
        serializer = BaseTestSerializer(city, data={'population': 1}, partial=True)

        assert serializer.is_valid()

        instance = serializer.save()

        assert instance.population == 1

    def test_create_objects_with_related_fields(self, city_data, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_DIRECT

        city_data["country"] = {
            "continent": "EU",
            "code2": "LO",
            "name": "Lol"
        }
        serializer = AnotherBaseTestSerializer(data=city_data)

        assert serializer.is_valid()

        instance = serializer.save()

        assert instance.name == city_data['name']
        assert instance.country.code2 == city_data['country']['code2']
        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_create_objects_with_invalid_related_fields_raises_error(self, city_data, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_DIRECT

        city_data["country"] = {
        }
        serializer = AnotherBaseTestSerializer(data=city_data)

        assert not serializer.is_valid()

        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_update_objects_with_new_related_object_partial(self, city, country, city_data):
        city_data['country'] = {
            "continent": "EU",
            "code2": "LO",
            "name": "Lol"
        }
        serializer = AnotherBaseTestSerializer(city, data=city_data, partial=True)

        assert serializer.is_valid()

        instance = serializer.save()

        assert instance.name == city_data['name']

    def test_self_related_fields(self, city):
        serializer = CompanyTestSerializer()

        assert not isinstance(serializer.fields['parent'], ApiBaseModelSerializer)

    def test_field_error_on_related(self, settings):
        settings.REST_FRAMEWORK['RELATED'] = RELATED_DIRECT

        with patch.object(City._meta, 'get_field', side_effect=FieldDoesNotExist):
            serializer = AnotherBaseTestSerializer()

            assert not isinstance(serializer.fields['country'], ApiBaseModelSerializer)

        settings.REST_FRAMEWORK['RELATED'] = RELATED_NONE

    def test_recursive_related(self, settings):
        CompanyTestSerializer.Meta.related = RELATED_FULL
        serializer = CompanyTestSerializer()

        assert not isinstance(serializer.fields['parent'], ApiBaseModelSerializer)

    def test_serializer_fields(self):
        serializer = CompanyTestSerializer()

        assert isinstance(serializer.fields['city'], ApiBaseModelSerializer)

    def test_many_to_one_relation(self):
        class CompanyRelatedTestSerializer(ApiBaseModelSerializer):
            class Meta:
                fields = ('name', 'company_addresses')
                model = Company
        serializer = CompanyRelatedTestSerializer()

        assert isinstance(serializer.fields['company_addresses'], serializers.ListSerializer)

    def test_read_only_fields_attribute(self):
        class CompanyReadOnlyTestSerializer(ApiBaseModelSerializer):
            _read_only_fields = ('__str__', 'name')

            class Meta:
                fields = ('name', 'company_addresses')
                model = Company
        serializer = CompanyReadOnlyTestSerializer()

        assert isinstance(serializer.fields['name'], serializers.ReadOnlyField)

    def test_read_only_fields_attribute_model_label(self):
        class CompanyReadOnlyTestSerializer(ApiBaseModelSerializer):

            class Meta:
                fields = ('name', 'company_addresses', '__str__')
                model = Company
        serializer = CompanyReadOnlyTestSerializer()

        assert isinstance(serializer.fields['__str__'], serializers.ReadOnlyField)
        assert serializer.fields['__str__'].label == Company._meta.verbose_name.title()

    def test_read_only_fields_attribute_parent_label(self):
        class CompanyReadOnlyTestSerializer(ApiBaseModelSerializer):

            class Meta:
                fields = ('name', 'company_addresses', '__str__')
                model = Company
        serializer = CompanyReadOnlyTestSerializer(parent_name='test_tester')

        assert isinstance(serializer.fields['__str__'], serializers.ReadOnlyField)
        assert serializer.fields['__str__'].label == 'Test Tester'

    def test_get_id_related_field_many_related(self):
        serializer = AnotherBaseTestSerializer()

        field = relations.ManyRelatedField(
            child_relation=relations.PrimaryKeyRelatedField(
                label='label',
                queryset=Company.objects.all(),
                required=False
            ),
            label='label',
            required=False
        )

        res_field = serializer._get_id_related_field(field)

        assert res_field.queryset is not None


@pytest.mark.django_db
class TestApiBaseModelSerializer:

    @pytest.fixture
    def fields_data(self):
        sets = 'abcde', 'abc', 'bcd', 'cde', ''
        return itertools.product(sets, sets[:-1], sets)

    def get_serializer_class(self, required_fields=(), fields=None, getter_fields=None):
        """
        Create class inheriting target mixin with attributes being set to given or default values.
        If getter_fields is given then get_required_fields is overridden too.
        """

        attrs = dict()
        attrs['required_fields'] = copy.copy(required_fields)
        attrs['fields'] = fields and copy.copy(fields) or dict()

        if getter_fields is not None:
            attrs['get_required_fields'] = lambda self: getter_fields

        return type('MyApiBaseModelSerializer', (ApiBaseModelSerializer,), attrs)

    def test_allowed_fields_change_fields(self):
        """Expect serializer fields changed by allowed fields"""

        fields_data = dict(zip('abc', 'def'))

        serializer_class = self.get_serializer_class(fields=fields_data)
        instance = serializer_class(fields='ab')

        fields_data.pop('c')
        # ab == abc - c
        assert instance.fields == fields_data

    def test_fields_not_affected_without_fields(self):
        """Expect serializer fields not changed without fields argument"""

        fields_data = dict(zip('abc', 'def'))

        serializer_class = self.get_serializer_class(fields=fields_data)
        instance = serializer_class()
        assert instance.fields == fields_data

    def test_get_required_fields_result(self):
        """Expect get_required_fields returns required_fields data by default"""

        fields = tuple('abc')

        serializer_class = self.get_serializer_class(required_fields=fields)
        instance = serializer_class()

        assert instance.get_required_fields() == fields

    def test_required_fields_not_used(self):
        """Expect required_fields used only through get_required_fields"""

        test_fields = dict(zip('abcdef', '123456'))

        serializer_class = self.get_serializer_class(
            required_fields=set('def'),
            fields=test_fields,
            getter_fields=list('cd')
        )

        test_fields.pop('e')
        test_fields.pop('f')
        instance = serializer_class(fields=list('ab'))
        # ab + cd == abcdef - ef
        assert instance.fields == test_fields

    def test_fields_affected_by_formula(self, fields_data):
        """Expect serializer fields correlate to input variants by formula"""

        for existing, allowed, required in fields_data:
            fields = {e: None for e in existing}
            serializer_class = self.get_serializer_class(required_fields=required, fields=fields)

            instance = serializer_class(fields=allowed)
            # existing - (existing - allowed - required)
            assert set(instance.fields.keys()) == set(existing) & (set(allowed) | set(required))


@pytest.mark.django_db
class TestAddressSerializer:

    @pytest.fixture
    def invalid_region(self, country):
        return Region.objects.exclude(country=country).first()

    @pytest.fixture
    def invalid_au_region(self, city):
        return Region.objects.exclude(id=city.region.id).first()

    @pytest.fixture
    def invalid_city(self, country):
        return City.objects.exclude(country=country).first()

    @patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
    def test_save_address_with_valid_city_region_country(self, mock_geo, city, region, country):
        address_data = {
            'street_address': 'test',
            'country': str(country.id),
            'state': str(region.id),
            'city': str(city.id),
            'postal_code': '111',
        }

        serializer = AddressSerializer(data=address_data)

        assert serializer.is_valid()

        instance = serializer.save()

        assert instance.city.id == city.id
        assert instance.state.id == region.id
        assert instance.country.id == country.id

    def test_save_address_with_invalid_region_for_country(self, country, invalid_region):
        address_data = {
            'street_address': 'test',
            'country': str(country.id),
            'state': str(invalid_region.id),
            'postal_code': '111',
        }

        serializer = AddressSerializer(data=address_data)

        assert not serializer.is_valid()
        assert 'state' in serializer.errors

    def test_save_address_with_invalid_city_for_country(self, country, invalid_city):
        address_data = {
            'street_address': 'test',
            'country': str(country.id),
            'city': str(invalid_city.id),
            'postal_code': '111',
        }

        serializer = AddressSerializer(data=address_data)

        assert not serializer.is_valid()
        assert 'city' in serializer.errors

    def test_save_address_with_invalid_city_for_region(self, country, city, invalid_au_region):
        address_data = {
            'street_address': 'test',
            'country': str(country.id),
            'state': str(invalid_au_region.id),
            'city': str(city.id),
            'postal_code': '111',
        }

        serializer = AddressSerializer(data=address_data)

        assert not serializer.is_valid()
        assert 'city' in serializer.errors


class SerializerMixin:
    serializer_class = None

    def execute_serializer(self, *args, **kwargs):
        serializer = self.serializer_class(*args, **kwargs)
        serializer.is_valid(raise_exception=True)
        return serializer.save()


@pytest.mark.django_db
class TestUserSerializer(SerializerMixin):
    serializer_class = UserSerializer

    def test_can_create_user(self, faker):
        password = faker.password(15)
        instance = self.execute_serializer(data=dict(password=password))
        assert isinstance(instance, User)
        assert instance.pk is not None
        assert instance.check_password(password)


@pytest.mark.django_db
class TestContactSerializer(SerializerMixin):
    serializer_class = ContactSerializer

    def test_to_representation(self, contact):
        serializer = self.serializer_class(instance=contact)
        data = serializer.data
        expected_keys = {
            'title', 'first_name', 'last_name', 'email', 'phone_mobile', 'gender', 'is_available',
            'birthday', 'picture', 'id', 'address', 'company_contact', 'availability',
            'phone_mobile_verified', 'email_verified', 'notes', '__str__', 'is_available',
            'notes', 'is_candidate_contact', 'is_company_contact', 'job_title', 'user', 'master_company',
            'candidate_contacts', 'created_at', 'updated_at', 'model_content_type'
        }
        assert expected_keys == set(data.keys())
        assert data['id'] == contact.id

    @patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
    def test_can_create_contact_with_address(self, mock_geo, contact_data, country, city):
        contact_data.pop('password')
        contact_data['address'] = {
            'country': country.id,
            'city': city.id,
            'street_address': 'test',
        }
        instance = self.execute_serializer(data=contact_data)
        assert isinstance(instance, Contact)
        assert instance.pk is not None
        assert instance.address is not None

    def test_cannot_create_contact_without_address(self, contact_data, country):
        contact_data.pop('password')
        with pytest.raises(serializers.ValidationError):
            self.execute_serializer(data=contact_data)

    @patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(1, 1))
    def test_can_create_contact_without_city(self, mock_geo, contact_data, country):
        contact_data.pop('password')
        contact_data['address'] = {
            'country': country.id,
            'street_address': 'test',
        }
        instance = self.execute_serializer(data=contact_data)

        assert instance.address.city is None

    def test_cannot_create_contact_without_street_address(self, contact_data, country, city):
        contact_data.pop('password')
        contact_data['address'] = {
            'country': country.id,
            'city': city.id,
        }
        with pytest.raises(serializers.ValidationError):
            self.execute_serializer(data=contact_data)

    @patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(None, None))
    def test_cannot_create_contact_with_wrong_address(self, mock_geo, contact_data, country, city, settings):
        settings.FETCH_ADDRESS_RAISE_EXCEPTIONS = True
        contact_data.pop('password')
        contact_data['address'] = {
            'country': country.id,
            'city': city.id,
            'street_address': 'test',
        }
        with pytest.raises(serializers.ValidationError):
            self.execute_serializer(data=contact_data)

    def test_cannot_create_contact_with_empty_email_and_phone(self, contact_data):
        contact_data.pop('password')
        contact_data['email'] = ''
        contact_data['phone_mobile'] = ''
        with pytest.raises(serializers.ValidationError):
            self.execute_serializer(data=contact_data)


@pytest.mark.django_db
class TestCompanySerializer(SerializerMixin):
    serializer_class = CompanySerializer

    def test_to_representation(self, company):
        serializer = self.serializer_class(instance=company)
        data = serializer.data
        expected_keys = {'name', 'business_id', 'registered_for_gst', 'tax_number', 'website',
                         'date_of_incorporation', 'description', 'notes', 'bank_account',
                         'credit_check', 'credit_check_date', 'terms_of_payment',
                         'payment_due_date', 'available', 'billing_email', 'credit_check_proof',
                         'type', 'purpose', 'id'}
        assert expected_keys == data.keys()
        assert data['id'] == company.id


@pytest.mark.django_db
class TestCompanyContactSerializer(SerializerMixin):
    serializer_class = CompanyContactSerializer

    @pytest.fixture
    def company_contact_data(self, faker, contact):
        company_contact_data = dict()
        company_contact_data['termination_date'] = faker.date_object()
        company_contact_data['job_title'] = faker.job()[:31]
        company_contact_data['rating_unreliable'] = faker.boolean()
        company_contact_data['receive_order_confirmation_sms'] = faker.boolean()
        company_contact_data['legacy_myob_card_number'] = faker.credit_card_number()[:15]
        company_contact_data['contact'] = str(contact.id)
        return company_contact_data

    @freeze_time("2012-01-14")
    def test_can_create_company_contact(self, contact, company_contact_data):
        mock = MagicMock()
        mock.user.contact = contact
        context = dict(request=mock, approved_by_staff=True, approved_by_primary_contact=False)
        serializer = self.serializer_class(data=company_contact_data, context=context)
        serializer.is_valid(raise_exception=True)
        instance = serializer.create(serializer.validated_data)
        assert isinstance(instance, CompanyContact)
        assert instance.pk is not None

    def test_contact_required(self, contact, company_contact_data):
        mock = MagicMock()
        mock.user.contact = contact
        context = dict(request=mock, approved_by_staff=True, approved_by_primary_contact=False)
        company_contact_data['contact'] = None
        serializer = self.serializer_class(data=company_contact_data, context=context)
        with pytest.raises(exceptions.ValidationError):
            serializer.is_valid(raise_exception=True)

    @freeze_time("2012-01-14")
    def test_process_approve(self, staff_user):
        mock = MagicMock()
        mock.user = staff_user
        # TODO: Fix timezone
        now = timezone.now()
        for left, right in itertools.product([True, False], repeat=2):
            instance = MagicMock()
            context = dict(
                request=mock,
                approved_by_staff=left,
                approved_by_primary_contact=right
            )
            serializer = self.serializer_class(context=context)
            serializer.process_approve(instance)
            assert left == (instance.approved_by_staff == staff_user.contact)
            assert left == (instance.staff_approved_at == now)
            assert right == (instance.approved_by_primary_contact == staff_user.contact)
            assert right == (instance.primary_contact_approved_at == now)


@pytest.mark.django_db
class TestFlatCompanyContactSerializer(SerializerMixin):
    serializer_class = CompanyContactRegisterSerializer

    @pytest.fixture
    def company_contact_data(self, country, company, city):
        company_contact_data = {
            'title': 'Mr.',
            'first_name': 'Test',
            'last_name': 'Tester',
            'email': 'tester@test.tt',
            'phone_mobile': '+12345678940',
            'password': 'secret',
            'address': {
                'street_address': 'test str',
                'country': country.id,
                'city': city.id
            },
            'company': company.id
        }
        return company_contact_data

    @patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
    def test_register(self, rf, staff_user, company_contact_data):
        req = rf.get('/')
        req.user = staff_user
        context = {'request': req}
        company_contact = self.execute_serializer(data=company_contact_data, context=context)
        assert isinstance(company_contact, CompanyContact)
        assert isinstance(company_contact.contact, Contact)
        assert isinstance(company_contact.contact.user, User)
        assert company_contact.relationships.exists()

    @patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
    def test_register_with_new_company(self, rf, staff_user, company_contact_data):
        req = rf.get('/')
        req.user = staff_user
        context = {'request': req}
        company_contact_data = copy.copy(company_contact_data)
        company_contact_data['company'] = {
            'name': 'test com',
        }
        company_contact = self.execute_serializer(data=company_contact_data, context=context)
        assert isinstance(company_contact, CompanyContact)
        assert isinstance(company_contact.contact, Contact)
        assert isinstance(company_contact.contact.user, User)
        assert company_contact.relationships.exists()

    def test_register_required_fileds(self, rf, staff_user, company_contact_data):
        req = rf.get('/')
        req.user = staff_user
        context = dict(request=req)
        company_contact_data = copy.copy(company_contact_data)
        company_contact_data.update(password='', email='', phone_mobile='')
        serializer = self.serializer_class(data=company_contact_data, context=context)

        with pytest.raises(exceptions.ValidationError):
            serializer.is_valid(raise_exception=True)


class TestApiFieldsMixin:

    def test_without_str_field(self):
        class Serializer(ApiFieldsMixin, serializers.ModelSerializer):
            class Meta:
                model = City
                fields = ('name', )

        serializer = Serializer(fields=['name'])

        assert set(serializer.Meta.fields) == {'name'}

    def test_with_str_field(self):
        class Serializer(ApiFieldsMixin, serializers.ModelSerializer):
            class Meta:
                model = City
                fields = ('name', '__str__')

        serializer = Serializer(fields=['name'])

        assert set(serializer.Meta.fields) == {'name', '__str__'}


class CompanyAddressTestSerializer(CompanyAddressSerializer):
    class Meta:
        model = CompanyAddress
        fields = '__all__'


@pytest.mark.django_db
class TestCompanyAddressSerializer:

    @patch.object(cache, 'set')
    @patch.object(cache, 'get', return_value=None)
    @patch('r3sourcer.apps.core.api.serializers.get_current_site')
    def test_get_company_rel(self, mock_current_site, mock_cache_get,
                             mock_cache_set, site, site_company,
                             company_address_regular, company_rel):
        mock_current_site.return_value = site

        serializer = CompanyAddressTestSerializer()
        rel = serializer.get_company_rel(company_address_regular)

        assert rel.id == company_rel.id

    @patch.object(cache, 'set')
    @patch.object(cache, 'get', return_value=None)
    @patch('r3sourcer.apps.core.api.serializers.get_current_site')
    def test_get_company_rel_no_site_company(
            self, mock_current_site, mock_cache_get, mock_cache_set, site,
            company_address_regular, company_rel):
        mock_current_site.return_value = site

        serializer = CompanyAddressTestSerializer()
        rel = serializer.get_company_rel(company_address_regular)

        assert rel is None

    @patch.object(cache, 'set')
    @patch.object(cache, 'get', return_value=None)
    @patch('r3sourcer.apps.core.api.serializers.get_current_site')
    def test_get_company_rel_no_master_site_company(
            self, mock_current_site, mock_cache_get, mock_cache_set,
            site_regular_company, site, company_address_regular, company_rel):
        mock_current_site.return_value = site

        serializer = CompanyAddressTestSerializer()
        rel = serializer.get_company_rel(company_address_regular)

        assert rel is None

    @patch.object(cache, 'set')
    @patch.object(cache, 'get', return_value=None)
    @patch('r3sourcer.apps.core.api.serializers.get_current_site')
    def test_get_company_rel_regular_site_company(
            self, mock_current_site, mock_cache_get, mock_cache_set,
            site_company, site, company_address_regular, company_rel):
        mock_current_site.return_value = site

        serializer = CompanyAddressTestSerializer()
        rel = serializer.get_company_rel(company_address_regular)

        assert rel.id == company_rel.id

    @patch.object(cache, 'set')
    @patch.object(cache, 'get')
    def test_get_company_rel_cached(
            self, mock_cache_get, mock_cache_set, company_address,
            company_rel):
        mock_cache_get.return_value = company_rel

        serializer = CompanyAddressTestSerializer()
        rel = serializer.get_company_rel(company_address)

        assert rel.id == company_rel.id

    def test_get_portfolio_manager_obj_none(self):
        serializer = CompanyAddressTestSerializer()

        portfolio_manager = serializer.get_portfolio_manager(None)

        assert portfolio_manager is None

    def test_get_portfolio_manager_obj_company_rel(self, company_address,
                                                   company_rel):
        serializer = CompanyAddressTestSerializer()

        with patch.object(serializer, 'get_company_rel') as mock_comp_rel:
            mock_comp_rel.return_value = company_rel

            portfolio_manager = serializer.get_portfolio_manager(company_address)

            assert portfolio_manager['id'] == str(company_rel.manager.id)

    def test_get_portfolio_manager_obj_company_rel_none(self, company_address,
                                                        company_rel):
        serializer = CompanyAddressTestSerializer()

        with patch.object(serializer, 'get_company_rel') as mock_comp_rel:
            mock_comp_rel.return_value = None

            portfolio_manager = serializer.get_portfolio_manager(company_address)

            assert portfolio_manager is None

    def test_get_active_states_obj_none(self):
        serializer = CompanyAddressTestSerializer()

        state = serializer.get_active_states(None)

        assert state is None

    def test_get_active_states_obj_company_rel(self, company_address, company_rel):
        serializer = CompanyAddressTestSerializer()

        with patch.object(serializer, 'get_company_rel') as mock_comp_rel:
            mock_comp_rel.return_value = company_rel

            with patch.object(company_rel, 'get_active_states') as mock_states:
                state = MockModel(number=10, name_after_activation='new')
                mock_states.return_value = [MockModel(state=state, object_id=company_rel.id)]

                state = serializer.get_active_states(company_address)

                assert state == [{'id': None, 'number': 10, '__str__': 'new'}]

    def test_get_active_states_obj_company_rel_none(self, company_address, company_rel):
        serializer = CompanyAddressTestSerializer()

        with patch.object(serializer, 'get_company_rel') as mock_comp_rel:
            mock_comp_rel.return_value = None

            state = serializer.get_active_states(company_address)

            assert state is None

    def test_get_invoices_count(self, company_address_regular, invoice):
        serializer = CompanyAddressTestSerializer()

        invoices_count = serializer.get_invoices_count(company_address_regular)

        assert invoices_count == 1

    def test_get_invoices_count_none(self):
        serializer = CompanyAddressTestSerializer()

        invoices_count = serializer.get_invoices_count(None)

        assert invoices_count == 0

    def test_get_orders_count(self, company_address, order):
        serializer = CompanyAddressTestSerializer()

        orders_count = serializer.get_orders_count(company_address)

        assert orders_count == 1

    def test_get_orders_count_none(self):
        serializer = CompanyAddressTestSerializer()

        orders_count = serializer.get_orders_count(None)

        assert orders_count == 0


class TestWorkflowNodeSerializer:

    @pytest.fixture
    def data(self):
        return {
            'number': 'test',
            'workflow': 'test',
            'company': 'test',
            'active': 'test',
            'rules': 'test'
        }

    @patch.object(WorkflowNode, 'validate_node', return_value=True)
    def test_validate(self, mock_validate, data):
        serializer = WorkflowNodeSerializer()

        assert serializer.validate(data) == data

    @patch.object(WorkflowNode, 'validate_node')
    def test_validate_exception(self, mock_validate, data):
        mock_validate.side_effect = ValidationError('error')

        serializer = WorkflowNodeSerializer()

        with pytest.raises(ValidationError):
            assert serializer.validate(data)


class TestWorkflowObjectSerializer:

    @pytest.fixture
    def data(self):
        return {
            'state': 'test',
            'object_id': 'test',
        }

    @patch.object(WorkflowObject, 'validate_tests', return_value=True)
    @patch.object(WorkflowObject, 'validate_object', return_value=True)
    def test_validate(self, mock_validate, mock_validate_tests, data):
        serializer = WorkflowObjectSerializer()

        assert serializer.validate(data) == data

    @patch.object(WorkflowObject, 'validate_object')
    def test_validate_exception(self, mock_validate, data):
        mock_validate.side_effect = ValidationError('error')

        serializer = WorkflowObjectSerializer()

        with pytest.raises(ValidationError):
            assert serializer.validate(data)


class TestWorkflowTimelineSerializer:

    @pytest.fixture
    def target(self):
        return MagicMock()

    @pytest.fixture
    def serializer(self, target):
        return WorkflowTimelineSerializer(target=target)

    def test_init(self, target):
        serializer = WorkflowTimelineSerializer(target=target)

        assert serializer.target is target

    def test_get_requirements(self, target, serializer):
        target.is_allowed.return_value = True

        assert serializer.get_requirements(MagicMock()) is None

    def test_get_requirements_no_object(self, target, serializer):
        assert serializer.get_requirements(None) is None

    def test_get_requirements_not_allowed(self, target, serializer):
        target.is_allowed.return_value = False
        target.get_required_messages.return_value = 'test'

        assert serializer.get_requirements(MagicMock()) is 'test'

    def test_get_state_no_obj(self, target, serializer):
        assert serializer.get_state(None) == NOT_ALLOWED

    @patch.object(WorkflowObject, 'validate_tests', return_value=True)
    @patch.object(WorkflowObject, 'objects', new_callable=PropertyMock)
    def test_get_state_allowed(self, mock_objects, mock_validate_tests, target, serializer):
        mock_objects.return_value = MockSet()
        target.is_allowed.return_value = True

        assert serializer.get_state(MagicMock()) == ALLOWED

    @patch.object(WorkflowObject, 'validate_tests', return_value=True)
    @patch.object(WorkflowObject, 'objects', new_callable=PropertyMock)
    def test_get_state_not_allowed(self, mock_objects, mock_validate_tests, target, serializer):
        mock_objects.return_value = MockSet()
        target.is_allowed.return_value = False
        target._check_condition.return_value = False

        assert serializer.get_state(MagicMock()) == NOT_ALLOWED

    @patch.object(WorkflowObject, 'validate_tests', return_value=True)
    @patch.object(WorkflowObject, 'objects', new_callable=PropertyMock)
    def test_get_state_need_requirements(self, mock_objects, mock_validate_tests, target, serializer):
        mock_objects.return_value = MockSet()
        target.is_allowed.return_value = False
        target._check_condition.return_value = True

        assert serializer.get_state(MagicMock()) == NEED_REQUIREMENTS

    @patch.object(WorkflowObject, 'objects', new_callable=PropertyMock)
    def test_get_wf_object_id_no_wf_objects(self, mock_objects, target,
                                            serializer):
        mock_objects.return_value = MockSet()

        assert serializer.get_wf_object_id(MagicMock()) is None

    @patch.object(WorkflowObject, 'objects', new_callable=PropertyMock)
    def test_get_wf_object_id_obj_is_none(self, mock_objects, target,
                                          serializer):
        mock_objects.return_value = MockSet()

        assert serializer.get_wf_object_id(None) is None

    @patch.object(WorkflowObject, 'objects', new_callable=PropertyMock)
    def test_get_wf_object_id(self, mock_objects, target, serializer):
        target.id = 2
        state = MockModel(id=1)
        mock_objects.return_value = MockSet(
            MockModel(id=1, state=state, object_id=2)
        )

        assert serializer.get_wf_object_id(state) == 1


@pytest.mark.django_db
class TestNavigationSerializer:

    @pytest.fixture
    def navigation_root(self):
        return ExtranetNavigation.objects.create(
            name='root', url='/url', endpoint='endpoint'
        )

    @pytest.fixture
    def navigation_child(self, navigation_root: ExtranetNavigation):
        return ExtranetNavigation.objects.create(
            parent=navigation_root,
            name='c_root',
            url='/c_url',
            endpoint='c_endpoint'
        )

    def test_get_childrens(self, navigation_root):
        serializer = NavigationSerializer()

        childs = serializer.get_childrens(navigation_root)

        assert len(childs) == 0

    def test_get_childrens_exists(self, navigation_root, navigation_child):
        serializer = NavigationSerializer()

        childs = serializer.get_childrens(navigation_root)

        assert len(childs) == 1

    def test_get_childrens_none(self):
        serializer = NavigationSerializer()

        childs = serializer.get_childrens(None)

        assert len(childs) == 0


@pytest.mark.django_db
class TestTrialSerializer:

    @pytest.fixture
    def user_data(self, contact_phone_sec):
        return {
            'first_name': 'testuser42',
            'last_name': 'tester42',
            'email': 'test4242@test.tt',
            'phone_mobile': contact_phone_sec,
            'company_name': 'Test Company',
            'website': 'test.r3sourcer.com',
        }

    def test_validate_success(self, user_data):
        serializer = TrialSerializer(data=user_data)

        assert serializer.is_valid()

    def test_validate_wrong_email(self, user_data):
        user_data['email'] = 'test42'
        serializer = TrialSerializer(data=user_data)

        assert not serializer.is_valid()
        assert 'email' in serializer.errors

    def test_validate_invalid_email(self, user_data):
        user_data['email'] = 'test42@ww'
        serializer = TrialSerializer(data=user_data)

        assert not serializer.is_valid()
        assert 'email' in serializer.errors

    def test_validate_wrong_phone_number(self, user_data):
        user_data['phone_mobile'] = '+123'
        serializer = TrialSerializer(data=user_data)

        assert not serializer.is_valid()
        assert 'phone_mobile' in serializer.errors

    def test_validate_user_with_email_exist(self, user_data, contact):
        user_data['email'] = contact.email
        serializer = TrialSerializer(data=user_data)

        assert not serializer.is_valid()
        assert 'email' in serializer.errors

    def test_validate_user_with_phone_number_exist(self, user_data, contact):
        user_data['phone_mobile'] = contact.phone_mobile
        serializer = TrialSerializer(data=user_data)

        assert not serializer.is_valid()
        assert 'phone_mobile' in serializer.errors

    def test_validate_company_with_name_exist(self, user_data, company):
        user_data['company_name'] = company.name
        serializer = TrialSerializer(data=user_data)

        assert not serializer.is_valid()
        assert 'company_name' in serializer.errors


@pytest.mark.django_db
class TestCompanyContactRenderSerializer:

    @pytest.fixture
    def company_contact_rel_data(self, staff_user, company):
        return {
            'contact': staff_user.contact,
            'company': str(company.id),
        }

    @pytest.fixture
    def company_contact_rel_update_data(self, staff_user, company):
        return {
            'contact': staff_user.contact,
            'company': str(company.id),
            'termination_date': date(2018, 5, 2),
            'active': True,
        }

    def test_get_company(self, staff_company_contact, staff_relationship, company):
        serializer = CompanyContactRenderSerializer()

        assert serializer.get_company(staff_company_contact)['id'] == str(company.id)

    def test_get_company_none(self, staff_company_contact):
        serializer = CompanyContactRenderSerializer()

        assert serializer.get_company(staff_company_contact) is None

    def test_get_primary_contact(self, staff_company_contact, staff_relationship, company):
        serializer = CompanyContactRenderSerializer()

        assert serializer.get_primary_contact(staff_company_contact)['id'] == str(company.primary_contact.id)

    def test_get_primary_contact_none(self, staff_company_contact):
        serializer = CompanyContactRenderSerializer()

        assert serializer.get_primary_contact(staff_company_contact) is None

    def test_create(self, company_contact_rel_data):
        serializer = CompanyContactRenderSerializer(data=company_contact_rel_data)
        instance = serializer.create({'contact': company_contact_rel_data['contact']})

        assert instance is not None
        assert instance.relationships.exists()

    def test_create_no_contact(self, company_contact_rel_data):
        company_contact_rel_data['contact'] = None
        serializer = CompanyContactRenderSerializer(data=company_contact_rel_data)

        with pytest.raises(serializers.ValidationError) as e:
            serializer.create({'contact': company_contact_rel_data['contact']})

            assert 'contact' in e.detail

    def test_create_no_company(self, company_contact_rel_data, company):
        company_contact_rel_data['company'] = None
        serializer = CompanyContactRenderSerializer(data=company_contact_rel_data)

        with pytest.raises(serializers.ValidationError) as e:
            serializer.create({'contact': company_contact_rel_data['contact']})

            assert 'company' in e.detail

    def test_update(self, company_contact_rel_update_data, staff_company_contact, staff_relationship, company):
        serializer = CompanyContactRenderSerializer(staff_relationship, data=company_contact_rel_update_data)
        data = {k: v for k, v in company_contact_rel_update_data.items() if k != 'company'}
        instance = serializer.update(staff_company_contact, data)

        assert instance is not None
        assert instance.relationships.exists()

    def test_update_no_contact(self, company_contact_rel_update_data, staff_company_contact, staff_relationship):
        company_contact_rel_update_data['contact'] = None
        serializer = CompanyContactRenderSerializer(staff_relationship, data=company_contact_rel_update_data)

        with pytest.raises(serializers.ValidationError) as e:
            data = {k: v for k, v in company_contact_rel_update_data.items() if k != 'company'}
            serializer.update(staff_company_contact, data)

            assert 'contact' in e.detail

    def test_update_no_company(self, staff_company_contact, company_contact_rel_update_data, staff_relationship):
        company_contact_rel_update_data['company'] = None
        serializer = CompanyContactRenderSerializer(staff_relationship, data=company_contact_rel_update_data)

        with pytest.raises(serializers.ValidationError) as e:
            data = {k: v for k, v in company_contact_rel_update_data.items() if k != 'company'}
            serializer.update(staff_company_contact, data)

            assert 'company' in e.detail

    @freeze_time('2018-05-02')
    def test_update_termination_date(self, staff_company_contact, company_contact_rel_update_data, staff_relationship):
        serializer = CompanyContactRenderSerializer(staff_relationship, data=company_contact_rel_update_data)
        company_contact_rel_update_data['active'] = False

        data = {k: v for k, v in company_contact_rel_update_data.items() if k != 'company'}
        instance = serializer.update(staff_company_contact, data)
        rel = instance.relationships.first()

        assert rel.termination_date == date(2018, 5, 2)
        assert not rel.active

    @freeze_time('2018-05-02')
    def test_update_reactivate(self, staff_company_contact, company_contact_rel_update_data, staff_relationship):
        serializer = CompanyContactRenderSerializer(staff_relationship, data=company_contact_rel_update_data)
        company_contact_rel_update_data['termination_date'] = date(2018, 5, 2)

        data = {k: v for k, v in company_contact_rel_update_data.items() if k != 'company'}
        instance = serializer.update(staff_company_contact, data)
        rel = instance.relationships.first()

        assert rel.termination_date is None
        assert rel.active

    @freeze_time('2018-05-02')
    @patch('r3sourcer.apps.core.api.serializers.core_tasks')
    def test_update_future_termination(
        self, mock_tasks, staff_company_contact, company_contact_rel_update_data, staff_relationship
    ):
        serializer = CompanyContactRenderSerializer(staff_relationship, data=company_contact_rel_update_data)
        company_contact_rel_update_data['termination_date'] = date(2018, 5, 5)

        data = {k: v for k, v in company_contact_rel_update_data.items() if k != 'company'}
        instance = serializer.update(staff_company_contact, data)
        rel = instance.relationships.first()

        assert rel.termination_date == date(2018, 5, 5)
        assert rel.active
        assert mock_tasks.terminate_company_contact.apply_async.called
