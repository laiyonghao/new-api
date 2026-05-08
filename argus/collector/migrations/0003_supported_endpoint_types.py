from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('collector', '0002_clear_model_name'),
	]

	operations = [
		migrations.AddField(
			model_name='modelpricesnapshot',
			name='supported_endpoint_types_json',
			field=models.TextField(blank=True, default='[]'),
		),
	]