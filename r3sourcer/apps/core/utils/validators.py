from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _


def string_is_numeric(value: str):
    if not value.isdigit():
        raise ValidationError(_("Value must be numeric"))


def build_validator_for_unique(model_cls, field_name):
    def validate_unique_value(value):
        if model_cls.objects.filter(**{field_name: value}).exists():
            raise ValidationError(_("Should be unique"))
    return validate_unique_value
