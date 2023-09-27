import warnings


class FactoryException(Exception):
    pass


class Stub(object):
    def __init__(self, message=None):
        super(Stub, self).__init__()
        self.__message = message

    def __warn__(self, *args, **kwargs):
        if self.__message:
            warnings.warn(self.__message)
        return Stub(message=self.__message)

    __getattr__ = __warn__
    __getitem__ = __warn__
    __call__ = __warn__


class FactoryService(object):
    def __init__(self):
        super(FactoryService, self).__init__()
        self.instance_classes = dict()
        self.stub_class = Stub

    def get_instance_class(self, name, fail_fast=False):
        try:
            return self.instance_classes[name]
        except KeyError:
            message = 'Instance cannot be factored for name {!r}'.format(name)
            if fail_fast:
                raise FactoryException(message)
            return self.stub_class(message)

    def get_instance(self, name, fail_fast=False, *args, **kwargs):
        instance_class = self.get_instance_class(name, fail_fast)
        if isinstance(instance_class, Stub):
            return instance_class
        elif callable(instance_class):
            return instance_class(*args, **kwargs)
        return instance_class

    def register(self, name, instance_class):
        self.instance_classes[name] = instance_class

    def unregister(self, name):
        self.instance_classes.pop(name, None)

    def get_factored_name(self, instance_class):
        for key, value in self.instance_classes.items():
            if isinstance(value, type) and value == instance_class or isinstance(value, object) and \
                            type(instance_class) == value:
                return key


factory = FactoryService()
