from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from easy_select2 import Select2
from phonenumber_field.formfields import PhoneNumberField

from r3sourcer.apps.core.utils.utils import is_valid_email, \
    is_valid_phone_number
from . import models
from ...helpers.datetimes import utc_now


class CoreAdminAuthenticationForm(AdminAuthenticationForm):
    """
    A custom authentication form used in the admin app.
    """
    username = forms.CharField(
        max_length=254,
        widget=forms.TextInput(attrs={'autofocus': ''}),
        label=_('Email or Mobile Phone Number')
    )

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        country_code = self.cleaned_data.get('country_code')

        email_username = is_valid_email(username)
        mobile_phone_username = is_valid_phone_number(username, country_code)
        if email_username is False and mobile_phone_username is False:
            raise forms.ValidationError(
                self.error_messages['invalid_login'],
                code='invalid_login',
                params={'username': _('email or mobile phone number')},
            )

        if username and password:
            self.user_cache = authenticate(username=username, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': _('email or mobile phone number')},
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class ContactForm(forms.ModelForm):

    phone_mobile = PhoneNumberField()

    def clean_phone_mobile(self):
        phone_number = self.cleaned_data.get('phone_mobile')
        return str(phone_number)

    class Meta:
        model = models.Contact
        fields = '__all__'


def get_year_choices():
    """
    Return year choices
    """
    year = utc_now().year
    year_from = year - 1
    year_to = year + 10
    return [(i, i) for i in range(year_from, year_to)]


def get_month_choices():
    """ Return month choices """
    default_items = [(None, '-----')]
    return default_items + [(i, i) for i in range(1, 13)]


class PublicHolidayFetchingForm(forms.Form):

    country = forms.ModelChoiceField(label=_("Country"), queryset=models.Country.objects.all(),
                                     widget=forms.Select(attrs={'class': 'dropdown-filter', 'data-width': 300}))
    year = forms.ChoiceField(label=_("Year"), choices=get_year_choices)
    month = forms.ChoiceField(label=_("Month"), required=False, choices=get_month_choices, initial=None)


class CompanyContactUserManagePermissions(forms.Form):

    user = forms.ModelChoiceField(
        queryset=models.User.objects.filter(contact__company_contact__isnull=False, is_active=True),
        widget=Select2(select2attrs={'width': 'auto'})
    )


class GroupManagePermissions(forms.Form):

    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        widget=Select2(select2attrs={'width': 'auto'})
    )


class FormBuilderAdminForm(forms.ModelForm):

    content_type = forms.ModelChoiceField(
        queryset=ContentType.objects.all(),
        widget=Select2(select2attrs={'width': 'auto'})
    )

    class Meta:
        model = models.FormBuilder
        fields = '__all__'


class ContentTypeChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, obj):
        model_class = obj.model_class()
        if model_class is None:
            model_name = str(obj)
        else:
            model_name = model_class._meta.verbose_name
        return '{app_label}: {model_name}'.format(
            app_label=obj.app_label,
            model_name=model_name
        )


class DashboardModuleForm(forms.ModelForm):

    content_type = ContentTypeChoiceField(
        queryset=ContentType.objects.all(), label=_("Model"),
        widget=Select2(select2attrs={'width': 'resolve'})
    )

    class Meta:
        model = models.DashboardModule
        fields = '__all__'
