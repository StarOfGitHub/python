from infi.clickhouse_orm import migrations
from r3sourcer.apps.logger import models

operations = [
    migrations.AlterTable(models.LocationHistory)
]
