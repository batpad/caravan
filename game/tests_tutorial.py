"""Tests for the "Learn to play" tutorial game and the hint endpoint."""
import copy
import json
import random

from django.test import TestCase, override_settings

from . import tutorial as T
from .engine import data as D
from .engine.engine import GameError, apply_action, public_view
from .models import Game


def _post(client, url, body=None, token=None):
    headers = {"HTTP_X_SEAT_TOKEN": token} if token else {}
    return client.post(url, json.dumps(body or {}), content_type="application/json", **headers)


def _get(client, url, token=None):
    headers = {"HTTP_X_SEAT_TOKEN": token} if token else {}
    return client.get(url, **headers)


def _learner_dice(st):
    return [d["value"] for d in st["players"][T.LEARNER]["dice"] if not d["white"]]


class TutorialStateTests(TestCase):
    def deal(self, character=None):
        st = T.new_tutorial_state("Ann", "Bot · Zed")
        me = st["players"][T.LEARNER]
        apply_action(st, T.LEARNER, {"type": "choose_character", "character": character or me["character_choices"][0]})
        T.on_state_change(st)
        return st

    def test_setup_is_deterministic(self):
        a, b = T.new_tutorial_state("Ann", "Bot"), T.new_tutorial_state("Ann", "Bot")
        self.assertEqual(a, b)
        self.assertEqual(a["phase"], "setup")
        self.assertTrue(a["players"][T.BOT]["character"], "the bot has already chosen")
        self.assertIsNone(a["players"][T.LEARNER]["character"])
        self.assertTrue(a["tutorial"])

    def test_learner_gets_known_choices_commission_and_contract(self):
        st = T.new_tutorial_state("Ann", "Bot")
        me = st["players"][T.LEARNER]
        self.assertEqual(sorted(me["character_choices"]), sorted(c for c in T.LEARNER_CHOICES if c in D.CHARACTERS))
        cities = [D.COMMISSIONS[c] for c in me["commissions"]]
        self.assertTrue(any("antioch" in pair for pair in cities))
        self.assertFalse(set(cities[0]) & set(cities[1]), "the two commissions share no city")
        self.assertEqual(len(set(me["commissions"]) | set(st["players"][T.BOT]["commissions"])), 4)
        # slot 1 holds a contract the learner can deliver after the Spice Stall lesson
        req = D.CONTRACTS[st["contract_market"][0]][0]
        spice = D.START_RESOURCES["spice"] + D.SPACES["bazaar_spice"]["table"][T.LEARNER_DICE[1][0]]
        self.assertLessEqual(req.get("spice", 0), spice)
        self.assertLessEqual(req.get("silk", 0), D.START_RESOURCES["silk"])
        self.assertEqual(len(st["contract_market"]), D.CONTRACT_SLOTS)
        everything = st["contract_market"] + st["contract_deck"] + st["contract_discard"]
        self.assertEqual(sorted(everything), list(range(len(D.CONTRACTS))), "no contract lost or duplicated")

    def test_round_one_dice_are_fixed_for_either_character(self):
        for ch in T.LEARNER_CHOICES:
            random.seed(ch)
            st = self.deal(ch)
            self.assertEqual(st["phase"], "play")
            self.assertEqual(st["round"], 1)
            self.assertEqual(_learner_dice(st), T.LEARNER_DICE[1])
            self.assertEqual(st["current"], T.LEARNER)
            roll = next(e["text"] for e in st["log"] if e.get("seat") == T.LEARNER and " rolls [" in e["text"])
            self.assertIn("[" + " ".join(map(str, T.LEARNER_DICE[1])) + "]", roll)
            self.assertFalse(T.on_state_change(st), "idempotent")

    def test_poor_roll_compensation_is_recomputed(self):
        random.seed(5)
        st = T.new_tutorial_state("Ann", "Bot")
        before = st["players"][T.LEARNER]["coins"]
        apply_action(st, T.LEARNER, {"type": "choose_character", "character": "cartographer"})
        p = st["players"][T.LEARNER]
        old = [d["value"] for d in p["dice"]]
        coins_after_roll = p["coins"]
        T.on_state_change(st)
        self.assertEqual(p["coins"] - coins_after_roll, T._comp(T.LEARNER_DICE[1]) - T._comp(old))
        self.assertEqual(p["coins"], before + T._comp(T.LEARNER_DICE[1]))

    def play_script(self, st):
        """The lesson path through round 1; returns the state at the start of round 2."""
        rng = random.Random(1)
        me = st["players"][T.LEARNER]

        def die(v):
            return next(d["id"] for d in me["dice"] if d["value"] == v and not d["placed"])

        def mine(a):
            apply_action(st, T.LEARNER, a)
            T.on_state_change(st)

        def end():
            mine({"type": "end_turn"})
            while st["phase"] == "play" and st["current"] == T.BOT:
                T.bot_turn(st, T.BOT, rng)

        mine({"type": "place", "die": die(5), "space": "bazaar_spice"})
        end()
        self.assertIn("Camel Market", st["log"][-1]["text"])
        mine({"type": "place", "die": die(3), "space": "caravanserai", "slot": 0})
        mine({"type": "fulfill", "index": 0})
        self.assertEqual(me["fulfilled"], 1)
        end()
        self.assertTrue(any(e["seat"] == T.BOT for e in st["spaces"]["road"]), "the bot crowded the Road")
        coins = me["coins"]
        mine({"type": "place", "die": die(1), "space": "road", "path": ["constantinople", "antioch"]})
        self.assertEqual(coins - me["coins"], 1 * D.TOLL_PER_PIP, "a 1 pays a one-pip toll")
        self.assertIn("antioch", me["posts"])
        end()
        mine({"type": "place", "die": die(4), "space": "city", "city": "antioch", "times": 1})
        end()
        mine({"type": "place", "die": die(2), "space": "temple"})
        end()
        return st

    def test_scripted_round_one_and_round_two_dice(self):
        random.seed(2)
        st = self.play_script(self.deal("seer"))
        self.assertEqual(st["round"], 2)
        self.assertEqual(_learner_dice(st), T.LEARNER_DICE[2])
        self.assertEqual(st["start_player"], T.LEARNER, "the Shrine visit gives the learner the lead")

    def test_scripted_bot_falls_back_when_script_is_illegal(self):
        random.seed(3)
        st = self.deal()
        apply_action(st, T.LEARNER, {"type": "place", "die": st["players"][0]["dice"][0]["id"], "space": "camels"})
        apply_action(st, T.LEARNER, {"type": "end_turn"})
        st["players"][T.BOT]["dice"] = [dict(d, placed=True) for d in st["players"][T.BOT]["dice"][:-1]] + st["players"][T.BOT]["dice"][-1:]
        st["players"][T.BOT]["coins"] = 0   # cannot pay the Camel Market toll for a high die
        T.bot_turn(st, T.BOT, random.Random(0))
        self.assertNotEqual(st["current"], T.BOT, "the bot always finishes its turn")

    def test_bot_turns_never_raise_over_a_full_game(self):
        for seed in range(3):
            random.seed(seed)
            st = self.deal(T.LEARNER_CHOICES[seed % 2])
            rng = random.Random(seed)
            from .engine import bot
            for _ in range(400):
                if st["phase"] == "finished":
                    break
                if st["current"] == T.BOT:
                    T.bot_turn(st, T.BOT, rng)
                else:
                    bot.take_turn(st, T.LEARNER, rng, "easy")
                    T.on_state_change(st)
            self.assertEqual(st["phase"], "finished")


@override_settings(BOT_STEP_DELAY=0, TUTORIAL_BOT_STEP_DELAY=0)
class TutorialApiTests(TestCase):
    def create(self, name="Ann"):
        r = _post(self.client, "/api/games/", {"player": name, "tutorial": True})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_create_tutorial(self):
        r = self.create()
        self.assertEqual((r["seat"], r["started"], r["tutorial"]), (0, True, True))
        g = Game.objects.get(code=r["code"])
        self.assertTrue(g.tutorial)
        self.assertEqual(g.status, Game.PLAYING)
        self.assertEqual([s.is_bot for s in g.seats.all()], [False, True])
        self.assertEqual(g.seats.get(index=1).bot_level, T.BOT_LEVEL)
        st = _get(self.client, f"/api/games/{r['code']}/state/", r["token"]).json()
        self.assertTrue(st["tutorial"])
        self.assertEqual(st["game"]["phase"], "setup")
        self.assertEqual(st["game"]["players"][0]["character_choices"], g.state["players"][0]["character_choices"])

    def test_creation_is_deterministic(self):
        a, b = self.create(), self.create()
        sa = Game.objects.get(code=a["code"]).state
        sb = Game.objects.get(code=b["code"]).state
        sb["players"][1]["name"] = sa["players"][1]["name"]   # bot names are random
        for e in sb["log"]:
            e["text"] = e["text"].replace(Game.objects.get(code=b["code"]).seats.get(index=1).name, sa["players"][1]["name"])
        self.assertEqual(sa, sb)

    def test_choose_character_applies_scripted_dice(self):
        r = self.create()
        a = _post(self.client, f"/api/games/{r['code']}/action/", {"type": "choose_character", "character": "seer"}, r["token"])
        self.assertEqual(a.status_code, 200, a.content)
        st = Game.objects.get(code=r["code"]).state
        self.assertEqual((st["phase"], st["current"]), ("play", 0))
        self.assertEqual(_learner_dice(st), T.LEARNER_DICE[1])

    def test_hidden_from_open_games_list(self):
        self.create()
        _post(self.client, "/api/games/", {"player": "Bea"})
        games = _get(self.client, "/api/games/").json()["games"]
        self.assertEqual(len(games), 1)
        self.assertFalse(games[0]["tutorial"])
        # even a tutorial row stuck in the lobby state never shows up
        Game.objects.filter(tutorial=True).update(status=Game.LOBBY)
        self.assertEqual(len(_get(self.client, "/api/games/").json()["games"]), 1)

    def test_regular_create_is_not_a_tutorial(self):
        r = _post(self.client, "/api/games/", {"player": "Ann", "bots": 1, "tutorial": "yes"}).json()
        self.assertFalse(Game.objects.get(code=r["code"]).tutorial)

    @override_settings(TUTORIAL_BOT_STEP_DELAY=30)
    def test_tutorial_bot_waits_longer(self):
        r = self.create()
        _post(self.client, f"/api/games/{r['code']}/action/", {"type": "choose_character", "character": "seer"}, r["token"])
        g = Game.objects.get(code=r["code"])
        die = g.state["players"][0]["dice"][0]["id"]
        _post(self.client, f"/api/games/{r['code']}/action/", {"type": "place", "die": die, "space": "bazaar_spice"}, r["token"])
        _post(self.client, f"/api/games/{r['code']}/action/", {"type": "end_turn"}, r["token"])
        st = _get(self.client, f"/api/games/{r['code']}/state/", r["token"]).json()
        self.assertEqual(st["game"]["current"], 1, "the bot has not moved yet")

    def test_bot_steps_through_tutorial_script(self):
        r = self.create()
        url = f"/api/games/{r['code']}"
        _post(self.client, f"{url}/action/", {"type": "choose_character", "character": "cartographer"}, r["token"])
        die = next(d["id"] for d in Game.objects.get(code=r["code"]).state["players"][0]["dice"] if d["value"] == 5)
        _post(self.client, f"{url}/action/", {"type": "place", "die": die, "space": "bazaar_spice"}, r["token"])
        _post(self.client, f"{url}/action/", {"type": "end_turn"}, r["token"])
        st = _get(self.client, f"{url}/state/", r["token"]).json()["game"]
        self.assertEqual(st["current"], 0)
        self.assertTrue(any(e["seat"] == 1 for e in st["spaces"]["camels"]), "scripted bot used the Camel Market")


@override_settings(BOT_STEP_DELAY=0, TUTORIAL_BOT_STEP_DELAY=0)
class HintApiTests(TestCase):
    def test_hint_returns_a_legal_action(self):
        r = _post(self.client, "/api/games/", {"player": "Ann", "tutorial": True}).json()
        url = f"/api/games/{r['code']}"
        h = _get(self.client, f"{url}/hint/", r["token"])
        self.assertEqual(h.status_code, 200, h.content)
        a = h.json()["action"]
        self.assertEqual(a["type"], "choose_character")
        _post(self.client, f"{url}/action/", a, r["token"])
        for _ in range(6):   # follow the hints for a few actions: every one must be legal
            g = Game.objects.get(code=r["code"])
            if g.state["current"] != 0:
                _get(self.client, f"{url}/state/", r["token"])   # let the bot move
                continue
            h = _get(self.client, f"{url}/hint/", r["token"]).json()
            self.assertEqual(h["seat"], 0)
            self.assertEqual(h["version"], g.version)
            st = copy.deepcopy(g.state)
            apply_action(st, 0, h["action"])   # raises GameError if illegal
            resp = _post(self.client, f"{url}/action/", h["action"], r["token"])
            self.assertEqual(resp.status_code, 200, resp.content)

    def test_hint_has_no_side_effects(self):
        r = _post(self.client, "/api/games/", {"player": "Ann", "bots": 1}).json()
        g = Game.objects.get(code=r["code"])
        before = (copy.deepcopy(g.state), g.version)
        _get(self.client, f"/api/games/{r['code']}/hint/", r["token"])
        g.refresh_from_db()
        self.assertEqual((g.state, g.version), before)

    def test_hint_permissions(self):
        r = _post(self.client, "/api/games/", {"player": "Ann", "bots": 1}).json()
        url = f"/api/games/{r['code']}/hint/"
        self.assertEqual(_get(self.client, url).status_code, 403)
        self.assertEqual(_get(self.client, url, "not-a-token").status_code, 403)
        bot_token = Game.objects.get(code=r["code"]).seats.get(index=1).token
        self.assertEqual(_get(self.client, url, bot_token).status_code, 403)
        self.assertEqual(_get(self.client, "/api/games/NOPE1/hint/", r["token"]).status_code, 404)
        self.assertEqual(self.client.post(url, "{}", content_type="application/json", HTTP_X_SEAT_TOKEN=r["token"]).status_code, 405)

    def test_hint_requires_your_turn(self):
        r = _post(self.client, "/api/games/", {"player": "Ann", "bots": 1}).json()
        g = Game.objects.get(code=r["code"])
        g.state["current"] = 1 if g.state["phase"] == "play" else g.state["current"]
        if g.state["phase"] == "setup":
            apply_action(g.state, 0, {"type": "choose_character", "character": g.state["players"][0]["character_choices"][0]})
            g.state["current"] = 1
        g.save()
        resp = _get(self.client, f"/api/games/{r['code']}/hint/", r["token"])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not your turn", resp.json()["error"])

    def test_hint_in_lobby(self):
        r = _post(self.client, "/api/games/", {"player": "Ann"}).json()
        resp = _get(self.client, f"/api/games/{r['code']}/hint/", r["token"])
        self.assertEqual(resp.status_code, 400)


class TutorialViewTests(TestCase):
    def test_public_view_keeps_tutorial_marker(self):
        st = T.new_tutorial_state("Ann", "Bot")
        self.assertIn("tutorial", public_view(st, 0))

    def test_invalid_actions_still_rejected(self):
        st = T.new_tutorial_state("Ann", "Bot")
        with self.assertRaises(GameError):
            apply_action(st, 0, {"type": "choose_character", "character": "heiress"})
