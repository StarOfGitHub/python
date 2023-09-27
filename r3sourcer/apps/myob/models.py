import datetime

from django.db import models
from django.utils.translation import ugettext_lazy as _
from model_utils import Choices

from r3sourcer.apps.core.models import Company, User
from r3sourcer.helpers.models.abs import UUIDModel
from r3sourcer.apps.core.managers import AbstractObjectOwnerManager
from r3sourcer.helpers.datetimes import utc_now


class MYOBWatchdogModel(models.Model):
    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created"),
    )

    modified = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated"),
    )

    class Meta:
        abstract = True


class MYOBRequestLog(UUIDModel, MYOBWatchdogModel):

    method = models.CharField(
        verbose_name=_("Method"),
        max_length=16,
        help_text=_("Request method"),
    )

    url = models.CharField(
        verbose_name=_("URL"),
        max_length=2048,
        help_text=_("Requested URL"),
    )

    headers = models.TextField(
        verbose_name=_("Headers"),
        null=True, blank=True,
        help_text=_("Headers sent with request"),
    )

    data = models.TextField(
        verbose_name=_("POST data"),
        null=True, blank=True,
        help_text=_("Request POST data as JSON"),
    )

    json = models.TextField(
        verbose_name=_("JSON content"),
        null=True, blank=True,
        help_text=_("Request JSON content"),
    )

    params = models.TextField(
        verbose_name=_("URL parameters"),
        null=True, blank=True,
        help_text=_("Request URL params as JSON"),
    )

    kwargs = models.TextField(
        verbose_name=_("kwargs"),
        null=True, blank=True,
        help_text=_("Additional kwargs to requests method"),
    )

    resp_status_code = models.PositiveIntegerField(
        verbose_name=_("HTTP response code"),
        null=True, blank=True,
    )

    resp_content = models.TextField(
        verbose_name=_("Response content"),
        null=True, blank=True,
    )

    resp_json = models.TextField(
        verbose_name=_("Response JSON"),
        null=True, blank=True,
    )

    class Meta:
        verbose_name = _("MYOB Request Log")
        verbose_name_plural = _("MYOB Request Logs")


class MYOBAuthData(UUIDModel, MYOBWatchdogModel):
    """
    This model contains information needed for  authentication in MYOB API and fetching company files
    It is called Access Token in MYOB API documentation
    """
    client_id = models.CharField(
        verbose_name=_("Client ID"),
        max_length=64,
        help_text=_("Registered MYOB application API Key")
    )

    client_secret = models.CharField(
        verbose_name=_("Client Secret"),
        max_length=64,
        help_text=_("Registered MYOB application API Secret")
    )

    access_token = models.TextField(
        verbose_name=_("Access Token"),
        max_length=2048,
    )

    refresh_token = models.CharField(
        verbose_name=_("Refresh Token"),
        max_length=1024,
    )

    myob_user_uid = models.CharField(
        verbose_name=_("User UID"),
        max_length=64,
    )

    myob_user_username = models.CharField(
        verbose_name=_(u"User Username"),
        max_length=512
    )

    expires_in = models.PositiveIntegerField(
        verbose_name=_("Expires in (seconds)")
    )

    expires_at = models.DateTimeField(
        verbose_name=_(u"Expires at (datetime)"),
        null=True, blank=True
    )

    user = models.ForeignKey(User, related_name='auth_data', blank=True, null=True, on_delete=models.CASCADE)
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='auth_data',
        blank=True,
        null=True)

    class Meta:
        verbose_name = _("MYOB OAuth2 Data")
        verbose_name_plural = _("MYOB OAuth2 Data")

    def __str__(self):
        return self.client_id

    @classmethod
    def persist(cls, auth_client):
        return cls.objects.update_or_create(
            client_id=auth_client.get_api_key(),
            myob_user_uid=auth_client.get_user_uid(),
            defaults={
                'client_secret': auth_client.get_api_secret(),
                'access_token': auth_client.get_access_token(),
                'refresh_token': auth_client.get_refresh_token(),
                'myob_user_username': auth_client.get_user_username(),
                'expires_in': auth_client.get_expires_in(),
                'expires_at': auth_client.get_expires_at(),
            }
        )


class MYOBCompanyFile(UUIDModel, MYOBWatchdogModel):
    """
    Represents a user's company file in MYOB API
    """
    cf_id = models.CharField(
        verbose_name=_("Company File Id"),
        max_length=64
    )

    cf_uri = models.CharField(
        verbose_name=_("Uri"),
        max_length=2048,
    )

    cf_name = models.CharField(
        verbose_name=_("Company File Name"),
        max_length=512,
    )

    authenticated = models.BooleanField(default=False)
    auth_data = models.ForeignKey(
        'myob.MYOBAuthData',
        related_name='company_file',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _("MYOB Company File")
        verbose_name_plural = _("MYOB Company Files")

    def __str__(self):
        return self.cf_name

    @classmethod
    def persist(cls, myob_client):
        return MYOBCompanyFile.objects.update_or_create(
            cf_id=myob_client.get_cf_id(),
            defaults={
                'cf_uri': myob_client.get_cf_uri(),
                'cf_name': myob_client.get_cf_name()
            }
        )


class MYOBCompanyFileTokenManager(AbstractObjectOwnerManager):

    def enabled(self, date=None):
        date = date or utc_now().date()
        if isinstance(date, datetime.datetime):
            date = date.date()

        return self.get_queryset().filter(
            (models.Q(enable_from__isnull=True) | models.Q(enable_from__lte=date)) &
            (models.Q(enable_until__isnull=True) | models.Q(enable_until__gte=date))
        )


class MYOBCompanyFileToken(UUIDModel, MYOBWatchdogModel):
    """
    Contains all information needed for authorization and fetching information related to a specific company file
    """
    company_file = models.ForeignKey(
        MYOBCompanyFile,
        related_name='tokens',
        on_delete=models.CASCADE,
    )
    auth_data = models.ForeignKey(
        'myob.MYOBAuthData',
        related_name='company_file_token',
        on_delete=models.CASCADE,
    )
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='company_file_tokens'
    )
    cf_token = models.CharField(
        verbose_name=_(u"Company File Token"),
        max_length=32,
    )
    enable_from = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Enable From")
    )
    enable_until = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Enable Until")
    )

    objects = MYOBCompanyFileTokenManager()

    class Meta:
        verbose_name = _("MYOB Company File Token")
        verbose_name_plural = _("MYOB Company File Tokens")

    @classmethod
    def persist(cls, myob_client, company=None):
        auth_data = MYOBAuthData.objects.get(
            client_id=myob_client.auth.get_api_key(),
            myob_user_uid=myob_client.auth.get_user_uid()
        )

        company_file, created = MYOBCompanyFile.persist(myob_client)

        obj, created = MYOBCompanyFileToken.objects.update_or_create(
            company_file=company_file,
            defaults={
                'auth_data': auth_data,
                'cf_token': myob_client.get_cf_token(),
            }
        )
        if company:
            obj.company = company
            obj.save()

        return obj, created

    def is_enabled(self, dt=None):
        if dt is None:
            dt = utc_now()

        date = dt.date()

        return (not self.enable_from or self.enable_from <= date) and \
            (not self.enable_until or self.enable_until >= date)


class MYOBSyncObject(UUIDModel, models.Model):

    SYNC_DIRECTION_CHOICES = Choices(
        ('myob', _('Django to MYOB')),
        ('django', _('MYOB to Django')),
    )

    app = models.CharField(
        verbose_name=_("App"),
        max_length=63
    )

    model = models.CharField(
        verbose_name=_("Model"),
        max_length=63
    )

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
        related_name='sync_objects',
        null=True,
        blank=True
    )

    company_file = models.ForeignKey(
        MYOBCompanyFile,
        on_delete=models.CASCADE,
        verbose_name=_("MYOB Company File"),
        related_name='sync_objects',
        null=True,
        blank=True,
    )

    record = models.UUIDField(
        verbose_name=_("Record ID")
    )

    synced_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_(u"Synced at (datetime)")
    )

    direction = models.CharField(
        max_length=8,
        verbose_name=_("Direction"),
        choices=SYNC_DIRECTION_CHOICES,
        default=SYNC_DIRECTION_CHOICES.myob
    )

    legacy_myob_card_number = models.CharField(
        max_length=15,
        verbose_name=_("Legacy MYOB Card Number"),
        null=True, blank=True
    )

    legacy_confirmed = models.NullBooleanField(
        verbose_name=_("Update legacy record")
    )

    class Meta:
        verbose_name = _("MYOB Sync Object")
        verbose_name_plural = _("MYOB Sync Objects")
