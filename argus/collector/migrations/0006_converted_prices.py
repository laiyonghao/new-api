from decimal import Decimal

from django.db import migrations, models


def backfill_converted_prices(apps, schema_editor):
	ModelPriceSnapshot = apps.get_model('collector', 'ModelPriceSnapshot')

	for snapshot in ModelPriceSnapshot.objects.select_related('site').all().iterator():
		exchange_rate = getattr(snapshot.site, 'usd_exchange_rate', None) or Decimal('1')
		if exchange_rate <= 0:
			exchange_rate = Decimal('1')

		input_price = snapshot.input_price_usd_per_1m
		output_price = snapshot.output_price_usd_per_1m
		request_price = snapshot.request_price_usd

		snapshot.input_price_converted_per_1m = input_price
		snapshot.output_price_converted_per_1m = output_price
		snapshot.request_price_converted = request_price

		if input_price is not None:
			snapshot.input_price_usd_per_1m = input_price / exchange_rate
		if output_price is not None:
			snapshot.output_price_usd_per_1m = output_price / exchange_rate
		if request_price is not None:
			snapshot.request_price_usd = request_price / exchange_rate

		snapshot.save(update_fields=[
			'input_price_usd_per_1m',
			'output_price_usd_per_1m',
			'request_price_usd',
			'input_price_converted_per_1m',
			'output_price_converted_per_1m',
			'request_price_converted',
		])


class Migration(migrations.Migration):

	dependencies = [
		('collector', '0005_remove_vendor_id'),
	]

	operations = [
		migrations.AddField(
			model_name='modelpricesnapshot',
			name='input_price_converted_per_1m',
			field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
		),
		migrations.AddField(
			model_name='modelpricesnapshot',
			name='output_price_converted_per_1m',
			field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
		),
		migrations.AddField(
			model_name='modelpricesnapshot',
			name='request_price_converted',
			field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
		),
		migrations.RunPython(backfill_converted_prices, migrations.RunPython.noop),
	]