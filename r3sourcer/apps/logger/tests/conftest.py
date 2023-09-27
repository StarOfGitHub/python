import pytest

from django.db import models
from django.contrib.auth import get_user_model

from r3sourcer.apps.logger.manager import get_endless_logger
from r3sourcer.apps.logger.models import LogHistory


class NameModel(models.Model):
    name = models.CharField(max_length=63)


class ModelForAutodiscover(models.Model):
    name = models.CharField(max_length=63)
    rel = models.ForeignKey(NameModel, null=True)

    @classmethod
    def use_logger(cls):
        return True


@pytest.fixture()
def test_model_for_autodiscover(db):
    return ModelForAutodiscover


@pytest.fixture()
def test_instance(db):
    obj = NameModel.objects.create(name='test name')
    return obj


@pytest.fixture()
def test_model(db):
    return NameModel


@pytest.fixture()
def user(db):
    User = get_user_model()
    return User.objects.create_superuser(email="test@test.com", password="TestPASS12")


@pytest.fixture(autouse=True)
def clickhouse_cleanup():
    logger = get_endless_logger()
    logger.logger_database.drop_table(LogHistory)
    logger.logger_database.create_table(LogHistory)
