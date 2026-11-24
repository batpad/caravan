"""Deterministic setup and scripting for the guided "Learn to play" game.

A tutorial game is an ordinary 2-seat game (the learner vs one easy bot) whose opening is
fixed so the coach-mark lessons in static/game/tutorial.js always have something to point at:

* the deal comes from `new_game(..., rng=random.Random(SEED))`;
* the learner is offered two gentle characters and a commission that includes Antioch;
* slot 1 of the contract market holds a contract the learner can deliver right after
  using the Spice Stall;
* the learner's dice for rounds 1 and 2 are fixed (see LEARNER_DICE);
* the bot's first two turns in round 1 are scripted (Camel Market, then the Road), so the
  Road is crowded when the learner travels and the toll lesson really costs something.

Nothing here changes a rule: every scripted move goes through `engine.apply_action`, and the
fixed dice only replace the values of an ordinary roll (low-roll compensation is recomputed).
Whenever a scripted move is not legal (for example because `data.py` was rebalanced), the
script quietly falls back to the normal bot, so a tutorial game can never get stuck.
"""
import copy
import random
import re

from .engine import bot
from .engine import data as D
from .engine.engine import GameError, apply_action, new_game, travel_options

SEED = 1871
LEARNER = 0
BOT = 1
BOT_LEVEL = "easy"
LEARNER_CHOICES = ["cartographer", "seer"]
BOT_CHARACTER = "pathfinder"
# Round -> the learner's dice. Round 1: spice (5), contract (3), road (1), city action (4),
# shrine (2). Round 2: a pair of 2s, a 6 to pair with a guide, a 3 to reroll/nudge, a 1 to rest.
LEARNER_DICE = {1: [5, 3, 1, 4, 2], 2: [2, 2, 6, 3, 1]}
# Where the scripted bot would like to travel on its second turn (never Antioch: that city
# belongs to the learner's lessons).
BOT_DESTINATIONS = ["trebizond", "baghdad", "tabriz"]


def _pick(seq, pred, default=None):
    return next((x for x in seq if pred(x)), default)


def _deliverable_contract(spice, silk):
    """Best contract payable with only spice/silk on hand (index into D.CONTRACTS)."""
    best = None
    for i, (req, vp, _bonus) in enumerate(D.CONTRACTS):
        if set(req) <= {"spice", "silk"} and req.get("spice", 0) <= spice and req.get("silk", 0) <= silk:
            if best is None or vp > D.CONTRACTS[best][1]:
                best = i
    return best


def new_tutorial_state(learner_name, bot_name):
    """The dealt (setup-phase) state of a tutorial game. Pure; the bot has already chosen."""
    st = new_game([learner_name, bot_name], rng=random.Random(SEED))
    me, rival = st["players"][LEARNER], st["players"][BOT]
    me["character_choices"] = [c for c in LEARNER_CHOICES if c in D.CHARACTERS][:2] or me["character_choices"]
    rival["character_choices"] = [BOT_CHARACTER if BOT_CHARACTER in D.CHARACTERS else rival["character_choices"][0],
                                  rival["character_choices"][1]]
    # A commission that includes Antioch, where the learner founds the first post.
    comm = _pick(range(len(D.COMMISSIONS)), lambda i: "antioch" in D.COMMISSIONS[i])
    if comm is not None and not any("antioch" in D.COMMISSIONS[c] for c in me["commissions"]):
        if comm in rival["commissions"]:
            rival["commissions"][rival["commissions"].index(comm)] = me["commissions"][0]
        me["commissions"][0] = comm
    # ...and a second one that does not repeat a city of the first.
    first = set(D.COMMISSIONS[me["commissions"][0]])
    if first & set(D.COMMISSIONS[me["commissions"][1]]):
        taken = set(me["commissions"]) | set(rival["commissions"])
        other = _pick(range(len(D.COMMISSIONS)), lambda i: i not in taken and not first & set(D.COMMISSIONS[i]))
        if other is not None:
            me["commissions"][1] = other
    # Slot 1: a contract the learner can deliver right after the Spice Stall lesson.
    first_die = LEARNER_DICE[1][0]
    spice = D.START_RESOURCES.get("spice", 0) + D.SPACES["bazaar_spice"]["table"][first_die]
    cid = _deliverable_contract(spice, D.START_RESOURCES.get("silk", 0))
    if cid is not None:
        market, deck = st["contract_market"], st["contract_deck"]
        if cid in market:
            market.remove(cid)
        elif cid in deck:
            deck.remove(cid)
        else:
            st["contract_discard"].remove(cid)
        market.insert(0, cid)
        while len(market) > D.CONTRACT_SLOTS:
            deck.append(market.pop())
    st["tutorial"] = {"seed": SEED, "learner": LEARNER, "scripted_rounds": [], "bot_turns": 0}
    apply_action(st, BOT, {"type": "choose_character", "character": rival["character_choices"][0]})
    return st


def _comp(values):
    return min(D.LOW_ROLL_MAX, max(0, D.LOW_ROLL_PER_DIE * len(values) - sum(values)))


def on_state_change(st):
    """Call after every applied action / bot step. Fixes the learner's dice once per scripted
    round, right after that round was rolled. Idempotent."""
    t = st.get("tutorial")
    if not t or st["phase"] != "play":
        return False
    rnd = st["round"]
    if rnd not in LEARNER_DICE or rnd in t["scripted_rounds"]:
        return False
    t["scripted_rounds"].append(rnd)
    p = st["players"][t.get("learner", LEARNER)]
    own = [d for d in p["dice"] if not d["white"]]
    if any(d["placed"] for d in own):
        return False   # too late: the learner already played (should not happen)
    old = [d["value"] for d in own]
    wanted = LEARNER_DICE[rnd]
    for i, d in enumerate(own):
        d["value"] = wanted[i % len(wanted)]
    new = [d["value"] for d in own]
    p["coins"] += _comp(new) - _comp(old)
    for e in reversed(st["log"]):   # keep the journal truthful about the roll
        if e.get("seat") == p["seat"] and e.get("round") == rnd and e["text"].startswith(f"{p['name']} rolls ["):
            e["text"] = _rewrite_roll(e["text"], p["name"], new, _comp(old), _comp(new))
            break
    return True


def _rewrite_roll(text, name, dice, old_comp, new_comp):
    """'<name> rolls [..] and collects 2 coins, 1 omens (incl. 2 coins for a poor roll).' with the
    fixed dice and the recomputed poor-roll coins."""
    m = re.match(r"^.* rolls \[[^\]]*\](?: and collects (.*?))?(?: \(incl\. \d+ coins for a poor roll\))?\.$", text)
    items = []
    if m and m.group(1):
        for part in m.group(1).split(", "):
            n, _, what = part.partition(" ")
            if n.isdigit():
                items.append([int(n), what])
    coins = next((it for it in items if it[1] == "coins"), None)
    if coins is None:
        coins = [0, "coins"]
        items.insert(0, coins)
    coins[0] += new_comp - old_comp
    items = [it for it in items if it[0] > 0]
    msg = f"{name} rolls [{' '.join(map(str, dice))}]"
    if items:
        msg += " and collects " + ", ".join(f"{n} {w}" for n, w in items)
        if new_comp:
            msg += f" (incl. {new_comp} coins for a poor roll)"
    return msg + "."


def _legal(st, seat, action):
    try:
        apply_action(copy.deepcopy(st), seat, action)
        return True
    except GameError:
        return False


def _scripted_bot_action(st, seat):
    """The bot's scripted placement for its first two turns of round 1, or None."""
    t = st["tutorial"]
    if st["round"] != 1 or st["turn_placed"] or t.get("bot_turns", 0) >= 2:
        return None
    p = st["players"][seat]
    free = sorted((d for d in p["dice"] if not d["placed"] and not d["white"]), key=lambda d: d["value"])
    if not free:
        return None
    if t["bot_turns"] == 0:   # turn 1: the Camel Market with its highest die
        for d in reversed(free):
            a = {"type": "place", "die": d["id"], "space": "camels"}
            if _legal(st, seat, a):
                return a
        return None
    # turn 2: travel with its lowest die, so the Road is crowded for the learner
    table = D.SPACES["road"]["table"]
    for d in free:
        steps = table[d["value"]]
        toll = 0
        if any(e["seat"] != seat for e in st["spaces"]["road"]):
            toll = d["value"] * D.TOLL_PER_PIP
        opts = travel_options(st, seat, steps, toll)
        for dest in BOT_DESTINATIONS:
            o = _pick(opts, lambda o: o["dest"] == dest)
            if o:
                a = {"type": "place", "die": d["id"], "space": "road", "path": o["path"]}
                if _legal(st, seat, a):
                    return a
    return None


def bot_turn(st, seat, rng):
    """Play one bot turn in a tutorial game: scripted early, the easy bot afterwards."""
    t = st.get("tutorial")
    a = _scripted_bot_action(st, seat) if t else None
    if t and st["phase"] == "play" and st["round"] == 1:
        t["bot_turns"] = t.get("bot_turns", 0) + 1
    if a is None:
        bot.take_turn(st, seat, rng, BOT_LEVEL)
    else:
        apply_action(st, seat, a)
        apply_action(st, seat, {"type": "end_turn"})
    on_state_change(st)
