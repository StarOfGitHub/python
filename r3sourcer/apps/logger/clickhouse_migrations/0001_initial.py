from infi.clickhouse_orm import migrations
from r3sourcer.apps.logger import models

operations = [
    migrations.CreateTable(models.LogHistory),
    migrations.CreateTable(models.LocationHistory)
]
