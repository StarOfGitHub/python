from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.db import models
from django.db.models.base import Model

from r3sourcer.helpers.models.abs import UUIDModel
from r3sourcer.apps.myob.models import MYOBCompanyFile


class SAASCompanySettings(Model):

    candidate_sale_commission = models.DecimalField(
        'Candidate sale commission',
        decimal_places=2,
        max_digits=5,
        default=20.0,
    )

    class Meta:
        verbose_name = "SAAS company settings"


class CompanySettings(UUIDModel):
    company = models.OneToOneField(
        'core.Company',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='company_settings')
    logo = models.ImageField(null=True, blank=True)
    color_scheme = models.CharField(null=True, blank=True, max_length=32)
    font = models.CharField(null=True, blank=True, max_length=32)
    forwarding_number = models.CharField(null=True, blank=True, max_length=32)
    billing_email = models.CharField(max_length=255, blank=True, null=True)
    sms_enabled = models.BooleanField(default=True)
    pre_shift_sms_enabled = models.BooleanField(default=True)
    pre_shift_sms_delta = models.PositiveIntegerField(default=90)
    invoice_template = models.TextField(null=True, blank=True, default='')
    advance_state_saving = models.BooleanField(default=False)
    allow_job_creation = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Company settings"
        verbose_name_plural = "Company settings"


class MYOBAccount(UUIDModel):
    uid = models.UUIDField(unique=True)
    name = models.CharField(max_length=63)
    display_id = models.CharField(max_length=63)
    classification = models.CharField(max_length=63)
    type = models.CharField(max_length=63)
    number = models.CharField(max_length=63)
    description = models.CharField(max_length=255)
    is_active = models.BooleanField()
    level = models.IntegerField()
    opening_balance = models.DecimalField(decimal_places=2, max_digits=16)
    current_balance = models.DecimalField(decimal_places=2, max_digits=16)
    is_header = models.BooleanField()
    uri = models.CharField(max_length=255)
    row_version = models.CharField(max_length=255)
    company_file = models.ForeignKey(
        'myob.MYOBCompanyFile',
        blank=True,
        null=True,
        related_name='accounts',
        on_delete=models.CASCADE
    )

    def __str__(self):
        return '{} - {}'.format(self.number, self.name)


class MYOBSettings(UUIDModel):
    company = models.OneToOneField(
        'core.Company',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='myob_settings')

    # form fields
    invoice_company_file = models.ForeignKey(MYOBCompanyFile,
                                             blank=True,
                                             null=True,
                                             on_delete=models.SET_NULL,
                                             related_name='invoice_company_files')

    invoice_activity_account = models.ForeignKey(MYOBAccount,
                                                 blank=True,
                                                 null=True,
                                                 on_delete=models.SET_NULL)

    timesheet_company_file = models.ForeignKey(MYOBCompanyFile,
                                               blank=True,
                                               null=True,
                                               on_delete=models.SET_NULL,
                                               related_name='timesheet_company_files')

    # last refreshed
    payroll_accounts_last_refreshed = models.DateTimeField(blank=True, null=True)
    company_files_last_refreshed = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "MYOB settings"
        verbose_name_plural = "MYOB settings"

    def get_client_myob_company_file(self):
        if self.company_client_labour_hire:
            return self.company_client_labour_hire.company_file.tokens.filter(company=self.company).first()
        if self.company_client_gst:
            return self.company_client_gst.company_file.tokens.filter(company=self.company).first()
        if self.company:
            return self.company.company_file_tokens.first()


class GlobalPermissionManager(models.Manager):
    def get_queryset(self):
        return super(GlobalPermissionManager, self).get_queryset().filter(content_type__model='global_permission')


class GlobalPermission(Permission):
    """A global permission, not attached to a model"""

    CONTENT_TYPE = 'global_permission'
    objects = GlobalPermissionManager()

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        content_type, _ = ContentType.objects.get_or_create(model=self.CONTENT_TYPE, app_label=self._meta.app_label)
        self.content_type = content_type
        super(GlobalPermission, self).save(*args, **kwargs)
