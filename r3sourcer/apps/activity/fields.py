from r3sourcer.apps.core.service import factory


class FactoryLookupField(object):
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

    def __init__(self, lookup_field_object_name, lookup_field_object_id, help_text=None, lookup_name=None, read_only=False):
        super(FactoryLookupField, self).__init__()

        # lookup settings
        self.lookup_field_object_name = lookup_field_object_name
        self.lookup_field_object_id = lookup_field_object_id

        self.name = "Lookup field"
        self.attname = None
        self.column = None
        self.lookup_name = 'asdasd'
        self.read_only = False
        self.help_text = help_text

    def contribute_to_class(self, cls, name):
        self.name = self.attname = self.column = name
        if self.lookup_name is None:
            self.lookup_name = name
        self.model = cls
        setattr(cls, name, self)

    def __get__(self, instance, owner):
        if instance is None:
            return None
        return instance.get_related_entity()

    def __set__(self, instance, value):
        if self.read_only or instance is None:
            return

        if value == self.model.UNRELATED_TYPE:
            setattr(instance, self.lookup_field_object_id, None)
            setattr(instance, self.lookup_field_object_name, '')
        else:
            # set value
            setattr(instance, self.lookup_field_object_name, factory.get_factored_name(value))
            setattr(instance, self.lookup_field_object_id, value.id)
