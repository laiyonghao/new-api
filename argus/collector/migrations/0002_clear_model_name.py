import re

from django.db import migrations, models


BRACKET_SEGMENT_RE = re.compile(r'\[[^\[\]]*\]')


def normalize_model_name(value: str) -> str:
	raw_value = (value or '').strip()
	if not raw_value:
		return ''
	cleaned = BRACKET_SEGMENT_RE.sub('', raw_value)
	return cleaned.strip() or raw_value


def backfill_clear_model_name(apps, schema_editor):
	ModelPriceSnapshot = apps.get_model('collector', 'ModelPriceSnapshot')
	for snapshot in ModelPriceSnapshot.objects.all().only('id', 'model_name'):
		snapshot.clear_model_name = normalize_model_name(snapshot.model_name)
		snapshot.save(update_fields=['clear_model_name'])


class Migration(migrations.Migration):

	dependencies = [
		('collector', '0001_initial'),
	]

	operations = [
		migrations.AddField(
			model_name='modelpricesnapshot',
			name='clear_model_name',
			field=models.CharField(db_index=True, default='', max_length=255),
			preserve_default=False,
		),
		migrations.RunPython(backfill_clear_model_name, migrations.RunPython.noop),
		migrations.AlterModelOptions(
			name='modelpricesnapshot',
			options={'ordering': ['clear_model_name', 'model_name', 'site__name', 'site__base_url']},
		),
		migrations.RemoveIndex(
			model_name='modelpricesnapshot',
			name='collector_m_model_n_c3523c_idx',
		),
		migrations.RemoveIndex(
			model_name='modelpricesnapshot',
			name='collector_m_site_id_e98c0c_idx',
		),
		migrations.AddIndex(
			model_name='modelpricesnapshot',
			index=models.Index(fields=['clear_model_name'], name='collector_m_clear_m_73af39_idx'),
		),
		migrations.AddIndex(
			model_name='modelpricesnapshot',
			index=models.Index(fields=['site', 'clear_model_name'], name='collector_m_site_id_e67cbb_idx'),
		),
	]