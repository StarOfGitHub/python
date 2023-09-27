import mock

from django_mock_queries.query import MockSet, MockModel, create_model

from r3sourcer.importer.importer import CoreImporter
from r3sourcer.importer.configs import BaseConfig


qs = MockSet(
    MockModel(id=1),
    MockModel(id=2)
)

Model = create_model('col1')
Model.objects = MockSet(Model(col1=1), model=Model)

ModelDep = create_model('id', 'col')
ModelDep.objects = MockSet(Model(id=1, col=Model(col1=2)), model=ModelDep)


class CoreTestConfig(BaseConfig):
    columns = ['col1']
    columns_map = {
        'col1': 'col2'
    }
    model = Model
    dependency = {}


class CoreTestChildConfig(BaseConfig):
    columns = ['col1']
    columns_map = {
        'col1': 'col2'
    }
    lbk_model = 'test'
    model = Model


class CoreTestChildDistinctConfig(BaseConfig):
    columns = ['col1']
    columns_map = {
        'col1': 'col2'
    }
    lbk_model = 'test'
    model = Model
    distinct = ['col1']


class CoreTestDepChildConfig(BaseConfig):
    columns = ['id']
    model = ModelDep
    dependency = {
        'col': CoreTestChildConfig
    }
    lbk_model = 'test'


class CoreTestDepConfig(BaseConfig):
    columns = ['id']
    model = ModelDep
    dependency = {
        'col': CoreTestConfig
    }


class CoreTestDepReqConfig(BaseConfig):
    columns = ['id']
    model = ModelDep
    dependency = {
        'col': CoreTestConfig.override(
            required={'col2', }
        )
    }


class TestCoreImporter:

    def test_dictfetchall(self):
        cursor = mock.MagicMock()
        type(cursor).description = mock.PropertyMock(return_value=[('col1',), ('col2',)])
        cursor.fetchall.return_value = [('test', 'test 1')]

        res = CoreImporter.dictfetchall(cursor)

        assert list(res) == [{'col1': 'test', 'col2': 'test 1'}]

    def test_dictfetchall_duplicated_column(self):
        cursor = mock.MagicMock()
        type(cursor).description = mock.PropertyMock(return_value=[('col1',), ('col1',)])
        cursor.fetchall.return_value = [('test', 'test 1')]

        res = CoreImporter.dictfetchall(cursor)

        assert list(res) == [{'col1': 'test 1'}]

    @mock.patch.object(CoreTestConfig, 'columns_map', new_callable=mock.PropertyMock)
    def test_map_columns(self, mock_columns):
        mock_columns.return_value = {'col1': 'col2'}

        res = CoreImporter.map_columns({'col1': 1, 'col2': 2}, CoreTestConfig)

        assert res == {'col1': 1, 'col2': 1}

    @mock.patch.object(CoreTestConfig, 'columns_map', new_callable=mock.PropertyMock)
    def test_map_columns_empty(self, mock_columns):
        mock_columns.return_value = {}

        res = CoreImporter.map_columns({'col1': 1, 'col2': 2}, CoreTestConfig)

        assert res == {'col1': 1, 'col2': 2}

    @mock.patch.object(CoreTestConfig, 'columns_map', new_callable=mock.PropertyMock)
    def test_map_columns_not_exists(self, mock_columns):
        mock_columns.return_value = {'col3': 'col2'}

        res = CoreImporter.map_columns({'col1': 1, 'col2': 2}, CoreTestConfig)

        assert res == {'col1': 1, 'col2': 2}

    @mock.patch.object(CoreImporter, 'map_columns')
    def test_import_row(self, mock_columns):
        mock_columns.return_value = {'col1': 1}

        res = CoreImporter.import_row({'col1': 1}, CoreTestConfig)

        assert res.col1 == 1

    @mock.patch.object(CoreImporter, 'map_columns')
    def test_import_row_exception(self, mock_columns):
        mock_columns.side_effect = [Exception]

        res = CoreImporter.import_row({'col1': 1}, CoreTestConfig)

        assert res is None

    @mock.patch.object(CoreImporter, 'import_data')
    def test_import_dependencies_with_model(self, mock_imported):
        mock_imported.return_value = Model(col1=10)

        res = CoreImporter.import_dependencies(
            {'id': 1, 'col1': 1}, CoreTestDepChildConfig
        )

        assert 'col' in res
        assert res['col'] is not None
        assert res['col'].col1 == 10

    @mock.patch.object(CoreImporter, 'import_row')
    def test_import_dependencies_without_model(self, mock_imported):
        mock_imported.return_value = Model(col1=10)

        res = CoreImporter.import_dependencies(
            {'id': 1, 'col1': 1}, CoreTestDepConfig
        )

        assert 'col' in res
        assert res['col'] is not None
        assert res['col'].col1 == 10

    def test_import_dependencies_without_deps(self):
        res = CoreImporter.import_dependencies(
            {'id': 1, 'col1': 1}, CoreTestConfig
        )

        assert 'col' not in res

    @mock.patch.object(CoreImporter, 'import_row')
    def test_import_dependencies_is_none(self, mock_imported):
        mock_imported.return_value = None

        res = CoreImporter.import_dependencies(
            {'id': 1, 'col1': 1}, CoreTestDepConfig
        )

        assert 'col' not in res

    @mock.patch.object(CoreImporter, 'import_row')
    def test_import_dependencies_with_required(self, mock_imported):
        mock_imported.return_value = Model(col1=11)

        res = CoreImporter.import_dependencies(
            {'id': 1, 'col1': 11, 'col2': 42}, CoreTestDepReqConfig
        )

        assert 'col2' in res
        assert 'col' in res

    @mock.patch.object(CoreImporter, 'import_row')
    def test_import_dependencies_required_not_match(self, mock_imported):
        mock_imported.return_value = Model(col1=11)

        res = CoreImporter.import_dependencies(
            {'id': 1, 'col1': 11}, CoreTestDepReqConfig
        )

        assert 'col2' not in res
        assert 'col' not in res

    @mock.patch.object(CoreTestChildConfig, 'exists')
    @mock.patch.object(CoreImporter, 'import_row')
    @mock.patch.object(CoreImporter, 'execute_sql')
    def test_import_data(self, mock_rows, mock_imported, mock_exists):
        mock_rows.side_effect = [1, [{'col1': 20, 'id': 1}]]
        mock_imported.return_value = Model(col1=20)
        mock_exists.return_value = False

        res = CoreImporter.import_data(CoreTestChildConfig)

        assert res.col1 == 20

    @mock.patch.object(CoreTestChildDistinctConfig, 'exists')
    @mock.patch.object(CoreImporter, 'import_row')
    @mock.patch.object(CoreImporter, 'execute_sql')
    def test_import_data_distinct(self, mock_rows, mock_imported, mock_exists):
        mock_rows.side_effect = [1, [{'col1': 20, 'id': 1}]]
        mock_imported.return_value = Model(col1=20)
        mock_exists.return_value = False

        res = CoreImporter.import_data(CoreTestChildDistinctConfig)

        assert res.col1 == 20

    @mock.patch.object(CoreTestChildConfig, 'exists')
    @mock.patch.object(CoreImporter, 'import_row')
    @mock.patch.object(CoreImporter, 'execute_sql')
    def test_import_data_with_params(self, mock_rows, mock_imported,
                                     mock_exists):
        mock_rows.side_effect = [1, [{'col1': 20, 'id': 1}]]
        mock_imported.return_value = Model(col1=20)
        mock_exists.return_value = False

        res = CoreImporter.import_data(CoreTestChildConfig, {'param': 1})

        assert res.col1 == 20

    @mock.patch.object(CoreTestChildConfig, 'exists')
    @mock.patch.object(CoreImporter, 'import_row')
    @mock.patch.object(CoreImporter, 'execute_sql')
    def test_import_data_exist(self, mock_rows, mock_imported, mock_exists):
        mock_rows.side_effect = [1, [{'col1': 20, 'id': 1}]]
        mock_imported.return_value = Model(col1=20)
        mock_exists.return_value = True

        res = CoreImporter.import_data(CoreTestChildConfig)

        assert res is None

    @mock.patch.object(CoreTestChildConfig, 'exists')
    @mock.patch.object(CoreImporter, 'import_row')
    @mock.patch.object(CoreImporter, 'execute_sql')
    def test_import_data_exist_with_params(self, mock_rows, mock_imported, mock_exists):
        mock_rows.side_effect = [1, [{'col1': 20, 'id': 1}]]
        mock_imported.return_value = Model(col1=20)
        mock_exists.return_value = True

        res = CoreImporter.import_data(CoreTestChildConfig, {'param': 1})

        assert res is None

    @mock.patch.object(CoreTestChildConfig, 'exists')
    @mock.patch.object(CoreImporter, 'import_dependencies')
    @mock.patch.object(CoreImporter, 'import_row')
    @mock.patch.object(CoreImporter, 'execute_sql')
    def test_import_data_with_dependencies(self, mock_rows, mock_imported,
                                           mock_dependencies, mock_exists):
        mock_rows.side_effect = [1, [{'col1': 20, 'id': 20}]]
        mock_imported.return_value = Model(id=20, col=Model(col1=20))
        mock_dependencies.return_value = {
            'col1': 20,
            'id': 20,
            'col': Model(col=20),
        }
        mock_exists.return_value = False

        res = CoreImporter.import_data(CoreTestDepChildConfig)

        assert res.col.col1 == 20
