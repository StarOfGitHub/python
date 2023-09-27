from django.db import models
from django.utils.translation import ugettext_lazy as _


class DefaultTemplateABS(models.Model):
    name = models.CharField(
        max_length=256,
        default="",
        verbose_name=_("Name"),
        db_index=True
    )
    slug = models.SlugField()
    message_text_template = models.TextField(
        default="",
        verbose_name=_("Text template"),
    )
    reply_timeout = models.IntegerField(
        default=10,
        verbose_name=_("Reply timeout"),
        help_text=_("Minutes")
    )
    delivery_timeout = models.IntegerField(
        default=10,
        verbose_name=_("Delivery timeout"),
        help_text=_("Minutes")
    )

    class Meta:
        abstract = True
