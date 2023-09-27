import decimal
import logging

from django.db.models import Q
from django.utils.decorators import method_decorator

from r3sourcer.apps.myob.helpers import get_myob_client
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.apps.myob.services.decorators import myob_enabled_mode
from r3sourcer.helpers.datetimes import utc_now

log = logging.getLogger(__name__)


class BaseSync:
    mapper_class = None
    mapper = None

    resource = None

    _clients = {}

    required_put_keys = ('UID', 'RowVersion', 'DisplayID')

    def __init__(self, client):
        self.client = client
        self.cf_data = client.cf_data
        self.company = self.cf_data.company
        self._clients[self.cf_data.id] = self.client

        self.client.init_api()
        if not self.mapper:
            self.mapper = self.mapper_class and self.mapper_class()
        self.resource = self._get_resource()

    def _switch_client(self, date=None, company_file_token=None):
        """ Did not use maybe deprecated"""
        kwargs = {
            'company': self.company,
            'date': date,
        }
        if company_file_token is not None:
            kwargs = {'cf_id': company_file_token.company_file.cf_id}

        client = get_myob_client(**kwargs)

        if client is None or client.cf_data.id == self.client.cf_data.id:
            return

        if client.cf_data.id not in self._clients:
            client.init_api()
            self.client = client

            self._clients[client.cf_data.id] = client
        else:
            self.client = self._clients[client.cf_data.id]

        self.resource = self._get_resource()

    def _update_sync_object(self, instance, legacy_number=None, direction=MYOBSyncObject.SYNC_DIRECTION_CHOICES.myob):
        sync_obj = self._get_sync_object(instance, direction=direction)

        created = False
        if not sync_obj:
            sync_obj = MYOBSyncObject.objects.create(
                app=self.app,
                model=self.model,
                record=instance.id,
            )
            created = True

        if not created:
            sync_obj.synced_at = utc_now()
        if self.company:
            sync_obj.company = self.company
        if legacy_number:
            sync_obj.legacy_myob_card_number = legacy_number
        if direction:
            sync_obj.direction = direction

        sync_obj.company_file = self.client.cf_data.company_file
        sync_obj.save()

    def _get_sync_objects_for_type(self, direction=MYOBSyncObject.SYNC_DIRECTION_CHOICES.myob):
        sync_obj_qs = MYOBSyncObject.objects.filter(
            app=self.app,
            model=self.model,
            direction=direction,
            company_file=self.client.cf_data.company_file
        )

        if self.company:
            qry = Q(company=self.company)
            if not self.company.parent:
                qry |= Q(company__isnull=True)
        else:
            qry = Q(company__isnull=True) | Q(company__parent__isnull=True)

        return sync_obj_qs.filter(qry)

    def _get_sync_object(self, instance, direction=MYOBSyncObject.SYNC_DIRECTION_CHOICES.myob):
        """
        Return MYOBSyncObject instance by object.

        :param instance: object Model subclass
        :param direction: str MYOBSyncObject.SYNC_DIRECTION_CHOICES
        :return: instance of MYOBSyncObject
        """

        sync_obj_qs = self._get_sync_objects_for_type(direction)
        return sync_obj_qs.filter(record=instance.id).first()

    def _is_synced(self, instance, sync_obj=None):
        """
        Check if object was synced.

        :param instance: object Model subclass
        :param sync_obj: object MYOBSyncObject
        :return: bool or None
        """

        if not sync_obj:
            sync_obj = self._get_sync_object(instance)

        if sync_obj:
            return instance.updated_at <= sync_obj.synced_at
        return

    def _is_synced_from_myob(self, instance, sync_obj=None):
        if not sync_obj:
            sync_obj = self._get_sync_object(
                instance, direction=MYOBSyncObject.SYNC_DIRECTION_CHOICES.django
            )

        if sync_obj:
            return instance.updated_at >= sync_obj.synced_at
        return

    def _get_object(self, params, resource=None, single=False):
        """
        Search remote resources from myob service.

        :param params: dict Search fields
        :param resource: object MYOBSyncObject
        :param single: bool Use for search single object
        :return: dict, list or None
        """

        resource = resource or self.resource
        resp = resource.get(raw_resp=True, params=params)

        try:
            resp = resp.json(parse_float=decimal.Decimal)
        except ValueError:
            log.warning('[MYOB API] Response error %s: %s', resp.status_code, resp.text)
            return

        if 'Errors' in resp:
            for error in resp['Errors']:
                log.warning('[MYOB API] params: %s, error: %s', params, error['Message'])
            return
        if single:
            return resp['Items'][0] if resp['Count'] else None
        return resp

    def _get_object_by_field(self, value, resource=None, myob_field='DisplayID', single=False):
        if value is None:
            return
        return self._get_object(
            {"$filter": "{} eq '{}'".format(myob_field, value.replace("'", "''"))},
            resource=resource, single=single
        )

    def _get_resource(self):
        return None

    def _get_data_to_update(self, existing, new, deep=False, if_not_exists=None):
        if_not_exists = if_not_exists or []
        for key, value in existing.items():
            if not value:
                continue
            if key in self.required_put_keys:
                new[key] = value
                continue
            if key in if_not_exists and key not in new:
                new[key] = value
                continue

            if key in new or deep:
                if isinstance(value, dict):
                    if deep and value.get('UID'):
                        if key not in new:
                            new[key] = {'UID': value['UID']}
                    else:
                        new_data = self._get_data_to_update(value, new.get(key, {}), True, if_not_exists=if_not_exists)
                        new[key] = new_data
                elif isinstance(value, list):
                    new_data = self._get_list_data_to_update(value, new.get(key, []))
                    new[key] = new_data
                elif new.get(key) is None or new.get(key) == '':
                    new[key] = value

        return new

    def _get_list_data_to_update(self, existing, new):
        if len(existing) == 0:
            return new
        result = new.copy()

        if not isinstance(existing[0], dict):
            return result

        add_only_param = False
        if existing[0].get('UID'):
            param = 'UID'
            add_only_param = True
        elif existing[0].get('Location'):
            param = 'Location'
        else:
            return result

        new_items = dict(map(lambda x: (x.get(param), x), result))
        for item in existing:
            existing_key = item[param]
            if existing_key not in new_items:
                result.append({param: existing_key} if add_only_param else item)
            elif not add_only_param:
                new_item = new_items[existing_key]
                new_item.update(self._get_data_to_update(item, new_item, True))

        return result

    def _sync_to(self, instance, sync_obj=None, partial=False):
        raise NotImplementedError()

    def _get_myob_existing_resp(self, instance, myob_card_number, sync_obj=None, field_name='DisplayID', resource=None):
        """
        Search remote resource by field.

        :param instance: Model subclass instance
        :param myob_card_number: str Remote ID (DisplayID)
        :param sync_obj: MYOBSyncObject instance
        :param field_name: str Field name for filtering
        :param resource: class self.client.api
        :return:
        """

        old_myob_card_number = sync_obj and sync_obj.legacy_myob_card_number
        if old_myob_card_number:
            myob_card_number = old_myob_card_number

        myob_resp = self._get_object_by_field(myob_card_number, myob_field=field_name, resource=resource)
        if not myob_resp or not myob_resp['Count']:
            old_myob_card = self._find_old_myob_card(instance, resource=resource)
            if old_myob_card:
                myob_resp = old_myob_card
                if myob_resp['Count']:
                    myob_card_number = old_myob_card['Items'][0][field_name]
                    old_myob_card_number = myob_card_number

        return myob_card_number, old_myob_card_number, myob_resp

    def _find_old_myob_card(self, instance, resource=None):
        raise NotImplementedError()

    def _get_tax_code(self, code):
        return self._get_object_by_field(
            code, self.client.api.GeneralLedger.TaxCode, 'Code', True
        )

    @method_decorator(myob_enabled_mode)
    def sync_to_myob(self, instance, partial=False):
        if self.client is None:
            log.info('MYOB client is not defined')
            return

        # TODO: fix switch client
        # self._switch_client(instance.updated_at)

        cf_data = self.client.cf_data
        if not cf_data.is_enabled(instance.updated_at):
            log.warning('%s Company File is not enabled', str(cf_data.company_file))
            return

        sync_obj = self._get_sync_object(instance)
        # WARNING: If uncomment this line re-sync should not work
        # if sync_obj and self._is_synced(instance, sync_obj=sync_obj) and partial:
        #     return

        res = self._sync_to(instance, sync_obj, partial)
        if res:
            self._update_sync_object(instance)
