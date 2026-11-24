# Caravan Road

An original online multiplayer Silk Road board game for 2–4 players: dice placement, bazaar trading, contracts, and a race across Asia.
The backend is Django and the frontend is vanilla JS ES modules, with no build step.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install "django>=5.1"
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

Open http://localhost:8000. To start a game, create one and share the 5-letter code or the `/g/CODE/` link with the other players. The host starts the game once at least 2 players have joined. Each browser keeps its seat token in localStorage, so refreshing the page or reconnecting puts you back in your seat.

```bash
.venv/bin/python manage.py test game            # rules + API tests
.venv/bin/python -m game.engine.simulate 600    # bot self-play balance report
.venv/bin/python -m game.engine.bench 100       # AI bot vs random bot, bot vs bot, per-character win rates
.venv/bin/python -m game.engine.bench 60 --levels  # easy vs normal vs hard
```

## Layout

| Path | What |
| --- | --- |
| `game/engine/data.py` | All game content and numbers: map, cities, characters, contracts, tables. **Tune balance here.** |
| `game/engine/engine.py` | Pure-Python rules engine. `new_game`, `apply_action`, `public_view` (hides secret info). |
| `game/engine/RULES_CHANGES.md` | Changelog of rules, action schema, state and `static_data` for the frontend/bot. |
| `game/engine/simulate.py` | Random-greedy bot used for tests and balance checks. |
| `game/engine/bot.py` | The AI opponent (easy / normal / hard): `choose_character`, `take_turn`, `plan_turn`, `next_action`. Decides only from `public_view`. |
| `game/engine/bench.py` | Benchmarks for the AI bot. |
| `game/views.py`, `urls.py` | JSON API: create/list/join/leave/start, `state?since=<version>` polling, `action`. |
| `game/static/game/` | `app.js` router + polling · `lobby.js` · `game.js` play UI · `board.js` SVG map · `dom.js` helpers. |

The server is authoritative: every action is validated in `engine.apply_action` inside a DB transaction. Seats authenticate with a secret `X-Seat-Token`.

### Playing against the AI

| Request | Body | Response |
| --- | --- | --- |
| `POST /api/games/` | `{"player", "bots": 1-3, "bot_level": "easy"\|"normal"\|"hard"}` | `{"code", "token", "seat": 0, "started": true}`: a solo table that starts at once |
| `POST /api/games/<code>/add_bot/` (host, lobby) | `{"level"}` (default `normal`) | `{"ok", "seat", "name", "level", "version"}` |
| `POST /api/games/<code>/remove_seat/` (host, lobby) | `{"index"}` (bots only) | `{"ok", "version"}` |
| `POST /api/games/` | `{"player", "tutorial": true}` | `{"code", "token", "seat": 0, "started": true, "tutorial": true}`: the guided "Learn to play" game (learner vs one easy bot, dealt deterministically by `game/tutorial.py`; hidden from the open-games list) |
| `GET /api/games/<code>/hint/` (seated human, on your move) | — | `{"action", "seat", "version"}`: the move the normal-level AI would make next (no side effects). 403 if not seated, 400 if it is not your move |

Lobby/state payloads also carry `tutorial` (bool). In tutorial games the bot waits `TUTORIAL_BOT_STEP_DELAY` seconds (2.5 by default, env `CARAVAN_TUTORIAL_BOT_STEP_DELAY`) before each move, its first two turns of round 1 are scripted, and the learner's dice for rounds 1–2 are fixed; every move still goes through `engine.apply_action`. The coach marks live in `static/game/tutorial.js`, the "How to play" reference in `static/game/rules.js`.

Lobby/state payloads list `players[]` with `is_bot` and `bot_level` (`null` for humans). Bots choose their characters when the game starts. On their turns they act lazily: a `state` poll plays one bot turn once the game has been idle for `BOT_STEP_DELAY` seconds (0.8 by default, env `CARAVAN_BOT_STEP_DELAY`). This happens inside the same IMMEDIATE transaction as human actions, and the version is re-checked so concurrent pollers never double-step. If every human leaves a lobby, it is deleted.

## Rules summary

**Setup:** each player chooses one of two dealt characters and secretly receives two commissions, each a pair of cities. All caravans start in Constantinople. Later seats start with a few extra coins.

**Round (5 total):**
1. **Income.** Each player collects the income of every city where they have a trading post, plus any character bonus. Then everyone rolls their dice (5 each). A low total, below 3 × the number of dice, earns up to 4 coins of compensation.
2. **Turns.** Players go clockwise from the lead player. On your turn, make **one placement**: a single die, or a **set** of 2–3 dice showing the same value on a space that accepts sets. You may take free actions before and after placing. Then end your turn, or **Rest**: take 1 coin per die you could still have placed and sit out the rest of the round. You can rest instead of placing, or straight after placing.
   - **Crowd toll:** if another player already has a die on a shared space, pay **1 coin per pip** of the value you place. A set pays the toll once. High dice are strong but expensive on a crowded space; low dice are cheap anywhere.
   - **Sets:** a set of n dice gives n × the single-die amount, plus a bonus of +1 for a pair or +2 for a triple. A hired guide die is wild in a set.

     | Accepts up to | Spaces |
     | --- | --- |
     | 3 dice | Spice Stall, Silk Stall, Camel Market |
     | 2 dice | Jade Stall, Moneychanger, The Road |
     | 1 die | Shrine, Caravanserai, city actions |
   - **Bazaar stalls (spice, silk, jade), Camel Market, Moneychanger, Shrine:** gain the amount shown for the die's value. The jade stall also costs 1 coin per die. The first visitor to the Shrine leads the next round; if nobody visits, the lead passes clockwise.
   - **Caravanserai:** take a contract from slots 1 up to your die value. The market refills at once. You may hold 2 open contracts; to take another, you must abandon one.
   - **The Road:** travel 1/1/2/2/3/3 steps (a pair travels 2 × that + 1). Pay each route's cost: road 1🐪, desert 2🐪, mountain 2🐪+1🪙, sea 3🪙. Where your journey ends, you found a trading post, worth the VP printed on the city. You have 8 posts, and none can be founded in Constantinople or Chang'an. Ending a journey in Chang'an for the first time scores 8/5/3/1 VP by arrival order.
   - **City action:** if you have a post in a city, place one die there to use its exchange 1/1/1/2/2/2 times (die 1–3: once, 4–6: twice). Each city's action can be used by only one player per round.
   - **Free actions:**
     - Deliver a contract.
     - Reroll a die (1🔮).
     - Change a die by ±1 (2🔮).
     - Hire a white guide die (3🪙). You can hire one per round, and there are 3 guides per round.
     - Use your Seer power, if you have it.
3. **End of round.** The two oldest contracts leave the market and it refills.

**Characters:**

| Character | Power |
| --- | --- |
| Cartographer | Once per round, a journey may also found a post (worth 1 VP) in a city it passes through. |
| Camel Breeder | +2 camels each round. Camels stand in for omens (1 each) and for missing contract goods (2 camels per good). |
| Seer | +1 omen and +1 coin each round. Nudges cost 1 omen. Twice per round, set an unused die to any value. |
| Silk Heiress | Rolls 6 dice but places at most 5 of them. +1 silk each round. |
| Moneylender | Pays half the crowd toll (rounded up). |
| Guildmaster | Holds 3 open contracts and reaches 1 slot further at the Caravanserai. +1 VP per contract delivered. |
| Pathfinder | Desert and mountain routes cost 1 fewer camel. +4 VP on first reaching Chang'an. |
| Quartermaster | City actions can be used one extra time. +1 coin per 4 trading posts each round. |

**End-game scoring** adds the following to VP earned during play:
- **Commissions:** 6 VP if you have posts in both cities, 2 VP if you have one.
- **Most trading posts:** 6 VP for first, and 3 VP for second (second place counts only with 3+ players).
- **Most contracts delivered:** 4 VP.
- **Leftovers:** 1 VP per 10 coins and 1 VP per 3 goods.

Ties are broken by coins, then goods; players still tied share the win.

See `game/engine/RULES_CHANGES.md` for the full list of rule, action-schema and state changes.
