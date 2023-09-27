import copy
import logging

from django.db import connections
from django.core.cache import cache

log = logging.getLogger(__name__)


class CoreImporter(object):

    @staticmethod
    def dictfetchall(cursor):
        """Return all rows from a cursor as a dict"""
        columns = [col[0] for col in cursor.description]

        return [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    @classmethod
    def execute_sql(cls, sql, one=False):  # pragma: no cover
        with connections['import'].cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchone()[0] if one else cls.dictfetchall(cursor)

    @classmethod
    def import_data(cls, config, params=None):
        if params is None:
            params = {}

        lbk_query = config.lbk_model.format(**params)
        distinct_query = (
            'DISTINCT ON ({}) '.format(','.join(config.distinct))
            if isinstance(config.distinct, list) else ''
        )
        group_by = ''
        if isinstance(config.distinct, list):
            group_by = 'GROUP BY {}'.format(','.join(config.distinct))
            total = cls.execute_sql(
                "SELECT count(*) FROM "
                "(SELECT {list} FROM {query} {group_by}) as sub".format(
                    query=lbk_query, group_by=group_by,
                    list=','.join(config.distinct)
                ),
                one=True
            )
        else:
            total = cls.execute_sql(
                "SELECT count(*) FROM {} {}".format(lbk_query, group_by),
                one=True
            )
        rows = cls.execute_sql("SELECT {} {} FROM {} order by {}".format(
            distinct_query, config.select, lbk_query, ','.join(
                config.distinct + [config.order_by])
            if isinstance(config.distinct, list) else config.order_by
        ))
        progress_format = '[%{count}d / %{count}d]'.format(
            count=len(str(total))
        )

        print(
            'Importing data from %s LBK model to %s. Total objects: %s' % (
                lbk_query, config.model.__name__, total
            )
        )

        instance = None
        for i, row in enumerate(rows):
            if not params:
                progress_str = progress_format % (i+1, total)
                print('%s id: %s started...' % (
                    progress_str, str(row['id'])
                ))

            if config.exists(row):
                if not params:
                    print('%s Entry %s with id=%s exists' % (
                        progress_str, config.model.__name__, str(row['id'])
                    ))
                continue  # pragma: no cover

            if config.dependency:
                row = cls.import_dependencies(row, config)

            instance = cls.import_row(row, config)

            config.post_process(row, instance)

            if not params:
                print('%s id: %s finished' % (
                    progress_str, str(row['id'])
                ))

        return instance

    @classmethod
    def import_row(cls, row, config):
        try:
            row = cls.map_columns(row, config)
            row = config.prepare_data(row)

            ids_mapping = cache.get('ids_mapping', {})
            row = {k: ids_mapping[v] if v in ids_mapping else v for k, v in row.items()}

            instance = config.process(row)
            return instance
        except Exception as e:
            # TODO: handle right exception
            print(e)

    @classmethod
    def map_columns(cls, row, config):
        col_map = config.columns_map
        if col_map:
            row = copy.copy(row)
        else:
            return row

        for old_name, new_name in col_map.items():
            if old_name in row:
                row[new_name] = row[old_name]
        return row

    @classmethod
    def import_dependencies(cls, row, config):
        for column, dep_config in config.dependency.items():
            required = dep_config.required or []

            if not all(row.get(k, False) for k in required):
                continue

            if dep_config.lbk_model:
                related_obj = cls.import_data(dep_config, params=row)
            else:
                related_obj = cls.import_row(row, dep_config)

            if related_obj is not None:
                row[column] = related_obj

        return row
