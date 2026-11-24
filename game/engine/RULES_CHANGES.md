# Rules engine changes

This file lists every change to the rules, the action schema, the state shape and `static_data()` made during the rules-engine review. It is written for the frontend and for the AI bot author. All numbers live in `game/engine/data.py`. The public API is unchanged: `new_game`, `apply_action`, `public_view`, `static_data`, `travel_options`.

## 1. Rule changes and why

### 1.1 Crowd toll scales with the die value
**Before:** placing on a shared space that already held another player's die cost +1 coin per other player there, up to 3.
**Now:** if any *other* player already has a die on the space, you pay **1 coin per pip** of the value you place (`TOLL_PER_PIP`). A set pays the toll **once**, for its common value. Your own dice never make a space crowded for you. City spaces stay exclusive, so they never charge a toll.

**Why:** this gives every placement a real tradeoff. A high die is strong but expensive on a crowded space. A low die is weak but cheap. Placing a 6 early, before anyone else, is free, so high dice reward tempo. Low dice can go anywhere for a coin or two. The new rule also creates small decisions within a table. On a crowded Road a 5 travels as far as a 6 and costs 1 coin less, so nudging a die down can be correct.

### 1.2 Sets: placing 2–3 dice of the same value at once
Some spaces accept a set of dice that all show the same value. The maximum set size is `SPACES[*].max_dice`:

| Space | max dice |
| --- | --- |
| Spice Stall, Silk Stall, Camel Market | 3 |
| Jade Stall, Moneychanger, The Road | 2 |
| Shrine, Caravanserai, city actions | 1 |

The effect is `table[value] × n + SET_BONUS[n]`, with `SET_BONUS = [0, 0, 1, 2]`. On the Road the formula gives the number of steps, so a pair of 1s travels 3 steps and a pair of 6s travels 7. A space's own cost (for example the Jade Stall's 1 coin) is paid per die. The crowd toll is paid once per placement.

A set is still **one placement**, so it uses your one action for the turn. It spends more dice in one go. It gets ahead of the crowd, pays a single toll, and earns a small bonus. This makes rerolls, nudges, the Seer and the guide die matter much more.

### 1.3 The guide die is wild in sets
A hired white guide die matches any value inside a set. The set's value is the value of your coloured dice. A guide die placed alone uses its own rolled value. Hiring a guide therefore means choosing between an extra action and completing a pair. The cost (3 coins), the limit of one per player per round, and the shared pool of 3 are unchanged.

### 1.4 Rest (pass)
- You may now rest **after placing in the same turn**; resting also ends your turn. Before, resting after placing was an error.
- `"type": "rest"` is a new alias for `"pass"`. Both still work.
- Resting pays `REST_COINS_PER_DIE` (1) per unused die you could still have placed. The Heiress's spare die does not count.

### 1.5 Contract market
- When a contract is taken, the market **refills immediately**: the remaining contracts slide down and a new card arrives in slot 6. Before, the market stayed short until the round ended, so later players in a 4-player round could face an empty Caravanserai.
- At the end of each round the `CONTRACT_CHURN` (2) oldest contracts still leave the market, as before.

### 1.6 Travel
- **No trading posts can be founded in Chang'an** or Constantinople (`NO_POST_CITIES`). Before, Chang'an silently used up one of your 8 posts and counted toward the post-majority bonus while scoring 0 VP. Arriving in Chang'an still scores 8/5/3/1 VP by arrival order, once per player, and only when the journey ends there.
- Path validation is strict. `path` must be a list of known city names that starts at your location, does not revisit a city, follows real routes, and is no longer than your step count. The crowd toll and the route costs are checked together before anything is paid.

### 1.7 Scoring
- **Post majority:** with 2 players only the first-place award (6 VP) is given. Before, the runner-up got 3 VP just for having at least one post.
- **Tiebreaks:** most VP, then most coins, then most goods (spice + silk + jade). Players still tied share the rank.

### 1.8 Seat compensation
The starting coins bonus by seat is now `SEAT_BONUS_COINS = [0, 1, 1, 2]`; before, it was `+seat` (0/1/2/3). The rotating lead player already offsets most of the turn-order advantage. In 1500-game self-play runs per setting, neither bonus table showed a seat effect larger than the noise, so the smaller table was chosen to keep 4th seat from starting 50% richer than 1st. This is a judgement call and easy to retune.

### 1.9 Unchanged, but reviewed
- Low-roll compensation: `min(LOW_ROLL_MAX, LOW_ROLL_PER_DIE × dice − total pips)`, counting only your coloured dice. The numbers are now in `data.py`.
- Start player: the first visitor to the Shrine leads the next round. If nobody visits, the lead passes clockwise.
- Reroll costs 1 omen. Nudge (±1) costs 2 omens; the Seer pays 1.
- City actions: you need a trading post there, a city can be used by one player per round, and the die gives 1/1/2/2/3/3 uses. `times` defaults to the largest number of uses you can afford.

## 2. Characters (first pass; see section 9 for the current powers)

| key | power | engine hook |
| --- | --- | --- |
| `cartographer` | Once per round, a journey also founds a trading post in one city it passes through. The surveyed post scores no printed VP (`CARTOGRAPHER_SURVEY_VP`) but counts for income, commissions, majority and city actions. | `_survey_choice` |
| `breeder` | +2 camels each round. May pay camels instead of omens, 1 for 1, for rerolls and nudges. | `_omen_payment` |
| `seer` | +1 omen each round. Nudges cost 1 omen. Once per round, set one unused die to any value. | `seer` action |
| `heiress` | Rolls 6 dice but may place at most 5 of her own dice per round. Guide dice are excluded from the limit. +1 silk each round. | `_placements_left` |
| `moneylender` | Pays half the crowd toll, rounded down. When a rival pays a toll on a space where the Moneylender has a die, the Moneylender takes 1 coin from the bank. | `_toll`, `_place` |
| `guildmaster` | Holds up to 3 open contracts; each delivered contract scores +1 VP. | unchanged |
| `pathfinder` | Desert **and mountain** routes cost 1 fewer camel. | `_route_cost` |
| `quartermaster` | City actions may be used one extra time (a die gives 2/2/3/3/4/4 uses). +1 coin per trading post each round. | `_city_uses` |

Why each one changed:
- **Cartographer:** +1 step rarely mattered, because travel is limited by camels and coins rather than steps. The new power rewards multi-step journeys and therefore high dice and sets. It scored too high in simulation while surveyed posts also scored their printed VP, so that VP was removed.
- **Breeder:** the flat +1 camel +1 coin was dull. The new power ties camels to dice manipulation.
- **Seer:** was the weakest character in simulation. The omen income and cheaper nudges let the Seer actually build sets.
- **Heiress:** was the strongest. A flat 6th die meant a sixth action every round. The Heiress now chooses her best 5 of 6, which gives better values and more sets. The silk income keeps her competitive.
- **Moneylender:** "never pays" would be overwhelming once tolls scale with the die value. The power now still centres on the toll mechanic and adds interaction with rivals.
- **Pathfinder:** the desert-only discount was narrow. Mountains are now included.
- **Quartermaster:** gains a dice-related half that turns cities into an engine.

## 3. Action schema

The existing actions still validate exactly as before, with stricter type checks: integers must be real JSON integers, so `true`, `1.0` and `"1"` are rejected. A non-object action is rejected with a `GameError`, which returns HTTP 400 instead of a 500.

### `place`
```jsonc
{"type": "place", "die": 12, "space": "treasury"}            // single die (unchanged)
{"type": "place", "dice": [12, 14], "space": "bazaar_spice"} // NEW: a set (1..max_dice ids)
{"type": "place", "dice": [12, 31], "space": "road", "path": [...]}  // 31 = guide die, wild
{"type": "place", "die": 12, "space": "road", "path": ["constantinople","antioch","baghdad"],
 "post_at": "antioch"}                                         // NEW (Cartographer only)
{"type": "place", "die": 12, "space": "city", "city": "baghdad", "times": 2} // times optional
{"type": "place", "die": 12, "space": "caravanserai", "slot": 0, "discard": 1}
```
- Send `die` **or** `dice`, never both. `dice` must be a non-empty list of distinct ids belonging to you and still unused. Its length must not exceed the space's `max_dice`, and all coloured dice must show the same value.
- `post_at` (Cartographer only):
  - a city name: survey that intermediate city;
  - omitted or `null`: the engine automatically surveys the highest-VP eligible city on the path, if the power is unused this round;
  - `false`: decline.
  Any other player who sends a string gets an error.
- `times` (city): optional; it defaults to the most uses you can afford.

### `reroll` / `nudge`
New optional field `"pay": "omens" | "camels"`. The default is omens first, then camels. Only the Breeder may pay with camels; anyone else who sends `"camels"` gets an error.

### `rest`
New alias for `pass`. It is also legal after placing in the same turn, and it ends the turn.

## 4. State changes (all additive)

| Where | Field | Meaning |
| --- | --- | --- |
| `state` | `next_set_id` | Counter for set ids. |
| `state.spaces[space][i]` | `set`, `set_size` | Present only on entries placed as part of a set. Every die in the set gets one entry, as before, so existing rendering still shows each die. |
| `player` | `power_used` | Once-per-round power flag (Cartographer survey and Seer). `seer_used` is still maintained for the Seer. |
| `player.dice[i]` | `rested` | `true` on dice that were set aside by resting. They still have `placed: true`. |
| `final[i]` | `rank` | 1-based. Tied players share a rank. |
| `final[i]` | `tiebreak2` | Total goods, the second tiebreaker. |

Other notes:
- Chang'an no longer appears in `posts`.
- `contract_market` always holds 6 contracts while the deck and discard pile last.

## 5. `public_view` changes

- Every player now has `placements_left` during play: how many more of their own dice they may place this round. This matters for the Heiress.
- The following are added only for the seat whose turn it is:
  - `tolls`: `{space: [t0, t1, …, t6]}`, the coins this player would pay to place a die or set of each value on each space. Index 0 is unused. This already includes the Moneylender's halving.
  - `occupy_cost` (**meaning changed**): `{space: 0|1}`. A 1 means the space is crowded for you, so the toll applies. Read `tolls[space][value]` for the amount; do not display `occupy_cost` as coins any more.
  - `travel` (unchanged keys `"1"`–`"6"`): single-die journeys. Affordability now holds back the Road toll for that die value.
  - `travel_pair` (new): the same structure for a **pair** of that value on the Road (`table[v] × 2 + SET_BONUS[2]` steps).
  - `costs`: `{"reroll": n, "nudge": n}` as they apply to this player (the Seer's nudge costs 1).

## 6. `static_data` changes (all additive)

- `spaces[*].max_dice`: the largest set each space accepts.
- `no_post_cities`: `["constantinople", "changan"]`.
- New `rules` keys:
  - `toll_per_pip`
  - `set_bonus`
  - `low_roll_per_die`, `low_roll_max`
  - `rest_coins_per_die`
  - `contract_churn`
  - `max_open_contracts`
  - `dice_per_player`
  - `seat_bonus_coins`
  - `guide_dice`
- `rules.max_occupy` is kept and is now 6, the largest possible toll.
- `powers` (new): the numbers behind the character powers:
  - `breeder_income`
  - `seer_income`, `seer_nudge_cost`
  - `heiress_dice`, `heiress_max_placed`, `heiress_income`
  - `guildmaster_contracts`, `guildmaster_bonus_vp`
  - `pathfinder_routes`, `pathfinder_discount`
  - `quartermaster_extra_uses`, `quartermaster_coins_per_post`
  - `moneylender_kickback`
  - `cartographer_survey_vp`
- `characters[*].text` has been updated for every character.

## 7. Bugs fixed

- **Validation before mutation.** Every rejected action now leaves the state byte-for-byte unchanged. The tests check this with a battery of bad inputs.
- `seer` with `"value": 1.0` or `true` was accepted and stored a float die value, which later crashed table lookups. Values must now be integers.
- `die: true` matched die id 1, because `True == 1` in Python. `nudge` with `delta: true` or `1.0` was accepted. Caravanserai `slot`/`discard` and `fulfill` `index` accepted booleans. All of these are now rejected.
- A Road `path` containing an unknown city crashed with `KeyError` (500). A path containing unhashable items crashed in `set()`. Both now give a `GameError`.
- City `times`: a non-numeric string crashed `int()`, a float was silently truncated, and `0` was treated as the maximum. All are now rejected.
- A non-object action body, such as a JSON list, crashed with `AttributeError`, which returned a 500.
- Chang'an used up a trading post and counted toward post majority.
- In 2-player games the runner-up always got the second-place post-majority award.
- The market was not refilled during a round, so it could empty in 4-player games.
- Players who could not place any more dice were auto-skipped only when they had no unused dice at all. This now also covers the Heiress's 5-die limit.

## 8. For the AI bot author
- Enumerating placements means: singles, plus sets of 2–3 equal values (with your guide as a wildcard), for each space up to its `max_dice`.
- `engine._placements_left(p)`, `engine._toll(state, seat, space, value)` and `engine._steps(table, value, n)` are pure helpers you can use.
- The engine uses Python's global `random` for dice and reshuffles. Seed it for reproducible lookahead.

## 9. Balance pass (after the strong AI bot)

With competent play from `bot.py`, the first-pass numbers showed real imbalance:
- Win share relative to fair, normal bots: Moneylender 2.19, Quartermaster 1.64, Breeder 0.31, Pathfinder 0.48.
- City actions produced about 45% of every score.

This pass fixes that with number changes plus three small mechanics. Every rule below is implemented and tested, and the bot plays the changed powers.

### 9.1 City actions are a supplement, not the engine
- `CITY_ACTION_REPEATS` is now `[0, 1, 1, 1, 2, 2, 2]`: a die of 1–3 gives one use and 4–6 gives two. Before, it was 1/1/2/2/3/3.
- Direct goods-to-VP exchanges now pay less than contracts, so contracts (main-board dice → goods → Caravanserai) are the main sink:

| City | before | now |
| --- | --- | --- |
| Trebizond | 1 spice → 2 coins + 1 VP | 1 spice → 3 coins |
| Baghdad | 1 silk → 3 VP | 1 silk → 2 VP |
| Hormuz | spice + silk → jade + 1 VP | spice + silk → jade |
| Bukhara | 1 spice → 2 VP | 1 spice → 1 VP + 1 coin |
| Samarkand | 1 jade → 5 VP | 1 jade → 3 VP |
| Kabul | 2 camels → 4 VP | 3 camels → 3 VP |
| Khotan | 1 silk → 2 coins + 2 VP | 1 silk → 2 VP |
| Dunhuang | spice + silk + jade → 9 VP | spice + silk + jade → 6 VP |

Incomes and the other city actions are unchanged.

### 9.2 Characters (current)

| key | power | numbers in `data.py` |
| --- | --- | --- |
| `cartographer` | Once per round, a journey may also found a post in one city it passes through. That post scores a flat 1 VP instead of its printed VP. | `CARTOGRAPHER_SURVEY_VP = 1`, `CARTOGRAPHER_SURVEY_COST = {}` |
| `breeder` | +2 camels each round. Camels stand in for omens (1 each) and **for missing contract goods (2 camels per good)**. | `BREEDER_INCOME`, `BREEDER_GOOD_CAMELS` |
| `seer` | +1 omen **and +1 coin** each round. Nudges cost 1 omen. **Twice** per round, set an unused die to any value. | `SEER_INCOME`, `SEER_USES = 2`, `SEER_NUDGE_COST` |
| `heiress` | Rolls 6 dice and places at most 5. +1 silk each round (unchanged). | `HEIRESS_INCOME` |
| `moneylender` | Pays half the crowd toll, **rounded up**. **No kickback.** | `MONEYLENDER_TOLL_SHARE = 0.5`, `MONEYLENDER_KICKBACK = 0` (the code path remains) |
| `guildmaster` | 3 open contracts, +1 VP per delivery, and **reaches 1 Caravanserai slot further** than the die value (a 2 can take slots 1–3). | `GUILDMASTER_REACH = 1`; `GUILDMASTER_BONUS_COINS = 0` is a tested knob that is off |
| `pathfinder` | Desert and mountain routes cost 1 fewer camel. **+4 VP on first reaching Chang'an.** | `PATHFINDER_CHANGAN_VP = 4` |
| `quartermaster` | City actions get one extra use. **+1 coin per 4 trading posts** each round (was 1 per post). | `QUARTERMASTER_POSTS_PER_COIN = 4` |

Why each one changed:
- **Moneylender:** half toll plus kickback made tolls, the core interaction, nearly free for him and profitable from rivals. With the toll halved and rounded up and no kickback, he simply pays less.
- **Quartermaster:** the extra use combined with 1 coin per post was the strongest pairing. Coins turned out to be the most valuable resource for competent players, because they pay tolls.
- **Breeder:** camels are abundant; every bot ends with 7–9 unused. The contract substitution turns surplus camels into a route to contract VP. This links the Camel Market (main board) to contracts.
- **Pathfinder:** camel discounts alone were worth little for the same reason. The Chang'an bonus makes the race east a real goal.
- **Seer:** set-any-value is strong only with several uses, and the bots barely spend omens. Two uses plus a coin landed it in band.
- **Cartographer:** in the first pass a surveyed post scored no VP. A flat 1 VP lifts the Cartographer with hard bots without bringing back the full printed VP.
- **Heiress:** unchanged. A +1 spice income was tried and pushed her to 1.25.
- **Guildmaster:** sat just under the band. A +1 coin per delivery overshot to 1.35 because coins are so valuable, so he gets reach instead: a dice-value interaction at the Caravanserai. `engine._contract_reach(p, value)` gives the highest slot a die can take.

### 9.3 Engine and API changes in this pass
- New player field `vp_sources`: `{"posts", "changan", "contracts", "cities": VP}`. It tracks in-game VP by where it came from. It is copy-on-write, so bot simulations cannot alias it.
- New `final[i].during_game_sources`: a copy of `vp_sources` at game end. The UI can show it as a breakdown of `breakdown.during_game`.
- `fulfill` for the Breeder: if goods are short, each missing good is paid with `BREEDER_GOOD_CAMELS` camels automatically. There is no new action field. Goods on hand are always used first. `engine._contract_payment(p, req)` returns the actual cost, so the UI can use it to enable the Deliver button for the Breeder.
- `seer`: the action is unchanged. The new player field `seer_uses` counts uses this round, and `seer_used` becomes true once `SEER_USES` is reached.
- Road `post_at` (Cartographer): if `CARTOGRAPHER_SURVEY_COST` is non-empty, an explicit survey the player cannot afford is rejected, and an automatic survey is silently skipped. The cost is currently empty.
- New `static_data.powers` keys:
  - `breeder_good_camels`
  - `seer_uses`
  - `cartographer_survey_cost`
  - `moneylender_toll_share`
  - `guildmaster_bonus_coins`
  - `pathfinder_changan_vp`
  - `guildmaster_reach`
  - `quartermaster_posts_per_coin`, which replaces `quartermaster_coins_per_post`. This is the one non-additive key change.
- `static_data.city_action_repeats` and `cities[*].action` reflect the new numbers.

### 9.4 UI follow-ups (not done here, because the frontend is owned by another agent)
- Character texts flow through from `static_data` automatically.
- The city "times" picker should use `city_action_repeats` (now 1/1/1/2/2/2), plus 1 for the Quartermaster.
- The Breeder's Deliver button should be enabled when camels can cover the missing goods.
- The Seer UI should allow two uses per round: show it while `!seer_used`.
- The Caravanserai should highlight slots up to the die value + 1 for the Guildmaster (`powers.guildmaster_reach`).
- Optional: show `final[i].during_game_sources` in the end screen.
