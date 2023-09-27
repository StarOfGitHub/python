from ..service import factory


class MasterCompanyGetter(object):
    def get_master_company_for_obj(self, obj):
        site = self.get_site_from_obj(obj)
        if site and site.site_companies.exists():
            return site.site_companies.first().company
        return None

    def get_site_from_obj(self, obj):
        if hasattr(obj, "site"):
            return obj.site
        else:
            for field in obj._meta.local_fields:
                if hasattr(field, "site"):
                    return field.site
        return None


factory.register('MasterCompanyGetter', MasterCompanyGetter)
