import math
from datetime import datetime

from django.conf import settings
from django.utils.formats import date_format

from r3sourcer.apps.core.models import WorkflowObject, Company
from r3sourcer.apps.hr.utils.utils import get_invoice_rule


class BSBNumberError(ValueError):
    """
    Raised when cannot map BSB Number
    """


def format_date_to_myob(date_time, only_date=False):
    if isinstance(date_time, datetime):
        date_time = date_time.date()
    return date_time and date_format(date_time, settings.DATE_MYOB_FORMAT)


def get_formatted_abn(business_id):
    abn = None
    if business_id and len(business_id) == 11:
        abn = '{}{} {}{}{} {}{}{} {}{}{}'.format(*business_id)
    elif business_id and len(business_id) == 14:
        abn = business_id

    return abn


class StandardPayMapMixin:
    def map_standard_pay(self, payroll_details_uid, payroll_categories, base_category=None, memo=None):
        data = {
            'EmployeePayrollDetails': {'UID': payroll_details_uid},
            'PayrollCategories': []
        }
        if memo:
            data['Memo'] = memo[:255]

        base_category_uid = None
        if base_category and base_category['Count']:
            base_category_uid = base_category['Items'][0]['UID']

        for payroll_category in payroll_categories:
            payroll_category_id = payroll_category['PayrollCategory']['UID']
            item = {
                'PayrollCategory': {'UID': payroll_category_id},
                'IsCalculated': payroll_category['IsCalculated']
            }
            if not payroll_category['IsCalculated']:
                item.update({
                    'Hours': payroll_category['Hours'],
                    'Amount': payroll_category['Amount'],
                })
            if payroll_category_id == base_category_uid:
                item['Hours'] = 0
                if not payroll_category['IsCalculated']:
                    item['Amount'] = 0
            if payroll_category['Job']:
                item['Job'] = {'UID': payroll_category['Job']['UID']}

            data['PayrollCategories'].append(item)

        return data


class ContactMapper:

    def _map_address_to_myob(self, address, idx=1):
        myob_address = {
            'Location': idx,
        }

        if not address:
            return myob_address

        myob_address.update({
            'City': address.city.name if address.city else '',
            'Street': address.street_address,
            'PostCode': address.postal_code,
            'State': address.state.name if address.state else '',
            'Country': address.country.name,
        })

        return myob_address

    def _map_contact_to_myob(self, contact_obj):
        myob_address = {
            'Email': contact_obj.email,
            'Location': 1,
        }
        if contact_obj.phone_mobile:
            myob_address['Phone1'] = str(contact_obj.phone_mobile)
        contact_active_address = contact_obj.active_address
        if contact_active_address:
            myob_address.update(self._map_address_to_myob(contact_active_address))

        first_name = contact_obj.first_name
        last_name = contact_obj.last_name
        if not last_name and first_name:
            name_parts = first_name.split(' ')
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ''

        data = {
            'FirstName': first_name[:20].strip(),
            'LastName': last_name[:30].strip(),
            'Addresses': [myob_address],
            'IsActive': contact_obj.get_availability(),
        }

        if contact_obj.notes.exists():
            data['Notes'] = ' | '.join(
                contact_obj.notes.values_list('note', flat=True)
            )[:255]

        return data

    def _map_extra_data_to_myob(self, contact):
        return {}

    def map_to_myob(self, contact, *args, **kwargs):
        data = {
            'IsIndividual': True,
        }
        data.update(self._map_contact_to_myob(contact.contact))
        data.update(self._map_extra_data_to_myob(contact))

        return data


class InvoiceMapper(ContactMapper):
    @classmethod
    def address(cls, line):
        return "{} {}".format(line.street_address, line.city)

    @classmethod
    def candidate_contact(cls, line):
        name = '{} {}'.format(line.candidate_first_name, line.candidate_last_name)
        if line.candidate_title:
            name = '{} {}'.format(line.candidate_title, name)
        return name

    def get_description(self, line, invoice_rule):
        candidate_contact = '' if invoice_rule.show_candidate_name is False else self.candidate_contact(line)
        return '{}\n{}\n{}'.format(candidate_contact, line.notes, self.address(line))

    def invoice_line(self, invoice, line, tax_codes, activity_uid, job):
        invoice_rule = get_invoice_rule(invoice.customer_company)
        line = {
            "Date": format_date_to_myob(line.date),
            "Hours": line.units,
            "Rate": line.unit_price,
            "Total": math.ceil(line.unit_price * line.units * 100) / 100,
            "Description": self.get_description(line, invoice_rule),
            "TaxCode": {"UID": tax_codes[line.vat_name]},
            "Units": line.units,
            "Job": {"UID": job['UID']},
            "Activity": {"UID": activity_uid}
        }
        return line

    def map_to_myob(self, invoice, lines, customer_uid, salesperson=None):
        data = {
            "Date": format_date_to_myob(invoice.date),
            "Customer": {'UID': customer_uid},
            "TotalTax": invoice.tax,
            "TotalAmount": invoice.total_with_tax,
            "Status": "Open",
            "Number": invoice.number,
            "CustomerPurchaseOrderNumber": invoice.order_number[:20],
            "IsTaxInclusive": False,
            "Terms": {
                "PaymentIsDue": CompanyMapper.PAYMENT_IS_DUE_MAP.get(invoice.customer_company.terms_of_payment),
                "BalanceDueDate": invoice.customer_company.payment_due_date
            },
            'Lines': lines}

        if salesperson:
            data["SalesPerson"] = {
                "UID": salesperson["UID"]
            }

        return data


class PayslipMapper:

    def map_to_myob(self, payslip, tax, account_wages, account_pay,
                    account_payg=None, account_superann_debit=None,
                    account_superann_credit=None):
        data = {
            'DateOccurred': format_date_to_myob(payslip.payment_date),
            'IsTaxInclusive': False,
            'IsYearEndAdjustment': False,
        }

        lines = [{
            'Account': {'UID': account_pay['UID']},
            'TaxCode': {'UID': tax['UID']},
            'Amount': payslip.get_gross_pay(),
            'IsCredit': True,
        }, {
            'Account': {'UID': account_wages['UID']},
            'TaxCode': {'UID': tax['UID']},
            'Amount': payslip.get_wage_pay(),
            'IsCredit': False
        }]

        if account_payg:
            lines.append({
                'Account': {'UID': account_payg['UID']},
                'TaxCode': {'UID': tax['UID']},
                'Amount': payslip.get_payg_pay(),
                'IsCredit': True
            })

        if account_superann_debit and account_superann_credit:
            lines.extend([{
                'Account': {'UID': account_superann_credit['UID']},
                'TaxCode': {'UID': tax['UID']},
                'Amount': payslip.get_superannuation_pay(),
                'IsCredit': True
            }, {
                'Account': {'UID': account_superann_debit['UID']},
                'TaxCode': {'UID': tax['UID']},
                'Amount': payslip.get_superannuation_pay(),
                'IsCredit': False
            }])

        data['Lines'] = lines

        return data


class ActivityMapper:
    TYPE_HOURLY = 'Hourly'
    TYPE_NON_HOURLY = 'NonHourly'

    STATUS_CHARGEABLE = 'Chargeable'
    STATUS_NON_CHARGEABLE = 'NonChargeable'

    TYPES = (TYPE_HOURLY, TYPE_NON_HOURLY)
    STATUSES = (STATUS_CHARGEABLE, STATUS_NON_CHARGEABLE)

    def map_to_myob(self, display_id, name, activity_type=TYPE_NON_HOURLY,
                    status=STATUS_NON_CHARGEABLE, income_account=None,
                    tax_code=None, rate=None, description=None):
        if activity_type not in self.TYPES or status not in self.STATUSES:
            return {}

        data = {
            'DisplayID': display_id[:30],
            'Type': activity_type,
            'Status': status,
            'Name': name,
        }
        if description:
            data['Description'] = description[:255]

        if activity_type != self.TYPE_HOURLY:
            data['UnitOfMeasurement'] = 'Irregular'
        else:
            if not income_account or not tax_code:
                return {}
            data['ChargeableDetails'] = {
                'IncomeAccount': {
                    'UID': income_account
                },
                'TaxCode': {
                    'UID': tax_code
                }
            }

            if rate:
                data['ChargeableDetails'].update({
                    'Rate': 'ActivityRate',
                    'ActivityRateExcludingTax': "{0:.2f}".format(rate.hourly_rate)
                })

        return data


class TimeSheetMapper(StandardPayMapMixin):

    def map_to_myob(self, timesheets_with_rates, employee_uid, start_date, end_date, myob_job=None, customer_uid=None,
                    address=None, candidate=None):
        data = {
            'StartDate': format_date_to_myob(start_date),
            'EndDate': format_date_to_myob(end_date),
            'Employee': {
                'UID': employee_uid
            },
        }

        lines = []

        for payroll_cat_uid, timesheets_data in timesheets_with_rates.items():
            entries = []

            for timesheet_dict in timesheets_data.get('timesheets', []):
                started = format_date_to_myob(timesheet_dict['timesheet'].shift_started_at_tz, only_date=True)

                if isinstance(timesheet_dict['hours'], str):
                    hours = timesheet_dict['hours']
                else:
                    hours = "{0:.2f}".format(timesheet_dict['hours'].seconds / 3600)

                entry = {
                    'Date': started,
                    'Hours': hours
                }

                entries.append(entry)

            line = {
                'PayrollCategory': {
                    'UID': payroll_cat_uid
                },
                'Entries': entries
            }

            if myob_job:
                line['Job'] = {
                    'UID': myob_job['UID']
                }
            if customer_uid:
                line['Customer'] = {
                    'UID': customer_uid
                }
            if address:
                line['Notes'] = address

            lines.append(line)

        data['Lines'] = lines

        return data

    def map_rate_to_myob_wage_category(self, name, fixed=None, mult=None, coefficient=None):
        data = {
            'Name': name[:31].strip(),
            'WageType': 'Hourly',
            'HourlyDetails': {},
            'StpCategory': 'GrossPayments',
        }

        if fixed and fixed > 0:
            data['HourlyDetails'] = {
                'PayRate': 'FixedHourly',
                'FixedHourlyRate': str(fixed)
            }
        elif mult and mult > 0:
            data['HourlyDetails'] = {
                'PayRate': 'RegularRate',
                'RegularRateMultiplier': str(mult)
            }
        else:
            return {}

        if coefficient and coefficient.is_allowance:
            data['StpCategory'] = 'AllowanceOther'

        return data

    def map_extra_rates(self, new_rates, rates=None):
        if rates is None:
            rates = []
        data = {
            'WageCategories': [{'UID': uid['UID']} for uid in rates if uid['UID'] not in new_rates]
        }

        data['WageCategories'].extend([{'UID': uid} for uid in new_rates])

        return data


class CandidateMapper(StandardPayMapMixin, ContactMapper):
    @property
    def layout_mapper(self):
        return {
            'BSBNumber': 'bsb_number',
            'BankAccountName': 'bank_account_name',
            'BankAccountNumber': 'bank_account_number',
        }

    def map_bank_account(self, contact):
        bank_account = contact.bank_accounts.filter(
            layout__payment_system='MYOB'
        ).first()
        if bank_account is None:
            return {}

        layout_fields = bank_account.layout.fields.filter(
            field__name__in=self.layout_mapper.values()
        ).all()
        if not layout_fields:
            return {}
        account_field_map = {x.field_id: x.value
                             for x in bank_account.fields.all()}

        field_values_map = {x.field.name: account_field_map.get(x.field.id)
                            for x in layout_fields}

        myob_layout_map = {k: field_values_map[v]
                           for k, v in self.layout_mapper.items()}

        bsb_number = myob_layout_map.get('BSBNumber')
        if bsb_number is None or len(bsb_number) < 6:
            return {}

        data = {
            'PaymentMethod': 'Electronic',
            'BankStatementText': 'pay {}'.format(str(contact))[:18],
            'BankAccounts': [{
                'BSBNumber': '{}-{}'.format(bsb_number[:3], bsb_number[3:]),
                'BankAccountName': myob_layout_map.get('BankAccountName', '')[:32].strip(),
                'BankAccountNumber': myob_layout_map.get('BankAccountNumber', '')[:9],
                'Value': 100,
                'Unit': 'Percent'
            }]
        }

        return data

    def map_extra_info(
        self, candidate_contact, expense_account=None, superannuation_fund=None, wage_categories=None, tax_table=None,
        withholding_rate=None, superannuation_category=None, employment_classification=None, base_hourly_rate=None
    ):
        contact = candidate_contact.contact
        data = {
            'EmploymentBasis': 'Individual',
            'EmploymentCategory': 'Temporary',
            'EmploymentStatus': 'Casual',
            'PaySlipDelivery': 'ToBePrinted',
            'Wage': {
                'PayBasis': 'Hourly',
                'HoursInWeeklyPayPeriod': 40,
            },
        }

        if expense_account:
            data['Wage'].update({
                'WagesExpenseAccount': {
                    'UID': expense_account['UID'],
                },
            })

        if wage_categories:
            data['Wage'].update({
                'WageCategories': [{'UID': uid} for uid in wage_categories],
            })

        if contact.email:
            data.update({
                'PaySlipDelivery': 'ToBePrintedAndEmailed',
                'PaySlipEmail': contact.email,
            })

        states = candidate_contact.get_active_states()
        if states.exists():
            try:
                status = states.filter(state__number=70).latest('created_at')
            except WorkflowObject.DoesNotExist:
                status = None

            if not status:
                status = states.latest('created_at')

            if status:
                data['StartDate'] = date_format(status.created_at, settings.DATETIME_MYOB_FORMAT)

        if contact.gender:
            data['Gender'] = contact.gender

        if contact.birthday:
            data['DateOfBirth'] = date_format(contact.birthday, settings.DATE_MYOB_FORMAT)

        if tax_table:
            data['Tax'] = {
                'TaxTable': {
                    'UID': tax_table['UID'],
                }
            }

            tax_file_num = candidate_contact.tax_number
            if tax_file_num and len(tax_file_num) == 9:
                data['Tax'].update({
                    'TaxFileNumber': '{} {} {}'.format(
                        tax_file_num[:3],
                        tax_file_num[3:6],
                        tax_file_num[6:]
                    ),
                })

            if withholding_rate is not None:
                data['Tax'].update({
                    'WithholdingVariationRate': withholding_rate,
                })

        if employment_classification:
            data['EmploymentClassification'] = {
                'UID': employment_classification['UID']
            }

        if superannuation_fund or superannuation_category:
            data['Superannuation'] = {
                'SuperannuationFund': None,
            }

        if superannuation_fund:
            data['Superannuation']['SuperannuationFund'] = {
                'UID': superannuation_fund['UID'],
            }
        if superannuation_category:
            data['Superannuation']['SuperannuationCategories'] = [{
                'UID': superannuation_category['UID'],
            }]

        super_member_number = candidate_contact.superannuation_membership_number
        if superannuation_fund and super_member_number:
            data['Superannuation'].update({
                'EmployeeMembershipNumber': super_member_number
            })

        if base_hourly_rate is not None:
            data['Wage']['HourlyRate'] = str(base_hourly_rate)

        return data

    def map_to_myob_wage_category(self, name, skill_rate):
        data = {
            'Name': name[:31].strip(),
            'WageType': 'Hourly',
            'HourlyDetails': {
                'PayRate': 'FixedHourly',
                'FixedHourlyRate': str(skill_rate.hourly_rate)
            }
        }

        return data


class CompanyMapper(ContactMapper):

    PAYMENT_IS_DUE_MAP = {
        Company.TERMS_PAYMENT_CHOICES.on_delivery: 'CashOnDelivery',
        Company.TERMS_PAYMENT_CHOICES.prepaid: 'PrePaid',
        Company.TERMS_PAYMENT_CHOICES.days: 'InAGivenNumberOfDays',
        Company.TERMS_PAYMENT_CHOICES.day_of_month: 'OnADayOfTheMonth',
        Company.TERMS_PAYMENT_CHOICES.days_eom: 'NumberOfDaysAfterEOM',
        Company.TERMS_PAYMENT_CHOICES.day_of_month_eom: 'DayOfMonthAfterEOM',
    }

    def map_to_myob(self, company, tax_code, salesperson=None, income_account=None):
        data = {
            'IsIndividual': False,
            'CompanyName': company.name
        }

        if company.primary_contact:
            data.update(self._map_contact_to_myob(company.primary_contact.contact))

        data.update(self._map_extra_data_to_myob(company, tax_code=tax_code))
        if salesperson:
            data['SellingDetails']['SalesPerson'] = {
                'UID': salesperson['UID']
            }

        if income_account:
            data['SellingDetails']['IncomeAccount'] = {
                'UID': income_account['UID']
            }

        return data

    def _map_extra_data_to_myob(self, company, tax_code):
        addresses = []
        primary_address = company.get_hq_address()
        addresses_qs = company.company_addresses.filter(active=True)
        if primary_address:
            addresses.append(self._map_address_to_myob(primary_address.address))
            addresses_qs = addresses_qs.exclude(id=primary_address.id)

        for address in addresses_qs:
            address_data = self._map_address_to_myob(address.address, idx=len(addresses) + 1)
            if address.phone_landline:
                address_data['Phone1'] = address.phone_landline
            if address.phone_fax:
                address_data['Fax'] = address.phone_fax
            if address.primary_contact:
                address_data['ContactName'] = address.primary_contact.contact.first_name
            addresses.append(address_data)

        if addresses:
            addresses[0]['Email'] = company.billing_email
        elif company.billing_email:
            addresses.append({
                'Location': 1,
                'Email': company.billing_email
            })

        data = {
            'SellingDetails': {
                'SaleLayout': 'TimeBilling',
                'InvoiceDelivery': 'Print',
                'ItemPriceLevel': 'Base Selling Price',
                'Terms': {
                    'PaymentIsDue': self.PAYMENT_IS_DUE_MAP.get(company.terms_of_payment),
                    'BalanceDueDate': company.payment_due_date
                }
            },
        }

        if addresses:
            data['Addresses'] = addresses
        # GST hardcoded
        if tax_code:
            data['SellingDetails'].update({
                'TaxCode': {
                    'UID': tax_code['UID']
                },
                'FreightTaxCode': {
                    'UID': tax_code['UID']
                }
            })

        abn = get_formatted_abn(company.business_id)
        if abn:
            data['SellingDetails']['ABN'] = abn

        if company.credit_check == Company.CREDIT_CHECK_CHOICES.approved:
            data['SellingDetails']['Credit'] = {
                'Limit': str(company.approved_credit_limit),
            }

        return data


class JobsiteMapper:

    def map_to_myob(self, jobsite):
        data = {
            'Number': jobsite.get_myob_card_number(),
            'Name': jobsite.get_myob_name(),
            'IsHeader': False,
            'Description': jobsite.notes or jobsite.notes[:255],
        }

        if jobsite.primary_contact:
            data['Contact'] = jobsite.primary_contact.contact.first_name[:25]

        if jobsite.portfolio_manager:
            data['Manager'] = jobsite.portfolio_manager.contact.first_name[:25]

        if jobsite.start_date:
            data['StartDate'] = format_date_to_myob(jobsite.start_date)

        if jobsite.end_date:
            data['FinishDate'] = format_date_to_myob(jobsite.end_date)

        return data
