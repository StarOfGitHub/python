from django.db import models


class LoggerModel(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    by = models.CharField(max_length=120)
    at = models.CharField(max_length=120)
    object_id = models.CharField(max_length=120, null=True, blank=True)
    transaction_type = models.CharField(max_length=120)
    timestamp = models.CharField(max_length=120)
    model = models.CharField(max_length=120)

    objects = models.QuerySet().none()

    class Meta:
        abstract = True
        verbose_name = 'Log'


class LoggerDiffModel(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    field = models.CharField(max_length=120)
    old_value = models.CharField(max_length=120)
    new_value = models.CharField(max_length=120)

    objects = models.QuerySet().none()

    class Meta:
        abstract = True
        verbose_name = 'Log Diff'
