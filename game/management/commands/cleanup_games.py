from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from game.models import Game


class Command(BaseCommand):
    help = "Delete stale games: empty lobbies, abandoned games and old finished games."

    def add_arguments(self, parser):
        parser.add_argument("--lobby-hours", type=int, default=24)
        parser.add_argument("--idle-days", type=int, default=30)
        parser.add_argument("--finished-days", type=int, default=14)

    def handle(self, *args, lobby_hours, idle_days, finished_days, **kw):
        now = timezone.now()
        counts = {
            "lobby": Game.objects.filter(status=Game.LOBBY, updated__lt=now - timedelta(hours=lobby_hours)).delete()[0],
            "idle": Game.objects.filter(status=Game.PLAYING, updated__lt=now - timedelta(days=idle_days)).delete()[0],
            "finished": Game.objects.filter(status=Game.FINISHED, updated__lt=now - timedelta(days=finished_days)).delete()[0],
        }
        self.stdout.write(f"Deleted rows: {counts}")
