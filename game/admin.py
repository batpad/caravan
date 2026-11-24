from django.contrib import admin

from .models import Game, Seat


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "version", "updated")
    inlines = [SeatInline]
