import decimal
import logging

from r3sourcer.apps.myob.mappers import PayslipMapper
from r3sourcer.apps.myob.services.base import BaseSync


log = logging.getLogger(__name__)


class PayslipSync(BaseSync):
    app = "hr"
    model = "Payslip"
    mapper_class = PayslipMapper

    def _get_resource(self):
        return self.client.api.GeneralLedger.GeneralJournal

    def _get_account(self, display_id):
        return self._get_object_by_field(
            display_id, self.client.api.GeneralLedger.Account, single=True
        )

    def _find_old_myob_card(self, payslip, resource=None):
        return self._get_object_by_field(
            payslip.myob_number.lower(),
            resource=resource,
        )

    def _sync_to(self, payslip, sync_obj=None, partial=False):
        myob_tax = self._get_tax_code('GST')
        myob_account_wages = self._get_account('6-5130')
        myob_account_pay = self._get_account('1-1190')

        myob_account_payg = None
        if payslip.get_payg_pay() > decimal.Decimal():
            myob_account_payg = self._get_account('2-1420')

        myob_account_superann_credit = None
        myob_account_superann_debit = None
        if payslip.get_superannuation_pay() > decimal.Decimal():
            myob_account_superann_credit = self._get_account('2-1415')
            myob_account_superann_debit = self._get_account('6-5120')

        data = self.mapper.map_to_myob(
            payslip, myob_tax, myob_account_wages, myob_account_pay,
            myob_account_payg, myob_account_superann_debit,
            myob_account_superann_credit
        )

        resp = self.resource.post(json=data, raw_resp=True)

        if 200 <= resp.status_code < 400:
            log.info('Payslip %s synced' % payslip.id)
        else:
            log.warning("[MYOB API] Payslip %s: %s", payslip.id, resp.text)
            return False

        return True
