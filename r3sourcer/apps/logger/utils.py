from crum import get_current_request
from django.contrib.auth import get_user_model
from django.conf import settings


def get_default_user():
    """
    Gets first superuser
    :return: first superuser of the system
    """
    if 'r3sourcer.apps.core' in settings.INSTALLED_APPS:
        from r3sourcer.apps.core.service import factory
        return factory.get_instance('get_default_user')
    else:
        cls = get_user_model()
        if cls.objects.filter(email=settings.SYSTEM_USER).exists():
            user = cls.objects.get(email=settings.SYSTEM_USER)
        else:
            user = cls.objects.create_user(username=settings.SYSTEM_USER,
                                           email=settings.SYSTEM_USER,
                                           is_active=False)
        return user


def get_current_user():
    """
    Gets current user from request or from db
    :return: current user of the system
    """
    request = get_current_request()
    if request and request.user and request.user.is_authenticated:
        default_user = request.user
    else:
        default_user = get_default_user()
    return default_user


def get_field_value(instance, field):
    """
    Gets value of the field. If the field is ForeignKey returns id of the related object
    :param instance: instance
    :param field: field of the instance
    :return: value of the field
    """
    if field.get_internal_type() == "ForeignKey" and getattr(instance, field.name):
        new_value = getattr(instance, field.name).pk
    else:
        new_value = getattr(instance, field.name)
    return new_value


def get_field_value_by_field_name(instance, field_name):
    """
    Gets value of the field by field's name
    """
    field = instance.__class__._meta.get_field(field_name)
    return get_field_value(instance, field)


def format_range(range_values):
    return "'%s'" % "','".join(map(str, range_values))
