from django.core.management.base import BaseCommand

from collector.models import LoginCode


class Command(BaseCommand):
	help = 'Delete LoginCode rows older than ARGUS_LOGIN_CODE_RETENTION_SECONDS.'

	def handle(self, *args, **options):
		deleted_count = LoginCode.purge_stale()
		self.stdout.write(self.style.SUCCESS(f'Deleted {deleted_count} stale login code row(s).'))
