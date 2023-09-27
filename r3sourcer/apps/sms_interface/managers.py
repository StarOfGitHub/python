from django.db.models import Q

from r3sourcer.apps.core.managers import AbstractObjectOwnerManager, AbstractObjectOwnerQuerySet


class SMSMessageObjectOwnerQueryset(AbstractObjectOwnerQuerySet):

    def get_lookups(self, _obj, path=''):
        from r3sourcer.apps.core.models import Contact

        owned_contacts = Contact.objects.owned_by(_obj).values_list('phone_mobile', flat=True)

        return [
            Q(from_number__in=owned_contacts),
            Q(to_number__in=owned_contacts),
        ]


class SMSMessageObjectOwnerManager(AbstractObjectOwnerManager):

    def get_queryset(self):
        return SMSMessageObjectOwnerQueryset(self.model, using=self._db)
