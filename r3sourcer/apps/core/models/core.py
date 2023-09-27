import json
import math
import os
import uuid
from datetime import date, datetime, timedelta, time

import pytz
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, Group
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.validators import MinLengthValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum, F, ProtectedError
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import APIException

from cities_light.abstract_models import (
    AbstractCity, AbstractRegion, AbstractCountry
)
from cities_light.receivers import connect_default_signals
from djmoney.models.fields import CurrencyField
from djmoney.settings import CURRENCY_CHOICES
from easy_thumbnails.fields import ThumbnailerImageField
from filer.models import Folder
from model_utils import Choices
from mptt.models import MPTTModel, TreeForeignKey
from phonenumber_field.modelfields import PhoneNumberField

from r3sourcer.apps.core.utils.companies import get_site_master_company
from r3sourcer.apps.core.utils.user import get_default_company
from r3sourcer.helpers.datetimes import utc_now
from r3sourcer.helpers.models.abs import UUIDModel, TimeZoneUUIDModel
from .company_languages import CompanyLanguage
from ..decorators import workflow_function
from ..fields import ContactLookupField
from ..managers import (
    TagManager, AbstractCompanyContactOwnerManager, AbstractObjectOwnerManager
)
from ..mixins import (
    CompanyLookupMixin, MasterCompanyLookupMixin, CategoryFolderMixin, MYOBMixin, GenerateAuthTokenMixin
)
from ..service import factory
from ..utils.geo import fetch_geo_coord_by_address
from ..utils.validators import string_is_numeric
from ..workflow import WorkflowProcess

from .constants import MANAGER, CANDIDATE, CLIENT


# do anything you want
class Contact(CategoryFolderMixin,
              MYOBMixin,
              GenerateAuthTokenMixin,
              UUIDModel):

    EXCLUDE_INPUT_FIELDS = (
        'files',
    )

    MARITAL_STATUS_CHOICES = Choices(
        ('Single', _('Single')),
        ('Married', _('Married')),
        ('Divorced', _('Divorced')),
        ('Widow', _('Widow')),
    )

    TITLE_CHOICES = Choices(
        ('Mr.', _('Mr.')),
        ('Ms.', _('Ms.')),
        ('Mrs.', _('Mrs.')),
        ('Dr.', _('Dr.')),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name='contact',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    title = models.CharField(
        max_length=7,
        verbose_name=_("Title"),
        choices=TITLE_CHOICES,
        blank=True,
        null=True,
    )

    first_name = models.CharField(
        max_length=255,
        verbose_name=_("First Name"),
        blank=True
    )

    last_name = models.CharField(
        max_length=255,
        verbose_name=_("Last Name"),
        blank=True
    )

    email = models.EmailField(
        max_length=255,
        verbose_name=_("E-mail"),
        null=True,
        blank=True,
        unique=True,
    )

    phone_mobile = PhoneNumberField(
        verbose_name=_("Mobile Phone"),
        null=True,
        blank=True,
        unique=True,
    )

    new_email = models.EmailField(
        max_length=255,
        verbose_name=_("New E-mail"),
        null=True,
        blank=True,
    )

    new_phone_mobile = PhoneNumberField(
        verbose_name=_("New Mobile Phone"),
        null=True,
        blank=True,
    )

    gender = models.CharField(
        max_length=7,
        verbose_name=_("Gender"),
        null=True,
        blank=True,
        choices=(("male", _("Male")), ("female", _("Female")))
    )

    marital_status = models.CharField(
        max_length=15,
        verbose_name=_("Marital Status"),
        choices=MARITAL_STATUS_CHOICES,
        null=True,
        blank=True
    )

    birthday = models.DateField(verbose_name=_("Birthday"), blank=True, null=True)
    spouse_name = models.CharField(max_length=63, blank=True, verbose_name=_("Spouse/Partner name"))
    children = models.PositiveSmallIntegerField(verbose_name=_("Children"), blank=True, null=True)

    is_available = models.BooleanField(verbose_name=_("Available"), default=True)

    picture = ThumbnailerImageField(
        upload_to='contact_pictures',
        default=os.path.join('contact_pictures', 'default_picture.jpg'),
        max_length=255,
        blank=True
    )

    phone_mobile_verified = models.BooleanField(verbose_name=_("Mobile Phone Verified"), default=False)
    email_verified = models.BooleanField(verbose_name=_("E-mail Verified"), default=False)
    # registration_completed = models.BooleanField(verbose_name=_("Registration Completed"), default=True)

    address = models.ManyToManyField(
        'Address',
        verbose_name=_("Addresses"),
        related_name='contacts',
        through='ContactAddress',
        blank=True
    )

    files = models.ForeignKey(
        Folder,
        related_name='contacts',
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    sms_enabled = models.BooleanField(default=True)

    verification_token = models.CharField(max_length=64, default='')

    myob_card_id = models.CharField(max_length=15, blank=True)
    old_myob_card_id = models.CharField(max_length=15, blank=True, null=True, editable=False)

    class Meta:
        verbose_name = _("Contact")
        verbose_name_plural = _("Contacts")
        unique_together = ('first_name', 'last_name', 'email', 'phone_mobile')

    def __str__(self):
        name = '{} {}'.format(self.first_name, self.last_name)
        if self.title:
            name = '{} {}'.format(self.title, name)
        return name

    @property
    def active_contact_address(self):
        return self.contact_address.filter(is_active=True).first()

    @property
    def active_address(self):
        active_contact_address = self.active_contact_address
        return active_contact_address.address if active_contact_address else None

    def get_active_address(self):
        active_address = self.active_address
        if active_address:
            return {"id": active_address.id,
                    "country": str(active_address.country),
                    "state": str(active_address.state),
                    "city": str(active_address.city),
                    "street_address": active_address.street_address,
                    "postal_code": active_address.postal_code,
                    "__str__": active_address.__str__(),
                    }

    @property
    def notes(self):
        return Note.objects.filter(
            content_type__model=self.__class__.__name__,
            object_id=self.pk
        )

    def get_availability(self):
        unavailable = self.contact_unavailabilities.filter(
            unavailable_from__lte=date.today(),
            unavailable_until__gte=date.today()
        )
        if len(unavailable) > 0:
            return False
        return self.is_available
    get_availability.boolean = True

    def is_company_contact(self):
        return self.company_contact.filter(relationships__active=True,
                                           contact__user__is_active=True
                                           ).exists()
    is_company_contact.boolean = True

    def is_candidate_contact(self):
        return self.candidate_contacts.exists()

    def get_job_title(self):
        if self.company_contact.exists():
            for company_contact in self.company_contact.all():
                if company_contact.relationships.filter(company__type=Company.COMPANY_TYPES.master).exists():
                    return company_contact.job_title
            return self.company_contact.first().job_title

    def get_company_contact_by_company(self, company):
        if self.is_company_contact():
            for company_contact in self.company_contact.all():
                if company_contact.relationships.filter(company=company).exists():
                    return company_contact
        return None

    def is_master_related(self):
        if self.company_contact.exists():
            for company_contact in self.company_contact.all():
                if company_contact.relationships.filter(company__type=Company.COMPANY_TYPES.master).exists():
                    return True
        return False

    def get_role(self):
        if self.is_company_contact():
            is_manager = self.company_contact.filter(
                relationships__active=True, relationships__company__type=Company.COMPANY_TYPES.master
            ).exists()
            return MANAGER if is_manager else CLIENT
        elif self.is_candidate_contact():
            return CANDIDATE
        return None

    def get_role_id(self):
        if self.is_company_contact():
            company_contact = self.company_contact.filter(relationships__company=get_site_master_company()).first()
            if company_contact:
                return company_contact.id
            return self.company_contact.first().id
        elif self.is_candidate_contact():
            candidate = self.candidate_contacts.filter(candidate_rels__master_company=get_site_master_company()).first()
            return candidate.id
        return None

    def get_closest_company(self):
        return get_site_master_company() or get_default_company()

    def get_master_companies(self):
        from r3sourcer.apps.core.utils.companies import get_site_master_company

        if self.is_company_contact():
            master_company = self.company_contact.filter(relationships__active=True).first().get_master_company()
            if len(master_company) > 0:
                return [master_company[0].pk]
        elif self.is_candidate_contact():
            return self.candidate_contacts.candidate_rels.filter(active=True).values_list('master_company', flat=True)

        return get_site_master_company() or get_default_company()

    def process_sms_reply(self, sent_sms, reply_sms, positive):
        if positive:
            self.phone_mobile_verified = True
            self.save(update_fields=['phone_mobile_verified'])

    def process_new_phone_mobile_reply(self, positive):
        if positive:
            self.phone_mobile = self.new_phone_mobile
            self.new_phone_mobile = None
            self.phone_mobile_verified = True
            self.save(update_fields=['phone_mobile_verified', 'phone_mobile', 'new_phone_mobile'])

    def save(self, *args, **kwargs):
        is_adding = self._state.adding
        if not self.email and not self.phone_mobile:
            raise ValidationError(_('Contact must have email and/or mobile phone number.'))

        if not self.myob_card_id:
            self.myob_card_id = self.get_myob_card_number()

        if is_adding and self.user is None:
            user = User.objects.create(email=self.email, phone_mobile=self.phone_mobile)
            self.user = user

        if is_adding and self.is_company_contact() and self.is_master_related():
            from r3sourcer.apps.company_settings.models import GlobalPermission
            permission_list = GlobalPermission.objects.all()
            self.user.user_permissions.add(*permission_list)
            self.user.save()

        if not is_adding:
            origin = Contact.objects.get(pk=self.pk)
            if origin.myob_card_id != self.myob_card_id:
                self.old_myob_card_id = origin.myob_card_id
        super().save(*args, **kwargs)

        if not self.languages.filter(default=True).first():
            master_company = self.get_closest_company()
            default_language = master_company.languages.filter(default=True).first()
            if default_language:
                contact_language = ContactLanguage(
                    contact=self,
                    language_id=default_language.language_id,
                    default=True,
                )
                contact_language.save()

    def get_myob_card_number(self):
        if not self.myob_card_id:
            return str(self.id)[-15:]
        return self.myob_card_id

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                Q(candidate_contacts__candidate_rels__master_company=owner),
                Q(company_contact__relationships__company=owner),
                Q(company_contact__relationships__company__regular_companies__master_company=owner),
                Q(contact_relations__company=owner),
            ]


class ContactAddress(UUIDModel):

    contact = models.ForeignKey(
        'Contact',
        on_delete=models.CASCADE,
        related_name='contact_address',
        verbose_name=_("Contact")
    )
    address = models.ForeignKey(
        'Address',
        on_delete=models.CASCADE,
        related_name='contact_address',
        verbose_name=_("Address")
    )
    is_active = models.BooleanField(_("Active"), default=True)

    def __str__(self):
        return '{} {}'.format(self.contact.last_name, self.contact.first_name)

    class Meta:
        verbose_name = _("Contact Address")
        verbose_name_plural = _("Contact Addresses")

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('address__longitude'),
            latitude=F('address__latitude')
        ).values_list('longitude', 'latitude').get()


class ContactRelationship(UUIDModel):

    contact = models.ForeignKey(
        'core.Contact',
        related_name="contact_relations",
        verbose_name=_("Contact"),
        on_delete=models.CASCADE
    )

    company = models.ForeignKey(
        'core.Company',
        related_name="contact_relations",
        verbose_name=_("Company"),
        on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = _("Contact Relationship")
        verbose_name_plural = _("Contact Relationships")

    def __str__(self):
        return '{}'.format(str(self.contact))


class ContactUnavailability(UUIDModel):

    contact = models.ForeignKey(
        'core.Contact',
        related_name="contact_unavailabilities",
        verbose_name=_("Contact"),
        on_delete=models.CASCADE
    )

    unavailable_from = models.DateField(
        verbose_name=_("From"),
        null=True,
        blank=True
    )

    unavailable_until = models.DateField(
        verbose_name=_("Until"),
        null=True,
        blank=True
    )

    notes = models.TextField(
        verbose_name=_("Notes"),
        help_text=_("Unavailability Description"),
        blank=True
    )

    class Meta:
        verbose_name = _("Contact Unavailability")
        verbose_name_plural = _("Contact Unavailabilities")

    def __str__(self):
        return '{} {} - {}'.format(str(self.contact), self.unavailable_from, self.unavailable_until)


class UserManager(AbstractObjectOwnerManager, BaseUserManager):

    use_in_migrations = True

    def _create_user(self, password, **extra_fields):
        """
        Creates and saves a User and Contact
        """
        email = self.normalize_email(extra_fields.pop('email', '')) or None
        phone_mobile = extra_fields.pop('phone_mobile', None)
        if not email and not phone_mobile:
            raise ValueError('User must have email and/or mobile phone number.')

        obj = self.model(email=email, phone_mobile=phone_mobile, **extra_fields)
        obj.set_password(password)
        obj.save()

        # Lookup fields create contact object implicitly
        # in ContactLookupField.__get__
        obj.contact.save()
        return obj

    def create_user(self, password=None, **extra_fields):
        extra_fields['is_staff'] = False
        extra_fields['is_superuser'] = False

        return self._create_user(password, **extra_fields)

    def create_superuser(self, password, **extra_fields):
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True

        return self._create_user(password, **extra_fields)


class User(UUIDModel,
           AbstractBaseUser,
           PermissionsMixin):

    EXCLUDE_INPUT_FIELDS = (
        'last_login', 'date_joined', 'is_staff', 'is_superuser', 'is_active',
        'is_superuser', 'groups', 'permissions', 'password'
    )

    email = ContactLookupField(lookup_model=Contact)
    phone_mobile = ContactLookupField(lookup_model=Contact)
    username = ContactLookupField(lookup_model=Contact,
                                  lookup_name='email',
                                  read_only=True)

    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('date joined'))
    trial_period_start = models.DateTimeField(_('trial start'), null=True, blank=True)
    role = models.ManyToManyField('Role')

    USERNAME_FIELD = 'id'
    REQUIRED_FIELDS = ['email', 'phone_mobile']

    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def __str__(self):
        return str(self.contact) if hasattr(self, 'contact') else '-'

    def get_short_name(self):
        return str(self)

    def first_name(self):
        return self.contact.first_name

    def last_name(self):
        return self.contact.last_name

    def get_full_name(self):
        return '{} {}'.format(self.first_name(), self.last_name())
    get_full_name.short_description = _("Full name")

    def get_end_of_trial(self):
        if self.trial_period_start:
            end_of_trial = self.trial_period_start + timedelta(days=30)
            return end_of_trial.strftime("%Y-%m-%d %H:%M:%S")
        else:
            return {"user": "User have no trial period start date"}

    def get_end_of_trial_as_date(self):
        if self.trial_period_start:
            end_of_trial = self.trial_period_start + timedelta(days=30)
            return end_of_trial
        else:
            return None

    def clean(self):
        if self.is_superuser \
                and User.objects.filter(is_superuser=True).exists() \
                and not User.objects.filter(is_superuser=True, id=self.id).exists():
            contact = getattr(self, "contact")
            relation = CompanyContactRelationship.objects.filter(
                company=get_default_company(),
                company_contact__contact=contact
            ).exists()

            if contact and not relation:
                raise ValidationError(
                    _("Additional superuser could be created only for "
                      "contact employed to SYSTEM_MASTER_COMPANY"))
            else:
                self.is_superuser = False

    def is_candidate(self) -> bool:
        return self.contact.candidate_contacts.exists()

    def is_contact(self) -> bool:
        return hasattr(self, 'contact')

    def is_manager(self) -> bool:
        if self.role.filter(name=Role.ROLE_NAMES.manager).exists():
            return True
        return False

    def is_client(self) -> bool:
        if self.contact.company_contact.first():
            return self.contact.company_contact.first().role == CLIENT
        return False

    @property
    def access_level(self) -> str:
        if self.is_manager():
            return MANAGER
        elif self.is_client():
            return CLIENT
        elif self.is_candidate() or self.is_contact():
            return CANDIDATE
        raise ValidationError("Unknown user role")

    def has_permission(self, permission_codename) -> bool:
        from r3sourcer.apps.company_settings.models import GlobalPermission

        try:
            permission = GlobalPermission.objects.get(codename=permission_codename)
            return permission in self.user_permissions.all()
        except GlobalPermission.DoesNotExist:
            return False

    def has_group_permission(self, permission_codename) -> bool:
        from r3sourcer.apps.company_settings.models import GlobalPermission

        try:
            groups = self.groups.all()
            granted_permissions = GlobalPermission.objects.filter(group__in=groups)
            permission = GlobalPermission.objects.get(codename=permission_codename)
            return permission in granted_permissions
        except GlobalPermission.DoesNotExist:
            return False

    @property
    def company(self):
        return get_site_master_company()

    @property
    def company_files(self):
        company_file_tokens = self.company.company_file_tokens.all()
        return [x.company_file for x in company_file_tokens]

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                Q(contact__candidate_contacts__candidate_rels__master_company=owner),
                Q(contact__company_contact__relationships__company=owner),
                Q(contact__company_contact__relationships__company__regular_companies__master_company=owner),
                Q(contact__contact_relations__company=owner)
            ]

    def save(self, *args, **kwargs):
        if not self.date_joined:
            self.date_joined = utc_now()
        super().save(*args, **kwargs)

    def track_login(self):
        self.last_login = utc_now()
        self.save(update_fields=['last_login'])


class Country(UUIDModel, AbstractCountry):
    currency = CurrencyField(default='USD', choices=CURRENCY_CHOICES)
    country_timezone = models.CharField(blank=True, null=False, max_length=255, verbose_name='Country Timezone')

    #Tax Number Type and Personal ID Type fields
    display_tax_number = models.BooleanField(_('Display Tax Number'), default=False)
    tax_number_type = models.CharField(_('Tax number type'), max_length=64, blank=True)
    tax_number_regex_validation_pattern = models.CharField(_('Tax Number Regex Validation Pattern'),
                                                           max_length=64, blank=True)
    display_personal_id = models.BooleanField(_('Display Personal ID'), default=False)
    personal_id_type = models.CharField(_('Personal ID number type'), max_length=64, blank=True)
    personal_id_regex_validation_pattern = models.CharField(_('Personal ID Regex Validation Pattern'),
                                                            max_length=64, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = _("Country")
        verbose_name_plural = _("Countries")

    @classmethod
    def is_owned(cls):
        return False


class Region(UUIDModel,
             AbstractRegion):

    class Meta:
        verbose_name = _("State/District")
        verbose_name_plural = _("States/Districts")

    @classmethod
    def is_owned(cls):
        return False

    @classmethod
    def get_countrys_regions(cls, country_code):
        regions = cls.objects.filter(country__code2=country_code).distinct().values('id', 'name')
        return [{'label': r['name'], 'value': r['id']} for r in regions]

    def __str__(self):
        return self.name


class City(UUIDModel,
           AbstractCity):

    class Meta:
        verbose_name = _("City")
        verbose_name_plural = _("Cities")

    @classmethod
    def is_owned(cls):
        return False

    def __str__(self):
        return self.name


class Address(TimeZoneUUIDModel):

    default_errors = {
        'fetch_error': _("Can't get coordinates by address")
    }

    street_address = models.CharField(
        max_length=126,
        verbose_name=_("Street Address")
    )

    city = models.ForeignKey(
        City,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    postal_code = models.CharField(max_length=11, blank=True, verbose_name=_("Postal Code"))

    state = models.ForeignKey(
        Region,
        blank=True,
        null=True,
        verbose_name=_("State/District"),
        on_delete=models.CASCADE
    )

    latitude = models.DecimalField(max_digits=18, decimal_places=15, default=0)
    longitude = models.DecimalField(max_digits=18, decimal_places=15, default=0)

    country = models.ForeignKey(Country, to_field='code2', default='AU', on_delete=models.CASCADE)
    apartment = models.CharField(max_length=6, blank=True, null=True, verbose_name=_('Apartment'))

    class Meta:
        verbose_name = _("Address")
        verbose_name_plural = _("Addresses")

    @property
    def geo(self):
        return self.longitude, self.latitude

    def __str__(self):
        apartment = ''
        if self.apartment:
            apartment = ''.join([str(self.apartment), ' / '])
        address = '{}{} \n{}'.format(apartment, self.street_address, self.postal_code)
        if self.city:
            country_part = ' {}\n{}'.format(self.city.name,
                                            self.country.name)
        else:
            country_part = '\n{}'.format(self.country.name)

        return '{}{}'.format(address, country_part)

    def get_full_address(self):
        if self.city:
            city_part = ',\n{} {}'.format(self.city.name, self.postal_code)
        else:
            city_part = ',\n{}'.format(self.postal_code)

        if self.state:
            country_part = ' {},\n{}'.format(self.state.name,
                                             self.country.name)
        else:
            country_part = ',\n{}'.format(self.country.name)

        return '{}{}{}'.format(self.street_address, city_part, country_part)

    def get_city_address(self):
        if self.city:
            city_part = '{} {}'.format(self.city.name, self.postal_code)
        else:
            city_part = '{}'.format(self.postal_code)

        if self.state:
            country_part = ' {} {}'.format(self.state.name,
                                           self.country.name)
        else:
            country_part = ' {}'.format(self.country.name)

        return '{}{}'.format(city_part, country_part)

    def get_address(self):
        if self.city:
            city_part = '{}, {},'.format(self.street_address, self.city.name)
        else:
            city_part = '{},'.format(self.street_address)

        address = '{} {}'.format(city_part, self.postal_code)
        if self.state:
            address = '{} {}'.format(address, self.state.name)
        return address

    def get_address_for_stripe(self, company_name=''):
        """address broken down as stripe api requires"""
        # hq_addr name can be retrieved from within method but passed to spare 1 MtoM request
        line1 = ' '.join((self.street_address, company_name))
        return {
            'line1': line1,
            'city': self.city,
            'country': self.country,
            'line2': self.apartment,
            'postal_code': self.postal_code,
            'state': self.state
        }

    def fetch_geo_coord(self, should_save=True):
        if self.latitude and self.longitude:
            return False

        latitude, longitude = fetch_geo_coord_by_address(self.get_full_address())
        if latitude and longitude:
            self.latitude = latitude
            self.longitude = longitude
            if should_save:
                self.save(update_fields=['latitude', 'longitude'])
            return True
        return False

    def save(self, *args, **kwargs):
        if self._state.adding:
            bind_address = True
        else:
            original = type(self).objects.get(id=self.id)
            bind_address = original.get_full_address() != self.get_full_address()

        if bind_address \
                and not self.fetch_geo_coord(False) \
                and None in [self.longitude, self.latitude]:
            if getattr(settings, 'FETCH_ADDRESS_RAISE_EXCEPTIONS', True):
                raise ValidationError(self.default_errors['fetch_error'])
        super(Address, self).save(*args, **kwargs)

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                Q(company_addresses__company=owner),
                Q(company_addresses__company__regular_companies__master_company=owner),
                Q(jobsites__master_company=owner),
                Q(jobsites__regular_company__regular_companies__master_company=owner),
            ]


class CompanyContact(UUIDModel, MasterCompanyLookupMixin):
    MANAGER = 'manager'
    CLIENT = 'client'
    ROLE_CHOICES = Choices(
        (MANAGER, _('Manager')),
        (CLIENT, _('Client')),
    )

    contact = models.ForeignKey(
        'core.Contact',
        on_delete=models.CASCADE,
        related_name="company_contact",
        verbose_name=_("Contact")
    )

    job_title = models.CharField(max_length=31, blank=True, verbose_name=_("Job title"))

    rating_unreliable = models.BooleanField(
        verbose_name=_("Ratings Unreliable"),
        help_text=_("Mark when rates Candidates badly but wants them again on the jobsite"),
        default=False
    )

    receive_job_confirmation_sms = models.BooleanField(
        verbose_name=_("Receive Job confirmation sms"),
        default=True
    )

    message_by_sms = models.BooleanField(
        default=True,
        verbose_name=_('By SMS')
    )

    message_by_email = models.BooleanField(
        default=True,
        verbose_name=_('By E-Mail')
    )

    legacy_myob_card_number = models.CharField(
        max_length=15,
        verbose_name=_("Legacy MYOB card number"),
        blank=True
    )

    approved_by_primary_contact = models.ForeignKey(
        'core.Contact',
        verbose_name=_("Approved by primary contact"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="primary_approvals",
    )

    primary_contact_approved_at = models.DateTimeField(
        verbose_name=_("Primary Contact approved at"),
        null=True,
        editable=False
    )

    approved_by_staff = models.ForeignKey(
        'core.Contact',
        verbose_name=_("Approved by staff"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="staff_approvals",
    )

    staff_approved_at = models.DateTimeField(verbose_name=_("Staff approved at"), null=True, editable=False)

    pin_code = models.CharField(
        verbose_name=_("PIN"),
        validators=[string_is_numeric, MinLengthValidator(4)],
        max_length=16,
        blank=True,
        default=''
    )

    role = models.CharField(max_length=63, choices=ROLE_CHOICES, default=ROLE_CHOICES.manager, verbose_name=_('Role'))

    timesheet_reminder = models.BooleanField(
        verbose_name=_("Timesheet Reminder"),
        help_text=_("Unmark when Company Contact does not need timesheet sign reminders"),
        default=True
    )

    objects = AbstractCompanyContactOwnerManager()

    class Meta:
        verbose_name = _("Company Contact")
        verbose_name_plural = _("Company Contacts")

    def __str__(self):
        return '{} {}'.format(self.job_title, str(self.contact))

    def get_master_company(self):
        master_companies = []
        for rel in self.relationships.all():
            master_companies.extend(rel.get_master_company())
        return master_companies

    @classmethod
    def get_master_company_lookup(cls, master_company):
        return Q(relationships__company=master_company)

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                Q(relationships__company=owner),
                Q(relationships__company__regular_companies__master_company=owner)
            ]

    def save(self, *args, **kwargs):
        just_added = self._state.adding
        super().save(*args, **kwargs)
        if just_added:
            from r3sourcer.apps.core.models import DashboardModule, UserDashboardModule
            dashboard_modules = []
            for dashboard_module in DashboardModule.objects.all():
                user_module = UserDashboardModule(
                    company_contact=self,
                    dashboard_module=dashboard_module,
                    position=1,
                )
                dashboard_modules.append(user_module)
            UserDashboardModule.objects.bulk_create(dashboard_modules)

            from r3sourcer.apps.company_settings.models import GlobalPermission
            permission_list = GlobalPermission.objects.all()
            self.contact.user.user_permissions.add(*permission_list)
            self.contact.user.save()


class BankAccount(UUIDModel):
    bank_name = models.CharField(max_length=63, verbose_name=_("Bank Name"))
    bank_account_name = models.CharField(max_length=63, verbose_name=_("Bank Account Name"))
    bsb = models.CharField(max_length=6, verbose_name=_("BSB"))
    account_number = models.CharField(max_length=10, verbose_name=_("Account Number"))

    contact = models.ForeignKey(
        'core.Contact',
        related_name="bank_accounts_old",
        on_delete=models.CASCADE,
        verbose_name="Contact"
    )

    class Meta:
        verbose_name = _("Bank Account")
        verbose_name_plural = _("Bank Accounts")

    def __str__(self):
        return '{}: {}'.format(self.bank_name, self.bank_account_name)

    def clean(self):
        if len(self.account_number) > 9:
            raise ValidationError(_('Bank account number must not exceed 9 digits!'))

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                Q(contact__candidate_contacts__candidate_rels__master_company=owner),
                Q(contact__company_contact__relationships__company=owner),
                Q(companies__regular_companies__master_company=owner),
                Q(companies__id=owner.id),
            ]


class Company(CategoryFolderMixin,
              MYOBMixin,
              WorkflowProcess,
              CompanyLookupMixin,
              TimeZoneUUIDModel,
              MasterCompanyLookupMixin):

    def get_myob_name(self):
        raise NotImplementedError

    name = models.CharField(max_length=127, verbose_name=_("Company Name"), unique=True)

    short_name = models.CharField(
        max_length=63,
        help_text=_('Used for Jobsite naming'),
        verbose_name=_("Short name"),
        null=True,
        blank=True,
        unique=True,
    )

    business_id = models.CharField(
        max_length=31,
        verbose_name=_("Business Number"),
        null=True,
        blank=True,
    )

    registered_for_gst = models.BooleanField(
        verbose_name=_("Registered for GST"),
        default=False
    )

    tax_number = models.CharField(
        max_length=31,
        verbose_name=_("Tax Number"),
        null=True,
        blank=True
    )

    website = models.URLField(verbose_name=_("Website"), blank=True)

    logo = ThumbnailerImageField(
        upload_to='company_pictures',
        default=os.path.join('company_pictures', 'default_picture.jpg'),
        blank=True
    )

    date_of_incorporation = models.DateField(
        verbose_name=_("Date of Incorporation"),
        null=True,
        blank=True
    )

    description = models.TextField(
        verbose_name=_("Public description"),
        blank=True
    )

    notes = models.TextField(
        verbose_name=_("Notes"),
        blank=True,
        help_text=_("Visible for anyone with access")
    )

    primary_contact = models.ForeignKey(
        'core.CompanyContact',
        on_delete=models.SET_NULL,
        related_name="companies",
        verbose_name=_("Manager"),
        null=True, blank=True,
    )

    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Parent Company")
    )

    industries = models.ManyToManyField(
        'pricing.Industry',
        through='core.CompanyIndustryRel',
        verbose_name=_("Industries"),
        blank=True,
    )

    CREDIT_CHECK_CHOICES = Choices(
        (True, 'approved', _("Approved")),
        (False, 'not_approved', _("Not Approved")),
    )

    credit_check = models.BooleanField(
        verbose_name=_("Credit Check"),
        choices=CREDIT_CHECK_CHOICES,
        default=CREDIT_CHECK_CHOICES.not_approved
    )

    credit_check_date = models.DateField(
        verbose_name=_("Credit Check Approval Date"),
        null=True,
        blank=True
    )

    approved_credit_limit = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Approved Credit Limit")
    )

    TERMS_PAYMENT_CHOICES = Choices(
        ('prepaid', _('Prepaid')),
        ('on_delivery', _('Cash on delivery')),
        ('days', _('NET Days')),
        ('day_of_month', _('Day of the month')),
        ('days_eom', _('Days after EOM')),
        ('day_of_month_eom', _('Day of month after EOM')),
    )

    terms_of_payment = models.CharField(
        verbose_name=_("Terms of Payment"),
        choices=TERMS_PAYMENT_CHOICES,
        default=TERMS_PAYMENT_CHOICES.on_delivery,
        max_length=20
    )

    payment_due_date = models.PositiveSmallIntegerField(
        verbose_name=_("Number of days to pay"),
        help_text=_("Or set the day of the month within which the payment must be made to pay"),
        default=0
    )

    available = models.BooleanField(verbose_name=_("Available"), default=True)

    billing_email = models.EmailField(
        max_length=255,
        verbose_name=_("Billing E-mail"),
        blank=True,
        null=True
    )

    def clients_credit_path(instance, filename):
        return 'clients/credit_checks/{}/{}'.format(instance.id, filename)

    credit_check_proof = models.FileField(
        verbose_name=_("Credit Check Proof"), upload_to=clients_credit_path, null=True, blank=True)

    bank_account = models.ForeignKey(
        BankAccount,
        related_name="companies",
        on_delete=models.PROTECT,
        verbose_name=_("Bank Account"),
        null=True,
        blank=True
    )

    COMPANY_TYPES = Choices(
        ('master', _('Master')),
        ('regular', _('Regular'))
    )

    type = models.CharField(
        verbose_name=_("Company type"),
        choices=COMPANY_TYPES,
        default=COMPANY_TYPES.regular,
        max_length=20
    )

    PURPOSE_CHOICES = Choices(
        ('hire', _('Hire')),
        ('self_use', _('Self Use')),
        ('recruitment', _('Recruitment'))
    )

    purpose = models.CharField(
        verbose_name=_("Porpose"),
        choices=PURPOSE_CHOICES,
        default=PURPOSE_CHOICES.hire,
        max_length=20
    )

    files = models.ForeignKey(
        Folder,
        related_name='companies',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    TIMESHEET_APPROVAL_SCHEME = Choices(
        ('BASIC', _("Basic")),
        ('PIN', _("PIN")),
        ('SIGNATURE', _("Signature"))
    )

    timesheet_approval_scheme = models.CharField(
        verbose_name=_("TimeSheet approval scheme"),
        default=TIMESHEET_APPROVAL_SCHEME.BASIC,
        choices=TIMESHEET_APPROVAL_SCHEME,
        max_length=16
    )

    expense_account = models.CharField(
        max_length=6,
        verbose_name=_('MYOB Expense Account'),
        default='4-1000',
    )

    is_system = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_('System Company')
    )

    groups = models.ManyToManyField(Group, related_name='companies')

    stripe_customer = models.CharField(max_length=255, blank=True, null=True)

    card_number = models.CharField(max_length=4, blank=True, null=True)

    sms_enabled = models.BooleanField(default=True)

    company_timezone = models.CharField(max_length=126, blank=True, null=True)

    default_phone_prefix = models.CharField(max_length=3, null=True, blank=True)

    myob_card_id = models.CharField(max_length=15, blank=True)
    old_myob_card_id = models.CharField(max_length=15, blank=True, null=True, editable=False)

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")

    def __str__(self):
        return self.name

    def get_formatted_abn(self):
        abn = self.business_id
        if self.business_id and len(self.business_id) == 11:
            abn = '{}{} {}{}{} {}{}{} {}{}{}'.format(*self.business_id)

        return abn

    def is_primary_contact_assigned(self):
        return self.primary_contact is not None
    is_primary_contact_assigned.short_description = _("Bind primary contact")

    def get_hq_address(self):
        if self.company_addresses.filter(hq=True).exists():
            return self.company_addresses.filter(hq=True).first()
        return None

    def is_business_id_set(self):
        return bool(self.business_id)
    is_business_id_set.short_description = _("Business id didn't set")

    def get_contact(self):
        return self.primary_contact.contact if self.primary_contact else None

    def get_user(self):
        contact = self.get_contact()
        return contact.user if contact else None

    def get_master_company(self):
        if self.type == self.COMPANY_TYPES.master:
            return [self]
        else:
            master_companies = []
            for company_rel in self.regular_companies.all():
                master_companies.extend(company_rel.master_company.get_master_company())
            return master_companies

    def get_closest_master_company(self):
        master_companies = self.get_master_company()

        return master_companies[0] if len(master_companies) > 0 else None

    @classmethod
    def get_master_company_lookup(cls, master_company):
        return Q(id=master_company.id)

    def get_regular_companies(self):
        if self.type == self.COMPANY_TYPES.regular:
            return [self]
        reg_companies = []
        for company_rel in self.master_companies.all():
            reg_companies.extend(company_rel.regular_company.get_regular_companies())
        return reg_companies

    def get_terms_of_payment(self):
        if self.terms_of_payment in (self.TERMS_PAYMENT_CHOICES.prepaid,
                                     self.TERMS_PAYMENT_CHOICES.on_delivery):
            return self.TERMS_PAYMENT_CHOICES[self.terms_of_payment]
        return '{}: {}'.format(
            self.TERMS_PAYMENT_CHOICES[self.terms_of_payment],
            self.payment_due_date
        )

    def get_effective_pricelist_qs(self, position=None):
        qs = self.price_lists.exclude(
            Q(approved_by__isnull=True) | Q(approved_by=None) | Q(approved_at__isnull=True) | Q(approved_at=None)
        ).filter(
            effective=True,
            valid_until__gte=date.today(),
            price_list_rates__rate__gt=0
        )

        if position:
            qs = qs.filter(price_list_rates__worktype__skill_name=position.name)

        return qs

    def get_portfolio_manager(self):
        company_rel = self.regular_companies.all().first()
        return company_rel and company_rel.manager

    @property
    def invoice_rule(self):
        return self.invoice_rules.first()

    @property
    def is_master(self):
        return self.type == self.COMPANY_TYPES.master

    @property
    def currency(self):
        try:
            return self.company_addresses.order_by('hq').first().address.country.currency.lower()
        except Exception:
            return 'aud'

    @property
    def country(self):
        try:
            return self.company_addresses.order_by('hq').first().address.country
        except Exception:
            return Country.objects.get(name='Australia')

    @property
    def active_subscription(self):
        return self.subscriptions.filter(active=True).first()

    def _get_active_workers(self, start_date=None):
        """ returns list of active workers"""
        from r3sourcer.apps.candidate.models import CandidateContact

        if not start_date:
            start_date = datetime.combine(utc_now().date(), time(0, 0)) - timedelta(days=31)

        return CandidateContact.objects.filter(
            job_offers__shift__date__job__customer_company=self,
            job_offers__time_sheets__shift_started_at__gt=start_date,
            job_offers__time_sheets__status=7,
        ).distinct()

    def active_workers(self, start_date=None):
        """ returns number of active workers"""
        return self._get_active_workers(start_date=start_date).count()

    def get_active_workers_ids(self, start_date=None):
        """ returns list with active workers ids"""
        return self._get_active_workers(start_date=start_date).values_list('id', flat=True)

    def get_active_discounts(self, payment_type=None):
        discounts = self.discounts.filter(active=True)

        if payment_type:
            discounts = discounts.filter(payment_type=payment_type)

        return discounts

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
            company_addresses__hq=True,
        ).annotate(
            longitude=F('company_addresses__address__longitude'),
            latitude=F('company_addresses__address__latitude')
        ).values_list('longitude', 'latitude').get()

    def save(self, *args, **kwargs):
        from r3sourcer.apps.company_settings.models import CompanySettings, MYOBSettings
        from r3sourcer.apps.core.models.workflow import WorkflowNode, CompanyWorkflowNode
        from r3sourcer.apps.hr.models import PayslipRule
        from r3sourcer.apps.billing.models import SMSBalance

        just_added = self._state.adding

        if just_added and not self.short_name:
            self.short_name = self.name

        if not self.myob_card_id:
            self.myob_card_id = self.get_myob_card_number()

        super(Company, self).save(*args, **kwargs)

        if not hasattr(self, 'company_settings'):
            CompanySettings.objects.create(company=self)

        if not hasattr(self, 'myob_settings'):
            MYOBSettings.objects.create(company=self)

        if not hasattr(self, 'sms_balance'):
            SMSBalance.objects.create(company=self)

        if not self.payslip_rules.all():
            PayslipRule.objects.create(company=self)

        if not self.invoice_rules.all():
            InvoiceRule.objects.create(company=self)

        if just_added and self.type == self.COMPANY_TYPES.master:
            bulk_objects = [
                CompanyWorkflowNode(company=self, workflow_node=wf_node)
                for wf_node in WorkflowNode.objects.filter(hardlock=True)
            ]

            CompanyWorkflowNode.objects.bulk_create(bulk_objects)

            self.create_state(10)

            # add default company language
            company_language = CompanyLanguage(company_id=self.id,
                                               language_id=settings.DEFAULT_LANGUAGE,
                                               default=True)
            company_language.save()

        if not just_added:
            origin = Company.objects.get(pk=self.pk)
            if origin.myob_card_id != self.myob_card_id:
                self.old_myob_card_id = origin.myob_card_id
            super(Company, self).save(*args, **kwargs)

    def get_myob_card_number(self):
        if not self.myob_card_id:
            return str(self.id)[-15:]
        return self.myob_card_id

    def get_closest_company(self):
        return self.get_closest_master_company()

    def get_timezone(self):
        master_company = self.get_master_company()[0]
        hq_address = master_company.get_hq_address()
        if hq_address:
            return master_company.tz
        return pytz.timezone(settings.TIME_ZONE)
    # TODO: use this everywhere

    def get_country_code(self):
        hq_address = self.get_hq_address()
        if hq_address:
            return hq_address.address.country.code2
        return 'EE' # TODO: refactor this

    def vat_name(self):
        try:
            return VAT.objects.get(country=self.get_country_code()).name
        except:
            return None

    def get_vat(self):
        company = self.get_closest_master_company()
        if company.registered_for_gst:
            return VAT.get_vat(company.get_country_code()).first()

    def get_default_language(self):
        default_language = self.languages.filter(default=True).first()
        if not default_language and self.type == self.COMPANY_TYPES.regular:
            default_language = self.get_closest_master_company().languages.filter(default=True).first()
        return default_language.language if default_language is not None else None

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [Q(regular_companies__master_company=owner), Q(id=owner.id)]


class CompanyRel(UUIDModel,
                 WorkflowProcess,
                 CompanyLookupMixin,
                 MasterCompanyLookupMixin):
    """
    Model for storing master and regular company relationship
    """
    master_company = models.ForeignKey(
        'core.Company',
        related_name="master_companies",
        verbose_name=_("Master company"),
        on_delete=models.CASCADE
    )

    regular_company = models.ForeignKey(
        'core.Company',
        related_name="regular_companies",
        verbose_name=_("Regular company"),
        on_delete=models.CASCADE
    )

    manager = models.ForeignKey(
        'core.CompanyContact',
        related_name="company_accounts",
        verbose_name=_("Primary Contact"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ('master_company', 'regular_company')
        verbose_name = _("Company Relationship")
        verbose_name_plural = _("Company Relationships")

    def __str__(self):
        return "{}/{}".format(self.master_company, self.regular_company)

    @workflow_function
    def is_manager_identified(self):
        return self.manager is not None
    is_manager_identified.short_description = _("Identify portfolio manager")

    @workflow_function
    def is_primary_contact_assigned(self):
        return self.regular_company.is_primary_contact_assigned()
    is_primary_contact_assigned.short_description = _("Identify primary Contact")

    @workflow_function
    def is_business_id_set(self):
        return self.regular_company.is_business_id_set()

    @workflow_function
    def is_state_60_available(self):
        req_class = factory.get_instance('company_state_60')
        return req_class.check(self)

    @workflow_function
    def is_address_valid(self):
        return self.regular_company.company_addresses.filter(active=True).exists()
    is_address_valid.short_description = _("Active address")

    @workflow_function
    def is_description_set(self):
        return bool(self.regular_company.description)
    is_description_set.short_description = _("Public description")

    @workflow_function
    def is_industry_set(self):
        return bool(self.regular_company.industries.all())
    is_industry_set.short_description = _("Industries")

    def get_master_company(self):
        return self.master_company.get_master_company()

    def get_closest_company(self):
        return self.master_company

    def after_state_activated(self, workflow_object):
        if workflow_object.state.number == 70 and workflow_object.active:
            jobs = self._get_jobs_with_states(40)

            for job in jobs:
                if job.is_allowed(20):
                    job.create_state(20)
        elif workflow_object.state.number == 80 and workflow_object.active:
            jobs = self._get_jobs_with_states(20)

            for job in jobs:
                if job.is_allowed(40):
                    job.create_state(40)

    def _get_jobs_with_states(self, state):
        from r3sourcer.apps.hr.models import Job
        from r3sourcer.apps.core.models.workflow import WorkflowObject

        content_type = ContentType.objects.get_for_model(Job)
        filter_values = WorkflowObject.objects.filter(
            state__number=state, state__workflow__model=content_type, active=True
        ).values_list('object_id', flat=True).distinct()

        return self.regular_company.customer_jobs.filter(id__in=filter_values)

    def save(self, *args, **kwargs):
        just_added = self._state.adding
        super().save(*args, **kwargs)

        if just_added:
            self.create_state(10)

        cache.set('company_rel_{}'.format(self.regular_company.id), None)


class CompanyContactRelationship(TimeZoneUUIDModel,
                                 CompanyLookupMixin,
                                 MasterCompanyLookupMixin):
    company = models.ForeignKey(
        'core.Company',
        related_name="relationships",
        verbose_name=_("Company"),
        on_delete=models.CASCADE
    )

    company_contact = models.ForeignKey(
        CompanyContact,
        related_name="relationships",
        verbose_name=_("Company Contact"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    active = models.BooleanField(verbose_name=_("Active"), default=True)
    termination_date = models.DateField(
        verbose_name=_("Termination date"),
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ('company', 'company_contact')
        verbose_name = _("Company Contact Relationship")
        verbose_name_plural = _("Company Contact Relationships")

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
            company__company_addresses__hq=True,
        ).annotate(
            longitude=F('company__company_addresses__address__longitude'),
            latitude=F('company__company_addresses__address__latitude')
        ).values_list('longitude', 'latitude').get()

    def __str__(self):
        return "{company}: {contact}".format(company=self.company, contact=self.company_contact)

    def get_master_company(self):
        return self.company.get_master_company()

    def get_closest_company(self):
        if self.termination_date and self.termination_date < utc_now():
            return None
        return self.company

    @classmethod
    def get_master_company_lookup(cls, master_company):
        return Q(company=master_company)

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                Q(company=owner),
                Q(company__regular_companies__master_company=owner)
            ]

    def save(self, *args, **kwargs):

        is_added = self._state.adding
        super().save(*args, **kwargs)

        if is_added:
            role = Role.ROLE_NAMES.client
            if self.company.type == self.company.COMPANY_TYPES.master:
                role = Role.ROLE_NAMES.manager

            self.company_contact.contact.user.role.add(Role.objects.create(name=role, company_contact_rel=self))


class CompanyIndustryRel(UUIDModel):

    company = models.ForeignKey(
        'core.Company',
        related_name='company_industry_rels',
        verbose_name=_("Company"),
        on_delete=models.CASCADE,
    )

    industry = models.ForeignKey(
        'pricing.Industry',
        related_name='company_industry_rels',
        verbose_name=_("Industry"),
        on_delete=models.CASCADE,
    )

    default = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Company Industry Relation")
        verbose_name_plural = _("Company Industries Relation")

    def __str__(self):
        return '{}, {}'.format(str(self.company), str(self.industry))

    def save(self, *args, **kwargs):
        # only one can be default
        # first should be default
        qs = type(self).objects.filter(default=True)
        if qs:
            if self.default:
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                qs.update(default=False)
        else:
            self.default = True

        super(CompanyIndustryRel, self).save(*args, **kwargs)
        from r3sourcer.apps.skills.models import Skill
        for skill_name in self.industry.skill_names.all():
            skill, _ = Skill.objects.get_or_create(name=skill_name,
                                                   company=self.company,
                                                   defaults={'active': False},
                                                   )

    def delete(self, using=None, keep_parents=False):
        for skill_name in self.industry.skill_names.all():
            for skill in skill_name.skills.all():
                try:
                    skill.delete()
                except ProtectedError:
                    continue
        super().delete()


class CompanyAddress(TimeZoneUUIDModel, MasterCompanyLookupMixin):

    name = models.CharField(
        max_length=63,
        blank=True,
        verbose_name=_("Name")
    )

    company = models.ForeignKey(
        'core.Company',
        related_name='company_addresses',
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )

    address = models.ForeignKey(
        Address,
        related_name='company_addresses',
        on_delete=models.PROTECT,
        verbose_name=_("Address"),
    )

    hq = models.BooleanField(default=False, verbose_name=_("HQ"))

    termination_date = models.DateField(
        verbose_name=_("Termination date"),
        null=True,
        blank=True
    )

    primary_contact = models.ForeignKey(
        CompanyContact,
        on_delete=models.SET_NULL,
        related_name='company_primary_addresses',
        verbose_name=_("Primary contact"),
        null=True,
        blank=True
    )

    active = models.BooleanField(default=True, verbose_name=_("Active"))

    phone_landline = PhoneNumberField(blank=True, verbose_name=_("Landline Phone"))
    email = models.EmailField(
        max_length=255,
        verbose_name=_("E-mail"),
        unique=True,
        null=True,      # null=True should be added because there are many objects already existing
        # blank=True,   # blank should be False to make the input field required in FE
    )

    class Meta:
        verbose_name = _("Company Address")
        verbose_name_plural = _("Company Addresses")

    def __str__(self):
        return self.name

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
            hq=True,
        ).annotate(
            longitude=F('address__longitude'),
            latitude=F('address__latitude')
        ).values_list('longitude', 'latitude').get()

    def save(self, *args, **kwargs):
        if self.hq:
            CompanyAddress.objects.filter(company=self.company).update(hq=False)
        elif not CompanyAddress.objects.filter(company=self.company, hq=True).exists():
            self.hq = True

        super(CompanyAddress, self).save(*args, **kwargs)

    def get_master_company(self):
        return self.company.get_master_company()

    @classmethod
    def get_master_company_lookup(cls, master_company):
        return Q(company=master_company)

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                Q(company=owner),
                Q(company__regular_companies__master_company=owner),
                Q(primary_contact__relationships__company=owner),
                Q(primary_contact__relationships__company__regular_companies__master_company=owner),
            ]


class CompanyContactAddress(
        UUIDModel,
        MasterCompanyLookupMixin):

    company_address = models.ForeignKey(
        CompanyAddress,
        related_name="company_contacts",
        verbose_name=_("Company Address"),
        on_delete=models.PROTECT
    )

    company_contact = models.ForeignKey(
        CompanyContact,
        related_name="company_addresses",
        verbose_name=_("Company Contact"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    active = models.BooleanField(verbose_name=_("Active"), default=True)
    termination_date = models.DateField(
        verbose_name=_("Termination date"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("Company Contact Address")
        verbose_name_plural = _("Company Contact Addresses")

    def __str__(self):
        return '{} {}'.format(str(self.company_contact),
                              str(self.company_address))

    @classmethod
    def get_master_company_lookup(cls, master_company):
        return Q(company_contact__relationships__company=master_company)

    def get_master_company(self):
        return self.company_contact.get_master_company()


class FileStorage(UUIDModel):
    PATHS = Choices(
        (('core', 'contact'), 'contacts/{owner.id}/{filename}'),
        (('core', 'company'), 'companies/{owner.id}/{filename}'),
    )
    owner_type = models.ForeignKey(
        ContentType,
        limit_choices_to=Q(app_label='core', model__in=['contact', 'company']),
        on_delete=models.CASCADE
    )
    owner_id = models.UUIDField()
    owner = GenericForeignKey('owner_type', 'owner_id')

    def content_path(self, filename):
        if self.owner is None:
            raise NotImplementedError('owner must be assigned before content can be used')

        natural_key = self.owner_type.natural_key()
        try:
            pattern = self.PATHS[natural_key]
            return pattern.format(
                filename=filename,
                owner=self.owner,
                instance=self,
            )
        except KeyError:
            raise NotImplementedError('content_path not support {} model'.format('.'.join(natural_key)))

    content = models.FileField(
        upload_to=content_path,
        verbose_name=_("Content"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("File Storage")
        verbose_name_plural = _("File Storage")

    @classmethod
    def is_owned(cls):
        return False


class CompanyLocalization(UUIDModel):
    field_name = models.CharField(
        max_length=64,
        verbose_name=_("Company field name"),
    )
    country = models.ForeignKey(
        Country,
        to_field='code2',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        help_text=_("Country of localization. Empty value used for default variant")
    )
    verbose_value = models.CharField(
        max_length=128,
        verbose_name=_("Company field verbose name"),
        null=True,
        blank=True,
    )
    help_text = models.CharField(
        max_length=512,
        verbose_name=_("Company field help text"),
        null=True,
        blank=True,
    )
    active = models.BooleanField(
        verbose_name=_("Company field is active"),
        default=True,
    )

    class Meta:
        verbose_name = _("Company Localization")
        verbose_name_plural = _("Company Localizations")

    @classmethod
    def get_company_metadata(cls, country=None):
        """
        Obtain company localization metadata in format::

            {
                "business_id": {
                    "verbose_value": "<verbose_value>",
                    "help_text": "<help_text>",
                    "active": bool,
                },
                "tax_number": {
                    "verbose_value": "<verbose_value>",
                    "help_text": "<help_text>",
                    "active": bool,
                }
            }

        Metadata picked for business_id and tax_number fields for given country or default variant.
        Company localization with empty country used as default variant

        :param country: Country to make lookup
        :return: Dict with metadata
        """
        localizations = cls.objects.filter(
            Q(country__in=[country]) | Q(country__isnull=True),
            field_name__in=["business_id", "tax_number"]
        )
        lookup = dict()
        for company in localizations:
            field_name = company.field_name
            if field_name in lookup and company.country is None:
                continue

            lookup[field_name] = dict(
                verbose_value=company.verbose_value,
                help_text=company.help_text,
                active=company.active,
            )
        return lookup


class CompanyTradeReference(UUIDModel):

    trade_reference = models.TextField(verbose_name=_("Trade Reference"))

    company = models.ForeignKey(
        'core.Company',
        related_name="company_trade_references",
        on_delete=models.CASCADE,
        verbose_name=_("Company")
    )

    referral_company_name = models.CharField(
        max_length=255,
        verbose_name=_("Company Name")
    )

    referral_person_name = models.CharField(
        max_length=255,
        verbose_name=_("Title, First and Last Name")
    )

    referral_email = models.EmailField(verbose_name=_("E-mail"))
    referral_phone = PhoneNumberField(verbose_name=_("Phone"))

    email_auth_code = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        verbose_name=_("E-mail authentication string")
    )

    class Meta:
        verbose_name = _("Company Trade Reference")
        verbose_name_plural = _("Company Trade References")

    def __str__(self):
        return _('{} from {}').format(self.company.name, self.referral_company_name)


class Note(UUIDModel):

    content_type = models.ForeignKey(
        ContentType,
        verbose_name=_("Content type"),
        on_delete=models.CASCADE
    )
    object_id = models.UUIDField(verbose_name=_("Object id"))
    object = GenericForeignKey()

    note = models.TextField(
        verbose_name=_("Notes"),
        blank=True
    )

    contact = models.ForeignKey(
        'core.Contact',
        related_name='created_notes',
        verbose_name=_('Contact'),
        on_delete=models.SET_NULL,
        null=True
    )

    def __str__(self):
        return '{} {}'.format(str(self.content_type), _("Note"))

    class Meta:
        verbose_name = _("Contact Note")
        verbose_name_plural = _("Contact Notes")

    @classmethod
    def is_owned(cls):
        return False


class NoteFile(UUIDModel):
    note = models.ForeignKey(
        Note,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name=_("Note")
    )

    def note_files_path(self, filename):
        return 'notes/{}/{}'.format(self.note_id, filename)

    file = models.FileField(
        verbose_name=_("Note File"),
        upload_to=note_files_path
    )

    class Meta:
        verbose_name = _("Note File")
        verbose_name_plural = _("Note Files")


class Tag(MPTTModel, UUIDModel):
    TAG_OWNER = Choices(
        ('system', _('System')),
        ('company', _('Company')),
    )
    name = models.CharField(max_length=63, verbose_name=_("Tag Name"))
    parent = TreeForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='children',
        db_index=True,
        on_delete=models.CASCADE,
    )
    active = models.BooleanField(default=True, verbose_name=_('Active'))
    evidence_required_for_approval = models.BooleanField(
        default=False,
        verbose_name=_('Evidence required for approval')
    )
    confidential = models.BooleanField(
        default=False,
        verbose_name=_('Confidential'),
    )
    owner = models.CharField(
        max_length=10,
        choices=TAG_OWNER,
        default=TAG_OWNER.system
    )

    objects = TagManager()

    class Meta:
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")

    def __str__(self):
        return self.name

    @classmethod
    def is_owned(cls):
        return False


class TagCompany(Tag):
    class Meta:
        proxy = True
        verbose_name = _("Tag owned by company")
        verbose_name_plural = _("Tags owned by company")


class CompanyTag(UUIDModel):
    tag = models.ForeignKey(
        'core.TagCompany',
        related_name="company_tags",
        on_delete=models.CASCADE,
        verbose_name=_("Tag company")
    )

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
        related_name="tags",
    )

    class Meta:
        verbose_name = _("Company Tag")
        verbose_name_plural = _("Company Tags")
        unique_together = ("tag", "company")

    def __str__(self):
        return self.tag.name


class TagLanguage(models.Model):
    tag = models.ForeignKey('core.Tag',
                            related_name='translations',
                            on_delete=models.CASCADE,
                            verbose_name=_('Tag Name')
                            )
    value = models.CharField(max_length=127, verbose_name=_("Tag transalation"))
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Tag name language"),
        on_delete=models.CASCADE,
        related_name='tag_names',
    )

    class Meta:
        verbose_name = _("Tag Language")
        verbose_name_plural = _("Tag Languages")
        unique_together = [
            'tag',
            'language',
        ]

    def __str__(self):
        return self.value


class VAT(UUIDModel):
    country = models.ForeignKey(
        'core.Country',
        to_field='code2',
        default='AU',
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        max_length=64,
        verbose_name=_("Name"),
    )
    rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        verbose_name=_("Rate"),
        default=0.00
    )
    stripe_rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        verbose_name=_("Stripe Rate"),
        default=10.00,
        help_text=_("Stripe Tax percentage"),
    )
    stripe_id = models.CharField(
        max_length=64,
        verbose_name=_("Stripe ID"),
    )
    start_date = models.DateField(verbose_name=_("Start Date"))
    end_date = models.DateField(verbose_name=_("End Date"), blank=True, null=True)

    class Meta:
        verbose_name = _("VAT")
        verbose_name_plural = _("VATs")

    def __str__(self):
        return f'{self.country.name} - {self.name}'

    @classmethod
    def is_owned(cls):
        return False

    @staticmethod
    def get_vat(country_code_2):
        return VAT.objects.filter(country=country_code_2)


class AbstractBaseOrder(TimeZoneUUIDModel,
                        WorkflowProcess,
                        CompanyLookupMixin,
                        MasterCompanyLookupMixin):

    provider_company = models.ForeignKey(  # master
        'core.Company',
        on_delete=models.CASCADE,
        verbose_name=_("Provider Company"),
        related_name="provider_%(class)ss",
    )

    customer_company = models.ForeignKey(  # any company
        'core.Company',
        on_delete=models.CASCADE,
        verbose_name=_("Customer Company"),
        related_name="customer_%(class)ss",
    )

    provider_representative = models.ForeignKey(
        'core.CompanyContact',
        on_delete=models.PROTECT,
        verbose_name=_("Provider Representative"),
        related_name="provider_representative_%(class)ss",
        blank=True,
        null=True
    )

    customer_representative = models.ForeignKey(
        'core.CompanyContact',
        on_delete=models.PROTECT,
        verbose_name=_("Customer Representative"),
        related_name="customer_representative_%(class)ss",
        null=True,
        blank=True,
    )

    # TODO: change path to files
    def customer_signature_path(self, filename):
        pattern = '{year}/{owner.id}/{filename}'
        return pattern.format(
            year=date().year,
            filename=filename,
            owner=self.customer_company,
            instance=self
        )

    customer_signature = models.FileField(
        upload_to=customer_signature_path,
        verbose_name=_("Customer signature"),
        null=True,
        blank=True
    )

    # TODO: change path to files
    def provider_signature_path(self, filename):
        pattern = '{year}/{owner.id}/{filename}'
        return pattern.format(
            year=date().year,
            filename=filename,
            owner=self.provider_company,
            instance=self
        )

    provider_signature = models.FileField(
        upload_to=provider_signature_path,
        verbose_name=_("Provider signature"),
        null=True,
        blank=True
    )

    customer_signed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Customer signed at")
    )

    provider_signed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Provider signed at")
    )

    class Meta:
        abstract = True

    def __str__(self):
        return "{}, {}".format(self.provider_company, self.customer_company)

    @property
    def provider_signed_at_tz(self):
        return self.utc2local(self.provider_signed_at)

    @property
    def provider_signed_at_utc(self):
        return self.provider_signed_at

    @property
    def customer_signed_at_tz(self):
        return self.utc2local(self.customer_signed_at)

    @property
    def customer_signed_at_utc(self):
        return self.customer_signed_at

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
            provider_company__company_addresses__hq=True,
        ).annotate(
            longitude=F('provider_company__company_addresses__address__longitude'),
            latitude=F('provider_company__company_addresses__address__latitude')
        ).values_list('longitude', 'latitude').get()

    def get_customer(self):
        return self.customer_company

    def get_provider(self):
        return self.provider_company

    @classmethod
    def get_master_company_lookup(cls, master_company):
        return Q(
            provider_company=master_company,
            provider_company__type=Company.COMPANY_TYPES.master) | \
            Q(
            customer_company=master_company,
            customer_company__type=Company.COMPANY_TYPES.master
        )

    def get_master_company(self):
        if self.provider_company.type == Company.COMPANY_TYPES.master:
            return self.provider_company.get_master_company()
        return self.customer_company.get_master_company()

    def get_closest_company(self):
        if self.provider_company.type == Company.COMPANY_TYPES.master:
            return self.provider_company
        return self.customer_company


class AbstractOrder(AbstractBaseOrder):

    total_with_tax = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Total with GST")
    )

    total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Total")
    )

    tax = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0.00,
        verbose_name=_("GST")
    )

    currency = CurrencyField(
        verbose_name=_('Currency'),
        default=settings.DEFAULT_CURRENCY,
        choices=CURRENCY_CHOICES
    )

    class Meta:
        abstract = True

    def calculate_vat(self):
        vat = 0
        for line in self.invoice_lines.all():
            if line.vat:
                vat += line.vat.rate * line.amount
        return math.ceil(vat) / 100

    def calculate_total(self):
        lines = getattr(self, '{}_lines'.format(self._meta.model_name))
        sum = lines.aggregate(sum=Sum('amount'))['sum'] or 0
        return math.ceil(sum * 100) / 100

    def save(self, *args, **kwargs):
        self.tax = self.calculate_vat()
        self.total = self.calculate_total()
        total_with_tax = self.tax + self.total
        self.total_with_tax = math.ceil(total_with_tax * 100) / 100
        super().save(*args, **kwargs)


class Order(AbstractOrder):

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    @workflow_function
    @workflow_function
    def is_state_50_available(self):
        return self._is_state_available(50)

    @workflow_function
    def is_state_90_available(self):
        return self._is_state_available(90)

    def _is_state_available(self, state_number):
        req_class = factory.get_instance('order_state_' + str(state_number))
        return req_class.check(self)

    def save(self, *args, **kwargs):
        just_added = self._state.adding
        super().save(*args, **kwargs)
        if just_added:
            self.create_state(10)


class AbstractOrderLine(TimeZoneUUIDModel):

    @property
    def geo(self):
        raise NotImplementedError

    date = models.DateField(verbose_name=_("Date"))

    units = models.DecimalField(
        verbose_name=_("Units"),
        max_digits=8,
        decimal_places=2,
    )

    notes = models.TextField(verbose_name=_("Notes"))

    unit_price = models.DecimalField(
        verbose_name=_("Rate"),
        max_digits=8,
        decimal_places=2,
    )

    amount = models.DecimalField(
        verbose_name=_("Amount"),
        max_digits=8,
        decimal_places=2,
    )

    unit_name = models.CharField(
        _("Unit Name"),
        max_length=20,
        default=_('hours')
    )

    vat = models.ForeignKey(
        'core.VAT',
        on_delete=models.PROTECT,
        verbose_name=_("VAT"),
        null=True,
        blank=True
    )

    def __str__(self):
        return self.name

    class Meta:
        abstract = True

    def get_tax(self):
        return self.vat.rate * self.unit_price

    def save(self, *args, **kwargs):
        self.amount = math.ceil(self.unit_price * self.units * 100) / 100
        super().save(*args, **kwargs)


class OrderLine(AbstractOrderLine):

    @property
    def geo(self):
        raise NotImplementedError

    order = models.ForeignKey(
        Order,
        related_name="order_lines",
        on_delete=models.PROTECT,
        verbose_name=_("Order"),
    )

    class Meta:
        verbose_name = _("Order Line")
        verbose_name_plural = _("Order Lines")


class Invoice(AbstractOrder):

    is_paid = models.BooleanField(
        default=False,
        verbose_name=_("Is paid")
    )

    paid = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Paid sum")
    )

    paid_at = models.DateField(
        verbose_name=_("Paid at"),
        editable=False,
        null=True
    )

    myob_number = models.CharField(
        max_length=8,
        verbose_name=_("MYOB Number"),
        null=True,
        blank=True
    )

    synced_at = models.DateTimeField(
        verbose_name=_("Synced to MYOB at"),
        blank=True,
        null=True
    )

    date = models.DateField(
        verbose_name=_("Creation date"),
        null=True
    )

    updated = models.DateField(null=True)

    number = models.CharField(
        verbose_name=_("Number"),
        max_length=8,
        null=True
    )

    order_number = models.TextField(
        verbose_name=_("Order Number"),
        null=True
    )

    period = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    separation_rule = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    approved = models.BooleanField(
        default=False
    )

    SYNC_STATUS_CHOICES = Choices(
        (0, 'not_synced', _('Not synced')),
        (1, 'sync_scheduled', _('Sync scheduled')),
        (2, 'syncing', _('Syncing...')),
        (3, 'synced', _('Synced')),
        (4, 'sync_failed', _('Sync failed')),
    )

    sync_status = models.PositiveSmallIntegerField(
        verbose_name=_("Sync status"),
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_STATUS_CHOICES.not_synced
    )

    class Meta:
        verbose_name = _("Company Invoice")
        verbose_name_plural = _("Company Invoices")

    def __str__(self):
        return 'Invoice {} {}'.format(
            str(self.customer_company),
            date_format(self.date, settings.DATE_FORMAT)
        )

    def set_sync_status(self, status):
        self.sync_status = status
        self.save(update_fields=['sync_status'])

    @property
    def synced_at_tz(self):
        if self.synced_at:
            return self.utc2local(self.synced_at)

    @property
    def synced_at_utc(self):
        return self.synced_at

    def get_invoice_number(self, rule):
        invoice_number = ''

        if rule.serial_number:
            invoice_number += rule.serial_number

        starting_number = format(rule.starting_number, '05')
        invoice_number += starting_number

        return invoice_number

    def save(self, *args, **kwargs):
        if not self.date:
            self.date = utc_now().date()
        self.updated = utc_now().date()
        just_added = self._state.adding

        if just_added:
            # TODO: Bad logic, add more clear solution
            rule = self.provider_company.invoice_rules.first()
            self.number = self.get_invoice_number(rule)
            rule.starting_number += 1
            rule.save()

        super(Invoice, self).save(*args, **kwargs)


class InvoiceLine(AbstractOrderLine):

    invoice = models.ForeignKey(
        'core.Invoice',
        related_name="invoice_lines",
        on_delete=models.CASCADE,
        verbose_name=_("Invoice"),
    )

    timesheet = models.ForeignKey(
        'hr.TimeSheet',
        related_name="invoice_lines",
        on_delete=models.CASCADE,
        verbose_name=_("TimeSheet"),
        blank=True,
        null=True
    )

    skill_activity = models.TextField(
        verbose_name=_("Skill Activity"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("Invoice Line")
        verbose_name_plural = _("Invoice Lines")

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
        ).annotate(
            longitude=F('timesheet__job_offer__shift__date__job__jobsite__address__longitude'),
            latitude=F('timesheet__job_offer__shift__date__job__jobsite__address__latitude')
        ).values_list('longitude', 'latitude').get()

    # TODO: Remove duplicated fields after make AbstractOrderLine TimeZoneUUID support
    @property
    def created_at_tz(self):
        return self.utc2local(self.created_at)

    @property
    def updated_at_tz(self):
        return self.utc2local(self.updated_at)

    @property
    def created_at_utc(self):
        return self.created_at

    @property
    def updated_at_utc(self):
        return self.updated_at

    @property
    def activities_list(self):
        activities_list = []
        master_company = self.timesheet.master_company
        company_language = master_company.get_default_language()
        timesheet_rates = self.timesheet.timesheet_rates

        for tr in timesheet_rates.all():
            activities_list.append(tr.worktype.translation(company_language))

        return ', '.join(activities_list)

    def __str__(self):
        return '{}: {}'.format(
            str(self.invoice),
            date_format(self.date, settings.DATE_FORMAT)
        )


class SiteCompany(
        UUIDModel,
        MasterCompanyLookupMixin):
    site = models.ForeignKey(
        Site,
        related_name="site_companies",
        on_delete=models.PROTECT,
        verbose_name=_("Site"),
    )
    company = models.ForeignKey(
        'core.Company',
        related_name="site_companies",
        on_delete=models.CASCADE,
        verbose_name=_("Company")
    )

    class Meta:
        verbose_name = _("Site/Company relationship")
        verbose_name_plural = _("Site/Company relationships")
        unique_together = ('site', 'company')

    def __str__(self):
        return "{}: {}".format(self.site, self.company)

    @classmethod
    def get_master_company_lookup(cls, master_company):
        return Q(company=master_company)

    def get_master_company(self):
        return self.company.get_master_company()


class AbstractPayRuleMixin(models.Model):

    PERIOD_CHOICES = Choices(
        ('weekly', _('Weekly')),
        ('fortnightly', _('Fortnightly')),
        ('monthly', _('Monthly')),
        ('daily', _('Daily')),
    )

    period = models.CharField(
        max_length=11,
        verbose_name=_("Period"),
        choices=PERIOD_CHOICES,
        default=PERIOD_CHOICES.weekly
    )

    period_zero_reference = models.IntegerField(
        verbose_name=_("Period zero reference"),
        default=1
    )

    starting_number = models.IntegerField(
        verbose_name=_("Starting number"),
        default=1
    )

    comment = models.TextField(
        verbose_name=_("Comment"),
        null=True,
        blank=True
    )

    class Meta:
        abstract = True

    def clean(self):
        if ((self.period == AbstractPayRuleMixin.PERIOD_CHOICES.weekly and self.period_zero_reference > 7)
                or (self.period == AbstractPayRuleMixin.PERIOD_CHOICES.fortnightly and self.period_zero_reference > 14)
                or (self.period == AbstractPayRuleMixin.PERIOD_CHOICES.monthly and self.period_zero_reference > 29)):
            raise ValidationError(_('Incorrect period zero reference'))


class InvoiceRule(AbstractPayRuleMixin, UUIDModel):

    company = models.ForeignKey(
        'core.Company',
        related_name="invoice_rules",
        verbose_name=_("Company"),
        on_delete=models.CASCADE
    )

    serial_number = models.CharField(
        max_length=3,
        verbose_name=_("Serial number"),
        null=True,
        blank=True
    )

    notice = models.TextField(
        verbose_name=_("Notice"),
        null=True,
        blank=True
    )

    SEPARATION_CHOICES = Choices(
        ('one_invoice', _('One invoice')),
        ('per_jobsite', _('Per jobsite')),
        ('per_candidate', _('Per candidate')),
    )

    separation_rule = models.CharField(
        max_length=13,
        verbose_name=_("Separation rule"),
        choices=SEPARATION_CHOICES,
        default=SEPARATION_CHOICES.one_invoice
    )

    show_candidate_name = models.BooleanField(
        verbose_name=_("Show Candidate Name"),
        default=False
    )

    @property
    def last_invoice_created(self):
        date = None

        if self.company.customer_invoices.exists():
            date = self.company.customer_invoices.order_by('-date')[0].date

        return date

    @property
    def last_invoice_updated(self):
        date = None

        if self.company.customer_invoices.exists():
            date = self.company.customer_invoices.order_by('-updated')[0].updated

        return date

    class Meta:
        verbose_name = _("Invoice Rule")
        verbose_name_plural = _("Invoice Rules")
        unique_together = ('company', 'serial_number')


class CurrencyExchangeRates(UUIDModel):
    from_currency = CurrencyField(
        verbose_name=_('From currency'),
        default='USD',
        choices=CURRENCY_CHOICES
    )
    to_currency = CurrencyField(
        verbose_name=_('To currency'),
        default='USD',
        choices=CURRENCY_CHOICES
    )
    exchange_rate = models.DecimalField(
        verbose_name=_('Exchange rate'),
        decimal_places=12,
        max_digits=18,
        default=1,
    )

    class Meta:
        verbose_name = _("Currency Exchange Rate")
        verbose_name_plural = _("Currency Exchange Rates")
        unique_together = ('from_currency', 'to_currency')

    @classmethod
    def is_owned(cls):
        return False


class PublicHoliday(UUIDModel):
    """
    Public holiday model
    """

    country = models.ForeignKey(
        'core.Country',
        verbose_name=_("Country"),
        on_delete=models.CASCADE
    )
    date = models.DateField(_("Date"))
    name = models.CharField(_("Name"), max_length=512)

    class Meta:
        ordering = ['country', 'date']
        verbose_name = _("Public holiday")
        verbose_name_plural = _("Public holidays")

    def __str__(self):
        return f'{self.date} - {self.name}'

    @classmethod
    def is_holiday(cls, date, country=None):
        if country is None:
            country = Country.objects.get(code2='AU')
        return cls.objects.filter(country=country, date=date).exists()

    @classmethod
    def is_owned(cls):
        return False


class ExtranetNavigation(MPTTModel, UUIDModel):
    CLIENT = 'client'
    MANAGER = 'manager'
    CANDIDATE = 'candidate'
    ADMIN = 'admin'
    ACCESS_LEVEL_CHOICES = Choices(
        (CLIENT, _('Client')),
        (MANAGER, _('Manager')),
        (CANDIDATE, _('Candidate')),
        (ADMIN, _('Admin'))
    )

    id = models.AutoField(auto_created=True, primary_key=True,
                          serialize=False, verbose_name='ID')
    parent = TreeForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='children',
        db_index=True,
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=63, verbose_name=_("Menu Title"))
    url = models.CharField(max_length=63, verbose_name=_("Default Url"))
    endpoint = models.CharField(max_length=63, verbose_name=_("DRF Endpoint"))
    access_level = models.CharField(max_length=63, choices=ACCESS_LEVEL_CHOICES,
                                    default=MANAGER, verbose_name=_("Acess Level"))

    class Meta:
        verbose_name = _("Extranet Navigation")
        verbose_name_plural = _("Extranet Navigations")

    def __str__(self):
        return self.name

    @classmethod
    def is_owned(cls):
        return False


class ContactLanguage(models.Model):
    contact = models.ForeignKey(
        'core.Contact',
        related_name='languages',
        verbose_name=_('Contact language'),
        on_delete=models.CASCADE
    )
    language = models.ForeignKey(
        'core.Language',
        related_name="contacts",
        verbose_name=_("Language"),
        on_delete=models.PROTECT)

    default = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Contact language")
        verbose_name_plural = _("Contact languages")
        unique_together = (("contact", "language"),)

    def __str__(self):
        return f'{self.language} - {self.default}'

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):

        if self.default is True:
            ContactLanguage.objects \
                           .filter(contact=self.contact, default=True) \
                           .update(default=False)

        super().save(force_insert, force_update, using, update_fields)


class Role(UUIDModel):
    ROLE_NAMES = Choices(
        ('candidate', _('Candidate')),
        ('manager', _('Manager')),
        ('client', _('Client')),
        ('trial', _('Trial')),
    )

    name = models.CharField(max_length=255, choices=ROLE_NAMES)

    company_contact_rel = models.ForeignKey(
        'core.CompanyContactRelationship',
        on_delete=models.CASCADE,
        related_name='user_roles',
        verbose_name=_('Company Contact Relation'),
        null=True,
        blank=True,
    )

    def __str__(self):
        return '{}: {}'.format(self.company_contact_rel, self.name)

    @classmethod
    def is_owned(cls):
        return False


connect_default_signals(Country)
connect_default_signals(Region)
connect_default_signals(City)

__all__ = [
    'Contact', 'ContactRelationship', 'ContactUnavailability',
    'ContactAddress', 'CompanyIndustryRel', 'User', 'UserManager',
    'Country', 'Region', 'City',
    'Company', 'CompanyContact', 'CompanyRel', 'CompanyContactRelationship', 'CompanyContactAddress',
    'CompanyAddress', 'CompanyLocalization', 'CompanyTradeReference', 'BankAccount', 'SiteCompany',
    'Address', 'FileStorage',
    'Order',
    'AbstractPayRuleMixin', 'Invoice', 'InvoiceLine',
    'Note', 'NoteFile', 'Tag', 'TagLanguage', 'CompanyTag', 'TagCompany',
    'VAT', 'InvoiceRule',
    'CurrencyExchangeRates', 'PublicHoliday', 'ExtranetNavigation',
    'AbstractBaseOrder', 'AbstractOrder', 'ContactLanguage', 'Role'
]
