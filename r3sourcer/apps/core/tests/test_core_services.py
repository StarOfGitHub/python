import pytest

from r3sourcer.apps.core.service import FactoryService, Stub, FactoryException


class TestFactoryStub(object):
    def test_stub_attributes(self):
        """Expect getattr on stub returns None and warning is shown"""
        stub = Stub('Dont do that!')
        with pytest.warns(UserWarning) as record:
            assert isinstance(stub.aaa, Stub)
        assert len(record) == 1

    def test_stub_items(self):
        """Expect getitem on stub returns None and warning is shown"""
        stub = Stub('Dont do that!')
        with pytest.warns(UserWarning) as record:
            assert isinstance(stub['aaa'], Stub)
        assert len(record) == 1

    def test_stub_call(self):
        """Expect stub invokation returns None and warning is shown"""
        stub = Stub('Dont do that!')
        with pytest.warns(UserWarning) as record:
            assert isinstance(stub(), Stub)
        assert len(record) == 1


class TestFactoryService(object):
    @pytest.fixture
    def empty_factory(self):
        return FactoryService()

    @pytest.fixture(scope='session')
    def dumb_type(self):
        return type('KnownType', (object,), dict())

    @pytest.fixture
    def dumb_factory(self, dumb_type):
        "Make factory with known type that can be checked"
        factory = FactoryService()
        factory.register('dumb_type', dumb_type)
        return factory

    def test_factory_register_usecase(self, empty_factory):
        """Test factory registry collection conform to added and removed classes"""
        type1 = type('type1', (object,), dict())
        type2 = type('type2', (object,), dict())

        assert not empty_factory.instance_classes

        empty_factory.register('type1', type1)
        assert dict(type1=type1) == empty_factory.instance_classes

        empty_factory.register('type2', type2)
        assert dict(type1=type1, type2=type2) == empty_factory.instance_classes

        empty_factory.unregister('type2')
        assert dict(type1=type1) == empty_factory.instance_classes

    def test_factory_unregister_silent(self, empty_factory):
        """Expect unregister silently executed"""
        empty_factory.unregister('ssssssss')

    def test_factory_reregister(self, empty_factory):
        """Expect register replaces old instance"""
        empty_factory.unregister('ssssssss')

    def test_factory_get_instance(self, dumb_factory, dumb_type):
        """Test get_instance returns instance of expected class"""
        instance_class = dumb_factory.get_instance('dumb_type')
        assert isinstance(instance_class, dumb_type)

    def test_factory_get_instance_fail_fast(self, dumb_factory):
        """Test get_instance fail fast when no classes registered for that name"""
        with pytest.raises(FactoryException):
            dumb_factory.get_instance('ssssssss', fail_fast=True)

    def test_factory_get_instance_stub(self, dumb_factory):
        """Test get_instance returns stub instance when no classes registered for that name"""
        instance_class = dumb_factory.get_instance('ssssssss')
        assert isinstance(instance_class, Stub)

    def test_factory_get_instance_class(self, dumb_factory, dumb_type):
        """Test get_instance_class returns expected class"""
        instance_class = dumb_factory.get_instance_class('dumb_type')
        assert dumb_type is instance_class

    def test_factory_get_instance_class_fail_fast(self, dumb_factory):
        """Test get_instance_class fail fast when no class supplied"""
        with pytest.raises(FactoryException):
            dumb_factory.get_instance_class('ssssssss', fail_fast=True)

    def test_factory_get_instance_class_stub(self, dumb_factory):
        """Test get_instance_class returns stub instance when no class supplied"""
        instance_class = dumb_factory.get_instance_class('ssssssss')
        assert isinstance(instance_class, Stub)
