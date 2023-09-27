from django.conf import settings
from ..service import factory


def get_default_user():
    from ..models import Contact, User
    if Contact.objects.filter(email=settings.SYSTEM_USER).exists():
        user = Contact.objects.get(email=settings.SYSTEM_USER).user
    else:
        user = User.objects.create_user(email=settings.SYSTEM_USER,
                                        is_active=False)
    return user


factory.register('get_default_user', get_default_user)


def get_default_company():
    from ..models import Company

    try:
        company = Company.objects.get(is_system=True)
    except Company.DoesNotExist:
        if Company.objects.filter(name=settings.SYSTEM_MASTER_COMPANY).exists():
            company = Company.objects.get(name=settings.SYSTEM_MASTER_COMPANY)
            company.is_system = True
            company.save(update_fields=['is_system'])
        else:
            company = Company.objects.create(
                name=settings.SYSTEM_MASTER_COMPANY,
                type=Company.COMPANY_TYPES.master,
                is_system=True,
            )
    return company
