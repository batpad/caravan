import copy
import math
import json
import random

from django.test import TestCase

from .engine import data as D
from .engine import engine as E
from .engine.engine import GameError, apply_action, new_game, public_view, static_data, travel_options
from .engine.simulate import play


def started(n=2, chars=None):
    """A game in round 1 with seat 0 to act. `chars` optionally forces characters."""
    random.seed(11)
    st = new_game([f"P{i}" for i in range(n)], random.Random(3))
    for p in st["players"]:
        apply_action(st, p["seat"], {"type": "choose_character", "character": p["character_choices"][0]})
    st["current"] = 0
    st["turn_placed"] = False
    for i, p in enumerate(st["players"]):
        p["character"] = (chars or {}).get(i, "guildmaster")
        # neutral, generous resources so tests control exactly what matters
        p.update({"coins": 20, "camels": 10, "spice": 0, "silk": 0, "jade": 0, "omens": 0, "vp": 0})
        n_dice = D.HEIRESS_DICE if p["character"] == "heiress" else D.DICE_PER_PLAYER
        p["dice"] = [{"id": 100 * i + k, "value": 3, "placed": False, "white": False} for k in range(n_dice)]
    return st


def dice(st, seat, *values):
    """Set the values of a player's first dice; returns their ids."""
    p = st["players"][seat]
    for d, v in zip(p["dice"], values):
        d["value"] = v
    return [d["id"] for d in p["dice"][:len(values)]]


def end_turn(st):
    apply_action(st, st["current"], {"type": "end_turn"})


class Base(TestCase):
    def assertRejected(self, st, seat, action, msg=None):
        before = json.dumps(st, sort_keys=True)
        with self.assertRaises(GameError) as cm:
            apply_action(st, seat, action)
        self.assertEqual(json.dumps(st, sort_keys=True), before, f"state changed after rejecting {action}")
        if msg:
            self.assertIn(msg, str(cm.exception))


class FlowTests(Base):
    def test_full_games_complete_and_stay_consistent(self):
        rng = random.Random(7)
        random.seed(7)
        for n in (2, 3, 4):
            for _ in range(15):
                st = play(n, rng)
                self.assertEqual(st["phase"], "finished")
                self.assertEqual(len(st["final"]), n)
                json.dumps(st)
                for p in st["players"]:
                    for r in D.RESOURCES:
                        self.assertGreaterEqual(p[r], 0)
                    self.assertLessEqual(len(p["posts"]), D.TRADING_POSTS)
                    self.assertEqual(len(set(p["posts"])), len(p["posts"]))
                    for c in D.NO_POST_CITIES:
                        self.assertNotIn(c, p["posts"])

    def test_turn_enforcement(self):
        st = started()
        self.assertRejected(st, 1, {"type": "place", "die": 100, "space": "treasury"}, "not your turn")
        self.assertRejected(st, 1, {"type": "rest"}, "not your turn")

    def test_one_placement_per_turn(self):
        st = started()
        a, b = dice(st, 0, 4, 2)
        apply_action(st, 0, {"type": "place", "die": a, "space": "treasury"})
        self.assertEqual(st["players"][0]["coins"], 24)
        self.assertRejected(st, 0, {"type": "place", "die": b, "space": "camels"}, "already taken your action")
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "camels"})

    def test_end_turn_requires_placement(self):
        st = started()
        self.assertRejected(st, 0, {"type": "end_turn"})

    def test_malformed_input_never_crashes_or_mutates(self):
        st = started()
        bad = [
            {"type": "place", "die": True, "space": "treasury"},
            {"type": "place", "die": "1", "space": "treasury"},
            {"type": "place", "die": 1.0, "space": "treasury"},
            {"type": "place", "die": 999, "space": "treasury"},
            {"type": "place", "space": "treasury"},
            {"type": "place", "die": 0, "space": ["treasury"]},
            {"type": "place", "die": 0, "space": "palace"},
            {"type": "place", "die": 0, "dice": [1], "space": "treasury"},
            {"type": "place", "dice": [], "space": "treasury"},
            {"type": "place", "dice": "0,1", "space": "treasury"},
            {"type": "place", "dice": [0, 0], "space": "treasury"},
            {"type": "place", "die": 0, "space": "road", "path": "constantinople"},
            {"type": "place", "die": 0, "space": "road", "path": ["constantinople", "atlantis"]},
            {"type": "place", "die": 0, "space": "road", "path": ["constantinople", ["x"]]},
            {"type": "place", "die": 0, "space": "road", "path": [None, None]},
            {"type": "place", "die": 0, "space": "road"},
            {"type": "place", "die": 0, "space": "caravanserai", "slot": True},
            {"type": "place", "die": 0, "space": "caravanserai", "slot": "0"},
            {"type": "place", "die": 0, "space": "caravanserai", "slot": -1},
            {"type": "place", "die": 0, "space": "city", "city": ["baghdad"]},
            {"type": "seer", "die": 0, "value": 6},
            {"type": "nudge", "die": 0, "delta": True},
            {"type": "nudge", "die": 0, "delta": 1.0},
            {"type": "nudge", "die": 0, "delta": 2},
            {"type": "reroll", "die": 0},  # no omens
            {"type": "reroll", "die": 0, "pay": "camels"},  # not the breeder
            {"type": "fulfill", "index": True},
            {"type": "fulfill", "index": 0},
            {"type": None},
            {"type": "teleport"},
            {},
        ]
        for a in bad:
            self.assertRejected(st, 0, a)
        with self.assertRaises(GameError):
            apply_action(st, 0, ["place"])
        with self.assertRaises(GameError):
            apply_action(st, "0", {"type": "rest"})
        with self.assertRaises(GameError):
            apply_action(st, 7, {"type": "rest"})

    def test_finished_game_rejects_actions(self):
        st = started()
        st["phase"] = "finished"
        self.assertRejected(st, 0, {"type": "rest"}, "over")

    def test_setup_validation(self):
        st = new_game(["A", "B"], random.Random(1))
        self.assertRejected(st, 0, {"type": "rest"}, "character first")
        other = st["players"][1]["character_choices"][0]
        self.assertRejected(st, 0, {"type": "choose_character", "character": other})
        self.assertRejected(st, 0, {"type": "choose_character", "character": ["seer"]})
        with self.assertRaises(GameError):
            new_game(["solo"])
        with self.assertRaises(GameError):
            new_game(["a", "b", "c", "d", "e"])


class DiceTests(Base):
    def test_toll_is_die_value_on_crowded_space(self):
        st = started()
        a, c = dice(st, 0, 2, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "treasury"})
        end_turn(st)
        b, = dice(st, 1, 5)
        apply_action(st, 1, {"type": "place", "die": b, "space": "treasury"})
        self.assertEqual(st["players"][1]["coins"], 20 + 5 - 5)
        end_turn(st)
        # the rival's die now crowds the space for seat 0 too
        apply_action(st, 0, {"type": "place", "die": c, "space": "treasury"})
        self.assertEqual(st["players"][0]["coins"], 22 + 1 - 1)

    def test_own_dice_do_not_crowd(self):
        st = started()
        a, b = dice(st, 0, 4, 4)
        apply_action(st, 0, {"type": "place", "die": a, "space": "camels"})
        end_turn(st)
        apply_action(st, 1, {"type": "rest"})
        apply_action(st, 0, {"type": "place", "die": b, "space": "camels"})
        self.assertEqual(st["players"][0]["coins"], 20)
        self.assertEqual(st["players"][0]["camels"], 16)

    def test_toll_unaffordable_rejected(self):
        st = started()
        a, = dice(st, 0, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "bazaar_spice"})
        end_turn(st)
        st["players"][1]["coins"] = 3
        b, c = dice(st, 1, 4, 3)
        self.assertRejected(st, 1, {"type": "place", "die": b, "space": "bazaar_spice"}, "afford")
        apply_action(st, 1, {"type": "place", "die": c, "space": "bazaar_spice"})
        self.assertEqual(st["players"][1]["coins"], 0)
        self.assertEqual(st["players"][1]["spice"], 2)

    def test_public_view_tolls(self):
        st = started()
        a, = dice(st, 0, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "temple"})
        end_turn(st)
        v = public_view(st, 1)
        self.assertEqual(v["tolls"]["temple"], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(v["tolls"]["treasury"], [0] * 7)
        self.assertEqual(v["occupy_cost"]["temple"], 1)
        self.assertIn("travel_pair", v)
        self.assertEqual(v["players"][1]["placements_left"], 5)

    def test_sets_need_matching_values(self):
        st = started()
        a, b, c = dice(st, 0, 3, 4, 3)
        self.assertRejected(st, 0, {"type": "place", "dice": [a, b], "space": "bazaar_spice"}, "same value")
        apply_action(st, 0, {"type": "place", "dice": [a, c], "space": "bazaar_spice"})
        p = st["players"][0]
        # 2 x table[3] + pair bonus
        self.assertEqual(p["spice"], 2 * D.SPACES["bazaar_spice"]["table"][3] + D.SET_BONUS[2])
        self.assertTrue(all(d["placed"] for d in p["dice"] if d["id"] in (a, c)))
        entries = st["spaces"]["bazaar_spice"]
        self.assertEqual(len(entries), 2)
        self.assertEqual({e["set_size"] for e in entries}, {2})

    def test_triple_and_size_limits(self):
        st = started()
        ids = dice(st, 0, 5, 5, 5, 5)
        self.assertRejected(st, 0, {"type": "place", "dice": ids, "space": "bazaar_silk"}, "at most 3")
        self.assertRejected(st, 0, {"type": "place", "dice": ids[:2], "space": "temple"}, "at most 1")
        self.assertRejected(st, 0, {"type": "place", "dice": ids[:2], "space": "caravanserai", "slot": 0})
        apply_action(st, 0, {"type": "place", "dice": ids[:3], "space": "bazaar_silk"})
        self.assertEqual(st["players"][0]["silk"], 3 * 3 + D.SET_BONUS[3])

    def test_single_die_in_dice_list_is_fine(self):
        st = started()
        a, = dice(st, 0, 6)
        apply_action(st, 0, {"type": "place", "dice": [a], "space": "treasury"})
        self.assertEqual(st["players"][0]["coins"], 26)

    def test_set_pays_toll_once_and_jade_cost_per_die(self):
        st = started()
        a, = dice(st, 0, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "bazaar_jade"})
        self.assertEqual(st["players"][0]["coins"], 19)
        end_turn(st)
        b, c = dice(st, 1, 5, 5)
        apply_action(st, 1, {"type": "place", "dice": [b, c], "space": "bazaar_jade"})
        p = st["players"][1]
        self.assertEqual(p["coins"], 20 - 5 - 2)  # toll 5 once, 1 coin per die
        self.assertEqual(p["jade"], 2 + 2 + D.SET_BONUS[2])

    def test_guide_die_is_wild_in_sets(self):
        st = started()
        p = st["players"][0]
        a, = dice(st, 0, 4)
        apply_action(st, 0, {"type": "hire_guide"})
        guide = p["dice"][-1]
        guide["value"] = 1
        self.assertTrue(guide["white"])
        apply_action(st, 0, {"type": "place", "dice": [a, guide["id"]], "space": "treasury"})
        self.assertEqual(p["coins"], 20 - D.GUIDE_COST + 4 * 2 + D.SET_BONUS[2])

    def test_guide_limits(self):
        st = started(3)
        apply_action(st, 0, {"type": "hire_guide"})
        self.assertEqual(st["guide_pool"], D.GUIDE_DICE - 1)
        self.assertRejected(st, 0, {"type": "hire_guide"}, "only one guide")
        st["players"][0]["guide_used"] = False
        st["guide_pool"] = 0
        self.assertRejected(st, 0, {"type": "hire_guide"}, "No guides")
        st["guide_pool"] = 1
        st["players"][0]["coins"] = D.GUIDE_COST - 1
        self.assertRejected(st, 0, {"type": "hire_guide"}, "afford")

    def test_reroll_and_nudge(self):
        st = started()
        p = st["players"][0]
        a, b = dice(st, 0, 1, 6)
        p["omens"] = D.REROLL_COST + D.NUDGE_COST
        apply_action(st, 0, {"type": "reroll", "die": a})
        self.assertEqual(p["omens"], D.NUDGE_COST)
        self.assertRejected(st, 0, {"type": "nudge", "die": b, "delta": 1}, "1 to 6")
        apply_action(st, 0, {"type": "nudge", "die": b, "delta": -1})
        self.assertEqual(p["dice"][1]["value"], 5)
        self.assertEqual(p["omens"], 0)
        self.assertRejected(st, 0, {"type": "nudge", "die": b, "delta": -1}, "afford")
        apply_action(st, 0, {"type": "place", "die": b, "space": "treasury"})
        p["omens"] = 5
        self.assertRejected(st, 0, {"type": "reroll", "die": b}, "used")
        self.assertRejected(st, 0, {"type": "nudge", "die": b, "delta": 1})

    def test_low_roll_compensation(self):
        st = started()
        p = st["players"][0]
        p["posts"] = []
        orig = random.randint
        try:
            random.randint = lambda a, b: 1
            coins = p["coins"]
            E._start_round(st)
        finally:
            random.randint = orig
        n = D.DICE_PER_PLAYER
        self.assertEqual(p["coins"], coins + min(D.LOW_ROLL_MAX, D.LOW_ROLL_PER_DIE * n - n))

    def test_rest(self):
        st = started()
        a, = dice(st, 0, 3)
        apply_action(st, 0, {"type": "place", "die": a, "space": "treasury"})
        apply_action(st, 0, {"type": "rest"})  # rest straight after placing ends the turn
        self.assertEqual(st["players"][0]["coins"], 23 + 4 * D.REST_COINS_PER_DIE)
        self.assertTrue(st["players"][0]["passed"])
        self.assertEqual(st["current"], 1)
        apply_action(st, 1, {"type": "pass"})  # legacy alias
        self.assertEqual(st["round"], 2)

    def test_players_without_dice_are_skipped(self):
        st = started(3)
        for d in st["players"][1]["dice"]:
            d["placed"] = True
        a, = dice(st, 0, 2)
        apply_action(st, 0, {"type": "place", "die": a, "space": "camels"})
        end_turn(st)
        self.assertEqual(st["current"], 2)
        self.assertTrue(st["players"][1]["passed"])


class SpaceTests(Base):
    def test_shrine_sets_next_start_player(self):
        st = started(3)
        apply_action(st, 0, {"type": "rest"})
        a, = dice(st, 1, 1)
        apply_action(st, 1, {"type": "place", "die": a, "space": "temple"})
        self.assertEqual(st["temple_claim"], 1)
        self.assertEqual(st["players"][1]["omens"], 1)
        end_turn(st)
        b, = dice(st, 2, 6)
        apply_action(st, 2, {"type": "place", "die": b, "space": "temple"})
        self.assertEqual(st["temple_claim"], 1)  # only the first visitor
        apply_action(st, 2, {"type": "rest"})
        apply_action(st, 1, {"type": "rest"})
        self.assertEqual(st["round"], 2)
        self.assertEqual(st["current"], 1)

    def test_start_player_rotates_without_shrine(self):
        st = started(3)
        for s in (0, 1, 2):
            apply_action(st, s, {"type": "rest"})
        self.assertEqual(st["start_player"], 1)
        self.assertEqual(st["current"], 1)

    def test_contract_take_refill_and_fulfil(self):
        st = started()
        p = st["players"][0]
        p["character"] = "pathfinder"
        a, = dice(st, 0, 6)
        cid = st["contract_market"][0]
        nxt = st["contract_market"][1]
        apply_action(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 0})
        self.assertEqual(p["contracts"], [cid])
        self.assertEqual(len(st["contract_market"]), D.CONTRACT_SLOTS)  # refilled at once
        self.assertEqual(st["contract_market"][0], nxt)
        req, vp, bonus = D.CONTRACTS[cid]
        self.assertRejected(st, 0, {"type": "fulfill", "index": 0}, "afford")
        for k, v in req.items():
            p[k] += v
        before = {k: p[k] for k in D.RESOURCES}
        apply_action(st, 0, {"type": "fulfill", "index": 0})
        self.assertEqual(p["vp"], vp)
        self.assertEqual(p["fulfilled"], 1)
        self.assertEqual(p["contracts"], [])
        for k in D.RESOURCES:
            self.assertEqual(p[k], before[k] - req.get(k, 0) + bonus.get(k, 0))

    def test_contract_slot_limited_by_die_and_hand_limit(self):
        st = started(chars={0: "pathfinder"})
        p = st["players"][0]
        a, = dice(st, 0, 2)
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 2}, "slots 1–2")
        p["contracts"] = [0, 1]
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 0}, "abandon")
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 0, "discard": 2})
        taken = st["contract_market"][1]
        apply_action(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 1, "discard": 0})
        self.assertEqual(p["contracts"], [1, taken])
        self.assertIn(0, st["contract_discard"])

    def test_city_action(self):
        st = started()
        p = st["players"][0]
        a, b = dice(st, 0, 6, 6)
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "city", "city": "baghdad"}, "trading post")
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "city", "city": "changan"}, "no action")
        p["posts"] = ["baghdad"]
        p["silk"] = 1  # Baghdad: 1 silk -> VP; a 6 allows 2 uses; default = as many as affordable
        uses = D.CITY_ACTION_REPEATS[6]
        for t in (0, uses + 1, True, "2", 1.5):
            self.assertRejected(st, 0, {"type": "place", "die": a, "space": "city", "city": "baghdad", "times": t})
        self.assertRejected(st, 0, {"type": "place", "dice": [a, b], "space": "city", "city": "baghdad"})
        apply_action(st, 0, {"type": "place", "die": a, "space": "city", "city": "baghdad"})
        self.assertEqual((p["silk"], p["vp"]), (0, D.CITIES["baghdad"]["action"]["gain"]["vp"]))
        self.assertEqual(p["vp_sources"], {"cities": p["vp"]})
        self.assertEqual(st["city_spaces"]["baghdad"]["seat"], 0)
        end_turn(st)
        st["players"][1]["posts"] = ["baghdad"]
        st["players"][1]["silk"] = 1
        c, = dice(st, 1, 1)
        self.assertRejected(st, 1, {"type": "place", "die": c, "space": "city", "city": "baghdad"}, "already been taken")

    def test_city_times_explicit(self):
        st = started()
        p = st["players"][0]
        p["posts"] = ["trebizond"]
        p["spice"] = 5
        a, = dice(st, 0, 4)
        apply_action(st, 0, {"type": "place", "die": a, "space": "city", "city": "trebizond", "times": 1})
        gain = D.CITIES["trebizond"]["action"]["gain"]
        self.assertEqual((p["spice"], p["coins"], p["vp"]), (4, 20 + gain.get("coins", 0), gain.get("vp", 0)))


class TravelTests(Base):
    def test_travel_founds_post(self):
        st = started()
        p = st["players"][0]
        a, = dice(st, 0, 3)  # 2 steps
        opts = {o["dest"] for o in travel_options(st, 0, 2)}
        self.assertTrue({"antioch", "baghdad", "trebizond", "tabriz"} <= opts)
        apply_action(st, 0, {"type": "place", "die": a, "space": "road",
                             "path": ["constantinople", "antioch", "baghdad"]})
        self.assertEqual(p["location"], "baghdad")
        self.assertEqual(p["posts"], ["baghdad"])
        self.assertEqual(p["camels"], 8)
        self.assertEqual(p["vp"], D.CITIES["baghdad"]["post_vp"])

    def test_travel_validation(self):
        st = started()
        a, = dice(st, 0, 1)
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road",
                                    "path": ["constantinople", "antioch", "baghdad"]}, "1 step")
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road",
                                    "path": ["antioch", "baghdad"]}, "start where")
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road",
                                    "path": ["constantinople", "baghdad"]}, "no route")
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road",
                                    "path": ["constantinople", "constantinople"]})
        b, = dice(st, 0, 6)
        self.assertRejected(st, 0, {"type": "place", "die": b, "space": "road",
                                    "path": ["constantinople", "antioch", "constantinople"]}, "revisit")

    def test_route_costs_and_toll_validated_together(self):
        st = started()
        a, = dice(st, 0, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "road", "path": ["constantinople", "antioch"]})
        end_turn(st)
        p = st["players"][1]
        b, = dice(st, 1, 2)
        p["coins"] = 4  # toll 2 + sea crossing 3 = 5
        self.assertRejected(st, 1, {"type": "place", "die": b, "space": "road",
                                    "path": ["constantinople", "trebizond"]}, "afford")
        self.assertEqual(travel_options(st, 1, 1, reserve_coins=2)[0]["dest"], "antioch")
        p["coins"] = 5
        apply_action(st, 1, {"type": "place", "die": b, "space": "road", "path": ["constantinople", "trebizond"]})
        self.assertEqual(p["coins"], 0)
        self.assertEqual(p["location"], "trebizond")

    def test_route_type_costs(self):
        st = started()
        p = st["players"][0]
        p["location"] = "trebizond"
        a, = dice(st, 0, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "road", "path": ["trebizond", "tabriz"]})
        m = D.ROUTE_TYPES["mountain"]
        self.assertEqual((p["camels"], p["coins"]), (10 - m["camels"], 20 - m["coins"]))

    def test_road_pair_goes_farther(self):
        st = started()
        p = st["players"][0]
        a, b = dice(st, 0, 1, 1)
        steps = 2 * D.SPACES["road"]["table"][1] + D.SET_BONUS[2]
        self.assertEqual(steps, 3)
        path = ["constantinople", "antioch", "baghdad", "tabriz"]
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road", "path": path})
        apply_action(st, 0, {"type": "place", "dice": [a, b], "space": "road", "path": path})
        self.assertEqual(p["posts"], ["tabriz"])

    def test_changan_arrival_order_and_no_post(self):
        st = started(3)
        for seat in (0, 1, 2):
            p = st["players"][seat]
            p["location"] = "lanzhou"
            a, = dice(st, seat, 1)
            apply_action(st, seat, {"type": "place", "die": a, "space": "road", "path": ["lanzhou", "changan"]})
            self.assertEqual(p["vp"], D.END_CITY_ORDER_VP[seat])
            self.assertNotIn("changan", p["posts"])
            self.assertTrue(p["reached_end"])
            end_turn(st)
        self.assertEqual(st["end_order"], [0, 1, 2])
        # coming back later scores nothing more
        p = st["players"][0]
        a, = dice(st, 0, 1)
        p["dice"][0]["placed"] = False
        p["location"] = "lanzhou"
        apply_action(st, 0, {"type": "place", "die": p["dice"][1]["id"], "space": "road", "path": ["lanzhou", "changan"]})
        self.assertEqual(p["vp"], D.END_CITY_ORDER_VP[0])

    def test_no_post_at_start_or_when_out_of_posts(self):
        st = started()
        p = st["players"][0]
        p["location"] = "antioch"
        a, b = dice(st, 0, 1, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "road", "path": ["antioch", "constantinople"]})
        self.assertEqual(p["posts"], [])
        end_turn(st)
        apply_action(st, 1, {"type": "rest"})
        p["posts"] = ["x"] * D.TRADING_POSTS
        apply_action(st, 0, {"type": "place", "die": b, "space": "road", "path": ["constantinople", "antioch"]})
        self.assertNotIn("antioch", p["posts"])
        self.assertEqual(p["location"], "antioch")


class CharacterTests(Base):
    def test_cartographer_surveys_once_per_round(self):
        st = started(chars={0: "cartographer"})
        p = st["players"][0]
        a, b = dice(st, 0, 3, 3)
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road",
                                    "path": ["constantinople", "antioch", "baghdad"], "post_at": "tabriz"})
        apply_action(st, 0, {"type": "place", "die": a, "space": "road",
                             "path": ["constantinople", "antioch", "baghdad"], "post_at": "antioch"})
        self.assertEqual(p["posts"], ["antioch", "baghdad"])
        bonus_vp = D.CARTOGRAPHER_SURVEY_VP
        self.assertEqual(p["vp"], D.CITIES["baghdad"]["post_vp"] + bonus_vp)
        self.assertTrue(p["power_used"])
        end_turn(st)
        apply_action(st, 1, {"type": "rest"})
        self.assertRejected(st, 0, {"type": "place", "die": b, "space": "road",
                                    "path": ["baghdad", "tabriz", "merv"], "post_at": "tabriz"}, "already surveyed")
        apply_action(st, 0, {"type": "place", "die": b, "space": "road", "path": ["baghdad", "tabriz", "merv"]})
        self.assertEqual(p["posts"], ["antioch", "baghdad", "merv"])  # no automatic survey either

    def test_cartographer_auto_survey_and_decline(self):
        st = started(chars={0: "cartographer"})
        p = st["players"][0]
        p["location"] = "baghdad"
        a, = dice(st, 0, 5)  # 3 steps: baghdad-tabriz-merv-bukhara
        apply_action(st, 0, {"type": "place", "die": a, "space": "road", "path": ["baghdad", "tabriz", "merv", "bukhara"]})
        self.assertEqual(p["posts"], ["tabriz", "bukhara"])  # tabriz and merv tie at 2 VP: first one
        st2 = started(chars={0: "cartographer"})
        a, = dice(st2, 0, 3)
        apply_action(st2, 0, {"type": "place", "die": a, "space": "road",
                              "path": ["constantinople", "antioch", "baghdad"], "post_at": False})
        self.assertEqual(st2["players"][0]["posts"], ["baghdad"])
        self.assertFalse(st2["players"][0]["power_used"])

    def test_non_cartographer_cannot_survey(self):
        st = started()
        a, = dice(st, 0, 3)
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road",
                                    "path": ["constantinople", "antioch", "baghdad"], "post_at": "antioch"}, "Cartographer")

    def test_breeder(self):
        st = started(chars={0: "breeder"})
        p = st["players"][0]
        a, = dice(st, 0, 2)
        apply_action(st, 0, {"type": "reroll", "die": a})  # no omens: camels are used
        self.assertEqual(p["camels"], 10 - D.REROLL_COST)
        p["omens"] = 1
        apply_action(st, 0, {"type": "nudge", "die": a, "delta": 1 if p["dice"][0]["value"] < 6 else -1})
        self.assertEqual((p["omens"], p["camels"]), (0, 10 - D.REROLL_COST - (D.NUDGE_COST - 1)))
        p["omens"] = 3
        apply_action(st, 0, {"type": "reroll", "die": a, "pay": "camels"})
        self.assertEqual(p["omens"], 3)
        self.assertRejected(st, 0, {"type": "reroll", "die": a, "pay": "gold"})
        p["camels"] = 0
        self.assertRejected(st, 0, {"type": "reroll", "die": a, "pay": "camels"}, "afford")
        camels = p["camels"]
        E._start_round(st)
        self.assertGreaterEqual(p["camels"], camels + D.BREEDER_INCOME["camels"])

    def test_breeder_pays_camels_for_missing_goods(self):
        st = started(chars={0: "breeder", 1: "guildmaster"})
        p = st["players"][0]
        cid = next(i for i, (req, _, _) in enumerate(D.CONTRACTS) if req == {"silk": 2})
        p["contracts"] = [cid]
        p.update(silk=0, camels=2 * D.BREEDER_GOOD_CAMELS - 1)
        self.assertRejected(st, 0, {"type": "fulfill", "index": 0}, "afford")
        p["silk"] = 1
        apply_action(st, 0, {"type": "fulfill", "index": 0})
        self.assertEqual((p["silk"], p["camels"]), (0, D.BREEDER_GOOD_CAMELS - 1))
        self.assertEqual(p["vp"], D.CONTRACTS[cid][1])
        # goods on hand are always used first; nobody else can substitute
        q = st["players"][1]
        q["contracts"] = [cid]
        q.update(silk=1, camels=10)
        st["current"] = 1
        self.assertRejected(st, 1, {"type": "fulfill", "index": 0}, "afford")
        p.update(silk=1, camels=0)
        self.assertEqual(E._contract_payment(p, {"silk": 1, "camels": 2}), {"silk": 1, "camels": 2})

    def test_cartographer_survey_costs_coins(self):
        st = started(chars={0: "cartographer"})
        p = st["players"][0]
        a, = dice(st, 0, 3)
        road = D.ROUTE_TYPES["road"]["camels"]
        p["coins"] = sum(D.CARTOGRAPHER_SURVEY_COST.values()) - 1
        path = ["constantinople", "antioch", "baghdad"]
        if D.CARTOGRAPHER_SURVEY_COST.get("coins"):
            self.assertRejected(st, 0, {"type": "place", "die": a, "space": "road", "path": path, "post_at": "antioch"}, "Surveying")
            apply_action(st, 0, {"type": "place", "die": a, "space": "road", "path": path})  # auto survey skipped
            self.assertEqual(p["posts"], ["baghdad"])
            self.assertFalse(p["power_used"])
        st = started(chars={0: "cartographer"})
        p = st["players"][0]
        a, = dice(st, 0, 3)
        apply_action(st, 0, {"type": "place", "die": a, "space": "road", "path": path})
        self.assertEqual(p["coins"], 20 - D.CARTOGRAPHER_SURVEY_COST.get("coins", 0))
        self.assertEqual(p["camels"], 10 - 2 * road - D.CARTOGRAPHER_SURVEY_COST.get("camels", 0))
        self.assertEqual(p["vp_sources"], {"posts": D.CITIES["baghdad"]["post_vp"] + D.CARTOGRAPHER_SURVEY_VP})

    def test_seer(self):
        st = started(chars={0: "seer", 1: "breeder"})
        p = st["players"][0]
        a, b = dice(st, 0, 1, 2)
        self.assertRejected(st, 0, {"type": "seer", "die": a, "value": 7})
        self.assertRejected(st, 0, {"type": "seer", "die": a, "value": 6.0})
        for _ in range(D.SEER_USES):
            apply_action(st, 0, {"type": "seer", "die": a, "value": 6})
        self.assertEqual(p["dice"][0]["value"], 6)
        self.assertTrue(p["seer_used"])
        self.assertRejected(st, 0, {"type": "seer", "die": b, "value": 6}, "Seer")
        p["omens"] = D.SEER_NUDGE_COST
        apply_action(st, 0, {"type": "nudge", "die": b, "delta": 1})
        self.assertEqual(p["omens"], 0)
        st["current"] = 1
        self.assertRejected(st, 1, {"type": "seer", "die": 100, "value": 6}, "Seer")
        omens, coins = p["omens"], p["coins"]
        E._start_round(st)
        self.assertFalse(p["seer_used"])
        self.assertEqual(p["seer_uses"], 0)
        self.assertEqual(p["omens"], omens + D.SEER_INCOME["omens"])
        self.assertGreaterEqual(p["coins"], coins + D.SEER_INCOME.get("coins", 0))

    def test_heiress(self):
        st = started(chars={0: "heiress"})
        p = st["players"][0]
        self.assertEqual(len(p["dice"]), D.HEIRESS_DICE)
        ids = dice(st, 0, 1, 1, 1, 1, 1, 1)
        for i in range(D.HEIRESS_MAX_PLACED - 1):
            apply_action(st, 0, {"type": "place", "die": ids[i], "space": "camels"})
            end_turn(st)
            apply_action(st, 1, {"type": "place", "die": 100 + i, "space": "treasury"})
            end_turn(st)
        self.assertEqual(public_view(st, 0)["players"][0]["placements_left"], 1)
        self.assertRejected(st, 0, {"type": "place", "dice": ids[4:6], "space": "camels"}, "only 5")
        apply_action(st, 0, {"type": "place", "die": ids[4], "space": "camels"})
        end_turn(st)
        apply_action(st, 1, {"type": "place", "die": 104, "space": "treasury"})
        end_turn(st)  # the heiress has a die left but may not place it: round ends
        self.assertEqual(st["round"], 2)

    def test_heiress_rest_and_income(self):
        st = started(chars={0: "heiress"})
        p = st["players"][0]
        apply_action(st, 0, {"type": "rest"})
        self.assertEqual(p["coins"], 20 + D.HEIRESS_MAX_PLACED)  # the spare die earns nothing
        silk = p["silk"]
        E._start_round(st)
        self.assertEqual(len(p["dice"]), D.HEIRESS_DICE)
        self.assertEqual(p["silk"], silk + D.HEIRESS_INCOME["silk"])

    def test_heiress_guide_beyond_cap(self):
        st = started(chars={0: "heiress"})
        p = st["players"][0]
        for d in p["dice"][:5]:
            d["placed"] = True
        apply_action(st, 0, {"type": "hire_guide"})
        apply_action(st, 0, {"type": "place", "die": p["dice"][-1]["id"], "space": "treasury"})

    def test_moneylender(self):
        st = started(3, chars={0: "moneylender"})
        a, b = dice(st, 0, 2, 5)
        apply_action(st, 0, {"type": "place", "die": a, "space": "treasury"})
        end_turn(st)
        c, = dice(st, 1, 4)
        apply_action(st, 1, {"type": "place", "die": c, "space": "treasury"})
        self.assertEqual(st["players"][1]["coins"], 20)  # +4 gained, -4 toll
        self.assertEqual(st["players"][0]["coins"], 22 + D.MONEYLENDER_KICKBACK)
        end_turn(st)
        apply_action(st, 2, {"type": "place", "die": 200, "space": "camels"})
        end_turn(st)
        half = math.ceil(5 * D.MONEYLENDER_TOLL_SHARE)
        self.assertEqual(public_view(st, 0)["tolls"]["camels"], [math.ceil(v * D.MONEYLENDER_TOLL_SHARE) for v in range(7)])
        apply_action(st, 0, {"type": "place", "die": b, "space": "camels"})
        self.assertEqual(st["players"][0]["coins"], 22 + D.MONEYLENDER_KICKBACK - half)

    def test_moneylender_kickback_knob(self):
        old = D.MONEYLENDER_KICKBACK
        D.MONEYLENDER_KICKBACK = 1
        try:
            st = started(3, chars={0: "moneylender"})
            a, = dice(st, 0, 2)
            apply_action(st, 0, {"type": "place", "die": a, "space": "treasury"})
            end_turn(st)
            apply_action(st, 1, {"type": "place", "die": 100, "space": "treasury"})
            self.assertEqual(st["players"][0]["coins"], 23)
            end_turn(st)
            apply_action(st, 2, {"type": "place", "die": 200, "space": "camels"})  # not crowded
            self.assertEqual(st["players"][0]["coins"], 23)
        finally:
            D.MONEYLENDER_KICKBACK = old

    def test_moneylender_no_kickback_when_absent(self):
        st = started(3, chars={0: "moneylender"})
        a, = dice(st, 0, 2)
        apply_action(st, 0, {"type": "place", "die": a, "space": "treasury"})
        end_turn(st)
        apply_action(st, 1, {"type": "place", "die": 100, "space": "camels"})
        end_turn(st)
        apply_action(st, 2, {"type": "place", "die": 200, "space": "camels"})
        self.assertEqual(st["players"][0]["coins"], 22)

    def test_guildmaster(self):
        st = started(chars={0: "guildmaster"})
        p = st["players"][0]
        p["contracts"] = [0, 1]
        a, = dice(st, 0, 6)
        self.assertRejected(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 6})
        apply_action(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 0})
        self.assertEqual(len(p["contracts"]), D.GUILDMASTER_CONTRACTS)
        req, vp, bonus = D.CONTRACTS[0]
        for k, v in req.items():
            p[k] += v
        coins = p["coins"] - req.get("coins", 0)
        apply_action(st, 0, {"type": "fulfill", "index": 0})
        self.assertEqual(p["vp"], vp + D.GUILDMASTER_BONUS_VP)
        self.assertEqual(p["coins"], coins + bonus.get("coins", 0) + D.GUILDMASTER_BONUS_COINS)

    def test_pathfinder(self):
        st = started(chars={0: "pathfinder", 1: "guildmaster"})
        p = st["players"][0]
        p["location"] = "baghdad"
        a, b = dice(st, 0, 1, 1)
        apply_action(st, 0, {"type": "place", "die": a, "space": "road", "path": ["baghdad", "hormuz"]})
        self.assertEqual(p["camels"], 10 - (D.ROUTE_TYPES["desert"]["camels"] - D.PATHFINDER_DISCOUNT))
        self.assertEqual(E._route_cost(p, "mountain"), (D.ROUTE_TYPES["mountain"]["camels"] - 1, D.ROUTE_TYPES["mountain"]["coins"]))
        self.assertEqual(E._route_cost(p, "road"), (1, 0))
        self.assertEqual(E._route_cost(st["players"][1], "desert"), (2, 0))

    def test_guildmaster_reach(self):
        st = started(chars={0: "guildmaster", 1: "pathfinder"})
        a, = dice(st, 0, 2)
        cid = st["contract_market"][1 + D.GUILDMASTER_REACH]
        apply_action(st, 0, {"type": "place", "die": a, "space": "caravanserai", "slot": 1 + D.GUILDMASTER_REACH})
        self.assertEqual(st["players"][0]["contracts"], [cid])
        end_turn(st)
        b, = dice(st, 1, 2)
        self.assertRejected(st, 1, {"type": "place", "die": b, "space": "caravanserai", "slot": 2}, "slots 1–2")

    def test_pathfinder_changan_bonus(self):
        st = started(chars={0: "pathfinder", 1: "guildmaster"})
        for seat in (0, 1):
            p = st["players"][seat]
            p["location"] = "lanzhou"
            a, = dice(st, seat, 1)
            apply_action(st, seat, {"type": "place", "die": a, "space": "road", "path": ["lanzhou", "changan"]})
            end_turn(st)
        self.assertEqual(st["players"][0]["vp"], D.END_CITY_ORDER_VP[0] + D.PATHFINDER_CHANGAN_VP)
        self.assertEqual(st["players"][1]["vp"], D.END_CITY_ORDER_VP[1])
        self.assertEqual(st["players"][0]["vp_sources"], {"changan": st["players"][0]["vp"]})

    def test_quartermaster(self):
        st = started(chars={0: "quartermaster"})
        p = st["players"][0]
        p["posts"] = ["tabriz", "merv"]
        p["posts"] = ["tabriz", "merv", "baghdad"]
        a, = dice(st, 0, 1)  # a 1 normally allows 1 use; the Quartermaster gets 2
        apply_action(st, 0, {"type": "place", "die": a, "space": "city", "city": "tabriz"})
        self.assertEqual(p["camels"], 10 + 2 * (D.CITY_ACTION_REPEATS[1] + D.QUARTERMASTER_EXTRA_USES))
        coins = p["coins"]
        E._start_round(st)
        income = 1 + 3 // D.QUARTERMASTER_POSTS_PER_COIN  # Tabriz coin + post coins
        self.assertGreaterEqual(p["coins"], coins + income)
        self.assertLessEqual(p["coins"], coins + income + D.LOW_ROLL_MAX)

    def test_every_character_has_a_test(self):
        names = {n[5:] for n in dir(self) if n.startswith("test_")}
        for c in D.CHARACTERS:
            self.assertTrue(any(n.startswith(c) for n in names), c)


class ScoringTests(Base):
    def test_end_of_round_churn(self):
        st = started()
        market = list(st["contract_market"])
        apply_action(st, 0, {"type": "rest"})
        apply_action(st, 1, {"type": "rest"})
        self.assertEqual(st["contract_market"][:D.CONTRACT_SLOTS - D.CONTRACT_CHURN], market[D.CONTRACT_CHURN:])
        self.assertEqual(len(st["contract_market"]), D.CONTRACT_SLOTS)

    def test_final_scoring(self):
        st = started(3)
        a, b, c = st["players"]
        a["posts"] = ["trebizond", "kabul", "antioch"]
        b["posts"] = ["baghdad", "tabriz"]
        c["posts"] = ["merv"]
        a["commissions"] = [D.COMMISSIONS.index(("trebizond", "kabul")), D.COMMISSIONS.index(("antioch", "kashgar"))]
        b["commissions"] = [D.COMMISSIONS.index(("hormuz", "bukhara")), D.COMMISSIONS.index(("merv", "dunhuang"))]
        c["commissions"] = [D.COMMISSIONS.index(("merv", "dunhuang")), D.COMMISSIONS.index(("tabriz", "khotan"))]
        a["fulfilled"], b["fulfilled"], c["fulfilled"] = 2, 2, 0
        a.update(coins=25, spice=4, silk=0, jade=2, vp=10)
        b.update(coins=9, vp=10)
        c.update(coins=0, vp=40)
        E._final_scoring(st)
        rows = {r["seat"]: r for r in st["final"]}
        self.assertEqual(rows[0]["breakdown"], {"during_game": 10, "commissions": 8, "post_majority": 6,
                                                 "contract_majority": 4, "coins": 2, "goods": 2})
        self.assertEqual(rows[1]["breakdown"]["post_majority"], 3)
        self.assertEqual(rows[1]["breakdown"]["contract_majority"], 4)
        self.assertEqual(rows[1]["breakdown"]["commissions"], 0)
        self.assertEqual(rows[2]["breakdown"]["commissions"], 2)
        self.assertEqual(st["final"][0]["seat"], 2)
        self.assertEqual(st["phase"], "finished")

    def test_two_player_post_majority_has_no_runner_up(self):
        st = started(2)
        st["players"][0]["posts"] = ["baghdad", "tabriz"]
        st["players"][1]["posts"] = ["merv"]
        E._final_scoring(st)
        rows = {r["seat"]: r for r in st["final"]}
        self.assertEqual(rows[0]["breakdown"]["post_majority"], D.POST_MAJORITY_VP[0])
        self.assertEqual(rows[1]["breakdown"]["post_majority"], 0)

    def test_tiebreaks_and_shared_rank(self):
        st = started(3)
        for p in st["players"]:
            p.update(vp=10, coins=5, spice=0, silk=0, jade=0, posts=[], commissions=[0, 1], fulfilled=0)
        st["players"][1]["spice"] = 1  # same VP and coins: more goods wins
        E._final_scoring(st)
        self.assertEqual([r["seat"] for r in st["final"]][0], 1)
        self.assertEqual([r["rank"] for r in st["final"]], [1, 2, 2])

    def test_last_round_finishes_game(self):
        st = started()
        st["round"] = D.NUM_ROUNDS
        apply_action(st, 0, {"type": "rest"})
        apply_action(st, 1, {"type": "rest"})
        self.assertEqual(st["phase"], "finished")
        self.assertRejected(st, 0, {"type": "rest"})


class ViewTests(Base):
    def test_hidden_info(self):
        st = started()
        v = public_view(st, 0)
        self.assertTrue(all(c is None for c in v["players"][1]["commissions"]))
        self.assertTrue(all(c is not None for c in v["players"][0]["commissions"]))
        self.assertNotIn("contract_deck", v)
        self.assertNotIn("contract_discard", v)
        self.assertNotIn("travel", public_view(st, 1))  # not their turn
        self.assertIn("travel", v)
        json.dumps(v)
        json.dumps(public_view(st, None))

    def test_static_data_serialisable(self):
        s = static_data()
        json.dumps(s)
        for k in ("toll_per_pip", "set_bonus", "low_roll_max"):
            self.assertIn(k, s["rules"])
        self.assertIn("powers", s)
        self.assertTrue(all("max_dice" in sp for sp in s["spaces"].values()))

    def test_view_does_not_mutate(self):
        st = started()
        before = copy.deepcopy(st)
        public_view(st, 0)
        self.assertEqual(st, before)


class ApiTests(TestCase):
    def post(self, url, body=None, token=None):
        headers = {"HTTP_X_SEAT_TOKEN": token} if token else {}
        data = body if isinstance(body, str) else json.dumps(body or {})
        return self.client.post(url, data, content_type="application/json", **headers)

    def test_full_flow(self):
        r = self.post("/api/games/", {"player": "Ana", "max_players": 2}).json()
        code, t0 = r["code"], r["token"]
        self.assertEqual(self.client.get("/api/games/").json()["games"][0]["code"], code)
        self.assertEqual(self.post(f"/api/games/{code}/start/", token=t0).status_code, 400)
        t1 = self.post(f"/api/games/{code}/join/", {"player": "Bo"}).json()["token"]
        self.assertEqual(self.post(f"/api/games/{code}/join/", {"player": "Cy"}).status_code, 400)  # full
        self.assertEqual(self.post(f"/api/games/{code}/start/", token=t1).status_code, 403)  # not host
        self.assertEqual(self.post(f"/api/games/{code}/start/", token=t0).status_code, 200)

        st = self.client.get(f"/api/games/{code}/state/", HTTP_X_SEAT_TOKEN=t0).json()
        self.assertEqual(st["seat"], 0)
        v = st["version"]
        self.assertTrue(self.client.get(f"/api/games/{code}/state/?since={v}").json()["unchanged"])

        for tok, seat in ((t0, 0), (t1, 1)):
            choices = self.client.get(f"/api/games/{code}/state/", HTTP_X_SEAT_TOKEN=tok).json()["game"]["players"][seat]["character_choices"]
            self.assertEqual(self.post(f"/api/games/{code}/action/", {"type": "choose_character", "character": choices[0]}, tok).status_code, 200)

        g = self.client.get(f"/api/games/{code}/state/", HTTP_X_SEAT_TOKEN=t0).json()["game"]
        self.assertEqual(g["phase"], "play")
        cur_tok = t0 if g["current"] == 0 else t1
        other_tok = t1 if cur_tok == t0 else t0
        r = self.post(f"/api/games/{code}/action/", {"type": "pass"}, other_tok)
        self.assertEqual(r.status_code, 400)
        self.assertIn("not your turn", r.json()["error"])
        self.assertEqual(self.post(f"/api/games/{code}/action/", "[1, 2]", cur_tok).status_code, 400)
        self.assertEqual(self.post(f"/api/games/{code}/action/", {"type": "pass"}, cur_tok).status_code, 200)
        self.assertEqual(self.post(f"/api/games/{code}/action/", {"type": "pass"}, "bogus").status_code, 403)


# --------------------------------------------------------------------------- AI bot

from django.test import override_settings  # noqa: E402

from . import views  # noqa: E402
from .engine import bot  # noqa: E402
from .engine.simulate import _bot_turn as random_turn  # noqa: E402
from .models import Game  # noqa: E402


def bot_game(agents, seed):
    """Play a full game; agents[i] is a bot level or "random". Bots run strict (errors raise)."""
    rng = random.Random(seed)
    random.seed(seed)
    st = new_game([f"S{i}" for i in range(len(agents))], rng)
    for p in st["players"]:
        if agents[p["seat"]] == "random":
            apply_action(st, p["seat"], {"type": "choose_character", "character": p["character_choices"][0]})
        else:
            bot.choose_character(st, p["seat"], rng, agents[p["seat"]])
    turns = 0
    while st["phase"] != "finished":
        seat = st["current"]
        if agents[seat] == "random":
            random_turn(st, rng)
        else:
            acts = bot.take_turn(st, seat, rng, agents[seat], strict=True)
            assert acts and acts[-1]["type"] in ("end_turn", "rest"), acts
        turns += 1
        assert turns < 1000, "runaway game"
    return st


class BotTests(Base):
    def test_bot_plays_only_legal_actions(self):
        seed = 0
        for n in (2, 3, 4):
            for level in bot.LEVELS:
                for mix in (False, True):
                    seed += 1
                    agents = [level] * n
                    if mix:
                        agents[seed % n] = "random"
                    st = bot_game(agents, seed)  # strict: an illegal action raises GameError
                    self.assertEqual(st["phase"], "finished")
                    for p in st["players"]:
                        for r in D.RESOURCES:
                            self.assertGreaterEqual(p[r], 0)

    def test_bot_beats_random_bot(self):
        wins = 0
        for g in range(6):
            agents = ["normal", "random"] if g % 2 == 0 else ["random", "normal"]
            st = bot_game(agents, 100 + g)
            best = st["final"][0]["seat"]
            wins += agents[best] == "normal"
        self.assertGreaterEqual(wins, 5)

    def test_bot_ignores_hidden_information(self):
        """Scrambling what the seat cannot see (deck order, rival commissions) changes nothing."""
        for seed in range(4):
            rng = random.Random(seed)
            random.seed(seed)
            st = new_game(["A", "B", "C"], rng)
            for p in st["players"]:
                bot.choose_character(st, p["seat"], rng)
            for _ in range(6 + seed * 3):  # advance into the game a little
                bot.take_turn(st, st["current"], rng, strict=True)
            seat = st["current"]
            twin = copy.deepcopy(st)
            random.Random(99).shuffle(twin["contract_deck"])
            twin["contract_discard"] = list(reversed(twin["contract_discard"]))
            for p in twin["players"]:
                if p["seat"] != seat:
                    p["commissions"] = [(c + 5) % len(D.COMMISSIONS) for c in p["commissions"]]
            state_rand = random.getstate()
            a1 = bot.take_turn(st, seat, random.Random(7), "hard", strict=True)
            random.setstate(state_rand)
            a2 = bot.take_turn(twin, seat, random.Random(7), "hard", strict=True)
            self.assertEqual(a1, a2)

    def test_planner_works_on_a_public_view(self):
        rng = random.Random(5)
        random.seed(5)
        st = new_game(["A", "B"], rng)
        for p in st["players"]:
            bot.choose_character(st, p["seat"], rng)
        view = public_view(st, st["current"])
        self.assertNotIn("contract_deck", view)
        before = copy.deepcopy(view)
        plan = bot.plan_turn(view, st["current"], rng, "normal")
        self.assertTrue(plan.action or plan.preps)
        self.assertEqual(view, before)  # planning never mutates its input
        a = bot.next_action(view, st["current"], rng)
        apply_action(st, st["current"], a)  # the suggestion is legal

    def test_bot_turn_is_fast(self):
        import time
        rng = random.Random(3)
        random.seed(3)
        st = new_game(["A", "B", "C", "D"], rng)
        for p in st["players"]:
            bot.choose_character(st, p["seat"], rng)
        worst = 0
        for _ in range(30):
            t = time.perf_counter()
            bot.take_turn(st, st["current"], rng, "hard", strict=True)
            worst = max(worst, time.perf_counter() - t)
        self.assertLess(worst, 1.0)  # generous: typical turns take a few ms

    def test_bot_names(self):
        taken = []
        for _ in range(20):
            taken.append(bot.bot_name(taken))
        self.assertEqual(len(set(n.lower() for n in taken)), 20)
        self.assertTrue(all(n.startswith("Bot · ") for n in taken))


class ApiBotTests(TestCase):
    def post(self, url, body=None, token=None):
        headers = {"HTTP_X_SEAT_TOKEN": token} if token else {}
        return self.client.post(url, json.dumps(body or {}), content_type="application/json", **headers)

    def get_state(self, code, token=None):
        headers = {"HTTP_X_SEAT_TOKEN": token} if token else {}
        return self.client.get(f"/api/games/{code}/state/", **headers).json()

    def lobby(self, max_players=4):
        r = self.post("/api/games/", {"player": "Ana", "max_players": max_players}).json()
        return r["code"], r["token"]

    def test_add_and_remove_bot_permissions(self):
        code, host = self.lobby(3)
        guest = self.post(f"/api/games/{code}/join/", {"player": "Bo"}).json()["token"]
        self.assertEqual(self.post(f"/api/games/{code}/add_bot/", {}, guest).status_code, 403)
        self.assertEqual(self.post(f"/api/games/{code}/add_bot/", {}).status_code, 403)
        self.assertEqual(self.post(f"/api/games/{code}/add_bot/", {"level": "godlike"}, host).status_code, 400)
        r = self.post(f"/api/games/{code}/add_bot/", {"level": "hard"}, host)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["seat"], 2)
        self.assertTrue(r.json()["name"].startswith("Bot · "))
        self.assertEqual(self.post(f"/api/games/{code}/add_bot/", {}, host).status_code, 400)  # full
        players = self.get_state(code, host)["players"]
        self.assertEqual([p["is_bot"] for p in players], [False, False, True])
        self.assertEqual(players[2]["bot_level"], "hard")
        # remove_seat: host only, bots only
        self.assertEqual(self.post(f"/api/games/{code}/remove_seat/", {"index": 2}, guest).status_code, 403)
        self.assertEqual(self.post(f"/api/games/{code}/remove_seat/", {"index": 1}, host).status_code, 400)
        self.assertEqual(self.post(f"/api/games/{code}/remove_seat/", {"index": 9}, host).status_code, 400)
        self.assertEqual(self.post(f"/api/games/{code}/remove_seat/", {"index": "2"}, host).status_code, 400)
        self.post(f"/api/games/{code}/add_bot/", {}, host)  # fails: full
        self.assertEqual(self.post(f"/api/games/{code}/remove_seat/", {"index": 2}, host).status_code, 200)
        self.assertEqual(len(self.get_state(code)["players"]), 2)
        # removing a bot in the middle compacts the seat indices
        self.post(f"/api/games/{code}/leave/", {}, guest)
        self.post(f"/api/games/{code}/add_bot/", {}, host)
        self.post(f"/api/games/{code}/add_bot/", {}, host)
        self.assertEqual(self.post(f"/api/games/{code}/remove_seat/", {"index": 1}, host).status_code, 200)
        self.assertEqual([p["index"] for p in self.get_state(code)["players"]], [0, 1])
        # nothing changes once the game has started
        self.assertEqual(self.post(f"/api/games/{code}/start/", {}, host).status_code, 200)
        self.assertEqual(self.post(f"/api/games/{code}/add_bot/", {}, host).status_code, 400)
        self.assertEqual(self.post(f"/api/games/{code}/remove_seat/", {"index": 1}, host).status_code, 400)

    def test_bots_choose_characters_at_start(self):
        code, host = self.lobby()
        self.post(f"/api/games/{code}/add_bot/", {"level": "easy"}, host)
        self.post(f"/api/games/{code}/add_bot/", {}, host)
        self.assertEqual(self.post(f"/api/games/{code}/start/", {}, host).status_code, 200)
        g = self.get_state(code, host)["game"]
        self.assertEqual(g["phase"], "setup")
        self.assertIsNone(g["players"][0]["character"])
        self.assertTrue(all(p["character"] for p in g["players"][1:]))

    def test_host_leaving_a_bot_only_lobby_deletes_it(self):
        code, host = self.lobby()
        self.post(f"/api/games/{code}/add_bot/", {}, host)
        self.post(f"/api/games/{code}/leave/", {}, host)
        self.assertFalse(Game.objects.filter(code=code).exists())

    def test_create_solo_game_with_bots(self):
        self.assertEqual(self.post("/api/games/", {"player": "Ana", "bots": 4}).status_code, 400)
        self.assertEqual(self.post("/api/games/", {"player": "Ana", "bots": 1, "bot_level": "x"}).status_code, 400)
        r = self.post("/api/games/", {"player": "Ana", "bots": 2, "bot_level": "easy"}).json()
        self.assertTrue(r["started"])
        st = self.get_state(r["code"], r["token"])
        self.assertEqual(st["status"], "playing")
        self.assertEqual(len(st["players"]), 3)
        self.assertEqual([p["is_bot"] for p in st["players"]], [False, True, True])
        self.assertNotIn(r["code"], [g["code"] for g in self.client.get("/api/games/").json()["games"]])

    @override_settings(BOT_STEP_DELAY=0)
    def test_lazy_stepping_finishes_game_when_human_always_rests(self):
        r = self.post("/api/games/", {"player": "Ana", "bots": 3, "bot_level": "normal"}).json()
        code, tok = r["code"], r["token"]
        g = self.get_state(code, tok)["game"]
        choice = g["players"][0]["character_choices"][0]
        self.assertEqual(self.post(f"/api/games/{code}/action/", {"type": "choose_character", "character": choice}, tok).status_code, 200)
        polls = 0
        while True:
            st = self.get_state(code, tok)
            if st["status"] == "finished":
                break
            g = st["game"]
            if g["phase"] == "play" and g["current"] == 0:
                self.assertEqual(self.post(f"/api/games/{code}/action/", {"type": "rest"}, tok).status_code, 200)
            polls += 1
            self.assertLess(polls, 600, "game stalled")
        g = st["game"]
        self.assertEqual(g["phase"], "finished")
        self.assertEqual(len(g["final"]), 4)
        v = st["version"]
        self.assertTrue(self.client.get(f"/api/games/{code}/state/?since={v}").json()["unchanged"])  # stops

    @override_settings(BOT_STEP_DELAY=3600)
    def test_bots_wait_for_the_pacing_delay(self):
        r = self.post("/api/games/", {"player": "Ana", "bots": 1}).json()
        code, tok = r["code"], r["token"]
        game = Game.objects.get(code=code)
        st = game.state
        apply_action(st, 0, {"type": "choose_character", "character": st["players"][0]["character_choices"][0]})
        st["current"] = 1  # the bot is to move
        game.state = st
        game.save()
        v = game.version
        self.assertEqual(self.get_state(code, tok)["version"], v)  # too soon: nothing happens
        stepped = views.step_bots(Game.objects.get(code=code), force=True)
        self.assertEqual(stepped.version, v + 1)

    def test_concurrent_pollers_step_only_once(self):
        r = self.post("/api/games/", {"player": "Ana", "bots": 1}).json()
        game = Game.objects.get(code=r["code"])
        st = game.state
        apply_action(st, 0, {"type": "choose_character", "character": st["players"][0]["character_choices"][0]})
        st["current"] = 1
        game.state = st
        game.save()
        a = Game.objects.get(pk=game.pk)
        b = Game.objects.get(pk=game.pk)  # a second poller that read the same version
        views.step_bots(a, force=True)
        after = Game.objects.get(pk=game.pk)
        views.step_bots(b, force=True)  # stale: must not play another bot turn
        self.assertEqual(Game.objects.get(pk=game.pk).version, after.version)
        self.assertEqual(Game.objects.get(pk=game.pk).state, after.state)
