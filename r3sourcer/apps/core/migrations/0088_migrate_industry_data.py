from django.db import models, migrations


def forward(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    CompanyIndustryRel = apps.get_model("core", "CompanyIndustryRel")
    for company in Company.objects.all():
        industry = company.industry
        if industry:
            CompanyIndustryRel.objects.create(company=company, industry=industry, default=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0087_added_company_industry_rel'),
    ]

    operations = [
        migrations.RunPython(forward)
]