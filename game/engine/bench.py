"""Benchmark the AI bot.

    python -m game.engine.bench                 # default: 60 games per matchup
    python -m game.engine.bench 200 --quick     # only bot-vs-random 2p and bot-vs-bot
    python -m game.engine.bench 100 --levels    # easy vs normal vs hard

Reports win rates (shared wins split), average scores, game length, per-turn timing,
and per-character win rates for bot-vs-bot (a balance signal).
"""
import random
import statistics
import sys
import time
from collections import defaultdict

from . import bot
from . import data as D
from .engine import apply_action, new_game
from .simulate import _bot_turn as random_turn


def play(agents, seed, characters=None, timing=None, random_chars=False):
    """agents: list per seat of "random" or a bot level. Returns the finished state and turn count."""
    rng = random.Random(seed)
    random.seed(seed)
    n = len(agents)
    state = new_game([f"S{i}" for i in range(n)], rng)
    for p in state["players"]:
        s = p["seat"]
        if characters:
            p["character_choices"] = [characters[s], p["character_choices"][0]]
            apply_action(state, s, {"type": "choose_character", "character": characters[s]})
        elif agents[s] == "random" or random_chars:
            apply_action(state, s, {"type": "choose_character", "character": rng.choice(p["character_choices"])})
        else:
            bot.choose_character(state, s, rng, agents[s])
    turns = 0
    while state["phase"] != "finished":
        seat = state["current"]
        if agents[seat] == "random":
            random_turn(state, rng)
        else:
            t0 = time.perf_counter()
            bot.take_turn(state, seat, rng, agents[seat])
            if timing is not None:
                timing.append(time.perf_counter() - t0)
        turns += 1
        assert turns < 2000, "runaway game"
    return state, turns


def matchup(label, agents_fn, games, n_players, timing, random_chars=False):
    wins = defaultdict(float)
    scores = defaultdict(list)
    lengths = []
    char_wins = defaultdict(float)
    char_games = defaultdict(int)
    for g in range(games):
        agents = agents_fn(g)
        st, turns = play(agents, 1000 + g * 7 + n_players, timing=timing, random_chars=random_chars)
        lengths.append(turns)
        win = [r["seat"] for r in st["final"] if r["rank"] == 1]
        for r in st["final"]:
            scores[agents[r["seat"]]].append(r["total"])
        for s in win:
            wins[agents[s]] += 1 / len(win) / agents.count(agents[s])
        for p in st["players"]:
            char_games[p["character"]] += 1
            if p["seat"] in win:
                char_wins[p["character"]] += 1 / len(win)
    kinds = sorted(set(scores))
    parts = []
    for k in kinds:
        parts.append(f"{k}: win {wins[k] / games:.0%} avg {statistics.mean(scores[k]):.1f}")
    print(f"{label:34s} {' | '.join(parts)} | turns {statistics.mean(lengths):.0f}")
    return char_wins, char_games


def main(argv):
    games = int(argv[0]) if argv and argv[0].isdigit() else 60
    quick = "--quick" in argv
    levels = "--levels" in argv
    timing = []
    t_start = time.time()
    print(f"== {games} games per matchup ==")
    if levels:
        for n in (2, 3, 4):
            for a, b in (("normal", "easy"), ("hard", "normal")):
                matchup(f"{a} vs {b} {n}p",
                        lambda g, a=a, b=b, n=n: [a if (i + g) % 2 == 0 else b for i in range(n)],
                        games, n, timing)
    else:
        for n in ((2,) if quick else (2, 3, 4)):
            # one bot (rotating seat) vs random-greedy bots
            matchup(f"normal vs {n - 1}x random {n}p",
                    lambda g, n=n: ["normal" if i == g % n else "random" for i in range(n)], games, n, timing)
            if not quick:
                matchup(f"easy vs {n - 1}x random {n}p",
                        lambda g, n=n: ["easy" if i == g % n else "random" for i in range(n)], games, n, timing)
        print("-- bot vs bot (normal, characters dealt at random), per-character win rate --")
        cw, cg = defaultdict(float), defaultdict(int)
        fair = defaultdict(float)
        for n in (2, 3, 4):
            w, gm = matchup(f"normal self-play {n}p", lambda g, n=n: ["normal"] * n, games, n, timing,
                            random_chars=True)
            for c in D.CHARACTERS:
                cw[c] += w[c]
                cg[c] += gm[c]
                fair[c] += gm[c] / n
        for c in sorted(D.CHARACTERS, key=lambda c: -(cw[c] / fair[c] if fair[c] else 0)):
            if cg[c]:
                print(f"  {c:14s} wins/fair {cw[c] / fair[c]:.2f}  win {cw[c] / cg[c]:.0%} over {cg[c]} seats")
    if timing:
        timing.sort()
        print(f"bot turn time: mean {statistics.mean(timing) * 1000:.1f} ms, "
              f"p95 {timing[int(len(timing) * 0.95)] * 1000:.1f} ms, max {timing[-1] * 1000:.1f} ms "
              f"over {len(timing)} turns")
    print(f"total {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
