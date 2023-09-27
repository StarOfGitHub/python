import json
import os
import tempfile

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from r3sourcer.apps.core.utils.user import get_default_company
from r3sourcer.apps.core.models.workflow import CompanyWorkflowNode
from r3sourcer.helpers.datetimes import utc_now


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--company_id', dest='company_id', type=str,
                            help='Use entered id instead of system company\'s',
                            default=str(get_default_company().id))

    def _load_fixtures(self, file_name, company_id):
        fixture_file = tempfile.NamedTemporaryFile(suffix='.json')

        pk_list = []
        try:
            with open(file_name, "r") as json_file:
                data = json.load(json_file)

            for el in data:
                if "workflownode" in el["model"]:
                    pk_list.append(el["pk"])
                elif "workflow" in el["model"]:
                    model_parts = el["fields"]["model"].split('.')
                    ct_model = ContentType.objects.get_by_natural_key(
                        model_parts[0],
                        model_parts[1]
                    )
                    el["fields"]["model"] = ct_model.id

                el["fields"]["created_at"] = utc_now().isoformat()
                el["fields"]["updated_at"] = utc_now().isoformat()

            with open(fixture_file.name, "w") as jsonFile:
                json.dump(data, jsonFile)
        except Exception as e:
            raise CommandError(e)

        call_command('loaddata', fixture_file.name)

        fixture_file.close()

        for pk in pk_list:
            CompanyWorkflowNode.objects.get_or_create(company_id=company_id, workflow_node_id=pk)

    def handle(self, *args, **options):
        company_id = options['company_id']

        basepath = os.path.dirname(__file__)
        filepath = os.path.abspath(os.path.join(
            basepath, "..", "..", "fixtures", "system_workflow_nodes.json")
        )

        self._load_fixtures(filepath, company_id)
