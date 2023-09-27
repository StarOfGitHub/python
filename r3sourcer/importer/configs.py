import os

from django.db.models import Q
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from model_utils import Choices

from r3sourcer.apps.core import models
from r3sourcer.apps.candidate import models as candidate_models
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.pricing import models as pricing_models
from r3sourcer.apps.skills import models as skill_models


class BaseConfig(object):
    columns = None
    columns_map = None
    model = None
    lbk_model = None
    order_by = 'created_at'
    dependency = None
    required = None
    distinct = None
    select = '*'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        return row

    @classmethod
    def exists(cls, row):   # pragma: no cover
        qs = cls.model.objects.filter(id=row['id'])

        return cls.is_watched_exists(row, qs)

    @classmethod
    def is_watched_exists(cls, row, qs):
        is_exists = qs.exists()
        is_watched = 'created_at' in row and 'updated_at' in row
        if is_exists and is_watched and not qs.filter(
            created_at=row['created_at'], updated_at=row['updated_at']
        ).exists():
            qs.update(created_at=row['created_at'], updated_at=row['updated_at'])
            return True
        return is_exists

    @classmethod
    def override(cls, **kwargs):
        attrs = {k: v for k, v in vars(cls).items() if not k.startswith('__')}
        attrs.update(kwargs)

        return type('%sDep' % cls.__name__, (cls, ), attrs)

    @classmethod
    def process(cls, row):   # pragma: no cover
        obj, _ = cls.model.objects.get_or_create(**{
            key: val for key, val in row.items()
            if key in cls.columns
        })
        if 'created_at' in row and 'updated_at' in row:
            cls.model.objects.filter(id=row['id']).update(created_at=row['created_at'], updated_at=row['updated_at'])

        return obj

    @classmethod
    def post_process(cls, row, instance):   # pragma: no cover
        pass


class BaseRateMixin:

    @classmethod
    def fetch_skill_base_rate(cls, row, rate_var):
        skill_base_rate_exists = not skill_models.SkillBaseRate.objects.filter(id=row[rate_var]).exists()
        if skill_base_rate_exists and row['skill_id'] and row['h_rate']:
            try:
                row[rate_var] = skill_models.SkillBaseRate.objects.get(
                    skill_id=row['skill_id'], hourly_rate=row['h_rate']
                ).id
            except skill_models.SkillBaseRate.DoesNotExist as e:
                print(e)

                row[rate_var] = None

        return row


class AddressConfig(BaseConfig):

    columns = {
        'street_address', 'city', 'postal_code', 'state', 'latitude', 'longitude', 'country',
        'updated_at', 'created_at',
    }
    columns_map = {
        'street_address_1': 'street_address',
    }
    model = models.Address

    STATE_CHOICES = Choices(
        ('ACT', "ACT"),
        ('NSW', "New South Wales"),
        ('NT', "Northern Territory"),
        ('Qld', "Queensland"),
        ('SA', "South Australia"),
        ('Tas', "Tasmania"),
        ('Vic', "Victoria"),
        ('WA', "Western Australia"),
        ('', None)
    )

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['country'] = models.Country.objects.filter(
            code2=row['country']).first()
        row['state'] = models.Region.objects.filter(
            name=cls.STATE_CHOICES[row['state']]).first()
        row['city'] = models.City.objects.filter(
            name=row['city'], country=row['country']).first()

        return row

    @classmethod
    def exists(cls, row):   # pragma: no cover
        qs = cls.model.objects.filter(
            country__code2=row['country'],
            state__name=cls.STATE_CHOICES[row['state']],
            city__name=row['city'],
            street_address=row['street_address_1'],
            postal_code=row['postal_code'],
        )

        return cls.is_watched_exists(row, qs)


class UserConfig(BaseConfig):

    columns = {
        'id', 'is_staff', 'is_active', 'is_superuser', 'date_joined',
        'password'
    }
    columns_map = {
        'user_id': 'id'
    }
    model = models.User
    lbk_model = 'core_user'
    order_by = 'date_joined'


class ContactConfig(BaseConfig):

    columns = {
        'id', 'title', 'first_name', 'last_name', 'email', 'phone_mobile',
        'gender', 'marital_status', 'birthday', 'spouse_name', 'children',
        'is_available', 'email_verified', 'phone_mobile_verified', 'address',
        'updated_at', 'created_at', 'user', 'picture',
    }
    model = models.Contact
    lbk_model = 'crm_core_contact'
    dependency = {
        'address': AddressConfig,
        'user': UserConfig.override(
            lbk_model="core_user where id='{user_id}'",
            required={'user_id', }
        ),
    }

    @classmethod
    def prepare_data(self, row):
        if not row['email']:
            row['email'] = None

        if not row['phone_mobile']:
            row['phone_mobile'] = None

        if not row.get('picture'):
            row['picture'] = os.path.join('contact_pictures', 'default_picture.jpg')

        return row

    @classmethod
    def post_process(cls, row, instance):   # pragma: no cover
        if row['user_id'] is None and (row['email'] or row['phone_mobile']):
            user_obj = models.User.objects.create(
                email=row['email'],
                phone_mobile=row['phone_mobile']
            )

            instance.user = user_obj
            instance.save()


class ContactUnavailabilityConfig(BaseConfig):

    columns = {
        'id', 'unavailable_from', 'unavailable_until', 'notes', 'contact_id',
        'updated_at', 'created_at',
    }
    model = models.ContactUnavailability
    lbk_model = 'crm_core_contactunavailability'


class ClientContactConfig(BaseConfig):

    columns = {
        'id', 'contact_id', 'job_title', 'rating_unreliable',
        'updated_at', 'created_at',
    }
    model = models.CompanyContact
    lbk_model = 'crm_core_clientcontact'


class ClientContactRelConfig(BaseConfig):

    columns = {
        'company_contact_id', 'company_id'
    }
    columns_map = {
        'id': 'company_contact_id',
        'client_id': 'company_id',
    }
    model = models.CompanyContactRelationship
    lbk_model = 'crm_core_clientcontact'

    @classmethod
    def exists(cls, row):  # pragma: no cover
        qs = cls.model.objects.filter(
            company_contact_id=row['id'],
            company_id=row['client_id']
        )

        return cls.is_watched_exists(row, qs)


class AccountContactConfig(BaseConfig):

    columns = {
        'id', 'contact_id', 'job_title', 'legacy_myob_card_number', 'updated_at', 'created_at',
    }
    model = models.CompanyContact
    lbk_model = 'crm_core_accountcontact'


class AccountCompanyConfig(BaseConfig):

    columns = {
        'id', 'name', 'business_id', 'registered_for_gst', 'website',
        'date_of_incorporation', 'description', 'notes', 'manager_id',
        'parent_id', 'updated_at', 'created_at', 'type',
    }
    model = models.Company
    lbk_model = 'crm_core_account'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['type'] = models.Company.COMPANY_TYPES.master
        return row

    @classmethod
    def process(cls, row):   # pragma: no cover
        defaults = {key: val for key, val in row.items() if key in cls.columns}
        obj, created = cls.model.objects.get_or_create(name=row['name'], defaults=defaults)
        if not created and obj.id != row['id']:
            ids_mapping = cache.get('ids_mapping', {})
            ids_mapping[row['id']] = str(obj.id)
            cache.set('ids_mapping', ids_mapping)

        return obj


class ClientCompanyConfig(BaseConfig):

    columns = {
        'id', 'name', 'business_id', 'registered_for_gst', 'website',
        'date_of_incorporation', 'description', 'notes', 'manager_id',
        'updated_at', 'created_at', 'type', 'credit_check',
        'credit_check_date', 'approved_credit_limit', 'terms_of_payment',
        'payment_due_date', 'available', 'billing_email',
    }
    columns_map = {
        'primary_contact_id': 'manager_id',
    }
    model = models.Company
    lbk_model = 'crm_core_client'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['type'] = models.Company.COMPANY_TYPES.regular

        if row['name'].lower() == 'labourking':
            row['name'] = settings.SYSTEM_MASTER_COMPANY

        return row


class CompanyRelConfig(BaseConfig):

    columns = {
        'master_company_id', 'regular_company_id', 'primary_contact_id',
    }
    model = models.CompanyRel
    lbk_model = 'crm_core_client'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['primary_contact_id'] = row['portfolio_manager_id']
        row['master_company_id'] = row['account_id']
        row['regular_company_id'] = row['id']

        return row

    @classmethod
    def exists(cls, row):  # pragma: no cover
        qs = cls.model.objects.filter(
            master_company_id=row['account_id'],
            regular_company_id=row['id']
        )

        return cls.is_watched_exists(row, qs)


class ClientAddressConfig(BaseConfig):

    columns = {
        'id', 'name', 'updated_at', 'created_at', 'address', 'company_id', 'phone_landline', 'phone_fax',
    }
    columns_map = {
        'client_id': 'company_id',
    }
    model = models.CompanyAddress
    lbk_model = 'crm_core_clientaddress'
    dependency = {
        'address': AddressConfig,
    }


class BankAccountConfig(BaseConfig):

    columns = {
        'id', 'bank_name', 'updated_at', 'created_at', 'bank_account_name',
        'bsb', 'account_number', 'contact_id'
    }
    model = models.BankAccount
    lbk_model = 'crm_hr_bankaccount'


class ContactNoteConfig(BaseConfig):

    columns = {
        'id', 'object_id', 'content_type', 'note', 'updated_at', 'created_at',
    }
    model = models.Note
    lbk_model = 'crm_core_contactnote'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        contact = models.Contact.objects.get(id=row['contact_id'])
        row['object_id'] = contact.id
        row['content_type'] = ContentType.objects.get_for_model(models.Contact)

        return row


class VisaTypeConfig(BaseConfig):

    columns = {
        'id', 'subclass', 'name', 'general_type', 'work_hours_allowed',
        'is_available',
    }
    model = candidate_models.VisaType
    lbk_model = 'crm_hr_visatype'
    order_by = 'name'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        if row['general_type'] == 'Bridging Visa':
            row['general_type'] = \
                candidate_models.VisaType.GENERAL_TYPE_CHOICES.bridging
        elif row['general_type'] == 'Temporary':
            row['general_type'] = \
                candidate_models.VisaType.GENERAL_TYPE_CHOICES.temp
        elif row['general_type'] == 'Temporary Resident':
            row['general_type'] = \
                candidate_models.VisaType.GENERAL_TYPE_CHOICES.temp_resid

        return row


class EmploymentClassificationConfig(BaseConfig):

    columns = {
        'id', 'name', 'updated_at', 'created_at',
    }
    model = skill_models.EmploymentClassification
    lbk_model = 'crm_hr_employmentclassification'


class SuperannuationFundConfig(BaseConfig):

    columns = {
        'id', 'name', 'updated_at', 'created_at',
    }
    model = candidate_models.SuperannuationFund
    lbk_model = 'crm_hr_superannuationfund'


class CandidateContactConfig(BaseConfig):

    columns = {
        'id', 'contact_id', 'residency', 'nationality', 'visa_type_id', 'visa_expiry_date', 'vevo_checked_at',
        'referral', 'tax_number', 'weight', 'height',
        'strength', 'language', 'transportation_to_work', 'emergency_contact_name', 'emergency_contact_phone',
        'autoreceives_sms', 'bank_account_id', 'updated_at', 'employment_classification_id', 'superannuation_fund',
        'created_at',
    }
    model = candidate_models.CandidateContact
    lbk_model = 'crm_hr_recruiteecontact'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['nationality'] = models.Country.objects.filter(
            code2=row['nationality']).first()

        return row

    @classmethod
    def post_process(cls, row, instance):   # pragma: no cover
        if not hasattr(instance, 'candidate_scores'):
            hr_models.CandidateScore.objects.create(
                candidate_contact=instance,
                reliability=row['reliability_score'],
                loyalty=row['loyalty_score'],
            )
        else:
            instance.candidate_scores.reliability = row['reliability_score']
            instance.candidate_scores.loyalty = row['loyalty_score']
            instance.candidate_scores.save(update_fields=['reliability', 'loyalty'])


class TagConfig(BaseConfig):
    columns = {
        'id', 'name', 'active', 'evidence_required_for_approval',
    }
    model = models.Tag
    lbk_model = 'crm_hr_tag'
    order_by = 'name'


class TagRelConfig(BaseConfig):
    columns = {
        'id', 'tag_id', 'candidate_contact_id', 'verified_by_id',
    }
    columns_map = {
        'recruitee_contact_id': 'candidate_contact_id',
    }
    model = candidate_models.TagRel
    lbk_model = 'crm_hr_recruiteetag'


class SkillConfig(BaseConfig):
    columns = {
        'id', 'name', 'carrier_list_reserve', 'short_name',
        'employment_classification_id', 'active',
    }
    model = skill_models.Skill
    lbk_model = 'crm_hr_skill'
    order_by = 'name'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        if row['active']:
            row['active'] = False

        return row


class SkillBaseRateConfig(BaseConfig):
    columns = {
        'id', 'skill_id', 'hourly_rate', 'default_rate',
    }
    columns_map = {
        'active': 'default_rate',
    }
    model = skill_models.SkillBaseRate
    lbk_model = (
        'crm_hr_skillbaserate as sbr LEFT JOIN '
        'crm_hr_skill as s on sbr.skill_id=s.id'
    )
    order_by = 'hourly_rate'
    select = 'sbr.*, s.active'

    @classmethod
    def exists(cls, row):   # pragma: no cover
        qs = cls.model.objects.filter(
            Q(id=row['id']) | Q(skill_id=row['skill_id'], hourly_rate=row['hourly_rate'])
        )

        return cls.is_watched_exists(row, qs)

    @classmethod
    def post_process(cls, row, instance):   # pragma: no cover
        try:
            if instance:
                instance.skill.active = row['active']
                instance.skill.save(update_fields=['active'])
        except ValidationError:
            pass


class SkillRelConfig(BaseConfig):
    columns = {
        'id', 'skill_id', 'score', 'candidate_contact_id', 'prior_experience',
        'created_at', 'updated_at',
    }
    columns_map = {
        'recruitee_contact_id': 'candidate_contact_id',
    }
    model = candidate_models.SkillRel
    lbk_model = 'crm_hr_recruiteeskill'


class IndustryConfig(BaseConfig):
    columns = {
        'id', 'type',
    }
    model = pricing_models.Industry
    lbk_model = 'crm_hr_jobsitetype'
    order_by = 'type'


class RateCoefficientGroupConfig(BaseConfig):
    columns = {
        'id', 'name', 'created_at', 'updated_at',
    }
    model = pricing_models.RateCoefficientGroup
    lbk_model = 'crm_hr_ratecoefficientgroup'


class RateCoefficientConfig(BaseConfig):
    columns = {
        'id', 'name', 'group_id', 'active', 'created_at', 'updated_at', 'industry_id',
    }
    model = pricing_models.RateCoefficient
    lbk_model = 'crm_hr_ratecoefficient'
    distinct = ['name']

    @classmethod
    def _create_rule(cls, rule_obj, coeff_obj):  # pragma: no cover
        pricing_models.DynamicCoefficientRule.objects.create(
            rate_coefficient=coeff_obj,
            rule=rule_obj
        )

    @classmethod
    def post_process(cls, row, instance):   # pragma: no cover
        if row.get('used_for_overtime'):
            obj, _ = pricing_models.OvertimeWorkRule.objects.get_or_create(
                overtime_hours_from=row.get('overtime_hours_from'),
                overtime_hours_to=row.get('overtime_hours_to'),
            )
            cls._create_rule(obj, instance)
        if row.get('used_for_time_of_day'):
            obj, _ = pricing_models.TimeOfDayWorkRule.objects.get_or_create(
                time_start=row.get('time_start'),
                time_end=row.get('time_end'),
            )
            cls._create_rule(obj, instance)
        if row.get('is_allowance'):
            obj, _ = pricing_models.AllowanceWorkRule.objects.get_or_create(
                allowance_description=row.get('allowance_description'),
            )
            cls._create_rule(obj, instance)

        weekday_list = (
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday',
            'sunday', 'bank_holiday'
        )

        if any([row.get('weekday_' + w) for w in weekday_list]):
            obj, _ = pricing_models.WeekdayWorkRule.objects.get_or_create(
                **{'weekday_' + w: row.get('weekday_' + w)
                   for w in weekday_list}
            )
            cls._create_rule(obj, instance)


class RateCoefficientModifierCompanyConfig(BaseConfig):
    columns = {
        'id', 'rate_coefficient_id', 'multiplier', 'fixed_addition',
        'fixed_override', 'created_at', 'updated_at', 'type',
    }
    model = pricing_models.RateCoefficientModifier
    lbk_model = (
        'crm_hr_ratecoefficientforclient as rcfc LEFT JOIN '
        'crm_hr_ratecoefficient as rc on rc.id=rcfc.rate_coefficient_id'
    )
    select = 'rcfc.*, rc.name as rc_name'
    order_by = 'rcfc.created_at'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['type'] = (
            pricing_models.RateCoefficientModifier.TYPE_CHOICES.company
        )
        row['rate_coefficient_id'] = (
            pricing_models.RateCoefficient.objects.get(name=row['rc_name']).id
        )

        return row


class RateCoefficientModifierCandidateConfig(BaseConfig):
    columns = {
        'id', 'rate_coefficient_id', 'multiplier', 'fixed_addition',
        'fixed_override', 'created_at', 'updated_at', 'type',
    }
    model = pricing_models.RateCoefficientModifier
    lbk_model = (
        'crm_hr_ratecoefficientforrecruitee as rcfr LEFT JOIN '
        'crm_hr_ratecoefficient as rc on rc.id=rcfr.rate_coefficient_id'
    )
    select = 'rcfr.*, rc.name as rc_name'
    order_by = 'rcfr.created_at'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['type'] = (
            pricing_models.RateCoefficientModifier.TYPE_CHOICES.candidate
        )
        row['rate_coefficient_id'] = (
            pricing_models.RateCoefficient.objects.get(name=row['rc_name']).id
        )

        return row


class PriceListConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'company_id', 'valid_from',
        'valid_until', 'effective', 'approved_by_id', 'approved_at',
    }
    columns_map = {
        'client_id': 'company_id',
        'approved_by_client_contact_id': 'approved_by_id',
        'approved_by_client_at': 'approved_at',
    }
    model = pricing_models.PriceList
    lbk_model = 'crm_hr_pricelist'


class PriceListRateConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'hourly_rate', 'price_list_id',
        'skill_id'
    }
    columns_map = {
        'plbr.skill_id': 'skill_id',
        'plbr.hourly_rate': 'hourly_rate',
    }
    model = pricing_models.PriceListRate
    lbk_model = (
        'crm_hr_pricelistrate as plr LEFT JOIN '
        'crm_hr_pricelistbaserate as plbr on plbr.id=plr.rate_id'
    )
    select = 'plbr.*, plr.*'
    order_by = 'plr.id'


class PriceListRateCoefficientConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'rate_coefficient_id', 'price_list_id'
    }
    columns_map = {
        'plr.price_list_id': 'price_list_id',
    }
    model = pricing_models.PriceListRateCoefficient
    lbk_model = (
        'crm_hr_pricelistratecoefficient as plrc LEFT JOIN '
        'crm_hr_pricelistrate as plr on plrc.price_list_rate_id=plr.id'
    )
    select = 'plrc.*, plr.*'
    order_by = 'plrc.id'

    @classmethod
    def exists(cls, row):   # pragma: no cover
        qs = cls.model.objects.filter(
            price_list_id=row['price_list_id'], rate_coefficient_id=row['rate_coefficient_id']
        )

        return cls.is_watched_exists(row, qs)


class JobsiteConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'industry_id', 'master_company_id',
        'portfolio_manager_id', 'primary_contact_id', 'is_available',
        'notes', 'start_date', 'end_date',
    }
    columns_map = {
        'type_id': 'industry_id',
    }
    dependency = {
        'address': AddressConfig,
    }
    model = hr_models.Jobsite
    lbk_model = 'crm_hr_jobsite'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        companies = models.Company.objects.get(
            id=row['client_id']
        ).get_master_company()

        row['master_company_id'] = (
            companies[0].id if len(companies) > 0 else row['client_id']
        )

        return row

    @classmethod
    def post_process(cls, row, instance):   # pragma: no cover
        address_data = AddressConfig.prepare_data({
            key: row.get(key) for key in AddressConfig.columns
        })
        for old_field, new_field in AddressConfig.columns_map.items():
            address_data[new_field] = row.get(old_field)

        address, _ = models.Address.objects.get_or_create(**address_data)
        instance.address = address
        instance.regular_company_id = row['client_id']
        instance.save(update_fields=['address', 'regular_company'])


class JobsiteUnavailabilityConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'jobsite_id', 'unavailable_from',
        'unavailable_until', 'notes',
    }
    model = hr_models.JobsiteUnavailability
    lbk_model = 'crm_hr_jobsiteunavailability'


class ShiftDateConfig(BaseRateMixin, BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'job_id', 'shift_date', 'hourly_rate_id', 'cancelled',
    }
    columns_map = {
        'shift_start_time': 'shift_date',
        'top_hourly_rate_id': 'hourly_rate_id',
        'vacancy_id': 'job_id',
    }
    model = hr_models.ShiftDate
    lbk_model = (
        'crm_hr_vacancydate as vd LEFT JOIN crm_hr_skillbaserate as sbr ON vd.top_hourly_rate_id=sbr.id'
    )
    select = (
        'vd.*, sbr.skill_id as skill_id, sbr.hourly_rate as h_rate'
    )

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        dt = row['shift_date']
        row['shift_date'] = dt.date()

        row = cls.fetch_skill_base_rate(row, 'hourly_rate_id')

        return row

    @classmethod
    def post_process(cls, row, instance):   # pragma: no cover
        if instance:
            dt = row['shift_start_time']
            hr_models.Shift.objects.get_or_create(
                date=instance,
                time=dt.time(),
                workers=row['workers'],
            )


class JobConfig(BaseRateMixin, BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'jobsite_id', 'position_id',
        'published', 'publish_on', 'expires_on', 'work_start_date',
        'workers', 'default_shift_starting_time', 'notes',
        'transportation_to_work', 'customer_company_id', 'provider_company_id', 'provider_signed_at',
        'customer_representative_id', 'provider_representative_id',
    }
    columns_map = {
        'client_id': 'customer_company_id',
        'client_representative_id': 'customer_representative_id',
        'account_representative_id': 'provider_representative_id',
        'account_accepted_at': 'provider_signed_at',
    }
    model = hr_models.Job
    lbk_model = (
        'crm_hr_vacancy as v LEFT JOIN crm_core_order as o on v.order_id=o.id '
        'LEFT JOIN crm_hr_skillbaserate as sbr ON v.top_hourly_rate_default_id=sbr.id'
    )
    select = (
        'v.*, o.client_id, o.client_representative_id, o.account_representative_id, o.account_accepted_at, '
        'sbr.skill_id as skill_id, sbr.hourly_rate as h_rate'
    )

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        companies = models.Company.objects.get(
            id=row['client_id']
        ).get_master_company()

        row['provider_company_id'] = (
            companies[0].id if len(companies) > 0 else row['client_id']
        )

        return row


class JobOfferConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'candidate_contact_id', 'status',
        'shift',
    }
    columns_map = {
        'recruitee_contact_id': 'candidate_contact_id',
    }
    model = hr_models.JobOffer
    lbk_model = 'crm_hr_vacancyoffer'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        cancelled = row['cancelled']
        accepted = row['accepted']

        if accepted:
            row['status'] = hr_models.JobOffer.STATUS_CHOICES.accepted
        elif cancelled:
            row['status'] = hr_models.JobOffer.STATUS_CHOICES.cancelled
        else:
            row['status'] = hr_models.JobOffer.STATUS_CHOICES.undefined

        row['shift'] = hr_models.Shift.objects.get(
            date_id=row['vacancy_date_id']
        )

        return row


class TimeSheetConfig(BaseRateMixin, BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'going_to_work_confirmation',
        'shift_started_at', 'break_started_at', 'break_ended_at',
        'shift_ended_at', 'supervisor_id', 'candidate_submitted_at',
        'supervisor_approved_at', 'candidate_rate_id', 'job_offer_id',
        'rate_overrides_approved_by_id', 'rate_overrides_approved_at',
    }
    columns_map = {
        'recruitee_signed_at': 'candidate_submitted_at',
        'supervisor_signed_at': 'supervisor_approved_at',
        'recruitee_rate_id': 'candidate_rate_id',
    }
    model = hr_models.TimeSheet
    lbk_model = (
        'crm_hr_timesheet as ts LEFT JOIN crm_hr_vacancyoffer as vo on ts.booking_id=vo.booking_id '
        'LEFT JOIN crm_hr_skillbaserate as sbr ON ts.recruitee_rate_id=sbr.id '
        'where ts.shift_started_at::date = vo.target_date_and_time::date'
    )
    select = 'ts.*, vo.id as job_offer_id, sbr.skill_id as skill_id, sbr.hourly_rate as h_rate'

    @classmethod
    def prepare_data(cls, row):
        row = cls.fetch_skill_base_rate(row, 'candidate_rate_id')

        return row


class BlackListConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'candidate_contact_id', 'company_id',
        'timesheet_id', 'jobsite_id', 'company_contact_id',
    }
    columns_map = {
        'client_id': 'company_id',
        'recruitee_contact_id': 'candidate_contact_id',
        'client_contact_id': 'company_contact_id',
    }
    model = hr_models.BlackList
    lbk_model = 'crm_hr_blacklist'


class FavouriteListConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'candidate_contact_id', 'company_id',
        'job_id', 'jobsite_id', 'company_contact_id',
    }
    columns_map = {
        'account_contact_id': 'company_contact_id',
        'client_id': 'company_id',
        'recruitee_contact_id': 'candidate_contact_id',
        'vacancy_id': 'job_id',
    }
    model = hr_models.FavouriteList
    lbk_model = 'crm_hr_favouritelist'


class CarrierListConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'job_offer_id', 'target_date',
        'candidate_contact_id', 'confirmed_available',
        'referral_job_offer_id',
    }
    columns_map = {
        'recruitee_contact_id': 'candidate_contact_id',
        'vacancy_offer_id': 'job_offer_id',
        'referral_vacancy_offer_id': 'referral_job_offer_id',
    }
    model = hr_models.CarrierList
    lbk_model = 'crm_hr_carrierlist'


class CandidateEvaluationConfig(BaseConfig):
    columns = {
        'id', 'created_at', 'updated_at', 'candidate_contact_id',
        'supervisor_id', 'evaluated_at', 'reference_timesheet_id',
        'level_of_communication', 'was_on_time', 'was_motivated',
        'had_ppe_and_tickets', 'met_expectations', 'representation'
    }
    columns_map = {
        'recruitee_contact_id': 'candidate_contact_id',
    }
    model = hr_models.CandidateEvaluation
    lbk_model = 'crm_hr_recruiteeevaluation'


class StatesConfigMixin:
    @classmethod
    def process(cls, row):   # pragma: no cover
        data = {key: val for key, val in row.items() if key in cls.columns}
        try:
            obj = cls.model.objects.get(**data)
        except cls.model.DoesNotExist:
            obj = cls.model(**data)
            obj.save(raw=True, lifecycle=False)

        cls.model.objects.filter(id=row['id']).update(created_at=row['created_at'], updated_at=row['updated_at'])

        return obj

    @classmethod
    def get_workflow_node(cls, number, model):
        return models.WorkflowNode.objects.get(number=number, workflow__model=ContentType.objects.get_for_model(model))


class CandidateStatesConfig(StatesConfigMixin, BaseConfig):
    columns = {'id', 'object_id', 'state', 'comment', 'active'}
    columns_map = {
        'notes': 'comment',
        'state': 'number',
        'recruitee_contact_id': 'object_id',
    }
    model = models.WorkflowObject
    lbk_model = 'crm_hr_recruitmentstatus'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        if row['number'] == 95:
            row['number'] = 90

        row['state'] = cls.get_workflow_node(row['number'], candidate_models.CandidateContact)

        return row


class CompanyStatesConfig(StatesConfigMixin, BaseConfig):
    columns = {'id', 'object_id', 'state', 'comment', 'active'}
    columns_map = {
        'description': 'comment',
        'state': 'number',
    }
    model = models.WorkflowObject
    lbk_model = 'crm_core_clientstate'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['state'] = cls.get_workflow_node(row['number'], models.CompanyRel)
        row['object_id'] = models.CompanyRel.objects.get(regular_company_id=row['client_id']).id

        return row

    @classmethod
    def exists(cls, row):
        if row['state'] == 50:
            return True

        return super().exists(row)


class JobsiteStatesConfig(StatesConfigMixin, BaseConfig):
    columns = {'id', 'object_id', 'state', 'comment', 'active'}
    columns_map = {
        'notes': 'comment',
        'state': 'number',
        'jobsite_id': 'object_id',
    }
    model = models.WorkflowObject
    lbk_model = 'crm_hr_jobsitestate'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        row['state'] = cls.get_workflow_node(row['number'], hr_models.Jobsite)

        models.WorkflowObject.objects.filter(object_id=row['object_id']).update(active=False)
        row['active'] = True

        return row


class JobStatesConfig(StatesConfigMixin, BaseConfig):
    columns = {'object_id', 'state', 'comment', 'active'}
    columns_map = {
        'notes': 'comment',
        'state': 'number',
        'vacancy_id': 'object_id',
    }
    model = models.WorkflowObject
    lbk_model = (
        'crm_hr_orderstate as os LEFT JOIN crm_core_order as o on os.order_id=o.id '
        'LEFT JOIN crm_hr_vacancy as v on o.id=v.order_id '
        'where v.id is not null'
    )
    select = 'os.*, v.id as vacancy_id'
    order_by = 'os.created_at'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        map_states = {70: 60, 50: 20, 0: 40}

        if row['number'] in map_states:
            row['number'] = map_states[row['number']]

        row['state'] = cls.get_workflow_node(row['number'], hr_models.Job)

        models.WorkflowObject.objects.filter(object_id=row['object_id']).update(active=False)
        row['active'] = True

        return row


class TimeSheetStatesConfig(StatesConfigMixin, BaseConfig):
    columns = {'object_id', 'state', 'comment', 'active'}
    columns_map = {
        'notes': 'comment',
        'state': 'number',
        'timesheet_id': 'object_id',
    }
    model = models.WorkflowObject
    lbk_model = (
        'crm_hr_bookingstate as bs left join crm_hr_booking as b on b.id=bs.booking_id '
        'left JOIN crm_hr_timesheet as t on t.booking_id=b.id '
        'where t.id is not null'
    )
    select = 'bs.*, t.id as timesheet_id'
    order_by = 'bs.created_at'

    @classmethod
    def prepare_data(cls, row):  # pragma: no cover
        map_states = {50: 20, 0: 90, 90: 60}

        if row['number'] in map_states:
            row['number'] = map_states[row['number']]

        row['state'] = cls.get_workflow_node(row['number'], hr_models.TimeSheet)

        models.WorkflowObject.objects.filter(object_id=row['object_id']).update(active=False)
        row['active'] = True

        return row

    @classmethod
    def exists(cls, row):   # pragma: no cover
        qs = cls.model.objects.filter(object_id=row['timesheet_id'], state__number=row['state'])

        return cls.is_watched_exists(row, qs)


ALL_CONFIGS = [
    ContactConfig, ContactUnavailabilityConfig, ClientContactConfig, AccountContactConfig,
    AccountCompanyConfig, ClientCompanyConfig, CompanyRelConfig, ClientAddressConfig,
    BankAccountConfig, ClientContactRelConfig, ContactNoteConfig, VisaTypeConfig,
    TagConfig, EmploymentClassificationConfig, SuperannuationFundConfig,
    CandidateContactConfig, TagRelConfig,
    SkillConfig, SkillBaseRateConfig, SkillRelConfig,
    IndustryConfig, RateCoefficientGroupConfig, RateCoefficientConfig, RateCoefficientModifierCompanyConfig,
    RateCoefficientModifierCandidateConfig, PriceListConfig, PriceListRateConfig, PriceListRateCoefficientConfig,
    JobsiteConfig, JobsiteUnavailabilityConfig,
    JobConfig, ShiftDateConfig, JobOfferConfig, TimeSheetConfig,
    BlackListConfig, FavouriteListConfig, CarrierListConfig, CandidateEvaluationConfig,
    CandidateStatesConfig, CompanyStatesConfig, JobsiteStatesConfig, JobStatesConfig, TimeSheetStatesConfig,
]
