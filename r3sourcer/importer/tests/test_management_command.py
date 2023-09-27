import mock

from r3sourcer.importer.importer import CoreImporter
from r3sourcer.importer.management.commands.import_data import Command
from r3sourcer.importer.configs import ALL_CONFIGS


class TestImportData:

    @mock.patch.object(CoreImporter, 'import_data')
    def test_import_data(self, mock_import):
        command = Command()
        command.handle()

        assert mock_import.call_count == len(ALL_CONFIGS)
