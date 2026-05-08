from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('collector', '0003_supported_endpoint_types'),
	]

	operations = [
		migrations.AddField(
			model_name='modelpricesnapshot',
			name='vendor_id',
			field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
		),
		migrations.AddField(
			model_name='modelpricesnapshot',
			name='vendor_name',
			field=models.CharField(blank=True, db_index=True, max_length=120),
		),
	]