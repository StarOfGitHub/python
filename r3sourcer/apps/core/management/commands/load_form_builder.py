import json
import os
import tempfile

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from r3sourcer.helpers.datetimes import utc_now


class Command(BaseCommand):

    def _load_fixtures(self, file_name):
        fixture_file = tempfile.NamedTemporaryFile(suffix='.json')

        try:
            with open(file_name, "r") as json_file:
                data = json.load(json_file)

            for el in data:
                model_parts = el["fields"]["content_type"].split('.')
                ct_model = ContentType.objects.get_by_natural_key(
                    model_parts[0],
                    model_parts[1]
                )
                el["fields"]["content_type"] = ct_model.id
                el["fields"]["created_at"] = utc_now().isoformat()
                el["fields"]["updated_at"] = utc_now().isoformat()

            with open(fixture_file.name, "w") as jsonFile:
                json.dump(data, jsonFile)
        except Exception as e:
            raise CommandError(e)

        call_command('loaddata', fixture_file.name)

        fixture_file.close()

    def handle(self, *args, **options):
        basepath = os.path.dirname(__file__)
        filepath = os.path.abspath(os.path.join(
            basepath, "..", "..", "fixtures", "form_builder.json")
        )

        self._load_fixtures(filepath)
