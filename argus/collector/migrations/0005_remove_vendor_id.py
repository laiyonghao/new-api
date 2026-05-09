from django.db import migrations


class Migration(migrations.Migration):

	dependencies = [
		('collector', '0004_vendor_fields'),
	]

	operations = [
		migrations.RemoveField(
			model_name='modelpricesnapshot',
			name='vendor_id',
		),
	]