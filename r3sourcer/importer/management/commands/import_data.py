from django.core.management.base import BaseCommand

from r3sourcer.importer.configs import ALL_CONFIGS
from r3sourcer.importer.importer import CoreImporter


class Command(BaseCommand):

    def handle(self, *args, **options):
        for config in ALL_CONFIGS:
            CoreImporter.import_data(config)
