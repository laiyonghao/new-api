import re

from django.db import migrations


BRACKET_SEGMENT_RE = re.compile(r'\[[^\[\]]*\]')
MODEL_VERSION_SEGMENT_RE = re.compile(r'-(?:latest|\d{8})(?=-|$)', re.IGNORECASE)
MULTI_HYPHEN_RE = re.compile(r'-{2,}')


def normalize_model_name(value: str) -> str:
	raw_value = (value or '').strip()
	if not raw_value:
		return ''
	cleaned = BRACKET_SEGMENT_RE.sub('', raw_value)
	cleaned = cleaned.replace('.', '-')
	cleaned = MODEL_VERSION_SEGMENT_RE.sub('', cleaned)
	cleaned = MULTI_HYPHEN_RE.sub('-', cleaned)
	cleaned = cleaned.strip(' -')
	segments = [segment.strip() for segment in cleaned.split('-') if segment.strip()]
	if len(segments) > 1 and not segments[1].isalpha():
		for index in range(2, len(segments)):
			if segments[index].isalpha():
				segment = segments.pop(index)
				segments.insert(1, segment)
				break
		if segments:
			cleaned = '-'.join(segments)
	return cleaned.strip() or raw_value


def backfill_clear_model_name(apps, schema_editor):
	ModelPriceSnapshot = apps.get_model('collector', 'ModelPriceSnapshot')
	for snapshot in ModelPriceSnapshot.objects.all().only('id', 'model_name').iterator():
		snapshot.clear_model_name = normalize_model_name(snapshot.model_name)
		snapshot.save(update_fields=['clear_model_name'])


class Migration(migrations.Migration):

	dependencies = [
		('collector', '0009_replace_dots_in_clear_model_name'),
	]

	operations = [
		migrations.RunPython(backfill_clear_model_name, migrations.RunPython.noop),
	]