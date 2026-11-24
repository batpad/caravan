"""Headless self-play with a simple greedy-random bot. Used for smoke tests and balance checks.

    python -m game.engine.simulate 500

The bot is deliberately weak: it picks a random legal placement, weighted towards
obviously useful moves, and occasionally uses every mechanic (sets, guides, rerolls,
nudges, character powers) so that full games exercise the whole engine.
"""
import random
import sys
from collections import Counter, defaultdict

from . import data as D
from .engine import GameError, _placements_left, apply_action, new_game, travel_options


def _try(state, seat, action):
    try:
        apply_action(state, seat, action)
        return True
    except GameError:
        return False


def _fulfil_all(state, seat):
    p = state["players"][seat]
    for i in reversed(range(len(p["contracts"]))):
        _try(state, seat, {"type": "fulfill", "index": i})


def _free_actions(state, seat, rng):
    p = state["players"][seat]
    unused = [d for d in p["dice"] if not d["placed"]]
    if not unused:
        return
    counts = Counter(d["value"] for d in unused if not d["white"])
    # Seer: turn a lone die into a match for the most common value
    if p["character"] == "seer" and not p["seer_used"] and counts:
        val, c = counts.most_common(1)[0]
        lone = [d for d in unused if d["value"] != val]
        if lone and rng.random() < 0.8:
            low = min(lone, key=lambda d: d["value"])
            _try(state, seat, {"type": "seer", "die": low["id"], "value": val if c >= 2 and rng.random() < 0.5 else 6})
    # nudge a die next to a pair to make a set
    if rng.random() < 0.4:
        for d in unused:
            for delta in (1, -1):
                if counts.get(d["value"] + delta, 0) >= 1 and counts.get(d["value"], 0) == 1:
                    if _try(state, seat, {"type": "nudge", "die": d["id"], "delta": delta}):
                        return
    # reroll low dice while omens are plentiful
    low = sorted((d for d in unused if d["value"] <= 2), key=lambda d: d["value"])
    fuel = p["omens"] + (p["camels"] // 3 if p["character"] == "breeder" else 0)
    if low and (fuel >= 2 or rng.random() < 0.3):
        _try(state, seat, {"type": "reroll", "die": low[0]["id"]})
    # hire a guide now and then
    if not p["guide_used"] and p["coins"] >= D.GUIDE_COST + 3 and rng.random() < 0.25:
        _try(state, seat, {"type": "hire_guide"})


def _candidates(state, seat):
    p = state["players"][seat]
    unused = [d for d in p["dice"] if not d["placed"]]
    own_ok = _placements_left(p) > 0
    singles = [d for d in unused if d["white"] or own_ok]
    by_val = defaultdict(list)
    for d in unused:
        if not d["white"] and own_ok:
            by_val[d["value"]].append(d)
    guide = next((d for d in unused if d["white"]), None)
    groups = [([d], d["value"]) for d in singles]
    for v, ds in by_val.items():
        pool = ds + ([guide] if guide else [])
        for n in (2, 3):
            if len(pool) >= n:
                groups.append((pool[:n], v))
    out = []  # (weight, action)
    for dice, v in groups:
        n = len(dice)
        ids = [d["id"] for d in dice]
        sel = {"die": ids[0]} if n == 1 else {"dice": ids}
        w_set = 3 if n > 1 else 1
        for s in ("bazaar_spice", "bazaar_silk", "bazaar_jade", "camels", "treasury", "temple"):
            if n <= D.SPACES[s]["max_dice"]:
                out.append((w_set, {"type": "place", "space": s, **sel}))
        if n == 1:
            for slot in range(min(v, len(state["contract_market"]))):
                a = {"type": "place", "space": "caravanserai", "slot": slot, **sel}
                if len(p["contracts"]) >= (D.GUILDMASTER_CONTRACTS if p["character"] == "guildmaster"
                                           else D.MAX_OPEN_CONTRACTS):
                    a["discard"] = 0
                out.append((1, a))
            for c in p["posts"]:
                if c in state["city_spaces"] and state["city_spaces"][c] is None:
                    out.append((4, {"type": "place", "space": "city", "city": c, **sel}))
        if n <= D.SPACES["road"]["max_dice"]:
            steps = D.SPACES["road"]["table"][v] * n + D.SET_BONUS[n]
            for o in travel_options(state, seat, steps):
                w = (5 if o["dest"] not in p["posts"] else 1) * w_set
                out.append((w, {"type": "place", "space": "road", "path": o["path"], **sel}))
    return out


def _bot_turn(state, rng):
    seat = state["current"]
    p = state["players"][seat]
    _fulfil_all(state, seat)
    if state["turn_placed"]:
        apply_action(state, seat, {"type": "end_turn"})
        return
    _free_actions(state, seat, rng)
    cands = _candidates(state, seat)
    # weighted shuffle
    order = sorted(cands, key=lambda wa: -rng.random() ** (1.0 / wa[0]))
    for _, a in order:
        if _try(state, seat, a):
            break
    else:
        apply_action(state, seat, {"type": "rest"})
        return
    _fulfil_all(state, seat)
    if p["character"] and rng.random() < 0.05:
        apply_action(state, seat, {"type": "rest"})  # occasionally rest early
        return
    apply_action(state, seat, {"type": "end_turn"})


def play(n_players, rng, characters=None):
    state = new_game([f"Bot{i}" for i in range(n_players)], rng)
    for p in state["players"]:
        if characters:
            p["character_choices"] = [characters[p["seat"]], p["character_choices"][0]]
            ch = characters[p["seat"]]
        else:
            ch = rng.choice(p["character_choices"])
        apply_action(state, p["seat"], {"type": "choose_character", "character": ch})
    guard = 0
    while state["phase"] != "finished":
        _bot_turn(state, rng)
        guard += 1
        assert guard < 5000, "runaway game"
    return state


def main(n=200):
    rng = random.Random(1)
    random.seed(1)
    wins_by_char = defaultdict(float)
    games_by_char = defaultdict(int)
    expected_by_char = defaultdict(float)
    wins_by_seat = defaultdict(int)
    totals = []
    for i in range(n):
        np_ = 2 + i % 3
        s = play(np_, rng)
        winners = [r["seat"] for r in s["final"] if r["rank"] == 1]
        for w in winners:
            wins_by_seat[(np_, w)] += 1
        for p in s["players"]:
            games_by_char[p["character"]] += 1
            expected_by_char[p["character"]] += 1 / np_
            if p["seat"] in winners:
                wins_by_char[p["character"]] += 1 / len(winners)
        totals.extend(r["total"] for r in s["final"])
    print(f"{n} games, avg score {sum(totals) / len(totals):.1f}, max {max(totals)}")
    for c in D.CHARACTERS:
        g = games_by_char[c]
        print(f"  {c:14s} win rate {wins_by_char[c] / g:.2f} (fair {expected_by_char[c] / g:.2f}) "
              f"wins/fair {wins_by_char[c] / expected_by_char[c]:.2f} over {g}")
    for k in sorted(wins_by_seat):
        print("  players/seat", k, wins_by_seat[k])


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
