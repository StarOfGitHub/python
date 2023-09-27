from datetime import date
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.query_utils import Q
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _

from r3sourcer.apps.core.mixins import MYOBMixin
from r3sourcer.apps.core.models import Company, UnitOfMeasurement
from r3sourcer.apps.pricing.models import PriceListRate
from r3sourcer.helpers.models.abs import UUIDModel
from r3sourcer.apps.skills.managers import SelectRelatedSkillManager, SkillManager


class EmploymentClassification(UUIDModel):

    name = models.CharField(
        max_length=255,
        verbose_name=_('Name')
    )

    class Meta:
        verbose_name = _("Employment Classification")
        verbose_name_plural = _("Employment Classifications")

    def __str__(self):
        return self.name

    @classmethod
    def is_owned(cls):
        return False


class SkillName(UUIDModel):

    name = models.CharField(max_length=127, verbose_name=_("Skill Name"))

    industry = models.ForeignKey(
        'pricing.Industry',
        on_delete=models.PROTECT,
        verbose_name=_('Industry'),
        related_name='skill_names'
    )

    class Meta:
        verbose_name = _("Skill Name")
        verbose_name_plural = _("Skill Names")
        unique_together = [
            'name',
            'industry',
        ]

    def __str__(self):
        return self.name

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                models.Q(industry__in=owner.industries.all())
            ]

    def translation(self, language):
        """ SkillName translation getter """
        try:
            return self.translations.get(language=language).value
        except:
            return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        for company in Company.objects.filter(industries__in=[self.industry]):
            Skill.objects.get_or_create(name=self,
                                        company=company,
                                        defaults={'active': False},
                                        )

        worktype, created = WorkType.objects.get_or_create(name=WorkType.DEFAULT,
                                                           skill_name=self,
                                                           uom=UnitOfMeasurement.objects.get(default=True))

        if created:
            WorkTypeLanguage.objects.create(name=worktype, language_id='en', value=WorkType.DEFAULT)
            WorkTypeLanguage.objects.create(name=worktype, language_id='et', value='Tunnitöö')
            WorkTypeLanguage.objects.create(name=worktype, language_id='ru', value='Почасовая робота')
            WorkTypeLanguage.objects.create(name=worktype, language_id='fi', value='Tunneittainen työ')


class SkillNameLanguage(models.Model):
    name = models.ForeignKey(
        'skills.SkillName',
        related_name='translations',
        on_delete=models.PROTECT,
        verbose_name=_('Skill Name'),
    )
    value = models.CharField(max_length=127, verbose_name=_("Skill Name translation"))
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Skill name language"),
        on_delete=models.CASCADE,
        related_name='skill_names',
    )

    class Meta:
        verbose_name = _("Skill Name Language")
        verbose_name_plural = _("Skill Name Languages")
        unique_together = [
            'name',
            'language',
        ]

    def __str__(self):
        return self.value


class Skill(MYOBMixin, UUIDModel):
    name = models.ForeignKey(
        SkillName,
        related_name='skills',
        on_delete=models.PROTECT,
        verbose_name=_('Skill Name'),
    )

    company = models.ForeignKey(
        'core.Company',
        related_name='skills',
        on_delete=models.CASCADE,
        verbose_name=_('Company')
    )
    # how many candidate system needs to find for backup
    carrier_list_reserve = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_('Carrier List Reserve')
    )

    short_name = models.CharField(
        max_length=15,
        verbose_name=_("Short Name"),
        help_text=_("Abbreviation, for use by staff reports and dashboards"),
        blank=True,
        null=True
    )

    employment_classification = models.ForeignKey(
        EmploymentClassification,
        on_delete=models.PROTECT,
        related_name="skills",
        verbose_name=_("Employment Classification"),
        null=True,
        blank=True
    )
    active = models.BooleanField(default=True, verbose_name=_("Active"))

    tags = models.ManyToManyField(
        'core.Tag',
        related_name='skills',
        through='SkillTag'
    )

    objects = SkillManager()

    class Meta:
        verbose_name = _("Skill")
        verbose_name_plural = _("Skills")
        unique_together = ['name', 'company']

    def __str__(self):
        return f'{self.company.name} - {self.name.name}'

    def get_myob_name(self):
        name = self.short_name
        if not name:
            parts = self.name.name.split(' ')
            parts_len = len(parts)
            trim_size = 1

            if parts_len == 1:
                trim_size = 6
            elif parts_len == 2 or parts_len == 3:
                trim_size = 6 // parts_len

            name = ''.join([p[:trim_size] for p in parts])

        return name[:6]

    def is_priced(self):
        worktypes = WorkType.objects.filter(Q(skill=self) | Q(skill_name=self.name))
        if worktypes:
            active_price_rates = PriceListRate.objects.filter(price_list__company=self.company,
                                                              price_list__effective=True,
                                                              price_list__valid_from__lte=date.today(),
                                                              price_list__valid_until__gte=date.today(),
                                                              worktype__in=worktypes,
                                                              )
            if active_price_rates.exists():
                return True
        return False

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                models.Q(company=owner),
                models.Q(company__regular_companies__master_company=owner)
            ]

    def get_hourly_rate(self):
        # search skill activity rate in job's skill activity rates
        hourly_work = WorkType.objects.filter(name='Hourly work',
                                              skill_name=self.name) \
                                      .first()
        skill_activity = self.skill_rate_ranges.filter(worktype=hourly_work).first()
        return skill_activity.default_rate if skill_activity else None


class SkillBaseRate(UUIDModel):   # TODO delete SkillBaseRate model after uom rates changes will be completed

    skill = models.ForeignKey(
        'skills.Skill',
        on_delete=models.CASCADE,
        related_name="skill_rate_defaults",
        verbose_name=_("Skill")
    )

    hourly_rate = models.DecimalField(
        decimal_places=2,
        max_digits=8,
        verbose_name=_("Hourly Rate"),
        default=0.00
    )

    default_rate = models.BooleanField(
        default=False,
        verbose_name=_("Is Default Rate")
    )

    objects = SelectRelatedSkillManager()

    class Meta:
        verbose_name = _("Skill Base Rate")
        verbose_name_plural = _("Skill Base Rates")
        ordering = ('hourly_rate',)
        unique_together = ('skill', 'hourly_rate')

    @classmethod
    def set_default_rate(cls, sender, instance, created, **kwargs):
        if created and not instance.skill.skill_rate_defaults.exclude(pk=instance.pk).count():
            instance.default_rate = True
            instance.save()

    def save(self, *args, **kwargs):
        super(SkillBaseRate, self).save(*args, **kwargs)

        if self.default_rate:
            default_rates = self.skill.skill_rate_defaults.filter(default_rate=True) \
                                                          .exclude(pk=self.pk)
            if default_rates:
                default_rates.update(default_rate=False)

    def __str__(self):
        return '{} ${}/h'.format(str(self.skill), str(self.hourly_rate))


post_save.connect(SkillBaseRate.set_default_rate, sender=SkillBaseRate)


class SkillTag(UUIDModel):
    tag = models.ForeignKey(
        'core.Tag',
        related_name="skill_tags",
        on_delete=models.CASCADE,
        verbose_name=_("Tag")
    )

    skill = models.ForeignKey(
        'skills.Skill',
        on_delete=models.CASCADE,
        related_name="skill_tags",
        verbose_name=_("Skill")
    )

    class Meta:
        verbose_name = _("Skill Tag")
        verbose_name_plural = _("Skill Tags")
        unique_together = ("tag", "skill")

    def __str__(self):
        return self.skill.short_name or self.skill.name.name

    @classmethod
    def owned_by_lookups(cls, owner):
        if isinstance(owner, Company):
            return [
                models.Q(skill__company=owner),
                models.Q(skill__company__regular_companies__master_company=owner)
            ]


class WorkType(UUIDModel):
    """Model for storing work types"""

    DEFAULT = 'Hourly work'

    skill_name = models.ForeignKey(
        SkillName,
        on_delete=models.CASCADE,
        verbose_name=_('Skill Name'),
        related_name='work_types',
        blank=True,
        null=True,
        help_text="Fill in this field only for System skill activities"
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        verbose_name=_('Skill'),
        related_name='work_types',
        blank=True,
        null=True,
        help_text="Fill in this field only for Company skill activities"
    )

    uom = models.ForeignKey(UnitOfMeasurement,
        verbose_name=_('Unit of measurement'),
        on_delete=models.CASCADE,
        related_name='timesheet_rates'
    )
    name = models.CharField(max_length=127, verbose_name=_("Skill activity name"))

    class Meta:
        verbose_name = _("Skill activity")
        verbose_name_plural = _("Skill activities")
        unique_together = [
            'skill_name',
            'skill',
            'uom',
            'name',
        ]

    def save(self, **kwargs):
        self.clean()
        return super().save(**kwargs)

    def clean(self):
        # Check if object has skill_name or skill but not both
        if not self.skill_name and not self.skill:
            raise ValidationError(_('Please set skill or skill_name field.'))
        if self.skill_name and self.skill:
            raise ValidationError(_('Please set or skill or skill_name field.'))
        # Check if object has unique values
        if self.skill_name and WorkType.objects.exclude(id=self.id) \
                                               .filter(skill_name=self.skill_name,
                                                       uom=self.uom,
                                                       name=self.name) \
                                               .exists():
            raise ValidationError(_("Such skill activity exists"))
        if self.skill and WorkType.objects.exclude(id=self.id) \
                                          .filter(skill=self.skill,
                                                  uom=self.uom,
                                                  name=self.name) \
                                          .exists():
            raise ValidationError(_("Such skill activity exists"))

    def __str__(self):
        if self.name == self.DEFAULT:
            return f"{self.skill_name} {self.name}"
        return f"{self.name} per {self.uom}"

    def is_system(self):
        if self.skill_name:
            return True
        else:
            return False

    def is_hourly(self):
        if self.name == self.DEFAULT:
            return True
        return False

    def get_skill_for_company(self, company):
        if self.skill:
            return self.skill
        else:
            return self.skill_name.skills.filter(company=company).first()

    def translation(self, language):
        """ WorkType translation getter """
        try:
            return self.translations.get(language=language).value
        except:
            return self.name

    def skill_translation(self, language):
        """ Skill name translation getter """
        if self.is_system:
            try:
                return self.skill_name.translation(language)
            except:
                return self.skill_name.name
        else:
            try:
                return self.skill.name.translation(language)
            except:
                return self.skill.name.name

class WorkTypeLanguage(models.Model):
    """Model for storing work type translations"""

    name = models.ForeignKey(
        WorkType,
        related_name='translations',
        on_delete=models.CASCADE,
        verbose_name=_('Work Name'),
    )
    value = models.CharField(max_length=127, verbose_name=_("Transalation"))
    language = models.ForeignKey(
        'core.Language',
        verbose_name=_("Language"),
        on_delete=models.CASCADE,
        related_name='work_types',
    )

    class Meta:
        verbose_name = _("Skill Activity Transalation")
        verbose_name_plural = _("Skill Activity Transalations")
        unique_together = [
            'name',
            'language',
        ]

    def __str__(self):
        return self.value


class SkillRateRange(MYOBMixin, UUIDModel):
    """Model for storing rate ranges"""

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="skill_rate_ranges",
        verbose_name=_("Skill")
    )
    worktype = models.ForeignKey(
        WorkType,
        on_delete=models.CASCADE,
        related_name="skill_rate_ranges",
        verbose_name=_("Skill Activity"),
    )
    upper_rate_limit = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )
    lower_rate_limit = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )
    default_rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
    )
    price_list_upper_rate_limit = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )
    price_list_lower_rate_limit = models.DecimalField(
        decimal_places=2,
        max_digits=16,
        blank=True,
        null=True
    )
    price_list_default_rate = models.DecimalField(
        decimal_places=2,
        max_digits=16,
    )

    class Meta:
        verbose_name = _("Skill Rate Range")
        verbose_name_plural = _("Skill Rate Ranges")
        unique_together = ("skill", "worktype")

    def __str__(self):
        return f"{self.skill.name.name} - {self.worktype.name}"
