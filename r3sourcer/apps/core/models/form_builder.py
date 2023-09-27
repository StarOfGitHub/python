from collections import OrderedDict

from django import forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField, ArrayField
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.db import models
from django.urls import reverse, exceptions as url_exceptions
from django.utils.functional import cached_property
from django.utils.module_loading import import_string
from django.utils.translation import ugettext_lazy as _

from inflector import Inflector
from model_utils import Choices
from model_utils.managers import InheritanceManager
from polymorphic.models import PolymorphicModel

from r3sourcer.apps.core.models import Country
from r3sourcer.helpers.models.abs import UUIDModel
from r3sourcer.apps.core.utils.address import parse_google_address
from r3sourcer.apps.core.utils.companies import get_master_companies_by_contact, get_site_master_company
from r3sourcer.apps.core.utils.form_builder import StorageHelper
from r3sourcer.apps.core.utils.user import get_default_company
from r3sourcer.apps.core_adapter.utils import api_reverse


__all__ = [
    'FormBuilder',
    'Form',
    'FormField',
    'FormFieldGroup',
    'FormLanguage',

    'ModelFormField',
    'SelectFormField',
    'TextAreaFormField',
    'TextFormField',
    'NumberFormField',
    'DateFormField',
    'FileFormField',
    'ImageFormField',
    'CheckBoxFormField',
    'RadioButtonsFormField',
    'RelatedFormField',
    'FormBuilderExtraFields',
    'transform_ui_choices'
]


def transform_ui_choices(values: list):
    return [
        (v['value'], v['label'])
        for v in values
    ]


class FormBuilder(UUIDModel):
    content_type = models.OneToOneField(
        'contenttypes.ContentType',
        verbose_name=_("Content type for form"),
        on_delete=models.CASCADE,
    )

    fields = ArrayField(
        models.CharField(max_length=255),
        default=list,
        verbose_name=_('Available fields'),
        blank=True
    )

    required_fields = ArrayField(
        models.CharField(max_length=255),
        default=list,
        verbose_name=_('Required fields'),
        blank=True
    )

    active_fields = ArrayField(
        models.CharField(max_length=255),
        default=list,
        verbose_name=_('Default active fields'),
        blank=True
    )

    def __str__(self):
        return str(self.content_type)

    class Meta:
        verbose_name = _("Form builder")
        verbose_name_plural = _("Form builders")


class FormBuilderExtraFields(UUIDModel):

    builder = models.ForeignKey(
        FormBuilder,
        related_name='extra_fields',
        verbose_name=_("Form Builder"),
        on_delete=models.CASCADE,
    )

    content_type = models.ForeignKey(
        'contenttypes.ContentType',
        verbose_name=_("Content type for field"),
        related_name='form_builder_fields',
        on_delete=models.CASCADE,
    )

    name = models.SlugField(
        verbose_name=_("Name"),
    )

    label = models.CharField(
        verbose_name=_("Label"),
        default='',
        max_length=512,
        blank=True
    )

    placeholder = models.CharField(
        verbose_name=_("Placeholder"),
        max_length=512,
        blank=True
    )

    help_text = models.CharField(
        verbose_name=_("Help text"),
        max_length=512,
        blank=True
    )

    required = models.BooleanField(
        verbose_name=_("Required"),
        default=True
    )

    related_through_content_type = models.ForeignKey(
        'contenttypes.ContentType',
        verbose_name=_("Content type of related model"),
        related_name='form_builder_through_fields',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _('Form Builder Extra Field')
        verbose_name_plural = _('Form Builder Extra Fields')

    def __str__(self):
        return '{} {}'.format(str(self.builder), self.name)


class Form(UUIDModel):

    company = models.ForeignKey(
        'core.Company',
        verbose_name=_("Company"),
        related_name='forms',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    builder = models.ForeignKey(
        FormBuilder,
        verbose_name=_("Form builder"),
        related_name='forms',
        on_delete=models.CASCADE,
    )

    is_active = models.BooleanField(
        verbose_name=_("Is active"),
        default=True
    )

    active_language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Active Language"),
        related_name="forms",
        default='en',
        on_delete=models.PROTECT)

    class Meta:
        unique_together = (
            ('company', 'builder'),
        )
        verbose_name = _("Form")
        verbose_name_plural = _("Forms")

    @property
    def title(self):
        """ Form title getter """
        return self.translations.filter(language=self.active_language).first().title

    @property
    def short_description(self):
        """ Form short_description getter """
        return self.translations.filter(language=self.active_language).first().short_description

    @property
    def save_button_text(self):
        """ Form button_text getter """
        return self.translations.filter(language=self.active_language).first().button_text

    @property
    def submit_message(self):
        """ Form result_messages getter """
        return self.translations.filter(language=self.active_language).first().result_messages

    def clean(self):
        super(Form, self).clean()
        if self.company_id is None and Form.objects.exclude(id=self.id).filter(
                builder=self.builder).exists():
            raise ValidationError({
                'builder': _("Default form for this builder already exists")
            })

    def __str__(self):
        return str(self.builder)

    def get_company_links(self, contact):
        """
        Get form links for contact.

        :param contact: Contact
        :return:
        """
        companies = get_master_companies_by_contact(contact)
        result_list = []
        if not companies:
            companies = [self.company or get_default_company()]
        for company in companies:
            result_list.append({
                'company': company.name,
                'url': reverse('form-builder-view', kwargs={'company': str(company.id), 'pk': str(self.pk)})
            })
        return result_list

    def _is_candidate_bank_account(self, model_class, field_name):
        from r3sourcer.apps.candidate.models import CandidateContact

        return 'contact__bank_accounts' in field_name and model_class == CandidateContact

    def _is_formality(self, model_class, field_name):
        from r3sourcer.apps.candidate.models import CandidateContact

        return 'formalities' in field_name and model_class == CandidateContact

    def is_valid_model_field_name(self, field_name: str) -> bool:
        """
        Checking model field name for attached content type model.
        We have two type names:
            - base name (first_name, etc.)
            - lookup name (contact__first_name, etc.)

        :param field_name: str Field name
        :return: bool
        """
        model_class = self.content_type.model_class()
        fields = field_name.split(StorageHelper.LOOKUP_SEPARATOR)
        count = len(fields)

        if self._is_candidate_bank_account(model_class, field_name):
            return True
        # if self._is_formality(model_class, field_name):
        #     return True

        for index, _field_name in enumerate(fields):
            if index != count - 1:
                try:
                    model_class = model_class._meta.get_field(
                        _field_name
                    ).related_model
                except models.FieldDoesNotExist:
                    return False
            else:
                try:
                    model_class._meta.get_field(_field_name)
                except models.FieldDoesNotExist:
                    return False
        return True

    def get_fieldsets(self) -> list:
        """
        Return forms as grouped fields.
        :return: list of dict Form instances with titles.
        """
        grouped_forms = []
        for group in FormFieldGroup.objects.filter(form=self):
            group_data = {
                'name': group.name,
                'fields': OrderedDict()
            }
            fields_qs = FormField.inheritance_objects.filter(group_id=group.id) \
                .exclude(name__startswith='contact__bank_accounts') \
                .exclude(name__startswith='formalities')
            for field in fields_qs.select_subclasses():
                group_data['fields'].setdefault(field.name, field.get_form_field())
            group_data['form_cls'] = type('BuilderForm', (forms.Form,), group_data['fields'].copy())

            if group_data['fields']:
                grouped_forms.append(group_data)

        return grouped_forms

    def get_ui_config(self) -> str:
        """
        Return json text with UI-config data for all form fields.

        :return: str
        """
        fields = []
        for group in self.groups.all():
            fields.append(group.get_ui_config())
            for field in group.fields.select_subclasses():
                fields.append(field.get_ui_config())
        return fields

    def get_form_class(self) -> type:
        """
        Generate and return Form class with all fields from all named groups.

        :return: Form class
        """
        fieldsets = self.get_fieldsets()
        form_fields = {}
        for fieldset in fieldsets:
            form_fields.update(fieldset['fields'].copy())

        return type('BuilderForm', (forms.Form,), form_fields)

    def get_url_for_company(self, company):
        return reverse('form-builder-view', kwargs={'pk': str(self.pk), 'company': company.pk})

    @cached_property
    def content_type(self) -> ContentType:
        return self.builder.content_type

    @classmethod
    def parse_data_to_storage(cls, data):
        """
        Parse and return data.

        :param form: Form instance
        :param data: dict Cleaned data from django.forms.Form.
        :return: dict
        """
        parsed_data = {}
        for (key, value) in data.items():
            if isinstance(value, models.Model):
                value = str(value.code2 if isinstance(value, Country) else value.id)
            elif not isinstance(value, (File)):
                value = value if isinstance(value, bool) or value is None else str(value)
            parsed_data.setdefault(key, value)
        return parsed_data

    def get_data(self, data):
        """
        Would be used for cleaning string values from dict.

        :return: dict Validated data from self.data field.
        """
        form_cls = self.get_form_class()   # type: forms.Form
        data_storage = {}
        errors = {}
        for name, data in data.items():
            try:
                if name not in form_cls.base_fields:
                    data_storage.setdefault(name, data)
                elif isinstance(form_cls.base_fields[name], forms.FileField):
                    data_storage.setdefault(name, data)
                else:
                    data_storage.setdefault(name, form_cls.base_fields[name].clean(data))
            except ValidationError as e:
                errors[name.replace('__', '.')] = e.messages

        return data_storage, errors

    @classmethod
    def parse_api_data(cls, data, parent=None, form=None):
        form_fields = {}
        if form:
            fieldsets = form.get_fieldsets()
            for fieldset in fieldsets:
                form_fields.update(fieldset['fields'].copy())

        parsed_data = {}
        errors = {}

        if 'street_address' in data:
            value = data['street_address']

            if isinstance(value, dict):
                data.update(parse_google_address(value))
                country = Country.objects.get(id=data['country'])
                data['country'] = country.code2

        for field, value in data.items():
            field_name = '%s__%s' % (parent, field) if parent else field

            if isinstance(value, dict):
                parsed_data.update(cls.parse_api_data(value, parent=field_name, form=form))
            else:
                if '__id' in field_name and parent:
                    try:
                        obj = form_fields[parent].queryset.get(id=value) if parent in form_fields else value
                        if not isinstance(obj, str):
                            parsed_data[parent] = obj.code2 if isinstance(obj, Country) else obj.id
                        else:
                            parsed_data[parent] = value
                    except Exception:
                        if form_fields[parent] and form_fields[parent].required:
                            errors[field_name] = _('This field is required.')
                elif value:
                    parsed_data[field_name] = value

        if errors:
            raise ValidationError(errors)

        return parsed_data

    @classmethod
    def parse_api_files(cls, data, parent=None):
        from r3sourcer.apps.core.api.fields import ApiBase64FileField

        parsed_data = {}
        for field, value in data.items():
            field_name = '%s__%s' % (parent, field) if parent else field

            if isinstance(value, dict):
                parsed_data.update(cls.parse_api_files(value, parent=field_name))
            else:
                if isinstance(value, str) and ';base64,' in value:
                    value = ApiBase64FileField().to_internal_value(value)

                parsed_data[field_name] = value

        return parsed_data

    def save(self, *args, **kwargs):
        just_added = self._state.adding

        super().save(*args, **kwargs)

        if just_added:
            builder = self.builder
            group = FormFieldGroup.objects.create(form=self, name='default')

            model_fields = ModelFormField.get_model_fields(
                builder.content_type.model_class(),
                builder=builder
            )
            model_fields = ModelFormField.flatten_model_fields_config(
                model_fields)

            for order, active_field in enumerate(builder.active_fields):
                if active_field not in builder.fields:
                    continue

                ModelFormField.objects.create(
                    group=group,
                    label=model_fields[active_field]['label'],
                    name=active_field,
                    position=order,
                    required=model_fields[active_field]['required'],
                    help_text=model_fields[active_field]['help_text'],
                )


class FormFieldGroup(UUIDModel):
    """
    Named groups for form fields.
    """
    form = models.ForeignKey(
        Form,
        verbose_name=_("Form"),
        related_name='groups',
        on_delete=models.CASCADE,
    )

    name = models.CharField(
        verbose_name=_("Group name"),
        max_length=512,
        default=''
    )

    position = models.PositiveIntegerField(
        verbose_name=_("Position"),
        default=0
    )

    def get_ui_config(self):
        return {
            'type': 'header',
            'subtype': 'h3',
            'label': self.name
        }

    def __str__(self):
        return '{name} ({form})'.format(
            form=self.form,
            name=self.name
        )

    class Meta:
        ordering = ['position']
        verbose_name = _("Form fields group")
        verbose_name_plural = _("Form fields groups")


class FormField(PolymorphicModel):
    """
    Base polymorphic form field, would be used for inheritance.
    """
    input_type = None
    extended_fields = ()

    group = models.ForeignKey(
        FormFieldGroup,
        verbose_name=_("Form group"),
        related_name='fields',
        on_delete=models.CASCADE,
    )

    name = models.SlugField(
        verbose_name=_("Name"),
        default=''
    )

    label = models.CharField(
        verbose_name=_("Label"),
        default='',
        max_length=512,
        blank=True
    )

    placeholder = models.CharField(
        verbose_name=_("Placeholder"),
        default='',
        max_length=512,
        blank=True
    )

    class_name = models.CharField(
        verbose_name=_("Class name"),
        max_length=64,
        default='form-control',
        blank=True
    )

    required = models.BooleanField(
        verbose_name=_("Required"),
        default=True
    )

    position = models.PositiveIntegerField(
        verbose_name=_("Position"),
        default=0
    )

    help_text = models.CharField(
        verbose_name=_("Help text"),
        max_length=512,
        default='',
        blank=True
    )

    regex = models.CharField(
        verbose_name=_("Regex Pattern"),
        default='',
        max_length=255,
        blank=True
    )

    inheritance_objects = InheritanceManager()

    class Meta:
        ordering = ('position',)

    def get_ui_config(self):
        return {
            'key': self.name,
            'type': 'input',
            'templateOptions': {
                'placeholder': self.placeholder,
                'description': self.help_text,
                'required': self.required,
                'label': self.label,
                'type': self.input_type,
                'regex': self.regex,
            }
        }

    def get_form_field(self):
        raise NotImplementedError

    def get_field_type(self):
        return type(self).__name__.lower().replace('form', '')

    @classmethod
    def get_serializer_fields(cls):
        return (
                   'id', 'group', 'name', 'label', 'placeholder', 'class_name',
                   'required', 'position', 'help_text', 'regex'
               ) + cls.extended_fields

    def __str__(self):
        return self.name


class ModelFormField(FormField):

    exclude_fields = [
        'id', 'pk', 'updated_at', 'created_at'
    ]

    MAX_RELATED_LEVEL = 2

    @classmethod
    def get_model_fields(cls, model, lookup='', level=0, builder=None):
        """
        Return list of model fields.

        :param model: models.Model subclass
        :param lookup: str Lookup field name, would be used as prefix in names.
        :param level: int Dept level

        :return: list of dict, which contains information about each field.
        """
        for field in model._meta.fields:

            exclude_fields = cls.exclude_fields
            if hasattr(model, 'EXCLUDE_INPUT_FIELDS'):
                exclude_fields.extend(model.EXCLUDE_INPUT_FIELDS)

            if field.name in cls.exclude_fields or not field.editable:
                continue
            in_builder_fields = field.name + '__id' in builder.fields
            if isinstance(field, models.ForeignObject) and level < cls.MAX_RELATED_LEVEL and not in_builder_fields:
                field_name = field.name
                if lookup:
                    field_name = StorageHelper.join_lookup_names(lookup, field.name)
                fields = list(cls.get_model_fields(
                    field.related_model,
                    lookup=field_name,
                    level=level+1,
                    builder=builder
                ))
                if len(fields) > 0:
                    yield {
                        'model_fields': fields,
                        'name': field_name,
                        'required': not field.blank,
                        'help_text': field.help_text,
                        'label': field.verbose_name
                    }
            else:
                field_name = field.name
                if lookup:
                    field_name = StorageHelper.join_lookup_names(lookup, field.name)
                if field_name in builder.fields or lookup in builder.fields or field.name + '__id' in builder.fields:
                    required = not field.blank or field_name in builder.required_fields
                    yield {
                        'name': field_name,
                        'required': required,
                        'help_text': field.help_text,
                        'label': field.verbose_name
                    }

        from r3sourcer.apps.candidate.models import CandidateContact
        from r3sourcer.apps.core.models import BankAccountLayout

        if issubclass(model, CandidateContact) and 'contact__bank_accounts' in builder.fields:
            master_company = get_site_master_company()
            bank_layout = BankAccountLayout.objects.filter(
                countries__country=master_company.country
            ).order_by('-countries__default').first()

            if not bank_layout:
                return

            model_fields = []
            for field in bank_layout.fields.all().order_by('order'):
                label = field.field.translation(master_company.get_default_language())
                model_fields.append({
                    'name': 'contact__bank_accounts__' + field.field.name,
                    'required': field.required,
                    'help_text': field.field.description,
                    'label': label
                })

            yield {
                'model_fields': model_fields,
                'name': 'contact__bank_accounts',
                'required': False,
                'help_text': '',
                'label': 'Bank Account'
            }

        if issubclass(model, CandidateContact) and 'formalities' in builder.fields:
            country = get_site_master_company().country

            model_fields = []
            if country.display_tax_number:
                model_fields.append({
                    'name': 'formalities__tax_number',
                    'required': "False",
                    'label': country.tax_number_type,
                    "regex": country.tax_number_regex_validation_pattern
                })
            if country.display_personal_id:
                model_fields.append({
                    'name': 'formalities__personal_id',
                    'required': "False",
                    'label': country.personal_id_type,
                    "regex": country.personal_id_regex_validation_pattern
                })
            yield {
                'model_fields': model_fields,
                'name': 'formalities',
                'required': False,
                'type': 'input',
                'help_text': '',
                'label': 'Formalities'
            }

    @classmethod
    def flatten_model_fields_config(cls, model_fields):
        fields = {}
        for model_field in model_fields:
            if 'model_fields' in model_field:
                fields.update(cls.flatten_model_fields_config(
                    model_field['model_fields']))
            else:
                fields[model_field['name']] = model_field

        return fields

    def _get_bank_account_field(self):
        return {
            'key': self.name.replace('__', '.'),
            'type': 'input',
            'templateOptions': {
                'description': self.help_text,
                'placeholder': self.placeholder,
                'required': self.required,
                'label': self.label,
                'type': 'text'
            }
        }

    def _get_formality_field(self):
        return {
            'key': self.name.replace('__', '.'),
            'type': 'input',
            'templateOptions': {
                'description': self.help_text,
                'placeholder': self.placeholder,
                'required': self.required,
                'label': self.label,
                'regex': self.regex,
                'type': 'input'
            }
        }

    def get_form_field(self) -> forms.Field:
        """
        Return form field from model meta options.
        :return: forms.Field object
        """
        content_type = self.group.form.content_type
        model_class, field_name = StorageHelper.get_field_from_lookup_name(content_type.model_class(), self.name)
        form_field = model_class._meta.get_field(field_name).formfield()
        form_field.required = self.required
        form_field.name = self.name
        return form_field

    def get_ui_config(self) -> dict:
        """
        Returns ui config for rendering on frontend part.

        :return: dict
        """
        if 'contact__bank_accounts' in self.name:
            return self._get_bank_account_field()

        if 'formalities' in self.name:
            return self._get_formality_field()

        ui_all_config = super(ModelFormField, self).get_ui_config()
        ui_config = ui_all_config.get('templateOptions', {})
        form_field = self.get_form_field()

        if not ui_config['description']:
            ui_config['description'] = str(form_field.help_text)

        if not ui_config['label']:
            ui_config['label'] = str(form_field.label)

        if not ui_config['placeholder']:
            ui_config['placeholder'] = str(
                form_field.widget.attrs.get('placeholder', ''))

        if isinstance(form_field, forms.CharField):
            if form_field.widget and isinstance(form_field, forms.PasswordInput):
                ui_config['type'] = 'password'
            else:
                ui_config['type'] = 'text'

            if isinstance(form_field.widget, forms.Textarea):
                ui_all_config['type'] = 'textarea'
        if isinstance(form_field, (forms.FloatField, forms.IntegerField, forms.DecimalField)):
            ui_config['type'] = 'number'
        elif isinstance(form_field, (forms.FileField, forms.ImageField)):
            ui_config['type'] = 'picture'
            ui_config['file'] = not isinstance(form_field, forms.ImageField)
        elif isinstance(form_field, forms.DateField):
            ui_all_config['type'] = 'datepicker'
            ui_config['type'] = 'date'
        elif isinstance(form_field, forms.DateTimeField):
            ui_all_config['type'] = 'datepicker'
            ui_config['type'] = 'datetime'
        elif isinstance(form_field, (forms.BooleanField, forms.NullBooleanField)):
            ui_all_config['type'] = 'checkbox'
        elif isinstance(form_field, (
            forms.ModelChoiceField, forms.ModelMultipleChoiceField, forms.ChoiceField, forms.MultipleChoiceField
        )):
            if isinstance(form_field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)):
                inflector = Inflector(import_string(settings.INFLECTOR_LANGUAGE))
                model = form_field.queryset.model
                try:
                    ui_all_config.update({
                        'type': 'related',
                        'endpoint': api_reverse('{}/{}'.format(
                            model._meta.app_label.lower(), inflector.pluralize(model.__name__.lower())
                        )),
                    })
                    ui_config['type'] = 'related'
                except url_exceptions.NoReverseMatch:
                    ui_all_config['type'] = 'select'
                    ui_config['type'] = 'select'
            else:
                ui_all_config['type'] = 'select'
                ui_config.update({
                    'type': 'select',
                    'options': [{'value': str(value), 'label': str(label)} for value, label in form_field.choices]
                })
            if isinstance(form_field, (forms.ModelMultipleChoiceField, forms.MultipleChoiceField)):
                ui_config['multiple'] = True
        # change Street Address field type to address
        if ui_config['label'] == 'Street Address':
            ui_all_config['type'] = 'address'

        ui_all_config['templateOptions'] = ui_config
        ui_all_config['key'] = ui_all_config['key'].replace('__', '.')
        return ui_all_config

    def clean(self):
        """
        Overridden clean method for validation lookup fields in admin.
        """
        super(ModelFormField, self).clean()
        if not self.group.form.is_valid_model_field_name(self.name):
            raise ValidationError({
                'name': _("Incorrect field name for model")
            })

    class Meta:
        verbose_name = _("Model field")
        verbose_name_plural = _("Model fields")


class SelectFormField(FormField):
    input_type = 'select'

    extended_fields = ('is_multiple', 'choices')

    is_multiple = models.BooleanField(
        verbose_name=_(" Allow Multiple Selections"),
        default=False
    )

    choices = JSONField(
        verbose_name=_("Choices"),
        default=[]
    )

    def get_ui_config(self):
        ui_config = super(SelectFormField, self).get_ui_config()
        ui_config['templateOptions'].update(**{
            'multiple': self.is_multiple,
            'options': self.choices
        })
        return ui_config

    def get_form_field(self):
        if self.is_multiple:
            field = forms.MultipleChoiceField
        else:
            field = forms.ChoiceField
        return field(
            required=self.required,
            choices=transform_ui_choices(self.choices)
        )

    class Meta:
        verbose_name = _("Select field")
        verbose_name_plural = _("Select fields")


class DateFormField(FormField):
    input_type = 'date'

    def get_form_field(self):
        return forms.DateField(
            required=self.required
        )

    class Meta:
        verbose_name = _("Date field")
        verbose_name_plural = _("Date fields")


class CheckBoxFormField(FormField):
    input_type = 'checkbox'

    def get_form_field(self):
        return forms.BooleanField(
            required=self.required
        )

    class Meta:
        verbose_name = _("Checkbox field")
        verbose_name_plural = _("Checkbox fields")


class RadioButtonsFormField(FormField):
    input_type = 'radio-group'
    extended_fields = ('choices',)

    choices = JSONField(
        verbose_name=_("choices"),
        default=[]
    )

    def get_ui_config(self):
        ui_config = super(RadioButtonsFormField, self).get_ui_config()
        ui_config['templateOptions'].update(**{
            'options': self.choices
        })
        return ui_config

    def get_form_field(self):
        return forms.ChoiceField(
            required=self.required,
            choices=transform_ui_choices(self.choices),
            widget=forms.RadioSelect()
        )

    class Meta:
        verbose_name = _("Radio button field")
        verbose_name_plural = _("Radio button fields")


class FileFormField(FormField):
    input_type = 'file'

    def get_form_field(self):
        return forms.FileField(
            required=self.required
        )

    class Meta:
        verbose_name = _("File field")
        verbose_name_plural = _("File fields")


class ImageFormField(FormField):
    input_type = 'file'

    def get_form_field(self):
        return forms.ImageField(
            required=self.required
        )

    class Meta:
        verbose_name = _("Image field")
        verbose_name_plural = _("Image fields")


class NumberFormField(FormField):
    input_type = 'number'
    extended_fields = ('min_value', 'max_value', 'step')

    min_value = models.FloatField(
        verbose_name=_("Min value"),
        default=None,
        null=True
    )

    max_value = models.FloatField(
        verbose_name=_("Max value"),
        default=None,
        null=True,
    )

    step = models.FloatField(
        verbose_name=_("Step"),
        default=1
    )

    def get_ui_config(self):
        ui_config = super(NumberFormField, self).get_ui_config()
        ui_config['templateOptions'].update(**{
            'min': self.min_value,
            'max': self.max_value,
            'step': self.step
        })
        return ui_config

    def get_form_field(self):
        return forms.FloatField(
            required=self.required,
            min_value=self.min_value,
            max_value=self.max_value
        )

    class Meta:
        verbose_name = _("Number field")
        verbose_name_plural = _("Number fields")


class TextFormField(FormField):
    input_type = 'text'
    extended_fields = ('subtype', 'max_length')

    SUBTYPE_CHOICES = Choices(
        ('text', 'TEXT', _("Text")),
        ('password', 'PASSWORD', _("Password")),
        ('email', 'EMAIL', _("Email")),
        ('tel', 'PHONE', _("Phone"))
    )

    max_length = models.PositiveIntegerField(
        verbose_name=_("Max length"),
        null=True,
        default=None
    )

    subtype = models.CharField(
        verbose_name=_("Subtype"),
        max_length=16,
        default=SUBTYPE_CHOICES.TEXT,
        choices=SUBTYPE_CHOICES
    )

    def get_ui_config(self):
        ui_config = super(TextFormField, self).get_ui_config()
        if self.max_length:
            ui_config['templateOptions'].setdefault('maxLength', self.max_length)
        ui_config['templateOptions']['type'] = self.subtype
        return ui_config

    def get_form_field(self):
        form_kwargs = {
            'required': self.required,
            'max_length': self.max_length
        }
        if self.subtype == self.SUBTYPE_CHOICES.PHONE:
            field = forms.CharField(**form_kwargs)
        elif self.subtype == self.SUBTYPE_CHOICES.PASSWORD:
            field = forms.CharField(widget=forms.PasswordInput(), **form_kwargs)
        elif self.subtype == self.SUBTYPE_CHOICES.EMAIL:
            field = forms.EmailField(**form_kwargs)
        else:
            field = forms.CharField(**form_kwargs)
        return field

    class Meta:
        verbose_name = _("Text field")
        verbose_name_plural = _("Text field")


class TextAreaFormField(FormField):
    input_type = 'textarea'
    extended_fields = ('rows', 'max_length')

    max_length = models.PositiveIntegerField(
        verbose_name=_("Max length")
    )

    rows = models.PositiveIntegerField(
        verbose_name=_("Rows")
    )

    def get_ui_config(self):
        ui_config = super(TextAreaFormField, self).get_ui_config()
        ui_config['templateOptions'].update(**{
            'maxLength': self.max_length,
            'rows': self.rows
        })
        return ui_config

    def get_form_field(self):
        return forms.CharField(
            required=self.required,
            max_length=self.max_length,
            widget=forms.Textarea()
        )

    class Meta:
        verbose_name = _("TextArea field")
        verbose_name_plural = _("TextArea field")


class RelatedFormField(FormField):
    input_type = 'related'

    extended_fields = ('is_multiple', 'content_type')

    is_multiple = models.BooleanField(
        verbose_name=_("Allow Multiple Selections"),
        default=False
    )

    content_type = models.ForeignKey(
        'contenttypes.ContentType',
        verbose_name=_("Content type for field"),
        on_delete=models.CASCADE,
    )

    def get_ui_config(self):
        inflector = Inflector(import_string(settings.INFLECTOR_LANGUAGE))

        return {
            'key': self.name,
            'type': 'related',
            'endpoint': api_reverse('{}/{}'.format(
                self.content_type.app_label.lower(), inflector.pluralize(self.content_type.model.lower())
            )),
            'templateOptions': {
                'placeholder': self.placeholder,
                'description': self.help_text,
                'required': self.required,
                'label': self.label,
                'type': self.input_type,
                'multiple': self.is_multiple,
            }
        }

    def get_form_field(self):
        return

    class Meta:
        verbose_name = _("Related field")
        verbose_name_plural = _("Related fields")

class FormLanguage(UUIDModel):
    form = models.ForeignKey(
        Form,
        on_delete=models.PROTECT,
        verbose_name=_('Form'),
        related_name='translations'
    )
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Form language"),
        on_delete=models.CASCADE,
        default='en',
        related_name='formlanguages',
    )
    title = models.CharField(max_length=64, verbose_name=_("Form Title"), default="Application Form")
    short_description = models.CharField(max_length=255, verbose_name=_("Form Short Description"), default="New application form")
    button_text = models.CharField(max_length=32, verbose_name=_("Form Button Text"), default="Save")
    result_messages = models.CharField(max_length=255, verbose_name=_("Form Result Message"), default="Your form has been saved")

    class Meta:
        verbose_name = _("Form translations")
        unique_together = [
            'form',
            'language',
        ]

    def __str__(self):
        return str(self.language)
