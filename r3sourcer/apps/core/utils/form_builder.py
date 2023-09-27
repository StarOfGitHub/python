import re

from django.core.files.base import File
from django.db import models
from django.db import transaction
from django.forms import ModelForm, ValidationError

from rest_framework import exceptions


__all__ = [
    'StorageHelper', 'SimpleFieldHelper', 'RelatedFieldHelper'
]


def _get_model_field_value(value):
    if isinstance(value, models.Model):
        from r3sourcer.apps.core.models import Country
        if isinstance(value, Country):
            return value.code2
        else:
            return value.id

    return value


class StorageHelper(object):
    """
    Helper class for form builder.
    Would be use for creating new objects from Form Builder.
    """

    __slots__ = ['_model', '_fields', '_source_fields', '_done', '_instance', '_validated_fields', '_errors', '_form']

    LOOKUP_SEPARATOR = '__'

    def __init__(self, model, fields: dict):
        assert issubclass(model, models.Model), "`model` should be models.Model subclass"

        self._model = model
        self._source_fields = fields
        self._fields = {}
        self._done = False
        self._instance = None
        self._errors = None
        self._form = None

    def process_fields(self):
        """

        :return:
        """
        for field_name, field_value in self._source_fields.items():
            if self.LOOKUP_SEPARATOR in field_name:
                field = RelatedFieldHelper(self._model, field_name, field_value)
                if field.name in self._fields:
                    old_field = self._fields.get(field.name)
                    RelatedFieldHelper.merge(old_field, field)
                else:
                    self._fields.setdefault(field.name, field)
            else:
                field_value = _get_model_field_value(field_value)
                self._fields.setdefault(field_name, SimpleFieldHelper(field_name, field_value))

    def validate(self, raise_errors=False):
        """
        Validate fields
        :return:
        """
        from r3sourcer.apps.candidate.models import CandidateContact

        fields_to_validate = {}
        self._errors = {}
        related_fields = {}
        lazy_fields = {}
        for name, field in self._fields.items():
            try:
                if isinstance(field, RelatedFieldHelper):

                    required_fields = field.get_missing_required_fields()
                    if len(required_fields) > 0:
                        lazy_fields[name] = field

                    if name in lazy_fields:
                        continue

                    field.save_related(name)
                    related_fields[name] = field
                    value = field.value.id
                else:
                    value = field.value

                fields_to_validate.setdefault(name, value)
            except exceptions.ValidationError as e:
                self._errors.update({k.replace('__', '.'): v for k, v in e.detail.items()})

        if not self._errors:
            for name, field in lazy_fields.items():
                field.save_related(name, values=fields_to_validate)
                related_fields[name] = field
                fields_to_validate.setdefault(name, field.value.id)

        meta_class = type('Meta', (object, ), {
            'model': self._model,
            'fields': [name for name, field in fields_to_validate.items()]
        })

        base_classes = (ModelForm, )
        if issubclass(self._model, CandidateContact):
            base_classes = (CandidateFormMixin, ) + base_classes

        form = type('MForm', base_classes, {
            'Meta': meta_class,
        })

        self._form = form(fields_to_validate)

        is_valid = self._form.is_valid()
        if not is_valid:
            self._errors.update({k.replace('__', '.'): v for k, v in self._form.errors.items()})

            for name, field in related_fields.items():
                field.value.delete()

            if raise_errors:
                raise exceptions.ValidationError(self._errors)

        return is_valid and not self._errors

    @transaction.atomic
    def create_instance(self):
        """
        Create instance using fields (RelatedFields and SimpleFields)

        :return: self.model instance.
        """
        assert self._instance is None, 'Instance already created'
        assert self._form is not None, 'Need to run `.validate()` first'
        assert not self._errors, 'Form invalid'

        self._instance = self._form.save()
        return self._instance

    @property
    def errors(self):
        return self._errors or {}

    @classmethod
    def separate_lookup_name(cls, field_name: str) -> tuple():

        """
        Separate lookup names.

        >> StorageHelper.separate_lookup_name('user__name')
        << ('user', 'name')

        >> StorageHelper.separate_lookup_name('name')
        << ('name', '')

        :return: tuple of str -> (first field name, lookup name)
        """
        field_name, _, lookup_name = field_name.partition(cls.LOOKUP_SEPARATOR)
        return field_name, lookup_name

    @classmethod
    def join_lookup_names(cls, *fields):
        return cls.LOOKUP_SEPARATOR.join(fields)

    @classmethod
    def get_field_from_lookup_name(cls, model_class, field_name: str) -> tuple():
        """
        Get model class and it's field from lookup string

        >> StorageHelper.get_field_from_lookup_name('contact__address__street_address')
        << (<class 'r3sourcer.apps.core.models.core.Address'>, 'street_address')

        :return: tuple ( model class object, field name )
        """
        if field_name.count(cls.LOOKUP_SEPARATOR):
            lookup_name, field_name = StorageHelper.separate_lookup_name(field_name)
            model_class = model_class._meta.get_field(lookup_name).related_model
            return cls.get_field_from_lookup_name(model_class, field_name)
        return model_class, field_name


class SimpleFieldHelper(object):
    """
    Helper class for flat fields (number, str, bool, etc.)
    """

    __slots__ = [
        'name', 'value'
    ]

    def __init__(self, name, value):
        assert re.match('^[a-z]+[\w_]*$', name, re.IGNORECASE), "Incorrect field name"

        self.name = name
        self.value = value


class RelatedFieldHelper(object):
    """
    Helper class for ForeignObject fields, would be used for storing and manipulation related object fields.
    """

    __slots__ = ['_model', 'name', '_lookup_name', 'value', 'simple_fields', 'related_fields', '_done', '_form']

    def __init__(self, model, name, value):

        assert re.match('^[a-z]+[\w_]*$', name, re.IGNORECASE), "Incorrect field name"

        self.name, self._lookup_name = StorageHelper.separate_lookup_name(name)
        self._model = model._meta.get_field(self.name).related_model
        self._form = None

        self.value = None
        self._done = False
        self.simple_fields = {}
        self.related_fields = {}

        self.process_field(value)

    def process_field(self, value):
        assert not self._done, "Field already processed"

        if StorageHelper.LOOKUP_SEPARATOR in self._lookup_name:
            related_field = RelatedFieldHelper(self._model, self._lookup_name, value)
            self.related_fields.setdefault(related_field.name, related_field)
        else:
            if '_id' not in self._lookup_name:
                value = _get_model_field_value(value)
                self.simple_fields.setdefault(self._lookup_name, SimpleFieldHelper(self._lookup_name, value))
        self._done = True

    @classmethod
    def merge(cls, field1, field2):
        """
        Merge fields from different related field instances.
        Would be use for extending field1 from field2.

        :param field1: RelatedFieldHelper
        :param field2: RelatedFieldHelper
        """

        for field_name, value in field2.related_fields.items():
            if field_name in field1.related_fields:
                cls.merge(field1.related_fields[field_name], field2.related_fields[field_name])
            else:
                field1.related_fields.setdefault(field_name, field2.related_fields[field_name])

        for field_name, value in field2.simple_fields.items():
            field1.simple_fields.setdefault(field_name, value)

    def save_related(self, parent_name=None, values=None):
        """
        Create new instance from related fields and simple fields, bind its to self._model instance.
        :return: self._model instance
        """
        if self.value is not None:
            return

        related_fields = {}
        errors = {}
        if self.related_fields:
            for name, related_field in self.related_fields.items():
                try:
                    related_field.save_related(name)
                    if isinstance(related_field.value, models.Model):
                        if name == 'address':
                            related_fields[name] = [related_field.value.pk]
                        else:
                            related_fields[name] = related_field.value.pk
                    else:
                        related_fields[name] = related_field.value
                except ValidationError as e:
                    if hasattr(e, 'error_dict'):
                        errors.update(e.error_dict)
                    elif hasattr(e, 'message'):
                        errors[name] = [e.message]
                    else:
                        errors[name] = e.error_list

        missing_fields = self.get_missing_required_fields()

        data = dict(
            **{name: field.value for name, field in self.simple_fields.items() if not isinstance(field.value, File)},
            **related_fields
        )
        files = {
            name: field.value for name, field in self.simple_fields.items() if isinstance(field.value, File)
        }

        if isinstance(values, dict):
            data.update({name: values[name] for name in missing_fields})

        model_form = self.get_modelform(data, files=files, required_fields=missing_fields)

        if not model_form.is_valid():
            errors.update({
                '{}__{}'.format(parent_name, field_name) if field_name != '__all__' else 'non_field_errors': errors
                for field_name, errors in model_form.errors.items()
            })
            raise exceptions.ValidationError(errors)

        form_obj = model_form.save(commit=False)
        form_obj.save()
        # create ContactAddress instance if address atribute exists
        if hasattr(form_obj, 'address'):
            from r3sourcer.apps.core.models import ContactAddress
            ContactAddress.objects.create(contact=form_obj,
                                          address=self.related_fields['address'].value,
                                          is_active=True)

        self.value = form_obj

    def get_modelform(self, data, files=None, required_fields=None):
        fields = [name for name, field in self.simple_fields.items()]
        fields.extend([name for name, field in self.related_fields.items()])
        fields.extend(required_fields)
        meta_class = type('Meta', (object, ), {
            'model': self._model,
            'fields': fields
        })

        form = type('RelatedForm', (ModelForm, ), {
            'Meta': meta_class,
        })

        return form(data, files=files)

    def get_required(self):
        model_fields = self._model._meta.get_fields()

        def has_attr(field, attr):
            return getattr(field, attr, False)

        return [
            field.name for field in model_fields
            if ((not has_attr(field, 'null') and not has_attr(field, 'blank') and
                field.default == models.NOT_PROVIDED) and
                field.name not in {'id', 'created_at', 'updated_at'})
        ]

    def get_missing_required_fields(self):
        return [
            name for name in self.get_required()
            if name not in self.simple_fields and name not in self.related_fields
        ]


class CandidateFormMixin(ModelForm):

    def save(self, *args, **kwargs):
        from r3sourcer.apps.candidate.models import CandidateRel
        from r3sourcer.apps.core.models import ContactRelationship
        from r3sourcer.apps.core.utils.companies import get_site_master_company
        from r3sourcer.apps.core.tasks import send_contact_verify_sms, send_contact_verify_email
        instance = super().save(*args, **kwargs)

        master_company = get_site_master_company()
        ContactRelationship.objects.create(
            contact=instance.contact,
            company=master_company
        )
        CandidateRel.objects.create(
            master_company=master_company,
            candidate_contact=instance,
            owner=True,
            active=True,
        )

        manager = master_company.primary_contact
        if not instance.contact.phone_mobile_verified:
            send_contact_verify_sms.apply_async(args=(instance.contact.id, manager.contact_id))
        if not instance.contact.email_verified:
            send_contact_verify_email.apply_async(args=(instance.contact.id, manager.contact_id, master_company.id))

        return instance
