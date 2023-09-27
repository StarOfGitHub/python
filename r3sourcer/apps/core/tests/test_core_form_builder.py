import datetime
import pytest
from django import forms

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError
from filer.models import Folder

from r3sourcer.apps.core import models


@pytest.mark.django_db
class TestFormFields:

    @pytest.fixture
    def form_builder(self):
        return models.FormBuilder.objects.create(
            content_type=ContentType.objects.get_for_model(models.Contact),

        )

    @pytest.fixture
    def form(self, company, form_builder):
        return models.Form.objects.create(
            title='test form1',
            builder=form_builder,
            is_active=True,
            company=company
        )

    @pytest.fixture
    def form_field_group(self, form):
        return models.FormFieldGroup.objects.create(
            form=form,
            name='General'
        )

    @pytest.fixture
    def form_fields(self, form_field_group):
        return [
            models.ModelFormField.objects.create(group=form_field_group, name='phone_mobile', required=True),
            models.ModelFormField.objects.create(group=form_field_group, name='email'),
            models.ModelFormField.objects.create(group=form_field_group, name='first_name', required=True)
        ]

    @pytest.fixture
    def form_fields_with_file(self, form_field_group, form_fields):
        return form_fields + [
            models.FormField.objects.create(group=form_field_group, name='picture', required=False)
        ]

    @pytest.fixture
    def form_fields_with_foreignkey(self, form_field_group, form_fields):
        return form_fields + [
            models.FormField.objects.create(group=form_field_group, name='address', required=False)
        ]

    @pytest.fixture
    def text_file(self, faker):
        return ContentFile(b'test text', faker.file_name(extension='txt'))

    @pytest.fixture
    def folder(self):
        return Folder.objects.create(name='test folder')

    def test_model_field(self, form_field_group):
        model_field = models.ModelFormField.objects.create(
            group=form_field_group,
            name='email',
            required=True,
            placeholder='test field name',
            class_name='input-field'
        )

        ui_all_config = model_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {'type', 'description', 'placeholder', 'label', 'required'}
        assert ui_config['required'] is True
        assert ui_all_config['key'] == model_field.name
        assert ui_config['placeholder'] == 'test field name'

        form_field = model_field.get_form_field()

        assert isinstance(form_field, forms.EmailField)

        with pytest.raises(ValidationError):
            form_field.clean('invalid_email')

        assert form_field.clean('test@example.com')

    def test_number_field(self, form_field_group):
        number_field = models.NumberFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field',
            min_value=0,
            max_value=10,
        )

        ui_all_config = number_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'label',
            'required',
            'min',
            'max',
            'description',
            'step'
        }
        assert ui_config['required'] is True
        assert ui_all_config['key'] == number_field.name
        assert ui_config['placeholder'] == 'test field name'
        assert ui_config['min'] == 0
        assert ui_config['max'] == 10

        form_field = number_field.get_form_field()

        assert isinstance(form_field, forms.FloatField)

        with pytest.raises(ValidationError):
            form_field.clean('invalid_number')
            form_field.clean('100')

        assert form_field.clean('9')
        assert form_field.clean('9.0')

    def test_email_field(self, form_field_group):
        email_field = models.TextFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field',
            subtype=models.TextFormField.SUBTYPE_CHOICES.EMAIL
        )

        ui_all_config = email_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'label',
            'description',
            'required',
        }
        assert ui_config['required'] is True
        assert ui_all_config['key'] == email_field.name
        assert ui_config['placeholder'] == 'test field name'
        assert ui_config['type'] == models.TextFormField.SUBTYPE_CHOICES.EMAIL

        form_field = email_field.get_form_field()

        assert isinstance(form_field, forms.EmailField)

        with pytest.raises(ValidationError):
            form_field.clean('invalid_email')

        assert form_field.clean('test@example.com')

    def test_date_field(self, form_field_group):
        date_field = models.DateFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field'
        )

        ui_all_config = date_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'label',
            'required',
            'description',
        }
        assert ui_config['required'] is True
        assert ui_all_config['key'] == date_field.name
        assert ui_config['placeholder'] == 'test field name'

        form_field = date_field.get_form_field()

        assert isinstance(form_field, forms.DateField)

        with pytest.raises(ValidationError):
            form_field.clean('invalid_date')

        assert form_field.clean('11/09/2017')

    def test_checkbox_field(self, form_field_group):
        checkbox_field = models.CheckBoxFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field'
        )

        ui_all_config = checkbox_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'description',
            'label',
            'required',
        }
        assert ui_all_config['key'] == checkbox_field.name
        assert ui_config['required'] is True
        assert ui_config['placeholder'] == 'test field name'

        form_field = checkbox_field.get_form_field()

        assert isinstance(form_field, forms.BooleanField)

        with pytest.raises(ValidationError):
            form_field.clean('False')
            form_field.clean('0')

        assert form_field.clean('True')

    def test_select_field(self, form_field_group):
        choices = [
            {'value': '1', 'label': 'test1'},
            {'value': '2', 'label': 'test2'},
            {'value': '3', 'label': 'test3'}
        ]
        choice_field = models.SelectFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field',
            choices=choices
        )

        ui_all_config = choice_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'description',
            'multiple',
            'label',
            'required',
            'options'
        }
        assert ui_config['required'] is True
        assert ui_config['multiple'] is False
        assert ui_all_config['key'] == choice_field.name
        assert ui_config['placeholder'] == 'test field name'
        assert len(ui_config['options']) == 3
        assert set([i['value'] for i in ui_config['options']]) == {'1', '2', '3'}
        assert set([i['label'] for i in ui_config['options']]) == {'test1', 'test2', 'test3'}

        form_field = choice_field.get_form_field()

        assert isinstance(form_field, forms.ChoiceField)

        with pytest.raises(ValidationError):
            form_field.clean('10')
            form_field.clean('invalid choice value')

        assert form_field.clean('1')
        assert form_field.clean('2')
        assert form_field.clean('3')

    def test_multiple_choice_field(self, form_field_group):
        choices = [
            {'value': '1', 'label': 'test1'},
            {'value': '2', 'label': 'test2'},
            {'value': '3', 'label': 'test3'}
        ]
        choice_field = models.SelectFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field',
            choices=choices,
            is_multiple=True
        )

        ui_all_config = choice_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'description',
            'multiple',
            'label',
            'required',
            'options'
        }
        assert ui_config['required'] is True
        assert ui_config['multiple'] is True
        assert ui_all_config['key'] == choice_field.name
        assert ui_config['placeholder'] == 'test field name'
        assert len(ui_config['options']) == 3
        assert set([i['value'] for i in ui_config['options']]) == {'1', '2', '3'}
        assert set([i['label'] for i in ui_config['options']]) == {'test1', 'test2', 'test3'}

        form_field = choice_field.get_form_field()

        assert isinstance(form_field, forms.MultipleChoiceField)

        with pytest.raises(ValidationError):
            form_field.clean('invalid choice value')
            form_field.clean(['4', '5', '6'])
            form_field.clean([])

        assert form_field.clean([1, '2', 3])

    def test_file_field(self, form_field_group, picture):
        file_field = models.FileFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field'
        )

        ui_all_config = file_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'description',
            'label',
            'required',
        }
        assert ui_config['required'] is True
        assert ui_all_config['key'] == file_field.name
        assert ui_config['placeholder'] == 'test field name'

        form_field = file_field.get_form_field()

        assert isinstance(form_field, forms.FileField)

        with pytest.raises(ValidationError):
            form_field.clean('invalid choice value')

        assert form_field.clean(picture)

    def test_image_field(self, form_field_group, picture, text_file):
        file_field = models.ImageFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field'
        )

        ui_all_config = file_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'description',
            'label',
            'required',
        }
        assert ui_all_config['key'] == file_field.name
        assert ui_config['required'] is True
        assert ui_config['placeholder'] == 'test field name'

        form_field = file_field.get_form_field()

        assert isinstance(form_field, forms.FileField)

        with pytest.raises(ValidationError):
            form_field.clean('invalid choice value')
            form_field.clean(text_file)

        assert form_field.clean(picture)

    def test_text_field(self, form_field_group, picture):
        text_field = models.TextFormField.objects.create(
            group=form_field_group,
            name='test_field_name',
            required=True,
            placeholder='test field name',
            class_name='input-field',
            max_length=20
        )

        ui_all_config = text_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'type',
            'placeholder',
            'description',
            'label',
            'maxLength',
            'required',
        }
        assert ui_all_config['key'] == text_field.name
        assert ui_config['required'] is True
        assert ui_config['placeholder'] == 'test field name'
        assert ui_config['maxLength'] == text_field.max_length

        form_field = text_field.get_form_field()

        assert isinstance(form_field, forms.CharField)

        with pytest.raises(ValidationError):
            form_field.clean('')
            form_field.clean('*'*30)

        assert form_field.clean('test text')

    def test_form_class(self, form, form_field_group, form_fields):
        form_cls = form.get_form_class()
        form_instance = form_cls(data={
            'phone_mobile': '+77777777777', 'email': 'test@example.com', 'first_name': 'Test'
        })

        assert {'phone_mobile', 'email', 'first_name'} == set(form_instance.base_fields.keys())

    def test_model_foreignkey_field(self, form_field_group, addresses, folder):
        model_field = models.ModelFormField.objects.create(group=form_field_group, name='files', required=True)

        assert set(model_field.get_ui_config()['templateOptions'].keys()) == {
            'type',
            'placeholder',
            'description',
            'label',
            'required'
        }

        form_field = model_field.get_form_field()

        assert isinstance(form_field, forms.ModelChoiceField)

    def test_radio_buttons_field(self, form_field_group, addresses, folder):
        choices = [
            {'label': 'test label1', 'value': 'value1'},
            {'label': 'test label1', 'value': 'value2'},
            {'label': 'test label1', 'value': 'value3'},
            {'label': 'test label1', 'value': 'value4'},
        ]
        radio_field = models.RadioButtonsFormField.objects.create(
            group=form_field_group,
            name='custom_choices',
            choices=choices,
            class_name='',
            required=True
        )

        ui_all_config = radio_field.get_ui_config()
        ui_config = ui_all_config['templateOptions']

        assert set(ui_config.keys()) == {
            'placeholder', 'description', 'required', 'label', 'type', 'options'
        }
        assert ui_all_config['key'] == radio_field.name
        assert ui_config['required'] is True
        assert ui_config['placeholder'] == ''

        form_field = radio_field.get_form_field()

        assert isinstance(form_field, forms.ChoiceField)
        assert isinstance(form_field.widget, forms.RadioSelect)

        with pytest.raises(ValidationError):
            form_field.clean('invalid test1')
            form_field.clean(10)

        assert form_field.clean('value4') == 'value4'

    def test_model_field_validation_method(self, form_field_group):
        assert form_field_group.form.is_valid_model_field_name(
            'first_name')
        assert form_field_group.form.is_valid_model_field_name(
            'user__is_active')
        assert not form_field_group.form.is_valid_model_field_name(
            'user__test')
        assert not form_field_group.form.is_valid_model_field_name('test')

        form = models.Form.objects.create(
            title='test form1',
            builder=models.FormBuilder.objects.create(
                content_type=ContentType.objects.get_for_model(
                    models.CompanyContact
                ),
            ),
            is_active=True
        )
        assert form.is_valid_model_field_name('contact__user__is_staff')
        assert not form.is_valid_model_field_name('contact__user__is_staff1')

    def test_get_fieldsets_method(self, form: models.Form, form_fields):
        fieldsets = form.get_fieldsets()

        assert len(fieldsets) == form.groups.count()
        for index, group in enumerate(form.groups.all()):
            assert fieldsets[index]['name'] == group.name

    def test_get_form_class_in_form(self, form: models.Form, form_fields):
        form_cls = form.get_form_class()()

        assert isinstance(form_cls.fields, dict)

        for form_field in form_fields:
            assert form_field.name in form_cls.fields

    def test_lookup_model_form_field(self, form_field_group):
        model_field = models.ModelFormField.objects.create(
            group=form_field_group, name='user__is_active')

        form_field = model_field.get_form_field()
        lookup_form_field = models.User._meta.get_field('is_active').formfield()
        assert type(form_field) == type(lookup_form_field)

    def test_unique_company_form(self, company, form_builder):
        models.Form.objects.create(
            title='test form1',
            builder=form_builder,
            is_active=True,
            company=company
        )

        with pytest.raises(IntegrityError):
            models.Form.objects.create(
                title='test form2',
                builder=form_builder,
                is_active=True,
                company=company
            )

    def test_unique_default_company_form(self, form_builder):
        models.Form.objects.create(
            title='test form1',
            builder=form_builder,
            is_active=True
        )

        with pytest.raises(ValidationError):
            form = models.Form(
                title='test form2',
                builder=form_builder,
                is_active=True
            )
            form.clean()

    def test_get_data_method(self, form, form_field_group):
        date_value = '2017-09-11'
        data = {
            'first_name': 'test name',
            'birthday': date_value,
            'children': '5',
        }

        models.ModelFormField.objects.create(group=form_field_group, name='first_name', required=True),
        models.ModelFormField.objects.create(group=form_field_group, name='children', required=True),
        models.ModelFormField.objects.create(group=form_field_group, name='birthday', required=True)

        cleaned_data, errors = form.get_data(data)

        assert isinstance(cleaned_data['birthday'], datetime.date)
        assert cleaned_data['birthday'] == datetime.datetime.strptime(data['birthday'], '%Y-%m-%d').date()
        assert cleaned_data['children'] == int(data['children'])

    def test_get_url_for_company(self, form, company):
        url = form.get_url_for_company(company)
        assert str(company.pk) in url
        assert str(form.pk) in url
