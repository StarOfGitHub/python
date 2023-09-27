from django.db import models
from django.core.exceptions import ValidationError


class ContactLookupField(object):
    """Virtual field used to lookup contact model fields"""

    blank = True
    auto_created = True
    concrete = False
    editable = False
    is_relation = False
    unique = False
    help_text = None
    remote_field = None
    primary_key = False
    one_to_one = False
    one_to_many = False
    serialize = False

    def __init__(self, lookup_model, help_text=None, lookup_name=None, read_only=False):
        super(ContactLookupField, self).__init__()
        self.name = None
        self.attname = None
        self.column = None
        self.lookup_name = lookup_name
        self.lookup_field = None
        self.lookup_model = lookup_model
        self.model = None
        self.read_only = read_only

    def contribute_to_class(self, cls, name):
        self.name = self.attname = self.column = name
        if self.lookup_name is None:
            self.lookup_name = name
        self.model = cls
        cls._meta.add_field(self, private=True)
        setattr(cls, name, self)
        self.setup_lookup_field()

    def setup_lookup_field(self):
        self.lookup_field = self.lookup_model._meta.get_field(self.lookup_name)
        self.unique = self.lookup_field.unique
        self.help_text = self.lookup_field.help_text
        self.verbose_name = self.lookup_field.verbose_name

    def __get__(self, instance, owner):
        if instance is None:
            return self

        try:
            return getattr(instance.contact, self.lookup_name)
        except self.model.contact.RelatedObjectDoesNotExist:
            return None

    def __set__(self, instance, value):
        if self.read_only or instance is None:
            return
        try:
            instance.contact
        except self.model.contact.RelatedObjectDoesNotExist:
            instance.contact = self.lookup_model()
        setattr(instance.contact, self.lookup_name, value)

    def clean(self, value, model_instance):
        if model_instance is not None:
            model_instance = model_instance.contact
        return self.lookup_field.clean(value, model_instance)

    def get_default(self):
        if self.lookup_field is None:
            return None
        return self.lookup_field.get_default()

    def formfield(self):
        return self.lookup_field.formfield()

    def to_python(self, value):
        if isinstance(value, self.lookup_model):
            return value

        if value is None:
            return value

        data = {
            self.lookup_name: value
        }
        try:
            contact = self.lookup_model(**data)
        except:
            raise ValidationError
        return contact


class AliasField(models.Field):

    def contribute_to_class(self, cls, name, private_only=False):
        '''
            virtual_only is deprecated in favor of private_only
        '''
        super(AliasField, self).contribute_to_class(cls, name, private_only=True)
        setattr(cls, name, self)

    def __get__(self, instance, instance_type=None):
        return getattr(instance, self.db_column)
