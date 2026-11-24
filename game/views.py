"""JSON API + single-page shell.

Auth is a per-seat secret token issued on create/join, sent as the `X-Seat-Token` header.
Clients poll `/state?since=<version>`; the server answers `{"unchanged": true}` when nothing moved.

AI seats (`Seat.is_bot`) are driven by "lazy stepping": whenever the state endpoint is polled
and a bot is to move, and the game has been idle for at least `BOT_STEP_DELAY` seconds, the
server plays ONE bot turn inside the same IMMEDIATE transaction that serialises human actions.
No background workers are needed; humans polling the game keep it moving at a readable pace.
"""
import json
import logging
import random
from functools import wraps

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import tutorial
from .engine import bot
from .engine.engine import GameError, apply_action, new_game, public_view, static_data
from .models import Game, Seat

log = logging.getLogger(__name__)
MAX_BOTS_ON_CREATE = 3


def index(request, code=None):
    return render(request, "game/index.html")


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return {}


def _err(msg, status=400):
    return JsonResponse({"error": msg}, status=status)


def _seat_for(request, game):
    tok = request.headers.get("X-Seat-Token") or request.GET.get("token")
    if not tok:
        return None
    return game.seats.filter(token=tok).first()


def _clean_name(raw):
    name = (raw or "").strip()[:30]
    return name or None


def api(view):
    @wraps(view)
    def wrapper(request, *a, **kw):
        try:
            return view(request, *a, **kw)
        except GameError as e:
            return _err(str(e))
    return csrf_exempt(wrapper)


def _lobby_payload(game):
    return {
        "code": game.code, "name": game.name, "status": game.status, "max_players": game.max_players,
        "players": [{"index": s.index, "name": s.name, "is_host": s.is_host, "is_bot": s.is_bot,
                     "bot_level": s.bot_level or None} for s in game.seats.all()],
        "version": game.version, "tutorial": game.tutorial,
    }


@require_GET
def static_info(request):
    return JsonResponse(static_data())


@api
def games(request):
    if request.method == "GET":
        qs = Game.objects.filter(status=Game.LOBBY, tutorial=False).order_by("-created")[:30]
        return JsonResponse({"games": [_lobby_payload(g) for g in qs]})
    if request.method != "POST":
        return _err("Method not allowed", 405)
    body = _body(request)
    player = _clean_name(body.get("player"))
    if not player:
        return _err("Enter your name.")
    if body.get("tutorial") is True:
        return _create_tutorial(player)
    name = (body.get("name") or "").strip()[:60] or f"{player}'s caravan"
    try:
        max_players = int(body.get("max_players", 4))
    except (TypeError, ValueError):
        max_players = 4
    bots = body.get("bots", 0)
    if bots in (None, ""):
        bots = 0
    if type(bots) is not int or not 0 <= bots <= MAX_BOTS_ON_CREATE:
        return _err("Add 0 to 3 AI opponents.")
    level = _bot_level(body.get("bot_level"))
    if level is None:
        return _err("Bot level must be easy, normal or hard.")
    if bots:
        max_players = 1 + bots   # a solo table: the human plus the bots, started at once
    if not 2 <= max_players <= 4:
        return _err("Games take 2 to 4 players.")
    with transaction.atomic():
        game = Game.objects.create(name=name, max_players=max_players)
        seat = Seat.objects.create(game=game, index=0, name=player, is_host=True)
        for _ in range(bots):
            _add_bot_seat(game, level)
        if bots:
            _start_game(game)
    return JsonResponse({"code": game.code, "token": seat.token, "seat": 0, "started": bool(bots)})


def _create_tutorial(player):
    """A started 2-seat game: the learner (seat 0) vs one easy bot, dealt deterministically."""
    with transaction.atomic():
        game = Game.objects.create(name="Learning the road", max_players=2, tutorial=True)
        seat = Seat.objects.create(game=game, index=0, name=player, is_host=True)
        b = _add_bot_seat(game, tutorial.BOT_LEVEL)
        game.state = tutorial.new_tutorial_state(player, b.name)
        game.status = Game.PLAYING
        game.version += 1
        game.save()
    return JsonResponse({"code": game.code, "token": seat.token, "seat": 0, "started": True, "tutorial": True})


def _bot_level(raw):
    if raw in (None, ""):
        return bot.DEFAULT_LEVEL
    return raw if raw in bot.LEVELS else None


def _add_bot_seat(game, level):
    seats = list(game.seats.all())
    name = bot.bot_name([s.name for s in seats])
    return Seat.objects.create(game=game, index=len(seats), name=name, is_bot=True, bot_level=level)


def _start_game(game):
    """Deal the game and let every bot choose its character straight away. Caller saves."""
    seats = list(game.seats.all())
    game.state = new_game([s.name for s in seats])
    rng = random.Random()
    for s in seats:
        if s.is_bot:
            bot.choose_character(game.state, s.index, rng, s.bot_level or bot.DEFAULT_LEVEL)
    game.status = Game.PLAYING
    game.version += 1
    game.save()


@api
@require_POST
def join(request, code):
    body = _body(request)
    player = _clean_name(body.get("player"))
    if not player:
        return _err("Enter your name.")
    with transaction.atomic():
        game = get_object_or_404(Game.objects.select_for_update(), code=code.upper())
        if game.status != Game.LOBBY:
            return _err("That game has already started.")
        seats = list(game.seats.all())
        if len(seats) >= game.max_players:
            return _err("That game is full.")
        if any(s.name.lower() == player.lower() for s in seats):
            return _err("Someone at the table already uses that name.")
        seat = Seat.objects.create(game=game, index=len(seats), name=player)
        game.version += 1
        game.save()
    return JsonResponse({"code": game.code, "token": seat.token, "seat": seat.index})


@api
@require_POST
def leave(request, code):
    with transaction.atomic():
        game = get_object_or_404(Game.objects.select_for_update(), code=code.upper())
        seat = _seat_for(request, game)
        if not seat:
            return _err("Not seated here.", 403)
        if game.status != Game.LOBBY:
            return _err("You cannot leave a game in progress.")
        was_host = seat.is_host
        seat.delete()
        remaining = list(game.seats.all())
        if not any(not s.is_bot for s in remaining):
            game.delete()  # only bots (or nobody) left
            return JsonResponse({"ok": True})
        new_host = next(s for s in remaining if not s.is_bot) if was_host else None
        _compact(remaining, new_host)
        game.version += 1
        game.save()
    return JsonResponse({"ok": True})


def _compact(seats, new_host=None):
    """Renumber seats 0..n-1 (two passes to dodge the unique (game, index) constraint)."""
    for i, s in enumerate(seats):
        s.index = 100 + i
        s.save(update_fields=["index"])
    for i, s in enumerate(seats):
        s.index = i
        if new_host is not None:
            s.is_host = s.pk == new_host.pk
        s.save(update_fields=["index", "is_host"])


@api
@require_POST
def add_bot(request, code):
    body = _body(request)
    level = _bot_level(body.get("level"))
    if level is None:
        return _err("Bot level must be easy, normal or hard.")
    with transaction.atomic():
        game = get_object_or_404(Game.objects.select_for_update(), code=code.upper())
        seat = _seat_for(request, game)
        if not seat or not seat.is_host:
            return _err("Only the host can add AI opponents.", 403)
        if game.status != Game.LOBBY:
            return _err("That game has already started.")
        if game.seats.count() >= game.max_players:
            return _err("That game is full.")
        b = _add_bot_seat(game, level)
        game.version += 1
        game.save()
    return JsonResponse({"ok": True, "seat": b.index, "name": b.name, "level": level, "version": game.version})


@api
@require_POST
def remove_seat(request, code):
    body = _body(request)
    index = body.get("index")
    if type(index) is not int:
        return _err("Choose a seat to remove.")
    with transaction.atomic():
        game = get_object_or_404(Game.objects.select_for_update(), code=code.upper())
        seat = _seat_for(request, game)
        if not seat or not seat.is_host:
            return _err("Only the host can remove seats.", 403)
        if game.status != Game.LOBBY:
            return _err("That game has already started.")
        target = game.seats.filter(index=index).first()
        if not target:
            return _err("No such seat.")
        if not target.is_bot:
            return _err("Only AI opponents can be removed.")
        target.delete()
        _compact(list(game.seats.all()))
        game.version += 1
        game.save()
    return JsonResponse({"ok": True, "version": game.version})


@api
@require_POST
def start(request, code):
    with transaction.atomic():
        game = get_object_or_404(Game.objects.select_for_update(), code=code.upper())
        seat = _seat_for(request, game)
        if not seat or not seat.is_host:
            return _err("Only the host can start the game.", 403)
        if game.status != Game.LOBBY:
            return _err("Already started.")
        if game.seats.count() < 2:
            return _err("Wait for at least one more merchant.")
        _start_game(game)
    return JsonResponse({"ok": True})


# --------------------------------------------------------------------------- bots

def _bot_due(game, bots):
    """Does a bot need to act in this game right now (ignoring pacing)?"""
    st = game.state
    if game.status != Game.PLAYING or not st or not bots:
        return False
    if st["phase"] == "setup":
        return any(not st["players"][i]["character"] for i in bots)
    return st["phase"] == "play" and st["current"] in bots


def step_bots(game, force=False):
    """Lazy stepping: play ONE bot turn if a bot is to move and the table has been idle long
    enough. Safe under concurrent pollers: the IMMEDIATE transaction serialises writers and the
    version is re-checked inside it, so two requests can never both step the same turn.
    Returns the (possibly updated) game."""
    if game.status != Game.PLAYING or not game.state:
        return game
    bots = {s.index: s.bot_level or bot.DEFAULT_LEVEL for s in game.seats.all() if s.is_bot}
    if not _bot_due(game, bots):
        return game
    delay = getattr(settings, "BOT_STEP_DELAY", 0.8)
    if game.tutorial:   # slow enough for a learner to watch the bot's move land
        delay = max(delay, getattr(settings, "TUTORIAL_BOT_STEP_DELAY", 2.5))
    if not force and game.state["phase"] == "play" and (timezone.now() - game.updated).total_seconds() < delay:
        return game
    seen = game.version
    with transaction.atomic():
        game = Game.objects.select_for_update().get(pk=game.pk)
        if game.version != seen or not _bot_due(game, bots):
            return game  # someone else moved first
        st = game.state
        rng = random.Random()
        if st["phase"] == "setup":
            for i, level in bots.items():
                if not st["players"][i]["character"]:
                    bot.choose_character(st, i, rng, level)
        else:
            seat = st["current"]
            try:
                if game.tutorial:
                    tutorial.bot_turn(st, seat, rng)
                else:
                    bot.take_turn(st, seat, rng, bots[seat])
            except Exception:  # a bot bug must never stall the table
                log.exception("bot turn failed in game %s", game.code)
                if st["phase"] == "play" and st["current"] == seat:
                    try:
                        apply_action(st, seat, {"type": "end_turn"} if st["turn_placed"] else {"type": "rest"})
                    except GameError:
                        log.exception("bot fallback failed in game %s", game.code)
                        return game
        game.state = st
        if st["phase"] == "finished":
            game.status = Game.FINISHED
        game.version += 1
        game.save()
    return game


@require_GET
def state(request, code):
    game = get_object_or_404(Game, code=code.upper())
    game = step_bots(game)
    since = request.GET.get("since")
    if since is not None and since.isdigit() and int(since) == game.version:
        return JsonResponse({"unchanged": True, "version": game.version})
    seat = _seat_for(request, game)
    payload = _lobby_payload(game)
    payload["seat"] = seat.index if seat else None
    payload["is_host"] = bool(seat and seat.is_host)
    if game.state:
        payload["game"] = public_view(game.state, seat.index if seat else None)
    return JsonResponse(payload)


@api
@require_POST
def action(request, code):
    body = _body(request)
    with transaction.atomic():
        game = get_object_or_404(Game.objects.select_for_update(), code=code.upper())
        seat = _seat_for(request, game)
        if not seat:
            return _err("You are not seated in this game.", 403)
        if game.status != Game.PLAYING or not game.state:
            return _err("The game is not in progress.")
        st = game.state
        apply_action(st, seat.index, body)  # raises GameError -> rolled back by atomic
        if game.tutorial:
            tutorial.on_state_change(st)
        game.state = st
        if st["phase"] == "finished":
            game.status = Game.FINISHED
        game.version += 1
        game.save()
    return JsonResponse({"ok": True, "version": game.version})


@require_GET
def hint(request, code):
    """The move the AI (normal level) would make next for the requesting seat. No side effects.

    200 -> {"action": {...}, "seat": n, "version": v}; 403 if not seated; 400 if it is not
    this seat's move."""
    game = get_object_or_404(Game, code=code.upper())
    seat = _seat_for(request, game)
    if not seat or seat.is_bot:
        return _err("You are not seated in this game.", 403)
    st = game.state
    if game.status != Game.PLAYING or not st:
        return _err("The game is not in progress.")
    if st["phase"] == "setup":
        if st["players"][seat.index]["character"]:
            return _err("Waiting for the other merchants to choose.")
    elif st["phase"] != "play" or st["current"] != seat.index:
        return _err("It is not your turn.")
    view = public_view(st, seat.index)
    try:
        a = bot.next_action(view, seat.index, random.Random(game.version), bot.DEFAULT_LEVEL)
    except Exception:  # a planner bug must never break the page
        log.exception("hint failed in game %s", game.code)
        a = {"type": "end_turn"} if st.get("turn_placed") else {"type": "rest"}
    return JsonResponse({"action": a, "seat": seat.index, "version": game.version})
