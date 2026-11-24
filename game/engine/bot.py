"""AI opponent for Caravan Road.

Pure Python, no Django. Public API:

    choose_character(state, seat, rng=None, level="normal") -> action dict (and applies it)
    take_turn(state, seat, rng=None, level="normal")         -> list of actions applied
    plan_turn(view, seat, rng=None, level="normal")          -> Plan (no side effects)
    next_action(view, seat, rng=None, level="normal")        -> the next action the bot would send

How it thinks
-------------
The bot never reads the raw state. Every decision starts from `engine.public_view(state, seat)`
and is turned into a private *simulation state*: the hidden contract deck is replaced by
dummy cards and rival commissions (already hidden by the view) become empty lists. Candidate
moves are simulated on cheap copies of that state through `engine.apply_action`, so only
legal moves are ever considered, and the resulting positions are scored by a hand-tuned
value function (`_value`) that estimates the seat's final VP:

* VP already scored, plus coins / camels / goods / omens at values that decay towards their
  end-game conversion rate as the game runs out (goods 1/3 VP, coins 1/10 VP, camels 0).
* Open contracts: goods in hand are allocated to them; the contract is worth
  p(complete) x (VP + bonus), where p falls with the weighted goods still missing and the
  placements left in the game.
* Trading posts: income and city-action value for the remaining rounds, commissions
  (6 / 2 VP), a soft (sigmoid) estimate of the post- and contract-majority awards.
* Travel potential: from the caravan's location, the best one- and two-leg journeys to
  unclaimed cities (post VP, income, commission pairs, Chang'an arrival order), discounted
  by distance and by the camels/coins still missing to get there.
* Lead next round (Shrine), unused once-per-round powers.
* Dice still in hand: each is worth a fraction of the best single placement a die of that
  value could make right now (but at least the coin from resting), so sets, nudges, rest and
  "which die to spend" decisions all fall out of one comparison.

Free actions are planned together with the placement: Seer foresight, ±1 nudges, hiring a
guide (wild in sets), and rerolls (scored by the expectation over all six faces).

Levels: "easy" (no reroll/guide planning, noisy choice), "normal", "hard" (two-placement
lookahead on the best candidates, rerolls on every die, Cartographer survey routing).
"""
import math
import random

from . import data as D
from .engine import (
    ADJ, GameError, _char_toll, _city_uses, _contract_payment, _contract_reach, _max_contracts, _nudge_cost, _placements_left, _steps,
    apply_action, public_view, travel_options,
)

LEVELS = ("easy", "normal", "hard")
DEFAULT_LEVEL = "normal"

BOT_NAMES = [
    "Zarina", "Batu", "Farrukh", "Mei Lin", "Rustam", "Anahita", "Temur", "Shirin",
    "Darius", "Yesui", "Kasim", "Roxana", "Arslan", "Nilufar", "Bahram", "Soraya",
]

GOODS = ("spice", "silk", "jade")
_VIEW_ONLY = ("tolls", "occupy_cost", "travel", "travel_pair", "costs", "deck_size")
_STALLS = ("bazaar_spice", "bazaar_silk", "bazaar_jade", "camels", "treasury", "temple")

# Static character preference (from bot-vs-bot benchmarks, higher = stronger for the bot).
CHARACTER_PREF = {   # balance pass: average of normal & hard wins/fair, scaled
    "cartographer": 1.0, "seer": 1.0, "quartermaster": 0.95, "pathfinder": 0.9,
    "moneylender": 0.88, "breeder": 0.88, "heiress": 0.82, "guildmaster": 0.8,
}

# ----------------------------------------------------------------------------- tunables
AVG_CITY_USES = sum(D.CITY_ACTION_REPEATS[1:]) / 6   # uses per city action for an average die
W = {
    # resource values early (f=1) -> end of game (f=0)
    "coin_early": 0.32, "coin_end": 1 / D.COINS_PER_VP,
    "good_early": {"spice": 0.75, "silk": 1.05, "jade": 1.8},
    "good_end": 1 / D.GOODS_PER_VP,
    "camel_base": 0.5,
    "omen_early": 0.5,
    "short_camel": 0.5, "short_coin": 0.15,
    "camel_trip": 4.0, "camel_trip_size": 3.0,   # an extra placement buys ~3 camels
    "coin_trip": 2.5, "coin_trip_size": 5.0,
    "edge_disc": 0.92,
    "tp_w1": 0.9, "tp_w2": 0.32,
    "lead": 1.1,
    "die_frac": 0.7,
    "seer_power": 0.7,
    "miss_w": {"spice": 1.0, "silk": 1.25, "jade": 2.2, "camels": 0.6, "coins": 0.3, "omens": 1.2},
    "goods_cap_units": {"spice": 3, "silk": 3, "jade": 2},
    "goods_cap": 0.5,          # contract goods obtainable per remaining placement
    "contract_max_p": 0.9,
    "action_avail": 0.55,      # chance a city action really gets used in a given round
    "maj_k0": 0.7, "maj_k1": 2.0,
}


def _sig(x):
    if x > 30:
        return 1.0
    if x < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


# ----------------------------------------------------------------------------- distances

def _all_pairs(pathfinder):
    """Cheapest (camels + 0.5 coins) path between every pair of cities: (camels, coins, edges)."""
    out = {}
    for src in D.CITIES:
        best = {src: (0.0, 0, 0, 0)}
        frontier = [src]
        # Bellman-Ford style relaxation; the map is tiny.
        changed = True
        while changed:
            changed = False
            for a in list(best):
                w, cam, coi, e = best[a]
                for b, kind in ADJ[a]:
                    r = D.ROUTE_TYPES[kind]
                    c_cam = r["camels"]
                    if pathfinder and kind in D.PATHFINDER_ROUTES:
                        c_cam = max(0, c_cam - D.PATHFINDER_DISCOUNT)
                    nc, nco, ne = cam + c_cam, coi + r["coins"], e + 1
                    nw = nc + 0.5 * nco + 0.05 * ne
                    if b not in best or nw < best[b][0] - 1e-9:
                        best[b] = (nw, nc, nco, ne)
                        changed = True
        del frontier
        out[src] = {b: v[1:] for b, v in best.items()}
    return out


DIST = {False: _all_pairs(False), True: _all_pairs(True)}
CITY_LIST = [c for c in D.CITIES]


# ----------------------------------------------------------------------------- sim state

def _sim_from_view(view, seat):
    """A private, playable copy of what `seat` can see. Hidden info is replaced by dummies."""
    s = {k: v for k, v in view.items() if k not in _VIEW_ONLY}
    s["contract_deck"] = [0] * 4      # dummy cards: refills during lookahead are meaningless
    s["contract_discard"] = []
    s["log"] = []
    players = []
    for p in view["players"]:
        q = dict(p)
        q.pop("placements_left", None)
        if q["seat"] != seat:
            q["commissions"] = []        # unknown to us
        players.append(q)
    s["players"] = players
    return s


def _clone(s):
    c = dict(s)
    ps = []
    for p in s["players"]:
        q = dict(p)
        q["dice"] = [dict(d) for d in p["dice"]]
        q["posts"] = list(p["posts"])
        q["contracts"] = list(p["contracts"])
        ps.append(q)
    c["players"] = ps
    c["spaces"] = {k: list(v) for k, v in s["spaces"].items()}
    c["city_spaces"] = dict(s["city_spaces"])
    c["contract_market"] = list(s["contract_market"])
    c["contract_deck"] = [0] * 4
    c["contract_discard"] = []
    c["end_order"] = list(s["end_order"])
    c["log"] = []
    return c


def _try(s, seat, action):
    try:
        apply_action(s, seat, action)
        return True
    except GameError:
        return False


def _auto_fulfill(s, seat):
    """Deliver every affordable contract, most valuable first."""
    p = s["players"][seat]
    done = True
    while done:
        done = False
        order = sorted(range(len(p["contracts"])), key=lambda i: -D.CONTRACTS[p["contracts"][i]][1])
        for i in order:
            req = _contract_payment(p, D.CONTRACTS[p["contracts"][i]][0])
            if all(p.get(k, 0) >= v for k, v in req.items()):
                if _try(s, seat, {"type": "fulfill", "index": i}):
                    done = True
                    break


# ----------------------------------------------------------------------------- context

class Ctx:
    """Per-decision constants: time left, resource values, city values."""

    def __init__(self, s, seat, level):
        self.seat = seat
        self.level = level
        p = s["players"][seat]
        self.n = len(s["players"])
        self.round = max(1, s["round"])
        self.R = D.NUM_ROUNDS - self.round                       # full rounds still to come
        own_left = _placements_left(p) if not p["passed"] else 0
        white_left = sum(1 for d in p["dice"] if d["white"] and not d["placed"]) if not p["passed"] else 0
        self.T_game = own_left + white_left + D.DICE_PER_PLAYER * self.R
        self.T_after = max(0, self.T_game - 1)
        total = D.DICE_PER_PLAYER * D.NUM_ROUNDS
        f = min(1.0, self.T_game / total)
        self.f = f
        self.cv = W["coin_end"] + (W["coin_early"] - W["coin_end"]) * f
        self.gv = {g: W["good_end"] + (W["good_early"][g] - W["good_end"]) * f for g in GOODS}
        self.camv = W["camel_base"] * min(1.0, f * 2.5)
        self.ov = W["omen_early"] * min(1.0, f * 2.0) * (1.4 if p["character"] == "seer" else 1.0)
        self.pathfinder = p["character"] == "pathfinder"
        self.char = p["character"]
        self.dist = DIST[self.pathfinder]
        # Loose goods have diminishing value: a few units feed contracts, our own city
        # actions convert a limited number per round, the rest only score 1/3 VP at the end.
        conv = {}
        for c in p["posts"]:
            act = D.CITIES[c]["action"]
            if not act:
                continue
            pays = [k for k in act["pay"] if k in GOODS]
            if not pays:
                continue
            per = self.res_value(act["gain"]) / sum(act["pay"].values())
            uses = AVG_CITY_USES + (D.QUARTERMASTER_EXTRA_USES if self.char == "quartermaster" else 0)
            free_now = 1 if (own_left and s["city_spaces"].get(c) is None) else 0
            n_conv = uses * (W["action_avail"] * self.R + free_now)
            for k in pays:
                conv.setdefault(k, []).append((n_conv, per))
        end = W["good_end"]
        self.tiers = {}
        for g in GOODS:
            t = [(n, v) for n, v in conv.get(g, [])]
            t.append((W["goods_cap_units"][g], self.gv[g]))
            t.append((W["goods_cap_units"][g], (self.gv[g] + end) / 2))
            t.sort(key=lambda x: -x[1])
            self.tiers[g] = [(n, max(v, end)) for n, v in t if v > end]
        self.lead = W["lead"] * (1.0 if self.R > 0 else 0.0) * (0.6 if self.R == 1 else 1.0)
        # majority steepness rises as the game ends
        self.maj_k = W["maj_k0"] + W["maj_k1"] * (1 - f)
        self.goods_cap = W["goods_cap"] * self.T_after
        # per-city future value of owning a post there (income + action) for us
        self.post_future = {}
        for c, info in D.CITIES.items():
            inc = self.res_value(info["income"]) * self.R * 0.95
            act = 0.0
            a = info["action"]
            if a:
                uses = AVG_CITY_USES + (D.QUARTERMASTER_EXTRA_USES if self.char == "quartermaster" else 0)
                one = self.res_value(a["gain"]) - self.res_value(a["pay"])
                act = max(0.0, one) * uses * W["action_avail"] * (self.R + 0.4)
                act = min(act, 8.0)
            qm = self.cv * self.R / D.QUARTERMASTER_POSTS_PER_COIN if self.char == "quartermaster" else 0
            self.post_future[c] = inc + act + qm
        self.dval = {v: 0.35 + 0.15 * v for v in range(1, 7)}
        self.rest_coin = D.REST_COINS_PER_DIE * self.cv
        self.tp_cache = {}

    def res_value(self, res, goods_raw=False):
        v = 0.0
        for k, n in res.items():
            if k == "vp":
                v += n
            elif k == "coins":
                v += n * self.cv
            elif k == "camels":
                v += n * max(self.camv, 0.3 * self.f)
            elif k == "omens":
                v += n * self.ov
            elif k in GOODS:
                v += n * (W["good_end"] + (W["good_early"][k] - W["good_end"]) * self.f if goods_raw else self.gv[k])
        return v

    def goods_value(self, g, n):
        v = 0.0
        for cnt, val in self.tiers[g]:
            if n <= 0:
                return v
            k = min(n, cnt)
            v += k * val
            n -= k
        return v + max(0, n) * W["good_end"]

    def p_complete(self, mw):
        if mw <= 0:
            return 1.0
        return W["contract_max_p"] * max(0.0, 1.0 - mw / (self.goods_cap + 1.0))


def _majority(mine, others, awards, k):
    """Soft expected award from a ranking where ties share the higher award."""
    if not others:
        return 0.0
    a = [_sig(k * (mine - o + 0.5)) for o in others]
    p_first = 1.0
    for x in a:
        p_first *= x
    v = awards[0] * p_first * (1.0 if mine > 0 else 0.0)
    if len(awards) > 1 and mine > 0:
        p_second = 0.0
        for i in range(len(a)):
            t = 1 - a[i]
            for j in range(len(a)):
                if j != i:
                    t *= a[j]
            p_second += t
        v += awards[1] * p_second
    return v


def _post_awards(n):
    return D.POST_MAJORITY_VP[:max(1, n - 1)]


# ----------------------------------------------------------------------------- evaluation

def _value(s, seat, cx):
    """Estimated final VP of `seat` in sim state `s`, excluding dice still in hand."""
    p = s["players"][seat]
    v = float(p["vp"])
    inv = {k: p[k] for k in ("coins", "camels", "spice", "silk", "jade", "omens")}

    # open contracts
    bonus_vp = D.GUILDMASTER_BONUS_VP if p["character"] == "guildmaster" else 0
    cons = sorted(p["contracts"], key=lambda c: -D.CONTRACTS[c][1])
    for cid in cons:
        req, cvp, bonus = D.CONTRACTS[cid]
        mw = 0.0
        alloc = 0.0
        short = 0
        for k, need in req.items():
            take = min(inv.get(k, 0), need)
            inv[k] -= take
            alloc += cx.res_value({k: take})
            mw += (need - take) * W["miss_w"].get(k, 1.0)
            short += (need - take) if k in GOODS else 0
        # Camel Breeder: missing goods can be paid with camels
        if p["character"] == "breeder" and short:
            sub = min(short, inv["camels"] // D.BREEDER_GOOD_CAMELS)
            inv["camels"] -= sub * D.BREEDER_GOOD_CAMELS
            alloc += cx.res_value({"camels": sub * D.BREEDER_GOOD_CAMELS})
            mw *= (short - sub) / short
        pc = cx.p_complete(mw)
        worth = cvp + bonus_vp + cx.res_value(bonus) + 0.6
        if p["character"] == "guildmaster":
            worth += D.GUILDMASTER_BONUS_COINS * cx.cv
        v += pc * worth + (1 - pc) * alloc

    # loose resources
    v += inv["coins"] * cx.cv + inv["omens"] * cx.ov + inv["camels"] * cx.camv
    for g in GOODS:
        v += cx.goods_value(g, inv[g])

    # posts: future income and actions, commissions, majorities
    posts = p["posts"]
    for c in posts:
        v += cx.post_future[c]
    for ci in p["commissions"]:
        a, b = D.COMMISSIONS[ci]
        have = (a in posts) + (b in posts)
        v += D.COMMISSION_BOTH_VP if have == 2 else D.COMMISSION_ONE_VP if have == 1 else 0
    others = [o for o in s["players"] if o["seat"] != seat]
    v += _majority(len(posts), [len(o["posts"]) for o in others], _post_awards(cx.n), cx.maj_k)
    v += _majority(p["fulfilled"], [o["fulfilled"] for o in others], [D.CONTRACT_MAJORITY_VP], cx.maj_k)

    if s.get("temple_claim") == seat:
        v += cx.lead

    v += _travel_potential(s, p, cx, posts)
    return v


def _target_values(s, p, cx, posts):
    tv = {}
    n_posts = len(posts)
    comm = [D.COMMISSIONS[ci] for ci in p["commissions"]]
    maj_marg = 1.2 if n_posts < D.TRADING_POSTS else 0.0
    for c in CITY_LIST:
        if c == D.END_CITY:
            if not p["reached_end"]:
                k = len(s["end_order"])
                tv[c] = D.END_CITY_ORDER_VP[k] if k < len(D.END_CITY_ORDER_VP) else 0
                tv[c] += D.PATHFINDER_CHANGAN_VP if p["character"] == "pathfinder" else 0
            else:
                tv[c] = 0.0
            continue
        if c in D.NO_POST_CITIES or c in posts or n_posts >= D.TRADING_POSTS:
            tv[c] = 0.0
            continue
        val = D.CITIES[c]["post_vp"] + cx.post_future[c] * 0.8 + maj_marg
        for a, b in comm:
            if c == a or c == b:
                other = b if c == a else a
                val += 4.0 if other in posts else 2.0
        tv[c] = val
    return tv


_EDPOW = [W["edge_disc"] ** e for e in range(32)]


def _travel_potential(s, p, cx, posts):
    T = cx.T_after
    if T <= 0:
        return 0.0
    loc = p["location"]
    camels, coins = p["camels"], p["coins"]
    key = (loc, camels, coins, tuple(sorted(posts)), p["reached_end"], len(s["end_order"]))
    hit = cx.tp_cache.get(key)
    if hit is not None:
        return hit
    w1 = W["tp_w1"] * min(1.0, T / 3.0)
    w2 = W["tp_w2"] * max(0.0, min(1.0, (T - 3) / 8.0))
    tv = _target_values(s, p, cx, posts)
    targets = [c for c in CITY_LIST if tv[c] > 0 and c != loc]
    dist = cx.dist
    sc, sco = W["short_camel"], W["short_coin"]
    tripf = min(1.0, T / 4.0)
    ctrip, ctsz = W["camel_trip"] * tripf, W["camel_trip_size"]
    otrip, otsz = W["coin_trip"] * tripf, W["coin_trip_size"]
    cv, camv = cx.cv, cx.camv
    best = 0.0
    dl = dist[loc]
    for c1 in targets:
        cam1, co1, e1 = dl[c1]
        a1 = tv[c1] * _EDPOW[e1]
        if cam1 > camels:
            sh = cam1 - camels
            a1 -= sh * sc + ctrip * math.ceil(sh / ctsz) + camels * camv
        else:
            a1 -= cam1 * camv
        if co1 > coins:
            sh = co1 - coins
            a1 -= sh * sco + otrip * math.ceil(sh / otsz) + coins * cv
        else:
            a1 -= co1 * cv
        tot = w1 * a1
        if w2 > 0 and tot + w2 * 20 > best:
            cam_left = camels - cam1 if camels > cam1 else 0
            co_left = coins - co1 if coins > co1 else 0
            d2 = dist[c1]
            b2 = 0.0
            for c2 in targets:
                if c2 == c1:
                    continue
                cam2, co2, e2 = d2[c2]
                a2 = tv[c2] * _EDPOW[e2]
                if cam2 > cam_left:
                    sh = cam2 - cam_left
                    a2 -= sh * sc + ctrip * math.ceil(sh / ctsz) + cam_left * camv
                else:
                    a2 -= cam2 * camv
                if co2 > co_left:
                    sh = co2 - co_left
                    a2 -= sh * sco + otrip * math.ceil(sh / otsz)
                if a2 > b2:
                    b2 = a2
            tot += w2 * b2
        if tot > best:
            best = tot
    cx.tp_cache[key] = best
    return best


def _hand(p):
    """Usable unused dice values: own (capped by placements left) then guides."""
    if p["passed"]:
        return []
    own = sorted((d["value"] for d in p["dice"] if not d["placed"] and not d["white"]), reverse=True)
    own = own[:_placements_left(p)]
    whites = [d["value"] for d in p["dice"] if not d["placed"] and d["white"]]
    return sorted(own + whites, reverse=True)


def _dice_term(vals, p, cx, seer_spent=False):
    if not vals:
        return 0.0
    t = 0.0
    m = 1.0
    for v in vals:
        t += cx.dval[v] * m
        m *= 0.92
    if p["character"] == "seer" and not p["seer_used"] and not seer_spent:
        t += W["seer_power"] * cx.f
    return t


# ----------------------------------------------------------------------------- candidates

class Cand:
    __slots__ = ("score", "vnd", "preps", "action", "used", "hand", "rest_after", "kind")

    def __init__(self, vnd, preps, action, used, hand, kind=""):
        self.vnd = vnd
        self.preps = preps
        self.action = action
        self.used = used
        self.hand = hand
        self.kind = kind
        self.score = 0.0
        self.rest_after = False

    def __repr__(self):
        return f"<Cand {self.score:.2f} {self.preps} {self.action} rest={self.rest_after}>"


def _paths(s, seat, steps, reserve, explore_survey):
    """Journeys to consider: (path, post_at) pairs. post_at None = engine default."""
    opts = travel_options(s, seat, steps, reserve)
    out = [(o["path"], None) for o in opts]
    p = s["players"][seat]
    if not explore_survey or p["character"] != "cartographer":
        return out
    if p.get("power_used") or len(p["posts"]) >= D.TRADING_POSTS - 1:
        return out
    # Cartographer: also explore paths through good cities to survey; keep cheapest per (dest, survey)
    best = {}
    budget_cam, budget_co = p["camels"], p["coins"] - reserve
    stack = [(p["location"], [p["location"]], 0, 0)]
    while stack:
        city, path, cam, co = stack.pop()
        if len(path) > 1:
            dest = path[-1]
            for mid in path[1:-1]:
                if mid in D.NO_POST_CITIES or mid in p["posts"]:
                    continue
                key = (dest, mid)
                if key not in best or cam + 0.5 * co < best[key][1]:
                    best[key] = (path, cam + 0.5 * co)
        if len(path) - 1 >= steps:
            continue
        for nxt, kind in ADJ[city]:
            if nxt in path:
                continue
            c_cam = D.ROUTE_TYPES[kind]["camels"]
            if p["character"] == "pathfinder" and kind in D.PATHFINDER_ROUTES:
                c_cam = max(0, c_cam - D.PATHFINDER_DISCOUNT)
            ncam, nco = cam + c_cam, co + D.ROUTE_TYPES[kind]["coins"]
            if ncam > budget_cam or nco > budget_co:
                continue
            stack.append((nxt, path + [nxt], ncam, nco))
    res = [(path, False) for path, _ in out]
    for (dest, mid), (path, _) in best.items():
        res.append((path, mid))
    return res


def _placements_for(s, seat, ids, value, cx, cartographer_full):
    """All placement actions for dice `ids` showing `value` (n = len(ids))."""
    p = s["players"][seat]
    n = len(ids)
    sel = {"die": ids[0]} if n == 1 else {"dice": list(ids)}
    acts = []
    for sp in _STALLS:
        if n <= D.SPACES[sp]["max_dice"]:
            acts.append({"type": "place", "space": sp, **sel})
    if n == 1:
        full = len(p["contracts"]) >= _max_contracts(p)
        for slot in range(min(_contract_reach(p, value), len(s["contract_market"]))):
            if full:
                for di in range(len(p["contracts"])):
                    acts.append({"type": "place", "space": "caravanserai", "slot": slot, "discard": di, **sel})
            else:
                acts.append({"type": "place", "space": "caravanserai", "slot": slot, **sel})
        for c in p["posts"]:
            if s["city_spaces"].get(c, 1) is None:
                for t in range(1, _city_uses(p, value) + 1):
                    acts.append({"type": "place", "space": "city", "city": c, "times": t, **sel})
    if n <= D.SPACES["road"]["max_dice"]:
        steps = _steps(D.SPACES["road"]["table"], value, n)
        toll = _toll_sim(s, seat, "road", value)
        for path, post_at in _paths(s, seat, steps, toll, cartographer_full):
            a = {"type": "place", "space": "road", "path": path, **sel}
            if post_at is not None:
                a["post_at"] = post_at
            acts.append(a)
    return acts


def _toll_sim(s, seat, space, value):
    if not any(e["seat"] != seat for e in s["spaces"][space]):
        return 0
    return _char_toll(s["players"][seat], value * D.TOLL_PER_PIP)


class Planner:
    def __init__(self, view, seat, rng, level):
        self.seat = seat
        self.rng = rng
        self.level = level
        base = _sim_from_view(view, seat)
        base["current"] = seat
        base["turn_placed"] = False
        self.base = base
        self.p = base["players"][seat]
        self.cx = Ctx(base, seat, level)
        self.v0 = _value(base, seat, self.cx)
        self.evals = 0

    # -- simulation of one candidate
    def sim(self, preps_fn, action):
        s = _clone(self.base)
        if preps_fn:
            preps_fn(s)
        if not _try(s, self.seat, action):
            return None
        _auto_fulfill(s, self.seat)
        self.evals += 1
        return s

    def make(self, s, preps, action, used, kind=""):
        p = s["players"][self.seat]
        return Cand(_value(s, self.seat, self.cx), preps, action, used, _hand(p), kind)

    def finish(self, c):
        cx = self.cx
        spent = any(x["type"] == "seer" for x in c.preps)
        keep = _dice_term(c.hand, self.p, cx, spent)
        rest = len(c.hand) * cx.rest_coin
        c.score = c.vnd + max(keep, rest)
        c.rest_after = rest > keep + 1e-9 and len(c.hand) > 0
        return c

    # -- enumerations
    def own_unused(self):
        return [d for d in self.p["dice"] if not d["placed"] and not d["white"]]

    def guide(self):
        return next((d for d in self.p["dice"] if not d["placed"] and d["white"]), None)

    def single_table(self):
        """For each value 1..6: candidate list for one own die showing that value."""
        own = self.own_unused()
        pl = _placements_left(self.p)
        rep = own[0] if (own and pl > 0) else self.guide()
        self.table = {u: [] for u in range(1, 7)}
        if rep is None:
            return
        self.rep = rep
        full = self.level == "hard"
        for u in range(1, 7):
            def setv(s, u=u):
                for d in s["players"][self.seat]["dice"]:
                    if d["id"] == rep["id"]:
                        d["value"] = u
            s0 = _clone(self.base)
            setv(s0)
            for a in _placements_for(s0, self.seat, [rep["id"]], u, self.cx, full):
                s = self.sim(setv, a)
                if s is None:
                    continue
                vnd = _value(s, self.seat, self.cx)
                self.table[u].append((vnd, a, s))
        for u in range(1, 7):
            g = max((x[0] for x in self.table[u]), default=self.v0) - self.v0
            self.cx.dval[u] = max(self.cx.rest_coin, W["die_frac"] * g)

    def hand_without(self, used_ids, changes=None):
        """Hand values after removing used dice (optionally with die value changes)."""
        p = self.p
        if p["passed"]:
            return []
        changes = changes or {}
        own = [changes.get(d["id"], d["value"]) for d in p["dice"]
               if not d["placed"] and not d["white"] and d["id"] not in used_ids]
        n_own_used = sum(1 for d in p["dice"] if d["id"] in used_ids and not d["white"])
        cap = max(0, _placements_left(p) - n_own_used)
        own = sorted(own, reverse=True)[:cap]
        whites = [changes.get(d["id"], d["value"]) for d in p["dice"]
                  if not d["placed"] and d["white"] and d["id"] not in used_ids]
        return sorted(own + whites, reverse=True)

    def singles_for(self, die, value, preps, extra_vnd=0.0, changes=None):
        """Candidates placing `die` alone at `value` (re-using the single table)."""
        out = []
        rep = self.rep
        hand = self.hand_without({die["id"]}, changes)
        for vnd, a, _s in self.table.get(value, []):
            act = dict(a)
            if "die" in act:
                act["die"] = die["id"]
            c = Cand(vnd + extra_vnd, preps, act, {die["id"]}, hand, "single")
            if die["white"] and not rep["white"]:
                # a guide placed alone does not use up a placement; recompute the hand
                c.hand = self.hand_without({die["id"]}, changes)
            out.append(self.finish(c))
        return out

    def sets_for(self, ids, value, preps, prep_fn, extra_vnd=0.0):
        out = []
        s0 = _clone(self.base)
        if prep_fn:
            prep_fn(s0)
        for a in _placements_for(s0, self.seat, ids, value, self.cx, False):
            s = self.sim(prep_fn, a)
            if s is None:
                continue
            c = self.make(s, preps, a, set(ids), "set")
            c.vnd += extra_vnd
            out.append(self.finish(c))
        return out

    def base_candidates(self):
        cands = []
        own = self.own_unused()
        pl = _placements_left(self.p)
        guide = self.guide()
        # singles: one per distinct value (plus the guide alone)
        if pl > 0:
            seen = set()
            for d in own:
                if d["value"] not in seen:
                    seen.add(d["value"])
                    cands += self.singles_for(d, d["value"], [])
        if guide is not None:
            cands += self.singles_for(guide, guide["value"], [])
        # sets
        by_val = {}
        for d in own:
            by_val.setdefault(d["value"], []).append(d)
        for v, ds in by_val.items():
            for k in (2, 3):
                if len(ds) >= k and pl >= k:
                    cands += self.sets_for([d["id"] for d in ds[:k]], v, [], None)
            if guide is not None:
                for k in (1, 2):
                    if len(ds) >= k and pl >= k:
                        cands += self.sets_for([d["id"] for d in ds[:k]] + [guide["id"]], v, [], None)
        # rest now
        s = _clone(self.base)
        if _try(s, self.seat, {"type": "rest"}):
            c = Cand(_value(s, self.seat, self.cx), [], {"type": "rest"}, set(), [], "rest")
            c.score = c.vnd
            cands.append(c)
        return cands

    def omen_cost(self, n):
        """(cost dict, VP value) of paying an omen-priced action, or None."""
        p = self.p
        if p["omens"] >= n:
            return {"omens": n}, n * self.cx.ov
        if p["character"] == "breeder" and p["omens"] + p["camels"] >= n:
            om = p["omens"]
            return {"omens": om, "camels": n - om}, om * self.cx.ov + (n - om) * max(self.cx.camv, 0.3)
        return None

    def with_value(self, die, u, preps, cost_vnd, cost_res, extra_flag=None):
        """Candidates where `die` is changed to `u` (by a prep) and then used."""
        out = []
        out += self.singles_for(die, u, preps, -cost_vnd, {die["id"]: u})
        # sets with other dice of value u
        others = [d for d in self.own_unused() if d["id"] != die["id"] and d["value"] == u]
        pl = _placements_left(self.p)
        guide = self.guide()
        did = die["id"]

        def prep_fn(s, did=did, u=u, cost_res=cost_res, extra_flag=extra_flag):
            q = s["players"][self.seat]
            for d in q["dice"]:
                if d["id"] == did:
                    d["value"] = u
            for k, n in cost_res.items():
                q[k] -= n
            if extra_flag:
                q[extra_flag] = True
                q["power_used"] = True
        groups = []
        if not die["white"]:
            for k in (1, 2):
                if len(others) >= k and pl >= k + 1:
                    groups.append([did] + [d["id"] for d in others[:k]])
            if guide is not None and guide["id"] != did:
                for k in (0, 1):
                    if len(others) >= k and pl >= k + 1:
                        groups.append([did] + [d["id"] for d in others[:k]] + [guide["id"]])
        for ids in groups:
            out += self.sets_for(ids, u, preps, prep_fn)
        return out

    def prep_candidates(self, cands):
        out = []
        p = self.p
        own = self.own_unused()
        pl = _placements_left(p)
        if pl <= 0 or not own:
            return out
        distinct = {}
        for d in own:
            distinct.setdefault(d["value"], d)
        # Seer: set one die to any value
        if p["character"] == "seer" and not p["seer_used"]:
            for v, d in distinct.items():
                for u in range(1, 7):
                    if u == v:
                        continue
                    out += self.with_value(d, u, [{"type": "seer", "die": d["id"], "value": u}],
                                           0.0, {}, "seer_used")
        # nudges
        nc = _nudge_cost(p)
        pay = self.omen_cost(nc)
        if pay:
            cost_res, cost_v = pay
            for v, d in distinct.items():
                for delta in (1, -1):
                    u = v + delta
                    if 1 <= u <= 6:
                        out += self.with_value(d, u, [{"type": "nudge", "die": d["id"], "delta": delta}],
                                               cost_v, cost_res)
        # guide: wild in sets, or just an extra die for later
        if (self.level != "easy" and not p["guide_used"] and self.base["guide_pool"] > 0
                and p["coins"] >= D.GUIDE_COST and self.guide() is None):
            cost_v = D.GUIDE_COST * self.cx.cv
            gid = 10 ** 6
            by_val = {}
            for d in own:
                by_val.setdefault(d["value"], []).append(d)
            for v, ds in by_val.items():
                for k in (1, 2):
                    if len(ds) >= k and pl >= k:
                        def prep_fn(s, v=v):
                            q = s["players"][self.seat]
                            q["coins"] -= D.GUIDE_COST
                            q["guide_used"] = True
                            s["guide_pool"] -= 1
                            q["dice"].append({"id": gid, "value": v, "placed": False, "white": True})
                        ids = [d["id"] for d in ds[:k]] + [gid]
                        for c in self.sets_for(ids, v, [{"type": "hire_guide"}], prep_fn):
                            c.action = None   # placement decided after seeing the guide
                            out.append(c)
            # hire now, use later: expected value of an extra die
            best = max((c for c in cands if c.kind != "rest"), key=lambda c: c.score, default=None)
            if best is not None:
                ev = sum(self.cx.dval[u] for u in range(1, 7)) / 6
                c = Cand(best.vnd, [{"type": "hire_guide"}], None, set(), best.hand, "guide")
                c.score = best.score + ev * (0.92 ** len(best.hand)) - cost_v
                out.append(c)
        # rerolls: expectation over all six faces
        if self.level != "easy":
            pay = self.omen_cost(D.REROLL_COST)
            if pay:
                cost_res, cost_v = pay
                dice = sorted(distinct.values(), key=lambda d: self.cx.dval[d["value"]])
                limit = len(dice) if self.level == "hard" else 2
                base_cands = [c for c in cands if not c.preps]
                for d in dice[:limit]:
                    ev = 0.0
                    for u in range(1, 7):
                        best_u = -1e9
                        for c in base_cands:
                            if d["id"] in c.used:
                                continue
                            hand = self.hand_without(c.used, {d["id"]: u}) if c.kind != "rest" else []
                            sc = c.vnd + max(_dice_term(hand, p, self.cx), len(hand) * self.cx.rest_coin) \
                                if c.kind != "rest" else c.score
                            best_u = max(best_u, sc)
                        for c in self.with_value(d, u, [], 0.0, {}):
                            best_u = max(best_u, c.score)
                        ev += best_u / 6
                    c = Cand(ev, [{"type": "reroll", "die": d["id"]}], None, set(), [], "reroll")
                    c.score = ev - cost_v - 0.15   # risk aversion
                    out.append(c)
        return out

    def run(self):
        self.single_table()
        cands = self.base_candidates()
        cands += self.prep_candidates(cands)
        return cands


def _second_ply(planner, cand):
    """Hard: value of the best follow-up own placement after `cand` (ignoring rivals)."""
    if cand.kind in ("rest", "reroll", "guide") or cand.action is None or cand.preps:
        return None
    s = planner.sim(None, cand.action)
    if s is None:
        return None
    seat = planner.seat
    q = s["players"][seat]
    if not cand.hand:
        return None
    s["turn_placed"] = False
    s["current"] = seat
    cx = planner.cx
    best = None
    own = [d for d in q["dice"] if not d["placed"]]
    seen = set()
    for d in own:
        key = (d["value"], d["white"])
        if key in seen:
            continue
        seen.add(key)
        if not d["white"] and _placements_left(q) <= 0:
            continue
        for a in _placements_for(s, seat, [d["id"]], d["value"], cx, False):
            s2 = _clone(s)
            if not _try(s2, seat, a):
                continue
            _auto_fulfill(s2, seat)
            planner.evals += 1
            q2 = s2["players"][seat]
            h = _hand(q2)
            sc = _value(s2, seat, cx) + max(_dice_term(h, q2, cx), len(h) * cx.rest_coin)
            if best is None or sc > best:
                best = sc
    return best


# ----------------------------------------------------------------------------- planning API

class Plan:
    def __init__(self, preps, action, rest_after, score, cands=0, evals=0):
        self.preps = preps
        self.action = action
        self.rest_after = rest_after
        self.score = score
        self.n_cands = cands
        self.evals = evals

    def __repr__(self):
        return f"<Plan {self.preps} {self.action} rest_after={self.rest_after} score={self.score:.2f}>"


def plan_turn(view, seat, rng=None, level=DEFAULT_LEVEL):
    rng = rng or random.Random()
    level = level if level in LEVELS else DEFAULT_LEVEL
    pl = Planner(view, seat, rng, level)
    cands = pl.run()
    if not cands:
        return Plan([], {"type": "rest"}, False, 0.0)
    if level == "easy":
        for c in cands:
            c.score += rng.gauss(0, 1.6)
    if level == "hard":
        top = sorted(cands, key=lambda c: -c.score)[:6]
        for c in top:
            s2 = _second_ply(pl, c)
            if s2 is not None:
                c.score = 0.6 * c.score + 0.4 * max(c.score, s2 - 0.3)
    cands.sort(key=lambda c: -c.score)
    best = cands[0]
    if level == "easy" and len(cands) > 2 and rng.random() < 0.2:
        best = cands[rng.randrange(min(4, len(cands)))]
    # a prep must clearly beat the best plain placement
    if best.preps:
        plain = next((c for c in cands if not c.preps), None)
        if plain is not None and best.score < plain.score + 0.25:
            best = plain
    action = best.action if best.action is not None else None
    return Plan(best.preps, action, best.rest_after, best.score, len(cands), pl.evals)


def next_action(view, seat, rng=None, level=DEFAULT_LEVEL):
    """The next single action the bot would take from this view (stateless)."""
    if view["phase"] == "setup":
        return {"type": "choose_character", "character": _pick_character(view, seat, rng or random.Random(), level)}
    p = view["players"][seat]
    for i in sorted(range(len(p["contracts"])), key=lambda i: -D.CONTRACTS[p["contracts"][i]][1]):
        req = _contract_payment(p, D.CONTRACTS[p["contracts"][i]][0])
        if all(p.get(k, 0) >= v for k, v in req.items()):
            return {"type": "fulfill", "index": i}
    if view["turn_placed"]:
        return {"type": "rest"} if _rest_after_placing(view, seat, level) else {"type": "end_turn"}
    plan = plan_turn(view, seat, rng, level)
    if plan.preps:
        return plan.preps[0]
    return plan.action or {"type": "rest"}


def _rest_after_placing(view, seat, level):
    pl = Planner(view, seat, random.Random(0), level)
    if not _hand(pl.p):
        return False
    pl.single_table()
    keep = _dice_term(_hand(pl.p), pl.p, pl.cx)
    return len(_hand(pl.p)) * pl.cx.rest_coin > keep + 1e-9


EVAL_BUDGET = 2500   # simulated positions per turn before free-action planning stops (~100 ms)


def take_turn(state, seat, rng=None, level=DEFAULT_LEVEL, max_free=4, strict=False, budget=EVAL_BUDGET):
    """Play one full turn for `seat` on the real state via apply_action. Returns the actions.

    Every decision is made from `public_view(state, seat)` only. With `strict=True` any
    rejected action propagates (tests); otherwise the bot falls back to ending its turn or
    resting so a table can never get stuck on a bot."""
    rng = rng or random.Random()
    done = []

    def do(a):
        apply_action(state, seat, a)
        done.append(a)

    if state["phase"] == "setup":
        if not state["players"][seat]["character"]:
            choose_character(state, seat, rng, level)
            done.append({"type": "choose_character"})
        return done
    if state["phase"] != "play" or state["current"] != seat:
        return done

    def fulfil():
        while True:
            view_p = public_view(state, seat)["players"][seat]
            a = None
            for i in sorted(range(len(view_p["contracts"])), key=lambda i: -D.CONTRACTS[view_p["contracts"][i]][1]):
                req = _contract_payment(view_p, D.CONTRACTS[view_p["contracts"][i]][0])
                if all(view_p.get(k, 0) >= v for k, v in req.items()):
                    a = {"type": "fulfill", "index": i}
                    break
            if a is None:
                return
            do(a)

    try:
        fulfil()
        rest_after = False
        if not state["turn_placed"]:
            preps_done = 0
            spent = 0
            while True:
                if spent > budget:   # deterministic compute cap: place without further planning
                    plan = _plain_plan(state, seat, rng, level)
                else:
                    plan = plan_turn(public_view(state, seat), seat, rng, level)
                    spent += plan.evals
                if plan.preps and preps_done < max_free:
                    try:
                        do(plan.preps[0])
                        preps_done += 1
                        continue
                    except GameError:
                        if strict:
                            raise
                        plan = _plain_plan(state, seat, rng, level)
                if plan.preps or plan.action is None:
                    plan = _plain_plan(state, seat, rng, level)
                a = plan.action
                if a is None or a["type"] in ("rest", "pass"):
                    do({"type": "rest"})
                    return done
                do(a)
                rest_after = plan.rest_after
                break
        else:
            rest_after = _rest_after_placing(public_view(state, seat), seat, level)
        fulfil()
        do({"type": "rest"} if rest_after else {"type": "end_turn"})
    except GameError:
        if strict:
            raise
        # Safety net: never leave the table stuck on a bot.
        if state["phase"] == "play" and state["current"] == seat:
            for a in ({"type": "end_turn"}, {"type": "rest"}):
                try:
                    do(a)
                    break
                except GameError:
                    continue
    return done


def _plain_plan(state, seat, rng, level):
    pl = Planner(public_view(state, seat), seat, rng, level)
    pl.single_table()
    cands = pl.base_candidates()
    if not cands:
        return Plan([], {"type": "rest"}, False, 0)
    best = max(cands, key=lambda c: c.score)
    return Plan([], best.action, best.rest_after, best.score)


# ----------------------------------------------------------------------------- characters

def _pick_character(view, seat, rng, level):
    p = view["players"][seat]
    choices = p["character_choices"]
    if level == "easy":
        return rng.choice(choices)

    def score(ch):
        sc = CHARACTER_PREF.get(ch, 0.5)
        comm = [D.COMMISSIONS[c] for c in p["commissions"] if c is not None]
        east = sum(D.CITIES[a]["post_vp"] + D.CITIES[b]["post_vp"] for a, b in comm)
        if ch == "pathfinder":
            sc += 0.02 * east
        return sc + rng.random() * 0.05
    return max(choices, key=score)


def choose_character(state, seat, rng=None, level=DEFAULT_LEVEL):
    rng = rng or random.Random()
    ch = _pick_character(public_view(state, seat), seat, rng, level)
    a = {"type": "choose_character", "character": ch}
    apply_action(state, seat, a)
    return a


def bot_name(taken, rng=None):
    """A themed bot name not already at the table."""
    rng = rng or random.Random()
    names = [f"Bot · {n}" for n in BOT_NAMES]
    free = [n for n in names if n.lower() not in {t.lower() for t in taken}]
    if free:
        return rng.choice(free)
    i = 2
    while True:
        n = f"Bot · {rng.choice(BOT_NAMES)} {i}"
        if n.lower() not in {t.lower() for t in taken}:
            return n
        i += 1
