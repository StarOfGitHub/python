from datetime import datetime, time
from itertools import chain
from collections import OrderedDict

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.sites.models import Site
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.utils import six
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers, exceptions, validators
from rest_framework.fields import empty

from django.db.models.fields.related import (
    RelatedField, ManyToOneRel, ManyToManyField, ManyToManyRel, OneToOneRel
)
from django.contrib.contenttypes.fields import GenericRelation

from r3sourcer.apps.acceptance_tests.models import AcceptanceTestWorkflowNode
from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core import models as core_models, tasks as core_tasks
from r3sourcer.apps.core.utils.utils import normalize_phone_number, validate_phone_number
from r3sourcer.apps.core.utils.companies import get_site_master_company
from r3sourcer.apps.core.workflow import (NEED_REQUIREMENTS, ALLOWED, ACTIVE, NOT_ALLOWED)
from r3sourcer.apps.core.api import mixins as core_mixins, fields as core_field
from r3sourcer.apps.core.models import Workflow
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.helpers.datetimes import utc_now, tz2utc

rest_settings = settings.REST_FRAMEWORK

RELATED_NONE, RELATED_DIRECT, RELATED_FULL = 'minimal', 'direct', 'full'


class ApiFullRelatedFieldsMixin():
    """
    Use Meta of the serializer class to render related objects

    Settings:
    ``settings.REST_FRAMEWORK['RELATED_FULL']`` (default: 'minimal') - render related object
    values: 'full', 'direct', 'minimal'
    """

    _read_only_fields = ('__str__', )

    def __init__(self, *args, **kwargs):
        parent_field_name = kwargs.pop('parent_name', None)
        context = kwargs.get('context', {})
        related_obj_setting = context.get(
            'related_setting') or kwargs.get('related_setting')

        super(ApiFullRelatedFieldsMixin, self).__init__(*args, **kwargs)

        data = kwargs.get('data', empty)
        request = context.get('request')

        if not hasattr(self, 'Meta'):
            return

        related_obj_setting = related_obj_setting or \
            getattr(self.Meta, 'related', rest_settings.get(
                'RELATED', RELATED_NONE))
        related_obj_setting = related_obj_setting or RELATED_NONE
        internal_fields_dict = getattr(self.Meta, 'related_fields', {})
        related_setting = related_obj_setting if related_obj_setting != RELATED_DIRECT else RELATED_NONE
        related_extra_kwargs = getattr(self.Meta, 'extra_kwargs', {})

        for field_name, field in self.fields.items():
            if field_name == 'id':
                kwargs = field._kwargs
                kwargs['required'] = False
                kwargs['read_only'] = False
                self.fields[field_name] = field.__class__(
                    *field._args, **kwargs
                )
                continue

            if field_name in self._read_only_fields:
                field_kwargs = {}
                if field_name == '__str__':
                    label = parent_field_name.title().replace('_', ' ') \
                        if parent_field_name \
                        else self.Meta.model._meta.verbose_name.title()
                    field_kwargs['label'] = label
                self.fields[field_name] = serializers.ReadOnlyField(
                    **field_kwargs
                )
                continue

            is_field_in_data = data is not empty and field_name in data
            is_pk_data = is_field_in_data and not isinstance(data[field_name], (list, dict))
            is_id_partial = kwargs.get('partial', False) or bool(
                is_field_in_data and isinstance(data[field_name], dict) and data[field_name].get('id')
            )

            if is_id_partial and is_field_in_data and isinstance(data[field_name], list):
                internal_fields_dict[field_name] = [f for f in data.get(field_name, [])]

            if not is_pk_data and isinstance(data, list) and len(data) > 0:
                data_elem = data[0]
                if isinstance(data_elem, dict):
                    is_pk_data = data_elem.get(field_name) and \
                        not isinstance(data_elem[field_name], (list, dict))
                else:
                    is_pk_data = True

            if isinstance(field, serializers.ChoiceField):
                self.fields[field_name] = core_field.ApiChoicesField(
                    *field._args, **field._kwargs
                )
                continue
            elif isinstance(field, serializers.ImageField):
                self.fields[field_name] = core_field.ApiContactPictureField(
                    *field._args, **field._kwargs
                )
                continue
            elif isinstance(field, serializers.FileField):
                self.fields[field_name] = core_field.ApiBase64FileField(
                    *field._args, **field._kwargs
                )
                continue
            elif isinstance(field, serializers.ModelSerializer):
                if is_pk_data:
                    self.fields[field_name] = self._get_id_related_field(
                        field, field.Meta.model.objects
                    )
                elif isinstance(field, ApiBaseModelSerializer):
                    continue
                else:
                    context['related_setting'] = related_setting
                    kwargs = dict(
                        required=field.required,
                        allow_null=field.allow_null,
                        read_only=field.read_only,
                        context=context,
                        many=getattr(field, 'many', False),
                        data=data.get(field_name, empty) if data is not empty else empty,
                        parent_name=parent_field_name or field_name,
                        partial=is_id_partial,
                    )

                    internal = self._get_internal_serializer(
                        field_name, field, field.Meta.model, related_setting, internal_fields_dict,
                        related_extra_kwargs
                    )
                    self.fields[field_name] = internal(**kwargs)
                continue

            try:
                related_field = self.Meta.model._meta.get_field(field_name)
            except FieldDoesNotExist:
                continue

            is_many_to_one_relation = isinstance(related_field, ManyToOneRel)
            is_many_to_many_relation = isinstance(related_field, (ManyToManyRel, ManyToManyField))
            is_one_to_one_relation = isinstance(related_field, OneToOneRel)
            if not isinstance(related_field, RelatedField) and not is_many_to_one_relation:
                if getattr(related_field, 'blank', False) and not getattr(related_field, 'null', False):
                    self.fields[field_name] = core_field.EmptyNullField.from_field(
                        field)

                continue

            is_generic_relation = isinstance(related_field, GenericRelation)
            is_many_relation = is_generic_relation or (is_many_to_one_relation and not is_one_to_one_relation)

            if is_many_to_one_relation:
                rel_model = related_field.related_model
            else:
                rel_model = related_field.remote_field.model

            if data is not empty or (request is not None and request.method in ('POST', 'PUT', 'PATCH')):
                if is_pk_data or (data is empty and related_obj_setting == RELATED_NONE and not is_many_relation and
                                  not is_many_to_many_relation):

                    kwargs = {'field': field}
                    if is_pk_data:
                        kwargs.update(read_only=False, queryset=rel_model.objects)

                    self.fields[field_name] = self._get_id_related_field(
                        **kwargs
                    )
                    continue
            if data is empty and related_obj_setting == RELATED_NONE and not is_many_relation and \
                    field_name not in internal_fields_dict:
                self.fields[field_name] = core_field.ApiBaseRelatedField(
                    read_only=True,
                    many=isinstance(
                        related_field, (ManyToManyRel, ManyToManyField)),
                )
                continue

            if self.Meta.model is rel_model and (
                data is empty or data.get(field_name) is None
            ):
                continue  # pragma: no cover

            if not isinstance(data, list) and data is not empty and not field.read_only:
                related_data = data.get(field_name, empty)
            else:
                related_data = empty

            if isinstance(related_data, list):
                related_data = [
                    {'id': related_item} if isinstance(related_item, str) else related_item
                    for related_item in related_data
                ]

            is_related_object_data = isinstance(related_data, dict) and len(related_data.keys()) > 1
            if related_data is not empty and is_related_object_data and 'id' in related_data:
                try:
                    rel_instance = rel_model.objects.get(id=related_data['id'])
                except rel_model.DoesNotExist:
                    rel_instance = None
            else:
                rel_instance = None

            kwargs = dict(
                required=field.required and not is_many_relation,
                allow_null=field.allow_null,
                read_only=field.read_only,
                context=context,
                many=is_many_relation,
                data=related_data,
                parent_name=parent_field_name or field_name,
                partial=is_id_partial,
                instance=rel_instance,
            )

            internal = self._get_internal_serializer(
                field_name, field, rel_model, related_setting, internal_fields_dict, related_extra_kwargs
            )

            kwargs['context']['related_setting'] = internal.Meta.related
            self.fields[field_name] = internal(**kwargs)

    def _get_internal_serializer(
        self, field_name, field, model, related_setting, internal_fields_dict, related_extra_kwargs=None
    ):
        related_fields = internal_fields_dict.get(field_name, [])
        if not isinstance(related_fields, (list, tuple)) or not related_fields:
            related_fields = '__all__'

        meta_properties = dict(
            model=model,
            fields=related_fields,
            related=related_setting
        )

        internal_meta = type('Meta', (object,), meta_properties)
        internal = type(
            '{}InternalSerializer'.format(model.__name__),
            (ApiBaseModelSerializer,),
            dict(Meta=internal_meta)
        )

        return internal

    def _get_id_related_field(self, field, queryset=None, read_only=None):
        if hasattr(field, 'child_relation'):
            child_queryset = field.child_relation.get_queryset()
            queryset = queryset if child_queryset is None else child_queryset

        read_only = read_only if read_only is not None else field.read_only

        return serializers.SlugRelatedField(
            slug_field='id',
            queryset=field._kwargs.get('queryset') or queryset,
            required=field.required,
            allow_null=field.allow_null,
            read_only=read_only,
        )

    def _process_related_extra_kwargs(self, related_extra_kwargs, field_name):
        if not related_extra_kwargs:
            return None

        related_kwargs = {
            field[field.index('.') + 1]: kwargs for field, kwargs in related_extra_kwargs.items()
            if '.' in field and field_name in field
        }

        return related_kwargs

    def create(self, validated_data):
        for field_name, field in self.fields.items():
            if isinstance(field, serializers.ModelSerializer):
                model = field.Meta.model
                instance = validated_data.pop(field_name, None)
                if instance is None:
                    continue

                if not isinstance(instance, model):
                    instance = model.objects.create(**instance)
                validated_data[field_name] = instance

        obj = self.Meta.model.objects.create(**validated_data)
        return obj

    def update(self, obj, validated_data):
        for field_name, field in self.fields.items():
            if isinstance(field, serializers.ModelSerializer):
                model = field.Meta.model
                instance = validated_data.pop(field_name, None)
                if instance is None:
                    continue

                if not isinstance(instance, model):  # pragma: no cover
                    instance_id = instance.get('id')
                    if instance_id:
                        instance, _ = model.objects.update_or_create(id=instance_id, defaults=instance)
                    else:
                        instance = model.objects.create(**instance)

                if not isinstance(getattr(obj.__class__, field_name, None), property):
                    setattr(obj, field_name, instance)

        return super(ApiFullRelatedFieldsMixin, self).update(obj, validated_data)


class ApiRelatedFieldManyMixin:

    # Format: {'many_related_field': 'related_field_name'}
    many_related_fields = None

    def create(self, validated_data):
        if self.many_related_fields:
            related_data = {
                field: validated_data.pop(field)
                for field in self.many_related_fields.keys()
                if validated_data.get(field)
            }
        else:
            related_data = {}

        instance = super().create(validated_data)
        related_data['id'] = instance.id

        self.create_many(related_data)
        return instance

    def create_many(self, validated_data):
        for field_name, related_name in self.many_related_fields.items():
            field = self.fields.get(field_name)

            if isinstance(field, serializers.ListSerializer) and not field.read_only:
                model = field.child.Meta.model
                instances = validated_data.pop(field_name, [])

                for instance in instances:
                    if instance is not None and not isinstance(instance, model):
                        instance[related_name + '_id'] = validated_data['id']
                        model.objects.create(**instance)

    def update(self, instance, validated_data):
        if self.many_related_fields:
            related_data = {
                field: validated_data.pop(field)
                for field in self.many_related_fields.keys()
                if field in validated_data
            }
        else:
            related_data = {}

        instance = super().update(instance, validated_data)
        related_data['id'] = instance.id

        self.update_many(instance, related_data)
        return instance

    def update_many(self, instance, validated_data):
        """
        Update related objects
        """
        for field_name, related_name in self.many_related_fields.items():
            field = self.fields.get(field_name)

            if isinstance(field, serializers.ListSerializer) and not field.read_only:
                instances = validated_data.get(field_name, [])

                objects = getattr(instance, field_name)
                for item in instances:
                    item[related_name + '_id'] = instance.id
                    if item.get('id'):
                        obj = objects.filter(id=item['id'])
                        obj.update(**item)
                    else:
                        model = field.child.Meta.model
                        model.objects.create(**item)


class ApiMethodFieldsMixin():
    method_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        method_fields = self.get_method_fields()
        for method_field in method_fields:
            field_kwargs = {}
            if isinstance(method_field, (list, tuple)) and len(method_field) == 2:
                field_kwargs['method_name'] = method_field[1]
                method_field = method_field[0]
            elif not isinstance(method_field, six.string_types):
                message = (
                    'Field data {!r} not supported. '
                    'Method fields can be declared as list or tuple of field name '
                    'strings or 2-item tuples in form (field_name, method_name)'
                )
                raise Exception(message.format(method_field))
            self.fields[method_field] = serializers.SerializerMethodField(**field_kwargs)

    def get_method_fields(self):
        return self.method_fields or []


class ApiFieldsMixin():

    required_fields = {'request', 'id'}

    def __init__(self, *args, **kwargs):
        fields = kwargs.pop('fields', [])

        if fields:
            self._declared_fields = OrderedDict([
                (name, field)
                for name, field in self._declared_fields.items()
                if name in fields
            ])

            allowed = set(fields)
            required = set(self.get_required_fields()) or set()
            possible_fields = allowed | required | set(self._declared_fields)

            if hasattr(self, 'Meta'):
                meta_parents = (self.Meta, )

                serializer_fields = set(self.get_fields().keys()) \
                    if self.Meta.fields == '__all__' else set(self.Meta.fields)
                fields_set = serializer_fields & possible_fields
                if '__str__' in serializer_fields:
                    fields_set.add('__str__')

                meta_attrs = {
                    'fields': list(fields_set)
                }
                Meta = type('Meta', meta_parents, meta_attrs)

                self.Meta = Meta

        super(ApiFieldsMixin, self).__init__(*args, **kwargs)

        if fields:
            existing = set(self.fields.keys())
            for field_name in existing - possible_fields:
                self.fields.pop(field_name)

    def get_required_fields(self):
        return self.required_fields


class ApiContactImageFieldsMixin():
    image_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        image_fields = self.image_fields or []
        for image_field in image_fields:
            self.fields[image_field] = core_field.ApiContactPictureField(required=False)


class MetaFields(serializers.SerializerMetaclass):

    def __new__(cls, name, bases, namespace, **kwargs):
        res_cls = super().__new__(cls, name, bases, namespace)

        if hasattr(res_cls, 'Meta'):
            super_meta = cls._get_super_meta(bases)
            meta_parents = (res_cls.Meta, )
            if super_meta:
                meta_parents += (super_meta, )

            Meta = type('Meta', meta_parents, {})

            fields = getattr(Meta, 'fields', [])
            if fields == '__all__' or '__all__' in fields:
                model = getattr(Meta, 'model')
                all_fields = model._meta.get_fields() if model is not None else []
                all_fields = [
                    field.name for field in all_fields
                    if (
                        ((not hasattr(field, 'field') and getattr(field, 'related_name', None) is None) or
                         isinstance(field, models.OneToOneRel)) and
                        not isinstance(field, GenericForeignKey)
                    )
                ]
                fields = chain(
                    all_fields, [field for field in fields if isinstance(field, dict)])

            if fields:
                serializer_fields = []
                related_fields = {}
                for field in fields:
                    if isinstance(field, dict):
                        related_fields.update(field)
                        serializer_fields.extend(field.keys())
                        continue

                    serializer_fields.append(field)

                if '__str__' not in serializer_fields:
                    serializer_fields.append('__str__')

                Meta.fields = serializer_fields
                if related_fields:
                    Meta.related_fields = related_fields

                res_cls.Meta = Meta

        return res_cls

    @classmethod
    def _get_super_meta(cls, bases):
        for base_cls in bases:
            if hasattr(base_cls, 'Meta'):
                return base_cls.Meta


@six.add_metaclass(MetaFields)
class ApiBaseModelSerializer(ApiFieldsMixin,
                             ApiMethodFieldsMixin,
                             ApiFullRelatedFieldsMixin,
                             serializers.ModelSerializer):
    pass


class AddressSerializer(ApiBaseModelSerializer):

    class Meta:
        model = core_models.Address
        fields = '__all__'

    def validate_state(self, value):
        if not value:
            return
        country = self.initial_data.get('country')
        if value and str(value.country.id) != country:
            raise serializers.ValidationError(
                "Country has no '%s' state" % value.name)
        return value

    def validate_city(self, value):
        if not value:
            return

        state = self.initial_data.get('state')
        if state and str(value.region.id) != state:
            raise serializers.ValidationError(
                "State has no '%s' city" % value.name)

        country = self.initial_data.get('country')
        if value and str(value.country.id) != country:
            raise serializers.ValidationError(
                "Country has no '%s' city" % str(value))
        return value


class UserSerializer(ApiBaseModelSerializer):

    def create(self, validated_data):
        user = self.Meta.model()
        self._set_password(user, validated_data.pop('password'))
        return user

    def update(self, instance, validated_data):
        self._set_password(instance, validated_data.pop('password'))
        return instance

    def _set_password(self, instance, password):
        instance.set_password(password)
        instance.save()

    class Meta:
        model = get_user_model()
        fields = 'password',


class CompanyContactSerializer(ApiBaseModelSerializer):

    def create(self, validated_data):
        contact = validated_data.get('contact', None)
        if not isinstance(contact, core_models.Contact):
            raise exceptions.ValidationError("Contact is required")

        instance = super(CompanyContactSerializer, self).create(validated_data)
        return instance

    def process_approve(self, instance):
        request = self.context['request']
        approved_by_staff = self.context['approved_by_staff']
        approved_by_primary_contact = self.context['approved_by_primary_contact']

        if approved_by_staff:
            instance.approved_by_staff = request.user.contact
            instance.staff_approved_at = utc_now()

        if approved_by_primary_contact:
            instance.approved_by_primary_contact = request.user.contact
            instance.primary_contact_approved_at = utc_now()

    class Meta:
        model = core_models.CompanyContact
        fields = (
            'id', 'job_title', 'rating_unreliable', 'contact', 'legacy_myob_card_number',
            'receive_job_confirmation_sms'
        )
        related = RELATED_DIRECT


class ContactUnavailabilitySerializer(ApiBaseModelSerializer):
    class Meta:
        model = core_models.ContactUnavailability
        fields = ('id', 'contact', 'unavailable_from', 'unavailable_until',
                  'notes',)
        related = RELATED_DIRECT


class NoteSerializer(
    core_mixins.CreatedUpdatedByMixin,
    ApiBaseModelSerializer
):

    class Meta:
        model = core_models.Note
        read_only = ('contact',)
        fields = ('__all__',
                  # {
                  #     'contact': ('id', 'first_name', 'last_name', 'phone_mobile', 'email')
                  # }
                  {'files': ('id', 'file')}
                  )
        related = RELATED_NONE


class NoteFileSerializer(ApiBaseModelSerializer):

    class Meta:
        model = core_models.NoteFile
        fields = '__all__'


class ContactSerializer(ApiContactImageFieldsMixin,
                        core_mixins.ApiContentTypeFieldMixin,
                        ApiBaseModelSerializer):
    image_fields = ('picture', )
    many_related_fields = {
        'company_contact': 'contact',
    }

    method_fields = ('job_title', 'availability', 'is_candidate_contact', 'is_company_contact',
                     'master_company', 'address')

    def get_job_title(self, obj):
        return obj.get_job_title() if obj and obj.is_company_contact() else None

    def get_availability(self, obj):
        return obj.get_availability() if obj else None

    def get_is_candidate_contact(self, obj):
        return obj.is_candidate_contact() if obj else None

    def get_is_company_contact(self, obj):
        return obj.is_company_contact() if obj else None

    def get_master_company(self, obj):
        master_company = obj.get_closest_company()
        return master_company and core_field.ApiBaseRelatedField.to_read_only_data(master_company)

    def get_address(self, obj):
        return obj.get_active_address()

    def to_representation(self, instance):
        data = super(ContactSerializer, self).to_representation(instance)
        data['id'] = instance.pk
        return data

    def create(self, validated_data):
        address = validated_data.pop('address', None)
        if address is not None and not isinstance(address, core_models.Address):
            try:
                address = core_models.Address.objects.create(**address)
            except (ValidationError, TypeError) as e:
                raise serializers.ValidationError({
                    'address': getattr(e, 'messages', _('Cannot create Contact without address'))
                })
        contact = core_models.Contact.objects.create(**validated_data)
        return contact

    def validate_email(self, email):
        return email.lower()

    def validate(self, data):
        if not self.partial and not data.get('email') and not data.get('phone_mobile'):
            raise serializers.ValidationError(_('Please specify E-mail and/or Mobile Phone'))

        if self.instance and getattr(self.instance, 'candidate_contacts', None) and not data.get('birthday'):
            raise serializers.ValidationError({'birthday': [_('Birthday is required')]})

        if core_models.Contact.objects.filter(email__iexact=data.get('email')).exists():
            raise exceptions.ValidationError({'email': ['Contact with this E-mail already exists.']})

        return data

    def get_or_update(self):
        defaults = self.data.copy()
        email = defaults.pop('email')
        phone_mobile = defaults.pop('phone_mobile')
        contact = core_models.Contact.objects.filter(email=email,
                                                     phone_mobile=phone_mobile) \
                                             .first()
        if contact:
            # update model fields
            for attr, value in defaults.items():
                setattr(contact, attr, value)
            contact.save()
            return contact

    class Meta:
        model = core_models.Contact
        read_only = ('is_available', 'contact_address', 'company_contact', 'object_history', 'notes')
        fields = (
            'title', 'first_name', 'last_name', 'email', 'phone_mobile', 'gender', 'is_available', 'birthday',
            'picture', 'phone_mobile_verified', 'email_verified', 'id', 'created_at', 'updated_at',
            {
                'contact_address': (
                    {'address': ('country', 'state', 'city', 'street_address', 'postal_code'),},
                    'is_active'
                ),
            },
            {
                'user': ('id',),
                'notes': ('id', 'note'),
                'company_contact': (
                    'id', 'job_title', 'rating_unreliable', 'legacy_myob_card_number', 'receive_job_confirmation_sms'
                ),
                'candidate_contacts': ('id', 'recruitment_agent'),
            }
        )
        related = RELATED_DIRECT
        extra_kwargs = {
            'candidate_contacts': {'read_only': True},
            'company_contact': {'read_only': True},
            'master_company': {'read_only': True},
            'user': {'read_only': True},
            'title': {'required': True},
        }


class ContactAddressSerializer(ApiBaseModelSerializer):
    class Meta:
        model = core_models.ContactAddress
        fields = (
            '__all__',
            {
                'address': ('__all__', ),
            }
        )


class ContactPasswordSerializer(UserSerializer):
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        password = data['password']
        confirm_password = data['confirm_password']

        if password != confirm_password:
            raise exceptions.ValidationError({
                'confirm_password': _('Passwords does not match'),
            })

        validate_password(password, self.instance)

        return data

    class Meta:
        model = get_user_model()
        fields = ('password', 'confirm_password')


class ContactChangePasswordSerializer(ContactPasswordSerializer):
    old_password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        old_password = data['old_password']

        if not self.instance.check_password(old_password):
            raise exceptions.ValidationError({
                'old_password': _('Password invalid')
            })

        return super().validate(data)

    class Meta:
        model = get_user_model()
        fields = ('password', 'confirm_password', 'old_password')


class ContactRegisterSerializer(ContactSerializer):

    def create(self, validated_data):

        try:
            user = get_user_model().objects.get(firts_name=validated_data('firts_name'),
                                                last_name=validated_data('last_name'),
                                                email=validated_data('email'),
                                                phone_mobile=validated_data('phone_mobile'),
                                                )
            return user.contact

        except get_user_model().DoesNotExist:
            # FIXME: change password handling
            user = UserSerializer().create({'password': ''})

            validated_data['user'] = user
            contact = super().create(validated_data)

            return contact

    class Meta:
        fields = (
            'title', 'first_name', 'last_name', 'email', 'phone_mobile',
            {
                'contact_address': (
                    {'address': ('country', 'state', 'city', 'street_address', 'postal_code'),},
                    'is_active'
                ),
            },
        )


class CompanySerializer(serializers.ModelSerializer):
    # TODO: Permission related issue: Some fields need to be checked depending on
    # TODO: company type when updated or created and role initialed action, for example parent field

    def to_representation(self, instance):
        data = super(CompanySerializer, self).to_representation(instance)
        data['id'] = instance.pk
        return data

    class Meta:
        model = core_models.Company
        fields = 'name', 'business_id', 'registered_for_gst', 'tax_number', 'website',\
                 'date_of_incorporation', 'description', 'notes', 'bank_account',\
                 'credit_check', 'credit_check_date', 'terms_of_payment',\
                 'payment_due_date', 'available', 'billing_email', 'credit_check_proof',\
                 'type', 'purpose',


class CompanyContactRelationshipSerializer(ApiBaseModelSerializer):

    class Meta:
        model = core_models.CompanyContactRelationship
        fields = ('__all__', {
            'company_contact': ('id', 'job_title', 'receive_job_confirmation_sms', {
                'contact': ('id', 'first_name', 'last_name', 'phone_mobile', 'email')
            })
        })


class CompanyContactRenderSerializer(core_mixins.ApiContentTypeFieldMixin, CompanyContactSerializer):

    method_fields = ('company', 'primary_contact')

    active = serializers.BooleanField(required=False)
    termination_date = serializers.DateField(required=False, allow_null=True)

    def get_company(self, instance):
        rel = instance.relationships.filter(active=True).first()
        if rel is not None:
            return CompanyListSerializer(rel.company, fields=('id', '__str__', 'primary_contact')).data
        return None

    def get_primary_contact(self, instance):
        company = self.get_company(instance)
        return company and company['primary_contact']

    class Meta:
        model = core_models.CompanyContact
        fields = (
            'id', 'job_title', 'rating_unreliable', 'legacy_myob_card_number', 'active',
            'receive_job_confirmation_sms', 'termination_date', 'created_at', 'updated_at',
            'message_by_email', 'message_by_sms',
            {
                'contact': (
                    'id', 'first_name', 'last_name', 'title', 'email', 'phone_mobile', 'is_available', 'picture',
                ),
            }
        )
        related = RELATED_DIRECT
        extra_kwargs = {
            'job_title': {'required': True},
            'contact': {'required': False, 'allow_null': True}
        }

    def validate(self, data):
        contact = data.get('contact', None)
        errors = {}
        if not isinstance(contact, core_models.Contact):
            errors['contact'] = _('Please select or create new contact!')
        else:
            contact_id = contact.id

        try:
            company = core_models.Company.objects.get(id=self.initial_data.get('company', None))
        except (core_models.Company.DoesNotExist, ValueError):
            errors['company'] = _('Please select or create new client!')
            company = None

        if company \
                and contact \
                and core_models.CompanyContactRelationship.objects.filter(
                        company=company,
                        company_contact__contact_id=contact_id,
                    ).exists():
            if not self.instance or self.instance.contact.id != contact_id:
                errors['contact'] = _('This client contact already exists!')

        if errors:
            raise exceptions.ValidationError(errors)

        return super().validate(data)

    def create(self, validated_data):
        try:
            company = core_models.Company.objects.get(id=self.initial_data.get('company', None))
        except core_models.Company.DoesNotExist:
            raise exceptions.ValidationError({
                'company': _('Company not found'),
            })

        if not validated_data.get('contact'):
            raise exceptions.ValidationError({
                'contact': _('Contact is required'),
            })

        instance = super(CompanyContactSerializer, self).create(validated_data)

        CompanyContactRelationshipSerializer().create({
            'company_contact': instance,
            'company': company,
        })

        if company.type == core_models.Company.COMPANY_TYPES.regular:
            instance.role = core_models.CompanyContact.ROLE_CHOICES.client
            instance.save(update_fields=['role'])

        return instance

    def update(self, instance, validated_data):
        contact = validated_data.get('contact')
        if contact is None:
            errors = {'contact': _('Contact is required')}
            raise exceptions.ValidationError(errors)

        try:
            company = core_models.Company.objects.get(pk=self.initial_data.get('company'))
        except core_models.Company.DoesNotExist:
            errors = {'company': _('Company is required')}
            raise exceptions.ValidationError(errors)

        instance = super(CompanyContactSerializer, self).update(instance, validated_data)

        today = company.now_tz.date()
        termination_date = validated_data.get('termination_date')

        if not validated_data['active']:
            termination_date = today

        if termination_date and validated_data['active'] and termination_date <= today:
            termination_date = None

        rel, created = core_models.CompanyContactRelationship.objects.update_or_create(
            company_contact=instance,
            company=company,
            defaults={
                'active': validated_data['active'],
                'termination_date': termination_date
            }
        )

        if termination_date and termination_date > today:
            eta = datetime.combine(termination_date, time(2))
            utc_eta = tz2utc(eta)
            core_tasks.terminate_company_contact.apply_async(args=[rel.id],
                                                             eta=utc_eta)

        return instance


class CompanyContactRegisterSerializer(ContactRegisterSerializer):

    company = CompanySerializer(required=False)

    def create(self, validated_data):
        company = validated_data.pop('company', None)

        contact = super().create(validated_data)

        company_contact = CompanyContactSerializer().create(
            {'contact': contact})

        if isinstance(company, dict):
            self.fields['company'].is_valid(raise_exception=True)
            company = self.fields['company'].save()

        CompanyContactRelationshipSerializer().create({
            'company_contact': company_contact,
            'company': company,
        })

        return company_contact

    class Meta:
        fields = (
            'title', 'first_name', 'last_name', 'email', 'phone_mobile', 'address',
            {
                # 'address': ('country', 'state', 'city', 'street_address',
                #             'postal_code'),
                'company': ('name', 'business_id'),
            },
        )


class CompanyAddressSerializer(core_mixins.WorkflowStatesColumnMixin, ApiBaseModelSerializer):
    method_fields = ('portfolio_manager', 'invoices_count', 'orders_count')

    class Meta:
        model = core_models.CompanyAddress
        fields = (
            '__all__',
            {
                'company': (
                    'id', 'name', 'credit_check', 'get_terms_of_payment',
                    'approved_credit_limit', 'type',
                ),
                'address': ('__all__', ),
                'primary_contact': ('id', {
                    'contact': ('__str__', 'phone_mobile')
                },)
            }
        )
        extra_kwargs = {
            'primary_contact': {'required': True},
        }

    def get_company_rel(self, obj):
        company = obj.company
        company_rel = cache.get('company_rel_{}'.format(company.id), None)
        if not company_rel:
            current_site = get_current_site(self.context.get('request'))

            site_company = core_models.SiteCompany.objects.filter(
                site=current_site,
                company__master_companies__regular_company=company
            ).last()
            master_type = core_models.Company.COMPANY_TYPES.master
            if not site_company or site_company.company.type != master_type:
                return

            company_rel = company.regular_companies.filter(
                master_company=site_company.company
            ).last()

            cache.set('company_rel_{}'.format(company.id), company_rel)
        return company_rel

    def get_portfolio_manager(self, obj):
        if not obj:
            return

        company_rel = self.get_company_rel(obj)
        if not company_rel:
            return

        if company_rel:
            return CompanyContactSerializer(company_rel.manager).data

    def get_active_states(self, obj):
        if obj:
            obj = self.get_company_rel(obj)

        return super().get_active_states(obj)

    def get_invoices_count(self, obj):
        if not obj:
            return 0

        return obj.company.customer_invoices.all().count()

    def get_orders_count(self, obj):
        if not obj:
            return 0

        return obj.company.provider_orders.all().count()


@six.add_metaclass(MetaFields)
class ApiBaseSerializer(ApiFullRelatedFieldsMixin,
                        ApiFieldsMixin,
                        serializers.ModelSerializer):

    # Small hack to use serializer with abstract model
    def get_fields(self):
        model = self.Meta.model
        model._meta.abstract = False

        try:
            return super(ApiBaseSerializer, self).get_fields()
        finally:
            model._meta.abstract = True


class WorkflowNodeSerializer(ApiBaseModelSerializer):
    class Meta:
        model = core_models.WorkflowNode
        fields = (
            '__all__', {
                'workflow': ('id', '__str__', 'name', 'model')
            }
        )

    def validate(self, data):
        if 'number' in data:
            if self.instance and self.instance.hardlock and self.instance.number != data["number"]:
                raise ValidationError({
                    'number': _("Number cannot be changed.")
                })

            company = data.get('company')
            core_models.WorkflowNode.validate_node(
                data["number"], data.get("workflow"), company, data.get("active"), data.get("rules"),
                self.instance is None, self.instance and self.instance.id
            )
        return data


class CompanyWorkflowNodeSerializer(ApiBaseModelSerializer):
    method_fields = ('app', 'model')
    class Meta:
        model = core_models.CompanyWorkflowNode
        fields = (
            '__all__', {
                'workflow_node': (
                    'id', '__str__', 'number', 'name_before_activation', 'name_after_activation', 'parent',
                )
            }
        )

    def get_app(self, obj):
        if not obj:
            return None
        return obj._meta.app_label

    def get_model(self, obj):
        if not obj:
            return None
        return obj.workflow_node.workflow.model.name

class WorkflowObjectSerializer(core_mixins.CreatedUpdatedByMixin, ApiBaseModelSerializer):
    method_fields = ('state_name', )

    class Meta:
        model = core_models.WorkflowObject
        fields = ('__all__', {
            'state': ('__all__', {
                'workflow': ('id', 'name'),
            })
        })

    def validate(self, data):
        core_models.WorkflowObject.validate_object(data["state"], data["object_id"], self.instance is None)
        core_models.WorkflowObject.validate_tests(data["state"], data["object_id"], data.get("active", True))

        return data

    def get_state_name(self, obj):
        if not obj:
            return None

        return obj.state.name_after_activation or obj.state.name_before_activation


class WorkflowTimelineSerializer(ApiBaseModelSerializer):

    method_fields = ('state', 'requirements', 'wf_object_id', 'acceptance_tests', 'substates', 'total_score')

    class Meta:
        model = core_models.WorkflowNode
        fields = ('id', 'name_before_activation', 'name_after_activation', 'endpoint', 'number')

    def __init__(self, *args, **kwargs):
        self.target = kwargs.pop('target', None)

        super(WorkflowTimelineSerializer, self).__init__(*args, **kwargs)

    def get_state(self, obj):
        if not obj:
            return NOT_ALLOWED

        workflow_object = core_models.WorkflowObject.objects.filter(
            state=obj, object_id=self.target.id
        )
        if workflow_object.exists():
            workflow_object = workflow_object.latest('updated_at')
        else:
            workflow_object = None

        if workflow_object is not None and workflow_object.active:
            return ACTIVE
        else:
            is_tests_filled = core_models.WorkflowObject.validate_tests(
                obj, self.target.id, True, raise_exception=False
            )
            is_test_fill_needed = workflow_object is not None and not workflow_object.active and not is_tests_filled

            if self.target.is_allowed(obj) or is_test_fill_needed:
                return ALLOWED

            if not self.target._check_condition(obj.rules.get('required_states')):
                return NOT_ALLOWED
            return NEED_REQUIREMENTS

    def get_requirements(self, obj):
        if not obj:
            return None

        if not self.target.is_allowed(obj):
            return self.target.get_required_messages(obj, False)

        return None

    def _get_wf_object(self, obj):
        if not obj:
            return None

        return core_models.WorkflowObject.objects.filter(
            state=obj, object_id=self.target.id
        ).first()

    def get_wf_object_id(self, obj):
        workflow_object = self._get_wf_object(obj)

        return workflow_object and workflow_object.id

    def get_acceptance_tests(self, obj):
        from r3sourcer.apps.acceptance_tests.models import AcceptanceTestWorkflowNode
        from r3sourcer.apps.acceptance_tests.api.serializers import AcceptanceTestWorkflowNodeSerializer

        qry = models.Q(
            acceptance_test__acceptance_tests_skills__isnull=True,
            acceptance_test__acceptance_tests_tags__isnull=True,
            acceptance_test__acceptance_tests_industries__isnull=True,
        )

        closest_company = self.target.get_closest_company()
        if closest_company.industries is not None:
            qry |= models.Q(acceptance_test__acceptance_tests_industries__industry_id__in=closest_company.industries.all().values_list('id'))

        if hasattr(self.target, 'candidate_skills'):
            skill_ids = self.target.candidate_skills.values_list('skill', flat=True)
            qry |= models.Q(acceptance_test__acceptance_tests_skills__skill_id__in=skill_ids)

        if hasattr(self.target, 'tag_rels'):
            tag_ids = self.target.tag_rels.values_list('tag', flat=True)
            qry |= models.Q(acceptance_test__acceptance_tests_tags__tag_id__in=tag_ids)

        tests = AcceptanceTestWorkflowNode.objects.filter(
            qry, company_workflow_node__workflow_node=obj, company_workflow_node__company=closest_company
        ).distinct()
        wf_object_id = self.get_wf_object_id(obj)

        return tests and AcceptanceTestWorkflowNodeSerializer(tests, many=True, workflow_object_id=wf_object_id).data

    def get_substates(self, obj):
        if obj.children.exists():
            return WorkflowTimelineSerializer(obj.children.all(), target=self.target, many=True).data

        return []

    def get_total_score(self, obj):
        children_cnt = 0
        sub_score = 0

        if obj.children.count() > 0:
            score_sum = 0
            for substate in obj.children.all():
                child_score = self.get_total_score(substate)
                if child_score > 0:
                    score_sum += child_score
                    children_cnt += 1

            if score_sum > 0 and children_cnt > 0:
                sub_score = score_sum / children_cnt

        workflow_object = self._get_wf_object(obj)
        if workflow_object and workflow_object.score > 0:
            return (workflow_object.score + sub_score) / 2 if sub_score > 0 else workflow_object.score

        a_tests = [a_test.get('score', 0) for a_test in self.get_acceptance_tests(obj)]
        if sub_score > 0:
            a_tests.append(sub_score)
        return sum(a_tests) / len(a_tests) if len(a_tests) > 0 else 0


class NavigationSerializer(ApiBaseModelSerializer):

    method_fields = ('childrens', )

    class Meta:
        model = core_models.ExtranetNavigation
        fields = ('id', 'name', 'url', 'endpoint')

    def get_childrens(self, obj):
        if obj is None:
            return []

        childrens = obj.get_children()

        serializer = NavigationSerializer(childrens, many=True)
        return serializer.data


class DashboardModuleSerializer(ApiBaseModelSerializer):

    module_data = serializers.SerializerMethodField(read_only=True)

    def get_module_data(self, obj):
        model_cls = obj.content_type.model_class()
        return {
            'app': obj.content_type.app_label,
            'model': obj.content_type.model,
            'name': model_cls._meta.verbose_name,
            'plural_name': model_cls._meta.verbose_name_plural,
            'endpoint': obj.endpoint,
            'description': obj.description,
            'add_label': obj.add_label,
            'label': obj.label,
        }

    def validate(self, attrs):
        if core_models.DashboardModule.objects.filter(content_type=attrs['content_type']).exists():
            raise serializers.ValidationError(
                {'content_type': _("Module already exists")})
        return attrs

    class Meta:
        model = core_models.DashboardModule
        fields = ('id', 'content_type', 'module_data', 'is_active')


class UserDashboardModuleSerializer(ApiBaseModelSerializer):

    class Meta:
        model = core_models.UserDashboardModule
        fields = (
            'id',
            'company_contact',
            'dashboard_module',
            'position',
            'ui_config',
        )
        extra_kwargs = {
            'company_contact': {'read_only': True}
        }


class InvoiceRuleSerializer(ApiBaseModelSerializer):

    class Meta:
        model = core_models.InvoiceRule
        fields = ('__all__', )
        extra_kwargs = {
            'serial_number': {'required': False},
        }


class GroupSerializer(ApiBaseModelSerializer):

    class Meta:
        model = Group
        fields = ('__all__', )


class CompanyIndustrySerializer(ApiBaseModelSerializer):
    id = serializers.ReadOnlyField(source='industry.id')
    __str__ = serializers.ReadOnlyField(source='industry.__str__')

    class Meta:
        model = core_models.CompanyIndustryRel
        fields = ('id', 'default', {'industry': ('id', {'translations': ('language', 'value')})})


class CompanyListSerializer(
    core_mixins.WorkflowStatesColumnMixin, core_mixins.WorkflowLatestStateMixin, core_mixins.ApiContentTypeFieldMixin,
    ApiBaseModelSerializer
):
    method_fields = (
        'manager', 'terms_of_pay', 'regular_company_rel', 'master_company', 'state', 'city', 'credit_approved',
        'address', 'manager_phone', 'myob_name', 'industries', 'vat_name'
    )

    invoice_rule = InvoiceRuleSerializer(required=False)

    class Meta:
        model = core_models.Company
        fields = (
            '__all__',
            {
                'invoice_rule': '__all__',
                'primary_contact': (
                    'id', '__str__', 'job_title',
                    {
                        'contact': ('id', 'email', 'phone_mobile')
                    }
                ),
                'groups': ('id', '__str__'),
                'company_settings': (
                    'id', 'allow_job_creation', '__str__'
                )
            }
        )
        extra_kwargs = {
            'myob_settings': {'read_only': True},
            'subcontractor': {'read_only': True},
            'groups': {'read_only': True},
            'business_id': {
                'required': True,
                'validators': [
                    validators.UniqueValidator(
                        queryset=core_models.Company.objects.all(), message=_('This Business Number already exists')
                    )
                ]
            },
            'sms_balance': {'required': False},
            'company_settings': {'required': False},
        }

    def get_company_rel(self, company):
        return company.regular_companies.last()

    def get_manager(self, obj):
        if not obj:
            return

        company_rel = self.get_company_rel(obj)
        if not company_rel:
            return

        if company_rel and company_rel.manager:
            return {
                'job_title': company_rel.manager.job_title,
                '__str__': str(company_rel.manager.contact),
                'phone_mobile': str(company_rel.manager.contact.phone_mobile),
                'id': company_rel.manager.id
            }

    def get_manager_phone(self, obj):
        manager = self.get_manager(obj)
        return manager and manager['phone_mobile']

    def get_master_company(self, obj):
        if not obj:
            return

        company_rel = self.get_company_rel(obj)
        if not company_rel:
            return

        if company_rel:
            return core_field.ApiBaseRelatedField.to_read_only_data(company_rel.master_company)

    def get_active_states(self, obj):
        if obj and obj.type == core_models.Company.COMPANY_TYPES.regular:
            obj = self.get_company_rel(obj)

        return super().get_active_states(obj)

    def get_terms_of_pay(self, obj):
        if not obj:
            return

        return obj.get_terms_of_payment()

    def get_regular_company_rel(self, obj):
        relation = self.get_company_rel(obj)
        return relation and core_field.ApiBaseRelatedField.to_read_only_data(relation)

    def _get_address(self, obj):
        return obj.company_addresses.filter(hq=True).first()

    def get_address(self, obj):
        address = self._get_address(obj)
        return address and core_field.ApiBaseRelatedField.to_read_only_data(address.address)

    def get_state(self, obj):
        address = self._get_address(obj)

        if address:
            return address.address.state and address.address.state.name

    def get_city(self, obj):
        address = self._get_address(obj)

        if address:
            return address.address.city and address.address.city.name

    def get_credit_approved(self, obj):
        if obj.credit_check == core_models.Company.CREDIT_CHECK_CHOICES.approved:
            msg = _('Approved')
            if obj.credit_check_date:
                msg = '%s %s' % (msg, date_format(obj.credit_check_date, settings.DATE_FORMAT))
        else:
            msg = _('Not Approved')
        return msg

    def get_latest_state(self, obj):
        if obj and obj.type == core_models.Company.COMPANY_TYPES.regular:
            obj = self.get_company_rel(obj)

        return super().get_latest_state(obj)

    def get_myob_name(self, obj):
        sync_obj = MYOBSyncObject.objects.filter(record=obj.pk).first()
        return sync_obj and sync_obj.legacy_myob_card_number

    def get_industries(self, obj):
        queryset = core_models.CompanyIndustryRel.objects.filter(company=obj)
        return [CompanyIndustrySerializer(q).data for q in queryset]

    def get_vat_name(self, company):
        return company.vat_name()

class FormFieldSerializer(ApiBaseModelSerializer):

    def to_representation(self, instance):
        if not isinstance(instance, core_models.FormField):
            raise NotImplementedError

        class DynamicFormFieldSerializer(ApiBaseModelSerializer):

            method_fields = ('field_type', )

            class Meta:
                model = type(instance)
                fields = model.get_serializer_fields()

            def get_field_type(self, obj):
                return obj.get_field_type()

        return DynamicFormFieldSerializer(instance).data

    class Meta:
        model = core_models.FormField
        fields = '__all__'


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = core_models.Language
        fields = ('name',)


class FormSerializer(ApiBaseModelSerializer):

    method_fields = ('model_fields', 'groups', 'company_links', 'extra_fields')

    class Meta:
        model = core_models.Form
        fields = (
            'id', 'company', 'builder', 'is_active',
            {
                'translations': ('language', 'title', 'short_description', 'button_text', 'result_messages')
            }
        )

    def validate(self, attrs):
        """
        Validate data for permissions to change default forms without company.
        """
        request = self.context['request']
        if attrs['company'] is None and not request.user.is_superuser:
            raise serializers.ValidationError({
                'company': _("You can't update/create default forms")
            })
        if self.instance is not None and self.instance.company is None and \
                not request.user.is_superuser:
            raise serializers.ValidationError({
                'company': _("You can't update/create default forms")
            })

        # TODO: check unique together constraint
        # # check if company/builder relation already exists
        # qs = core_models.Form.objects.filter(company=attrs['company'],
        #                                 builder=attrs['builder'])
        # if qs.exists():
        #     if self.instance is None or qs.exclude(id=self.instance.id).exists():
        #         raise serializers.ValidationError({
        #             'company': _("Form for this company already exists"),
        #             'builder': _("Form for this builder already exists")
        #         })
        return attrs

    def get_model_fields(self, obj):
        if obj.builder:
            return list(core_models.ModelFormField.get_model_fields(
                obj.builder.content_type.model_class(),
                builder=obj.builder
            ))

        return []

    def get_extra_fields(self, obj):
        if obj.builder:
            return obj.builder.extra_fields.values('name', 'required', 'help_text', 'label', 'content_type')
        return []

    def get_groups(self, obj):
        return FormFieldGroupSerializer(obj.groups.all(), many=True).data

    def get_company_links(self, obj):
        return obj.get_company_links(self.context['request'].user.contact)


class FormRenderSerializer(ApiBaseModelSerializer):

    method_fields = ('ui_config', 'tests')

    class Meta:
        model = core_models.Form
        fields = (
            'id', 'title', 'company', 'builder', 'is_active', 'short_description', 'save_button_text', 'submit_message'
        )

    def get_ui_config(self, obj):
        return obj.get_ui_config()

    def get_tests(self, obj):
        from r3sourcer.apps.acceptance_tests.api.serializers import  AcceptanceTestSerializer
        from r3sourcer.apps.acceptance_tests.models import AcceptanceTest
        qry = models.Q(
            acceptance_test__acceptance_tests_skills__isnull=True,
            acceptance_test__acceptance_tests_industries__isnull=True,
            )

        company = obj.company
        if company.industries.all() is not None:
            qry |= models.Q(
                acceptance_test__acceptance_tests_industries__industry_id__in=company.industries.all().values_list('id'))

        skill_ids = company.skills.values_list('id', flat=True)
        qry |= models.Q(acceptance_test__acceptance_tests_skills__skill_id__in=skill_ids)

        workflow = Workflow.objects.get(model=ContentType.objects.get_for_model(CandidateContact))

        tests_node = AcceptanceTestWorkflowNode.objects.filter(
            qry, company_workflow_node__workflow_node__workflow=workflow,
            company_workflow_node__workflow_node__name_before_activation="Register New Candidate",
            company_workflow_node__company=company
            ).distinct()
        test_ids = [i.acceptance_test.id for i in tests_node]
        tests = AcceptanceTest.objects.filter(id__in=test_ids).distinct()

        return AcceptanceTestSerializer(tests, many=True).data


class FormFieldGroupSerializer(ApiBaseModelSerializer):

    method_fields = ('field_list', )

    class Meta:
        model = core_models.FormFieldGroup
        fields = (
            'id', 'form', 'name', 'position'
        )

    def get_field_list(self, obj):
        return FormFieldSerializer(instance=obj.fields.all(), many=True).data


class BaseFormFieldSerializer(ApiBaseModelSerializer):

    method_fields = ('field_type',)

    def get_field_type(self, obj):
        return obj.get_field_type()


class ModelFormFieldSerializer(BaseFormFieldSerializer):

    def validate(self, attrs):
        """
        Validate unique field on the form and check field name
        """
        if not attrs['group'].form.is_valid_model_field_name(attrs['name']):
            raise serializers.ValidationError({
                'name': _("Incorrect field name for model")
            })
        base_qs = core_models.FormField.objects.filter(
            group__form_id=attrs['group'].form_id, name=attrs['name']
        )
        if self.instance is not None:
            if base_qs.exclude(id=self.instance.id).exists():
                raise serializers.ValidationError({
                    'name': _('Field must be unique on the form')
                })
        else:
            if base_qs.exists():
                raise serializers.ValidationError({
                    'name': _('Field must be unique on the form')
                })
        return attrs

    class Meta:
        model = core_models.ModelFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text', 'regex'
        )


class SelectFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.SelectFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text', 'is_multiple', 'choices'
        )


class DateFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.DateFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text'
        )


class CheckBoxFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.CheckBoxFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text'
        )


class RadioButtonsFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.RadioButtonsFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text', 'choices'
        )


class FileFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.FileFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text'
        )


class ImageFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.ImageFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text'
        )


class NumberFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.NumberFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text',
            'min_value', 'max_value', 'step'
        )


class TextFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.TextFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text',
            'max_length', 'subtype'
        )


class TextAreaFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.TextAreaFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text',
            'max_length', 'rows'
        )


class RelatedFormFieldSerializer(BaseFormFieldSerializer):

    class Meta:
        model = core_models.RelatedFormField
        fields = (
            'id', 'group', 'name', 'label', 'placeholder', 'class_name',
            'required', 'position', 'help_text',
            'content_type', 'is_multiple'
        )


class FormBuilderSerializer(ApiBaseModelSerializer):

    class Meta:
        model = core_models.FormBuilder
        fields = (
            'id', 'content_type'
        )


class TrialSerializer(serializers.Serializer):

    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    phone_mobile = serializers.CharField()
    company_name = serializers.CharField(max_length=127)
    website = serializers.CharField()
    country_code = serializers.CharField()

    def validate(self, data):
        email = data['email']
        company_name = data['company_name']
        data['phone_mobile'] = normalize_phone_number(data.get('phone_mobile', ''),
                                                      data.get('country_code'))

        if not data['phone_mobile'] or validate_phone_number(data['phone_mobile'], data.get('country_code')) is False:
            raise serializers.ValidationError({'phone_mobile': _('Invalid phone number')})

        messages = {}

        if core_models.Contact.objects.filter(email=email).exists():
            messages['email'] = _('User with this email already registered')

        if core_models.Contact.objects.filter(phone_mobile=data['phone_mobile']).exists():
            messages['phone_mobile'] = _('User with this phone number already registered')

        if messages:
            raise serializers.ValidationError(messages)

        try:
            core_models.Company.objects.get(name=company_name)
            raise serializers.ValidationError({
                'company_name': _('Company with this name already registered')
            })
        except core_models.Company.DoesNotExist:
            pass

        domain = '{}.{}'.format(data['website'].lower(), settings.REDIRECT_DOMAIN)
        try:
            URLValidator()('https://{}'.format(domain))
        except ValidationError:
            raise serializers.ValidationError({
                'website': _('Website address is invalid')
            })

        try:
            Site.objects.get(domain__iexact=domain)
            raise serializers.ValidationError({
                'website': _('Website address already registered')
            })
        except Site.DoesNotExist:
            pass
        return data


class TagTranslationSerializer(serializers.ModelSerializer):
    language = LanguageSerializer()

    class Meta:
        model = core_models.TagLanguage
        fields = (
            'language',
            'value',
        )


class TagSerializer(ApiBaseModelSerializer):
    method_fields = ('skills', 'children')

    class Meta:
        model = core_models.Tag
        fields = (
            'id',
            'name',
            'parent',
            'active',
            'evidence_required_for_approval',
            'confidential',
            'owner',
            {'translations': ('language', 'value')}
        )

    @classmethod
    def skill_translation(cls, skill):
        response = []
        for x in skill.skill.name.translations.all():
            response.append({
                'value': x.value,
                'language': {
                    'id': x.language.pk,
                    'name': x.language.name,
                    '__str__': x.language.__str__()
                },
                '__str__': x.__str__()
            })
        return response

    def get_skills(self, obj):
        if isinstance(obj, core_models.Tag):
            return [{'id': skill.id, '__str__': str(skill.skill), 'translations': self.skill_translation(skill)}
                    for skill in obj.skill_tags.all()]
        return []

    @classmethod
    def get_children(cls, obj):
        if isinstance(obj, core_models.Tag):
            return [core_field.ApiBaseRelatedField.to_read_only_data(child) for child in obj.children.all()]
        return []


class ContactForgotPasswordSerializer(serializers.Serializer):

    email = serializers.EmailField()

    def validate_email(self, email):
        if not core_models.Contact.objects.filter(email=email).exists():
            raise exceptions.ValidationError(_("User with this email doesn't exist"))

        return email


class CompanyPurposeSerializer(ApiBaseModelSerializer):

    class Meta:
        model = core_models.Company
        fields = ('purpose', )


class CompanyDomainSerializer(serializers.Serializer):

    website = serializers.CharField()

    def validate(self, data):
        domain = '{}.{}'.format(data['website'].lower(), settings.REDIRECT_DOMAIN)
        try:
            URLValidator()('https://{}'.format(domain))
        except ValidationError:
            raise serializers.ValidationError({
                'website': _('Website address is invalid')
            })

        try:
            Site.objects.get(domain__iexact=domain)
            raise serializers.ValidationError({
                'website': _('Website address already registered')
            })
        except Site.DoesNotExist:
            pass
        return data


class TimezoneApiSerializerMixin:
    method_fields = ('timezone',)

    @classmethod
    def get_timezone(cls, obj):
        return obj.timezone


class UUIDApiSerializerMixin(TimezoneApiSerializerMixin):
    method_fields = (
        *TimezoneApiSerializerMixin.method_fields,
        'updated_at',
        'created_at',
        'updated_at_tz',
        'created_at_tz',
    )

    @classmethod
    def get_created_at(cls, obj):
        return obj.created_at_utc

    @classmethod
    def get_updated_at(cls, obj):
        return obj.updated_at_utc

    @classmethod
    def get_created_at_tz(cls, obj):
        return obj.created_at_tz

    @classmethod
    def get_updated_at_tz(cls, obj):
        return obj.updated_at_tz


class InvoiceSerializer(UUIDApiSerializerMixin, ApiBaseModelSerializer):
    method_fields = (
        *UUIDApiSerializerMixin.method_fields,
        *ApiBaseModelSerializer.method_fields,
        'synced_at',
        'synced_at_tz',
    )

    @classmethod
    def get_synced_at(cls, obj):
        return obj.synced_at_utc

    @classmethod
    def get_synced_at_tz(cls, obj):
        return obj.synced_at_tz

    class Meta:
        model = core_models.Invoice
        fields = (
            '__all__',
            {'invoice_lines': '__all__'}
        )


class InvoiceLineSerializer(UUIDApiSerializerMixin, ApiBaseModelSerializer):
    method_fields = (
        *UUIDApiSerializerMixin.method_fields,
        *ApiBaseModelSerializer.method_fields,
    )

    class Meta:
        model = core_models.InvoiceLine
        fields = ('__all__', {
            'vat': ('id', 'name'),
            'timesheet': ('id', {
                'job_offer': ('id', 'candidate_contact'),
            })
        })


class VATSerializer(ApiBaseModelSerializer):
    class Meta:
        model = core_models.VAT
        fields = (
            '__all__',
        )


class UomSerializer(ApiBaseModelSerializer):
    class Meta:
        model = core_models.UnitOfMeasurement
        fields = (
            'id', 'name', 'short_name', 'default',
            {'translations': ('id', 'language', 'name', 'short_name')},
        )


class RoleSerializer(ApiBaseModelSerializer):
    method_fields = ['domain', 'is_active', 'is_primary']

    class Meta:
        model = core_models.Role
        fields = (
            'id', 'name',
            {'company_contact_rel': ('id', 'company', 'company_contact')},
        )

    def get_domain(cls, obj):
        if obj.company_contact_rel:
            site_company = obj.company_contact_rel.company.get_closest_master_company().site_companies.last()
            return site_company.site.domain if site_company else None
        return None

    def get_is_active(cls, obj):
        if obj.name != core_models.Role.ROLE_NAMES.candidate:
            if not obj.company_contact_rel:
                return False
        return True

    def get_is_primary(cls, obj):
        request = cls.context['request']
        if obj.company_contact_rel and obj.company_contact_rel.company.primary_contact and \
            request.user == obj.company_contact_rel.company.primary_contact.contact.user:
                return True
        return False

class PublicHolidaySerializer(ApiBaseModelSerializer):
    class Meta:
        model = core_models.PublicHoliday
        fields = (
            'id', 'date', 'name', 'country'
            )
