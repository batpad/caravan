import secrets
import string

from django.db import models


def _code():
    return "".join(secrets.choice(string.ascii_uppercase.replace("O", "").replace("I", "")) for _ in range(5))


def _token():
    return secrets.token_urlsafe(24)


class Game(models.Model):
    LOBBY, PLAYING, FINISHED = "lobby", "playing", "finished"
    STATUS = [(LOBBY, "Lobby"), (PLAYING, "Playing"), (FINISHED, "Finished")]

    code = models.CharField(max_length=8, unique=True, default=_code)
    name = models.CharField(max_length=60)
    max_players = models.PositiveSmallIntegerField(default=4)
    status = models.CharField(max_length=10, choices=STATUS, default=LOBBY)
    state = models.JSONField(null=True, blank=True)
    version = models.PositiveIntegerField(default=0)
    tutorial = models.BooleanField(default=False)  # guided "Learn to play" game: scripted opening, hidden from lists
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Seat(models.Model):
    game = models.ForeignKey(Game, related_name="seats", on_delete=models.CASCADE)
    index = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=30)
    token = models.CharField(max_length=64, unique=True, default=_token)
    is_host = models.BooleanField(default=False)
    is_bot = models.BooleanField(default=False)
    bot_level = models.CharField(max_length=10, blank=True, default="")  # easy / normal / hard

    class Meta:
        ordering = ["index"]
        unique_together = [("game", "index")]
