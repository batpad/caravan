"""Rules engine for Caravan Road.

The whole game state is a JSON-serialisable dict. Every mutation goes through
`apply_action(state, seat, action)`, which validates and raises `GameError` on
anything illegal. Validation always completes before the state is touched, so a
rejected action leaves the state exactly as it was. Nothing here touches Django.

See RULES_CHANGES.md for the action schema and state fields.
"""
import copy
import math
import random
from collections import deque

from . import data as D


class GameError(Exception):
    pass


# --------------------------------------------------------------------------- helpers

def _adjacency():
    adj = {c: [] for c in D.CITIES}
    for a, b, kind in D.ROUTES:
        adj[a].append((b, kind))
        adj[b].append((a, kind))
    return adj


ADJ = _adjacency()


def _log(state, text, seat=None):
    state["log"].append({"round": state["round"], "seat": seat, "text": text})
    if len(state["log"]) > 300:
        state["log"] = state["log"][-300:]


def _fmt(res):
    names = {"vp": "VP", "coins": "coins", "camels": "camels", "spice": "spice",
             "silk": "silk", "jade": "jade", "omens": "omens"}
    parts = [f"{v} {names.get(k, k)}" for k, v in res.items() if v]
    return ", ".join(parts) if parts else "nothing"


def _is_int(x):
    return type(x) is int  # rejects bool, float, str


def _add(*costs):
    out = {}
    for c in costs:
        for k, v in c.items():
            if v:
                out[k] = out.get(k, 0) + v
    return out


def _can_pay(p, cost):
    return all(p.get(k, 0) >= v for k, v in cost.items())


def _check(p, cost, what="that"):
    if not _can_pay(p, cost):
        raise GameError(f"You cannot afford {what} ({_fmt(cost)}).")


def _pay(p, cost, what="that"):
    _check(p, cost, what)
    for k, v in cost.items():
        p[k] -= v


def _gain(p, res):
    for k, v in res.items():
        p[k] = p.get(k, 0) + v


def _scale(res, n):
    return {k: v * n for k, v in res.items()}


def _player(state, seat):
    return state["players"][seat]


def _die(p, die_id):
    if not _is_int(die_id):
        raise GameError("Die ids are whole numbers.")
    for d in p["dice"]:
        if d["id"] == die_id:
            return d
    raise GameError("No such die.")


def _unused_dice(p):
    return [d for d in p["dice"] if not d["placed"]]


def _placements_left(p):
    """How many more of their own (coloured) dice this player may place this round."""
    if p["character"] != "heiress":
        return len([d for d in p["dice"] if not d["white"] and not d["placed"]])
    placed = len([d for d in p["dice"] if not d["white"] and d["placed"] and not d.get("rested")])
    unused = len([d for d in p["dice"] if not d["white"] and not d["placed"]])
    return max(0, min(unused, D.HEIRESS_MAX_PLACED - placed))


def _can_place(p):
    return _placements_left(p) > 0 or any(d["white"] and not d["placed"] for d in p["dice"])


def _max_contracts(p):
    return D.GUILDMASTER_CONTRACTS if p["character"] == "guildmaster" else D.MAX_OPEN_CONTRACTS


def _contract_reach(p, value):
    """Highest Caravanserai slot (1-based) a die of `value` can take from."""
    return value + (D.GUILDMASTER_REACH if p["character"] == "guildmaster" else 0)


def _route_cost(p, kind):
    r = D.ROUTE_TYPES[kind]
    camels = r["camels"]
    if p["character"] == "pathfinder" and kind in D.PATHFINDER_ROUTES:
        camels = max(0, camels - D.PATHFINDER_DISCOUNT)
    return camels, r["coins"]


def _steps(space_table, value, n):
    return space_table[value] * n + D.SET_BONUS[n]


def _city_uses(p, value):
    extra = D.QUARTERMASTER_EXTRA_USES if p["character"] == "quartermaster" else 0
    return D.CITY_ACTION_REPEATS[value] + extra


def _crowded(state, seat, space):
    return any(e["seat"] != seat for e in state["spaces"][space])


def _toll(state, seat, space, value):
    """Coins to place a die/set of `value` on a shared space already used by a rival."""
    if not _crowded(state, seat, space):
        return 0
    return _char_toll(_player(state, seat), value * D.TOLL_PER_PIP)


def _char_toll(p, t):
    """Apply character discounts to a toll of `t` coins."""
    if p["character"] == "moneylender":
        return math.ceil(t * D.MONEYLENDER_TOLL_SHARE)
    return t


# legacy name, kept for callers of the old API
def _occupy_cost(state, seat, space, value=1):
    return _toll(state, seat, space, value)


def _nudge_cost(p):
    return D.SEER_NUDGE_COST if p["character"] == "seer" else D.NUDGE_COST


def _omen_payment(p, n, pay):
    """Cost dict for an omen-priced action. The Camel Breeder may use camels instead."""
    if pay not in (None, "omens", "camels"):
        raise GameError("Pay with 'omens' or 'camels'.")
    if p["character"] != "breeder":
        if pay == "camels":
            raise GameError("Only the Camel Breeder may pay camels for omens.")
        return {"omens": n}
    if pay == "omens":
        return {"omens": n}
    if pay == "camels":
        return {"camels": n}
    om = min(p["omens"], n)  # omens first, the rest in camels
    return _add({"omens": om}, {"camels": n - om})


# --------------------------------------------------------------------------- setup

def new_game(player_names, rng=None):
    rng = rng or random.Random()
    if not isinstance(player_names, (list, tuple)):
        raise GameError("Caravan Road needs 2 to 4 players.")
    n = len(player_names)
    if not 2 <= n <= 4:
        raise GameError("Caravan Road needs 2 to 4 players.")
    chars = list(D.CHARACTERS)
    rng.shuffle(chars)
    commissions = list(range(len(D.COMMISSIONS)))
    rng.shuffle(commissions)
    deck = list(range(len(D.CONTRACTS)))
    rng.shuffle(deck)

    players = []
    for i, name in enumerate(player_names):
        p = {
            "seat": i, "name": name, "color": D.PLAYER_COLORS[i], "color_name": D.COLOR_NAMES[i],
            "character": None, "character_choices": [chars.pop(), chars.pop()],
            "commissions": [commissions.pop(), commissions.pop()],
            "dice": [], "posts": [], "location": D.START_CITY, "contracts": [],
            "fulfilled": 0, "passed": False, "seer_used": False, "seer_uses": 0, "power_used": False,
            "guide_used": False, "reached_end": False, "vp_sources": {},
        }
        p.update(copy.deepcopy(D.START_RESOURCES))
        p["coins"] += D.SEAT_BONUS_COINS[i]
        players.append(p)

    state = {
        "phase": "setup", "round": 0, "players": players,
        "start_player": 0, "current": 0, "turn_placed": False,
        "spaces": {s: [] for s in D.SPACES},
        "city_spaces": {c: None for c, info in D.CITIES.items() if info["action"]},
        "contract_deck": deck, "contract_market": [], "contract_discard": [],
        "guide_pool": D.GUIDE_DICE, "temple_claim": None, "end_order": [],
        "log": [], "final": None, "next_die_id": 1, "next_set_id": 1,
    }
    _refill_market(state)
    _log(state, "The caravan masters gather in Constantinople. Choose your characters.")
    return state


def _refill_market(state):
    m = state["contract_market"]
    while len(m) < D.CONTRACT_SLOTS:
        if not state["contract_deck"]:
            if not state["contract_discard"]:
                break
            state["contract_deck"] = state["contract_discard"]
            state["contract_discard"] = []
            random.shuffle(state["contract_deck"])
        m.append(state["contract_deck"].pop())


def _new_die(state, white=False):
    d = {"id": state["next_die_id"], "value": random.randint(1, 6), "placed": False, "white": white}
    state["next_die_id"] += 1
    return d


def _start_round(state):
    state["round"] += 1
    state["phase"] = "play"
    state["spaces"] = {s: [] for s in D.SPACES}
    state["city_spaces"] = {c: None for c in state["city_spaces"]}
    state["guide_pool"] = D.GUIDE_DICE
    state["temple_claim"] = None
    _log(state, f"— Round {state['round']} of {D.NUM_ROUNDS} begins —")
    for p in state["players"]:
        p["passed"] = False
        p["seer_used"] = False
        p["seer_uses"] = 0
        p["power_used"] = False
        p["guide_used"] = False
        income = {}
        for c in p["posts"]:
            income = _add(income, D.CITIES[c]["income"])
        if p["character"] == "breeder":
            income = _add(income, D.BREEDER_INCOME)
        if p["character"] == "seer":
            income = _add(income, D.SEER_INCOME)
        if p["character"] == "heiress":
            income = _add(income, D.HEIRESS_INCOME)
        if p["character"] == "quartermaster":
            income = _add(income, {"coins": len(p["posts"]) // D.QUARTERMASTER_POSTS_PER_COIN})
        n = D.HEIRESS_DICE if p["character"] == "heiress" else D.DICE_PER_PLAYER
        p["dice"] = [_new_die(state) for _ in range(n)]
        total = sum(d["value"] for d in p["dice"])
        comp = min(D.LOW_ROLL_MAX, max(0, D.LOW_ROLL_PER_DIE * n - total))
        if comp:
            income = _add(income, {"coins": comp})
        _gain(p, income)
        roll = " ".join(str(d["value"]) for d in p["dice"])
        msg = f"{p['name']} rolls [{roll}]"
        if income:
            msg += f" and collects {_fmt(income)}"
            if comp:
                msg += f" (incl. {comp} coins for a poor roll)"
        _log(state, msg + ".", p["seat"])
    state["current"] = state["start_player"]
    state["turn_placed"] = False


# --------------------------------------------------------------------------- travel

def travel_options(state, seat, steps, reserve_coins=0):
    """All reachable destinations within `steps`, with the cheapest affordable paths.

    Returns list of {dest, path, camels, coins}. Paths are simple (no repeats).
    Several Pareto-optimal paths to one destination are all returned.
    `reserve_coins` is held back for e.g. the crowd toll on the Road.
    """
    p = _player(state, seat)
    start = p["location"]
    budget = p["coins"] - reserve_coins
    results = {}
    q = deque([(start, [start], 0, 0)])
    while q:
        city, path, camels, coins = q.popleft()
        if len(path) - 1 >= steps:
            continue
        for nxt, kind in ADJ[city]:
            if nxt in path:
                continue
            c_cam, c_coin = _route_cost(p, kind)
            tc, tco = camels + c_cam, coins + c_coin
            if tc > p["camels"] or tco > budget:
                continue
            npath = path + [nxt]
            opts = results.setdefault(nxt, [])
            if not any(o["camels"] <= tc and o["coins"] <= tco for o in opts):
                opts[:] = [o for o in opts if not (tc <= o["camels"] and tco <= o["coins"])]
                opts.append({"dest": nxt, "path": npath, "camels": tc, "coins": tco})
            q.append((nxt, npath, tc, tco))
    out = []
    for opts in results.values():
        out.extend(opts)
    out.sort(key=lambda o: (o["dest"], o["camels"] + o["coins"]))
    return out


def _plan_travel(p, steps, path):
    """Validate a journey without mutating anything. Returns its (camels, coins) cost."""
    if not isinstance(path, list) or len(path) < 2 or not all(isinstance(c, str) for c in path):
        raise GameError("Choose a destination for your caravan.")
    if any(c not in D.CITIES for c in path):
        raise GameError("Unknown city on that path.")
    if path[0] != p["location"]:
        raise GameError("A journey must start where your caravan is.")
    if len(path) - 1 > steps:
        raise GameError(f"This placement only allows {steps} step(s).")
    if len(set(path)) != len(path):
        raise GameError("A journey may not revisit a city.")
    camels = coins = 0
    for a, b in zip(path, path[1:]):
        kind = next((k for n, k in ADJ[a] if n == b), None)
        if kind is None:
            raise GameError(f"There is no route from {D.CITIES[a]['name']} to {D.CITIES[b]['name']}.")
        c1, c2 = _route_cost(p, kind)
        camels += c1
        coins += c2
    return camels, coins


def _can_found(p, city):
    return city not in D.NO_POST_CITIES and city not in p["posts"]


def _survey_choice(p, path, post_at):
    """Cartographer: which intermediate city (if any) gets a bonus post. Pure."""
    if post_at is not None and post_at is not False and not isinstance(post_at, str):
        raise GameError("post_at must be a city name.")
    if p["character"] != "cartographer":
        if isinstance(post_at, str):
            raise GameError("Only the Cartographer founds posts along the way.")
        return None
    if post_at is False:
        return None
    dest = path[-1]
    room = D.TRADING_POSTS - len(p["posts"]) - (1 if _can_found(p, dest) else 0)
    eligible = [c for c in path[1:-1] if _can_found(p, c)]
    if isinstance(post_at, str):
        if p.get("power_used"):
            raise GameError("You have already surveyed a city this round.")
        if post_at not in eligible:
            raise GameError("You can only survey a city your journey passes through and where you have no post.")
        if room <= 0:
            raise GameError("You have no trading posts left.")
        return post_at
    if p.get("power_used") or room <= 0 or not eligible:
        return None
    return max(eligible, key=lambda c: D.CITIES[c]["post_vp"])  # default: the richest city


def _score(p, source, vp):
    """Add in-game VP and remember where it came from (player.vp_sources)."""
    if vp:
        p["vp"] += vp
        src = dict(p.get("vp_sources") or {})  # copy: callers may share nested dicts (bot sims)
        src[source] = src.get(source, 0) + vp
        p["vp_sources"] = src


def _found_post(p, city, vp=None):
    """Found a post; it scores the printed VP unless `vp` overrides it."""
    p["posts"].append(city)
    vp = D.CITIES[city]["post_vp"] if vp is None else vp
    _score(p, "posts", vp)
    return vp


def _apply_travel(state, p, path, survey):
    dest = path[-1]
    p["location"] = dest
    parts = []
    if survey:
        vp = _found_post(p, survey, D.CARTOGRAPHER_SURVEY_VP)
        p["power_used"] = True
        parts.append(f"surveys {D.CITIES[survey]['name']} on the way (+{vp} VP)")
    if _can_found(p, dest):
        if len(p["posts"]) < D.TRADING_POSTS:
            parts.append(f"founds a trading post (+{_found_post(p, dest)} VP)")
        else:
            parts.append("has no trading posts left")
    if dest == D.END_CITY and not p["reached_end"]:
        p["reached_end"] = True
        order = len(state["end_order"])
        state["end_order"].append(p["seat"])
        vp = D.END_CITY_ORDER_VP[order] if order < len(D.END_CITY_ORDER_VP) else 0
        if p["character"] == "pathfinder":
            vp += D.PATHFINDER_CHANGAN_VP
        _score(p, "changan", vp)
        parts.append(f"arrives in Chang'an #{order + 1} for {vp} VP")
    return f"{p['name']} travels to {D.CITIES[dest]['name']}" + ("".join(f", {x}" for x in parts))


# --------------------------------------------------------------------------- placement

def _select_dice(p, action, max_dice):
    """Parse `die` / `dice` from the action. Returns (dice, value). Pure."""
    has_die = action.get("die") is not None
    has_dice = action.get("dice") is not None
    if has_die and has_dice:
        raise GameError("Send either 'die' or 'dice', not both.")
    if has_dice:
        ids = action["dice"]
        if not isinstance(ids, list) or not ids:
            raise GameError("'dice' must be a non-empty list of die ids.")
    elif has_die:
        ids = [action["die"]]
    else:
        raise GameError("Choose a die to place.")
    dice = [_die(p, i) for i in ids]
    if len(set(ids)) != len(ids):
        raise GameError("You cannot use the same die twice.")
    if any(d["placed"] for d in dice):
        raise GameError("That die has already been used.")
    if len(dice) > max_dice:
        raise GameError(f"That space takes at most {max_dice} {'die' if max_dice == 1 else 'dice'}.")
    own = [d for d in dice if not d["white"]]
    values = {d["value"] for d in (own or dice)}
    if len(values) != 1:
        raise GameError("All dice in a set must show the same value (a guide die matches any value).")
    if len(own) > _placements_left(p):
        raise GameError(f"The Silk Heiress may place only {D.HEIRESS_MAX_PLACED} of her dice each round.")
    return dice, values.pop()


def _mark_placed(state, dice, target, seat, value):
    set_id = None
    if len(dice) > 1:
        set_id = state.get("next_set_id", 1)
        state["next_set_id"] = set_id + 1
    for d in dice:
        d["placed"] = True
        entry = {"seat": seat, "value": value, "white": d["white"]}
        if set_id is not None:
            entry["set"] = set_id
            entry["set_size"] = len(dice)
        target.append(entry)


def _place_city(state, p, action):
    seat = p["seat"]
    city = action.get("city")
    if not isinstance(city, str) or city not in state["city_spaces"]:
        raise GameError("That city offers no action.")
    if city not in p["posts"]:
        raise GameError("You need a trading post in that city to use its action.")
    if state["city_spaces"][city] is not None:
        raise GameError("That city's action has already been taken this round.")
    dice, v = _select_dice(p, action, 1)
    act = D.CITIES[city]["action"]
    max_times = _city_uses(p, v)
    times = action.get("times")
    if times is None:
        times = max_times
        while times > 1 and not _can_pay(p, _scale(act["pay"], times)):
            times -= 1  # default: as many times as you can afford
    if not _is_int(times) or not 1 <= times <= max_times:
        raise GameError(f"This die lets you use the action 1–{max_times} times.")
    pay, gain = _scale(act["pay"], times), _scale(act["gain"], times)
    _check(p, pay, "that exchange")
    # --- mutate
    _pay(p, pay)
    _gain(p, {k: v for k, v in gain.items() if k != "vp"})
    _score(p, "cities", gain.get("vp", 0))
    d = dice[0]
    d["placed"] = True
    state["city_spaces"][city] = {"seat": seat, "value": v, "white": d["white"]}
    return f"{p['name']} trades in {D.CITIES[city]['name']} ×{times}: pays {_fmt(pay)}, gains {_fmt(gain)}."


def _place(state, p, action):
    space = action.get("space")
    if space == "city":
        return _place_city(state, p, action)
    if not isinstance(space, str) or space not in D.SPACES:
        raise GameError("Unknown action space.")
    spec = D.SPACES[space]
    seat = p["seat"]
    dice, v = _select_dice(p, action, spec.get("max_dice", 1))
    n = len(dice)
    toll = _toll(state, seat, space, v)
    cost = _add(_scale(spec["cost"], n), {"coins": toll})

    # ---- validate everything first; no mutation in this block
    if space == "caravanserai":
        slot = action.get("slot")
        if not _is_int(slot) or not 0 <= slot < len(state["contract_market"]):
            raise GameError("Choose a contract to take.")
        reach = _contract_reach(p, v)
        if slot + 1 > reach:
            raise GameError(f"A {v} can only take contracts from slots 1–{reach}.")
        discard = action.get("discard")
        full = len(p["contracts"]) >= _max_contracts(p)
        if full and (not _is_int(discard) or not 0 <= discard < len(p["contracts"])):
            raise GameError("Your hands are full — choose an open contract to abandon.")
        _check(p, cost, f"the {spec['name']}")
    elif space == "road":
        steps = _steps(spec["table"], v, n)
        path = action.get("path")
        camels, coins = _plan_travel(p, steps, path)
        survey = _survey_choice(p, path, action.get("post_at"))
        cost = _add(cost, {"camels": camels, "coins": coins})
        _check(p, cost, "the journey")
        if survey:
            with_survey = _add(cost, D.CARTOGRAPHER_SURVEY_COST)
            if _can_pay(p, with_survey):
                cost = with_survey
            elif isinstance(action.get("post_at"), str):
                raise GameError(f"Surveying costs {_fmt(D.CARTOGRAPHER_SURVEY_COST)} more than you have.")
            else:
                survey = None  # automatic survey skipped when unaffordable
    else:
        _check(p, cost, f"the {spec['name']}")

    # ---- mutate
    _pay(p, cost)
    if space == "caravanserai":
        if full:
            state["contract_discard"].append(p["contracts"].pop(discard))
        p["contracts"].append(state["contract_market"].pop(slot))
        _refill_market(state)
        msg = f"{p['name']} signs a contract at the Caravanserai"
    elif space == "road":
        msg = _apply_travel(state, p, path, survey)
        msg += f" (paid {_fmt({'camels': camels, 'coins': coins})}"
        msg += f", with a set of {n})" if n > 1 else ")"
    else:
        amount = _steps(spec["table"], v, n)
        _gain(p, {spec["gain"]: amount})
        what = f"a set of {n}" if n > 1 else "a die"
        msg = f"{p['name']} places {what} on the {spec['name']} and gains {_fmt({spec['gain']: amount})}"
        if space == "temple" and state["temple_claim"] is None:
            state["temple_claim"] = seat
            msg += " and will lead next round"
    if toll:
        msg += f" (paid a {toll}-coin crowd toll)"
        for other in ([] if not D.MONEYLENDER_KICKBACK else state["players"]):
            if (other["seat"] != seat and other["character"] == "moneylender"
                    and any(e["seat"] == other["seat"] for e in state["spaces"][space])):
                other["coins"] += D.MONEYLENDER_KICKBACK
                msg += f"; {other['name']} collects {D.MONEYLENDER_KICKBACK} coin"
    _mark_placed(state, dice, state["spaces"][space], seat, v)
    return msg + "."


def _contract_payment(p, req):
    """What delivering `req` actually costs `p`. The Camel Breeder covers each missing
    good with BREEDER_GOOD_CAMELS camels (applied automatically, only when short)."""
    if p["character"] != "breeder":
        return req
    pay = dict(req)
    missing = 0
    for good in D.GOODS:
        short = req.get(good, 0) - p.get(good, 0)
        if short > 0:
            pay[good] -= short
            missing += short
    if not missing:
        return req
    return _add({k: v for k, v in pay.items() if v}, {"camels": D.BREEDER_GOOD_CAMELS * missing})


def _fulfill(state, p, idx):
    if not _is_int(idx) or not 0 <= idx < len(p["contracts"]):
        raise GameError("No such contract.")
    cid = p["contracts"][idx]
    req, vp, bonus = D.CONTRACTS[cid]
    req = _contract_payment(p, req)
    _pay(p, req, "that contract")
    if p["character"] == "guildmaster":
        vp += D.GUILDMASTER_BONUS_VP
        if D.GUILDMASTER_BONUS_COINS:
            bonus = _add(bonus, {"coins": D.GUILDMASTER_BONUS_COINS})
    _score(p, "contracts", vp)
    _gain(p, bonus)
    p["fulfilled"] += 1
    p["contracts"].pop(idx)
    state["contract_discard"].append(cid)
    extra = f" and {_fmt(bonus)}" if bonus else ""
    return f"{p['name']} delivers {_fmt(req)} for {vp} VP{extra}."


# --------------------------------------------------------------------------- round flow

def _advance_turn(state):
    n = len(state["players"])
    for step in range(1, n + 1):
        seat = (state["current"] + step) % n
        p = state["players"][seat]
        if p["passed"]:
            continue
        if not _can_place(p):
            p["passed"] = True
            continue
        state["current"] = seat
        state["turn_placed"] = False
        return
    _end_round(state)


def _end_round(state):
    if state["temple_claim"] is not None:
        state["start_player"] = state["temple_claim"]
    else:
        state["start_player"] = (state["start_player"] + 1) % len(state["players"])
    # the oldest contracts leave the market, the rest slide down
    for _ in range(min(D.CONTRACT_CHURN, len(state["contract_market"]))):
        state["contract_discard"].append(state["contract_market"].pop(0))
    _refill_market(state)
    for p in state["players"]:
        p["dice"] = []
    if state["round"] >= D.NUM_ROUNDS:
        _final_scoring(state)
    else:
        _start_round(state)


def _rank_awards(values, awards):
    """values: {seat: n}. Ties share the award for their rank; next rank is skipped."""
    out = {s: 0 for s in values}
    ordered = sorted({v for v in values.values() if v > 0}, reverse=True)
    rank = 0
    for v in ordered:
        tied = [s for s, x in values.items() if x == v]
        if rank < len(awards):
            for s in tied:
                out[s] = awards[rank]
        rank += len(tied)
    return out


def _final_scoring(state):
    players = state["players"]
    # a runner-up award only makes sense with 3+ players
    post_awards = D.POST_MAJORITY_VP[:max(1, len(players) - 1)]
    posts = _rank_awards({p["seat"]: len(p["posts"]) for p in players}, post_awards)
    contracts = _rank_awards({p["seat"]: p["fulfilled"] for p in players}, [D.CONTRACT_MAJORITY_VP])
    rows = []
    for p in players:
        comm = 0
        for ci in p["commissions"]:
            a, b = D.COMMISSIONS[ci]
            have = (a in p["posts"]) + (b in p["posts"])
            comm += D.COMMISSION_BOTH_VP if have == 2 else D.COMMISSION_ONE_VP if have == 1 else 0
        goods = p["spice"] + p["silk"] + p["jade"]
        breakdown = {
            "during_game": p["vp"], "commissions": comm, "post_majority": posts[p["seat"]],
            "contract_majority": contracts[p["seat"]], "coins": p["coins"] // D.COINS_PER_VP,
            "goods": goods // D.GOODS_PER_VP,
        }
        total = sum(breakdown.values())
        p["vp"] = total
        rows.append({"seat": p["seat"], "name": p["name"], "total": total, "breakdown": breakdown,
                     "during_game_sources": dict(p.get("vp_sources", {})),
                     "tiebreak": p["coins"], "tiebreak2": goods})
    key = lambda r: (r["total"], r["tiebreak"], r["tiebreak2"])  # noqa: E731
    rows.sort(key=key, reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = rows[i - 1]["rank"] if i and key(rows[i - 1]) == key(r) else i + 1
    state["phase"] = "finished"
    state["final"] = rows
    winners = [r["name"] for r in rows if r["rank"] == 1]
    _log(state, f"The journey ends. {' and '.join(winners)} {'is' if len(winners) == 1 else 'are'} "
                f"the greatest merchant{'s' if len(winners) > 1 else ''} of the Silk Road!")


# --------------------------------------------------------------------------- dispatcher

def _rest(state, p):
    own_unused = [d for d in p["dice"] if not d["placed"] and not d["white"]]
    white_unused = [d for d in p["dice"] if not d["placed"] and d["white"]]
    usable = min(len(own_unused), _placements_left(p)) + len(white_unused)
    coins = usable * D.REST_COINS_PER_DIE
    p["coins"] += coins
    for d in own_unused + white_unused:
        d["placed"] = True
        d["rested"] = True
    p["passed"] = True
    return f"{p['name']} rests for the round and takes {coins} coin(s)."


def apply_action(state, seat, action):
    """Validate and apply. Mutates and returns state. On GameError the state is untouched."""
    if not isinstance(action, dict):
        raise GameError("Malformed action.")
    t = action.get("type")
    if state["phase"] == "finished":
        raise GameError("The game is over.")
    if not _is_int(seat) or not 0 <= seat < len(state["players"]):
        raise GameError("You are not seated in this game.")
    p = _player(state, seat)

    if state["phase"] == "setup":
        if t != "choose_character":
            raise GameError("Choose a character first.")
        if p["character"]:
            raise GameError("You have already chosen.")
        ch = action.get("character")
        if not isinstance(ch, str) or ch not in p["character_choices"]:
            raise GameError("That character was not offered to you.")
        p["character"] = ch
        _log(state, f"{p['name']} will travel as {D.CHARACTERS[ch]['name']}.", seat)
        if all(x["character"] for x in state["players"]):
            _start_round(state)
        return state

    if seat != state["current"]:
        raise GameError("It is not your turn.")

    if t == "place":
        if state["turn_placed"]:
            raise GameError("You have already taken your action this turn — end your turn.")
        msg = _place(state, p, action)
        state["turn_placed"] = True
        _log(state, msg, seat)
    elif t == "fulfill":
        _log(state, _fulfill(state, p, action.get("index")), seat)
    elif t == "reroll":
        die = _die(p, action.get("die"))
        if die["placed"]:
            raise GameError("That die has been used.")
        cost = _omen_payment(p, D.REROLL_COST, action.get("pay"))
        _pay(p, cost, "a reroll")
        old = die["value"]
        die["value"] = random.randint(1, 6)
        _log(state, f"{p['name']} consults the omens ({_fmt(cost)}) and rerolls a {old} into a {die['value']}.", seat)
    elif t == "nudge":
        die = _die(p, action.get("die"))
        delta = action.get("delta")
        if die["placed"] or not _is_int(delta) or delta not in (1, -1):
            raise GameError("Invalid adjustment.")
        nv = die["value"] + delta
        if not 1 <= nv <= 6:
            raise GameError("Dice range from 1 to 6.")
        cost = _omen_payment(p, _nudge_cost(p), action.get("pay"))
        _pay(p, cost, "an adjustment")
        die["value"] = nv
        _log(state, f"{p['name']} bends fate ({_fmt(cost)}), turning a {nv - delta} into a {nv}.", seat)
    elif t == "seer":
        if p["character"] != "seer" or p["seer_used"]:
            raise GameError("You cannot use the Seer's gift now.")
        die = _die(p, action.get("die"))
        val = action.get("value")
        if die["placed"] or not _is_int(val) or not 1 <= val <= 6:
            raise GameError("Invalid choice.")
        die["value"] = val
        p["seer_uses"] = p.get("seer_uses", 0) + 1
        p["seer_used"] = p["seer_uses"] >= D.SEER_USES
        p["power_used"] = True
        _log(state, f"{p['name']} foresees a {val}.", seat)
    elif t == "hire_guide":
        if p["guide_used"]:
            raise GameError("You may hire only one guide per round.")
        if state["guide_pool"] <= 0:
            raise GameError("No guides are left this round.")
        _pay(p, {"coins": D.GUIDE_COST}, "a guide")
        d = _new_die(state, white=True)
        p["dice"].append(d)
        p["guide_used"] = True
        state["guide_pool"] -= 1
        _log(state, f"{p['name']} hires a guide, who rolls a {d['value']}.", seat)
    elif t in ("pass", "rest"):
        _log(state, _rest(state, p), seat)
        _advance_turn(state)
    elif t == "end_turn":
        if not state["turn_placed"]:
            raise GameError("Place a die (or rest) before ending your turn.")
        _advance_turn(state)
    else:
        raise GameError("Unknown action.")
    return state


# --------------------------------------------------------------------------- views

def public_view(state, seat):
    """State as seen by `seat` (None for spectators): hides others' commissions and the deck."""
    v = copy.deepcopy(state)
    v.pop("contract_deck", None)
    v["deck_size"] = len(state["contract_deck"])
    v.pop("contract_discard", None)
    for p, raw in zip(v["players"], state["players"]):
        if p["seat"] != seat and state["phase"] != "finished":
            p["commissions"] = [None] * len(p["commissions"])
            if state["phase"] == "setup":
                p["character_choices"] = []
        if state["phase"] == "play":
            p["placements_left"] = _placements_left(raw)
    if seat is not None and state["phase"] == "play" and state["current"] == seat:
        me = state["players"][seat]
        table = D.SPACES["road"]["table"]
        road_max = D.SPACES["road"].get("max_dice", 1)
        v["tolls"] = {s: [_toll(state, seat, s, val) for val in range(7)] for s in D.SPACES}
        v["occupy_cost"] = {s: int(_crowded(state, seat, s)) for s in D.SPACES}
        v["travel"] = {
            str(val): travel_options(state, seat, _steps(table, val, 1), v["tolls"]["road"][val])
            for val in range(1, 7)
        }
        if road_max >= 2:
            v["travel_pair"] = {
                str(val): travel_options(state, seat, _steps(table, val, 2), v["tolls"]["road"][val])
                for val in range(1, 7)
            }
        v["costs"] = {"reroll": D.REROLL_COST, "nudge": _nudge_cost(me)}
    return v


def static_data():
    return {
        "cities": D.CITIES, "routes": D.ROUTES, "route_types": D.ROUTE_TYPES,
        "spaces": D.SPACES, "characters": D.CHARACTERS,
        "contracts": [{"req": r, "vp": vp, "bonus": b} for r, vp, b in D.CONTRACTS],
        "commissions": D.COMMISSIONS, "city_action_repeats": D.CITY_ACTION_REPEATS,
        "num_rounds": D.NUM_ROUNDS, "end_city_order_vp": D.END_CITY_ORDER_VP,
        "no_post_cities": list(D.NO_POST_CITIES),
        "rules": {
            "guide_cost": D.GUIDE_COST, "guide_dice": D.GUIDE_DICE,
            "reroll_cost": D.REROLL_COST, "nudge_cost": D.NUDGE_COST,
            "commission_both": D.COMMISSION_BOTH_VP, "commission_one": D.COMMISSION_ONE_VP,
            "post_majority": D.POST_MAJORITY_VP, "contract_majority": D.CONTRACT_MAJORITY_VP,
            "coins_per_vp": D.COINS_PER_VP, "goods_per_vp": D.GOODS_PER_VP,
            "max_occupy": D.MAX_OCCUPY_COST, "trading_posts": D.TRADING_POSTS,
            "toll_per_pip": D.TOLL_PER_PIP, "set_bonus": D.SET_BONUS,
            "low_roll_per_die": D.LOW_ROLL_PER_DIE, "low_roll_max": D.LOW_ROLL_MAX,
            "rest_coins_per_die": D.REST_COINS_PER_DIE, "contract_churn": D.CONTRACT_CHURN,
            "max_open_contracts": D.MAX_OPEN_CONTRACTS, "dice_per_player": D.DICE_PER_PLAYER,
            "seat_bonus_coins": D.SEAT_BONUS_COINS,
        },
        "powers": {
            "breeder_income": D.BREEDER_INCOME, "breeder_good_camels": D.BREEDER_GOOD_CAMELS, "seer_income": D.SEER_INCOME, "seer_uses": D.SEER_USES, "seer_nudge_cost": D.SEER_NUDGE_COST,
            "cartographer_survey_vp": D.CARTOGRAPHER_SURVEY_VP, "cartographer_survey_cost": D.CARTOGRAPHER_SURVEY_COST,
            "heiress_dice": D.HEIRESS_DICE, "heiress_income": D.HEIRESS_INCOME, "heiress_max_placed": D.HEIRESS_MAX_PLACED,
            "guildmaster_contracts": D.GUILDMASTER_CONTRACTS, "guildmaster_bonus_vp": D.GUILDMASTER_BONUS_VP, "guildmaster_bonus_coins": D.GUILDMASTER_BONUS_COINS, "guildmaster_reach": D.GUILDMASTER_REACH,
            "pathfinder_routes": list(D.PATHFINDER_ROUTES), "pathfinder_discount": D.PATHFINDER_DISCOUNT, "pathfinder_changan_vp": D.PATHFINDER_CHANGAN_VP,
            "quartermaster_extra_uses": D.QUARTERMASTER_EXTRA_USES,
            "quartermaster_posts_per_coin": D.QUARTERMASTER_POSTS_PER_COIN,
            "moneylender_kickback": D.MONEYLENDER_KICKBACK, "moneylender_toll_share": D.MONEYLENDER_TOLL_SHARE,
        },
    }
