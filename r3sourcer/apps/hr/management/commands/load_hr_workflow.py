import os

from r3sourcer.apps.core.management.commands.load_workflow import (
    Command as WorkflowCommand
)


class Command(WorkflowCommand):

    def handle(self, *args, **options):
        company_id = options['company_id']

        basepath = os.path.dirname(__file__)
        filepath = os.path.abspath(os.path.join(
            basepath, "..", "..", "fixtures", "hr_workflow_nodes.json")
        )

        self._load_fixtures(filepath, company_id)
