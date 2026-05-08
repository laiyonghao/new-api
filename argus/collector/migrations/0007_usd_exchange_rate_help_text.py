from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		('collector', '0006_converted_prices'),
	]

	operations = [
		migrations.AlterField(
			model_name='competitorsite',
			name='usd_exchange_rate',
			field=models.DecimalField(
				decimal_places=6,
				default=Decimal('1.0'),
				help_text='RMB needed to buy 1 USD of credit. Examples: 1 = 1 RMB for 1 USD, 2 = 2 RMB for 1 USD, 0.6 = 0.6 RMB for 1 USD. Smaller means cheaper.',
				max_digits=12,
			),
		),
	]