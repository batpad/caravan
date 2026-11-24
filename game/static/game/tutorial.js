// Coach marks: the guided "Learn to play" lessons and the in-game "Hint" pointer.
//
// A Coach is attached to every GameView (app.js). It renders into #overlay-root:
//   .coach-spot  a spotlight cut-out around the element to tap (dims the rest, never blocks taps)
//   .coach-ping  a pulsing "tap here" pointer ("Show me")
//   .coach-card  the parchment callout, placed beside its target so it never covers it or the
//                docked dice tray; it can be minimised to a small pill.
// Lessons are state-driven: each one knows the action it is teaching (`intent`) and checks the
// game state for completion (`done`). If the learner does something else, the lesson re-targets
// (e.g. back to the right die), offers to try again next turn, or lets them skip it.
// Progress is kept per game in localStorage. Numbers in the text come from static data.

import { api } from "./api.js";
import { h, toast } from "./dom.js";
import { dieFace, icon, pipFace, resChips } from "./icons.js";
import { canDeliver, canPay } from "./parts.js";

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const store = {
  key: (code) => `caravan:tutorial:${code}`,
  get(code) { try { return JSON.parse(localStorage.getItem(this.key(code))) || null; } catch { return null; } },
  set(code, v) { try { localStorage.setItem(this.key(code), JSON.stringify(v)); } catch { /* private mode */ } },
};

// ------------------------------------------------------------------ state helpers
const unusedOwn = (me) => me.dice.filter((d) => !d.placed && !d.white);
const unusedGuide = (me) => me.dice.find((d) => !d.placed && d.white) || null;
const placedCount = (me) => me.dice.filter((d) => d.placed && !d.rested).length;
const setEntries = (g, seat, white = false) => Object.values(g.spaces).flat()
  .filter((e) => e.seat === seat && (e.set_size || 1) >= 2 && (!white || e.white)).length;
const diceSig = (me) => me.dice.filter((d) => !d.placed).map((d) => `${d.id}:${d.value}`).join(",");

/** Unused coloured die: the preferred value if present, else lowest/highest with value ≥ min. */
function pickDie(me, { prefer = null, min = 1, mode = "high", exclude = [] } = {}) {
  const free = unusedOwn(me).filter((d) => d.value >= min && !exclude.includes(d.id));
  if (me.placements_left != null && me.placements_left <= 0) return null;
  return free.find((d) => d.value === prefer)
    || free.sort((a, b) => (mode === "low" ? a.value - b.value : b.value - a.value))[0] || null;
}

function snapshot(c) {
  const { g, me } = c;
  return {
    round: g.round, fulfilled: me.fulfilled, contracts: me.contracts.length, posts: me.posts.length,
    location: me.location, omens: me.omens, camels: me.camels, seer: !!me.seer_used, dice: diceSig(me),
    placed: placedCount(me), sets: setEntries(g, me.seat), whiteSets: setEntries(g, me.seat, true),
    guide: !!me.guide_used, passed: !!me.passed, log: g.log.length, phase: g.phase,
  };
}

// ------------------------------------------------------------------ text helpers
const P = (...kids) => h("p", {}, ...kids);
const B = (...kids) => h("b", {}, ...kids);
const ic = (name) => icon(name, { cls: "coach-ic" });
const chips = (res, empty = "nothing") => resChips(res, { empty });
const die = (c, v, white = false) => dieFace(v, c.me.color, { white, cls: "coach-die" });
const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;
const cityName = (c, id) => c.info.cities[id]?.name || id;
const routeCosts = (c) => h("span", { class: "coach-routes" }, Object.entries(c.info.route_types).map(([k, v]) =>
  h("span", { class: "coach-route" }, ic(k), v.label, " ", chips({ camels: v.camels, coins: v.coins }, "free"))));
const yieldRow = (table) => h("span", { class: "yield coach-yield" },
  table.slice(1).map((n, i) => h("span", { class: "y" }, pipFace(i + 1), h("b", {}, String(n)))));
const botSeat = (c) => c.g.players.find((p) => p.seat !== c.me.seat && c.v.bots?.[p.seat] != null)?.seat
  ?? c.g.players.find((p) => p.seat !== c.me.seat)?.seat;
const botName = (c) => c.g.players[botSeat(c)]?.name || "your rival";

/** Can I place `n` dice showing `value` on simple space `key` right now? */
function spaceOK(c, key, n, value) {
  const sp = c.info.spaces[key];
  if (!sp || n > (sp.max_dice || 1)) return false;
  const cost = Object.fromEntries(Object.entries(sp.cost || {}).map(([k, v]) => [k, v * n]));
  const toll = c.g.tolls?.[key]?.[value] || 0;
  if (toll) cost.coins = (cost.coins || 0) + toll;
  return canPay(c.me, cost);
}
const setAmount = (c, key, n, value) => c.info.spaces[key].table[value] * n + ((c.info.rules.set_bonus || [0, 0, 1, 2])[n] || 0);

/** Keep the learner's current selection if it already suits the lesson. */
function keptSelection(c, ok) {
  const pl = c.v.placing;
  return pl && ok(pl) ? pl.dice.map((d) => d.id) : null;
}
const placeAct = (ids, space, extra = {}) => (ids.length === 1 ? { type: "place", die: ids[0], space, ...extra } : { type: "place", dice: ids, space, ...extra });

// ------------------------------------------------------------------ action -> what to tap
/** Where to tap next to perform `a`. Returns {sel, say} or null. */
export function nextTap(a, c) {
  if (!a) return null;
  const v = c.v, me = c.me;
  const dieSel = (id) => `#tray-dice [data-die="${id}"]`;
  const dieVal = (id) => me?.dice.find((d) => d.id === id)?.value;
  switch (a.type) {
    case "choose_character":
      return { sel: `.char-card[data-character="${a.character}"]`, say: c.v.coach?.tutorialActive ? "Tap a merchant card" : `Tap ${c.info.characters[a.character]?.name || "a character"}` };
    case "place": {
      const ids = a.dice || [a.die];
      const extra = v.sel.filter((id) => !ids.includes(id));
      const missing = ids.find((id) => !v.sel.includes(id));
      // Tapping a die of another value restarts the selection by itself; only a same-value
      // extra die would wrongly join the set, so then clear first.
      const want = me.dice.find((x) => x.id === missing);
      const clash = extra.some((id) => { const x = me.dice.find((y) => y.id === id); return !want || x?.white || want.white || x?.value === want.value; });
      if (extra.length && v.canPlace && clash) return { sel: "#die-tools [data-tool='clear']", say: "Clear your selection first" };
      if (missing != null) {
        const d = me.dice.find((x) => x.id === missing);
        const say = d?.white ? "Tap the white guide die" : v.sel.length ? `Now tap your other ${dieVal(missing)}` : `Tap your ${dieVal(missing)}`;
        return { sel: dieSel(missing), say };
      }
      const sp = c.info.spaces[a.space];
      if (a.space === "caravanserai") return { sel: `#market [data-slot="${a.slot + 1}"] .take-btn`, say: `Tap “Take” on contract ${a.slot + 1}` };
      if (a.space === "road") return { sel: `#map-panel .city[data-city="${a.path[a.path.length - 1]}"]`, say: `Tap ${cityName(c, a.path[a.path.length - 1])} on the map` };
      if (a.space === "city") {
        return document.querySelector(`#city-charters button[data-city="${a.city}"]`)
          ? { sel: `#city-charters button[data-city="${a.city}"]`, say: `Tap ${cityName(c, a.city)} under “Your city actions”` }
          : { sel: `#map-panel .city[data-city="${a.city}"]`, say: `Tap ${cityName(c, a.city)}` };
      }
      return { sel: `#bazaar [data-space="${a.space}"]`, say: `Tap the ${sp?.name || a.space}` };
    }
    case "fulfill": return { sel: `#my-contracts > .contract:nth-child(${a.index + 1}) .deliver-btn`, say: "Tap Deliver" };
    case "reroll": case "nudge": case "seer": {
      if (v.selDie?.id !== a.die) return { sel: dieSel(a.die), say: `Tap your ${dieVal(a.die)}` };
      const tool = a.type === "reroll" ? "reroll" : a.type === "seer" ? "seer" : a.delta > 0 ? "up" : "down";
      const say = a.type === "reroll" ? "Tap Reroll" : a.type === "seer" ? `Tap Seer, then the ${a.value}` : `Tap ${a.delta > 0 ? "+1" : "−1"}`;
      return { sel: `#die-tools [data-tool='${tool}']`, say };
    }
    case "hire_guide": return { sel: "#turn-buttons .guide-btn", say: "Tap Hire guide" };
    case "rest": case "pass": return { sel: "#turn-buttons .rest-btn", say: "Tap Rest" };
    case "end_turn": return { sel: "#turn-buttons .end-btn", say: "Tap End turn" };
    default: return null;
  }
}

/** One-line description of an action (for hints). */
export function describe(a, c) {
  if (!a) return "";
  const me = c.me, info = c.info;
  const val = (id) => me.dice.find((d) => d.id === id)?.value;
  switch (a.type) {
    case "choose_character": return `Travel as ${info.characters[a.character]?.name}.`;
    case "place": {
      const ids = a.dice || [a.die];
      const vals = ids.map(val);
      const what = ids.length > 1 ? `a set of ${ids.length} (${vals.join(" + ")})` : `your ${vals[0]}`;
      if (a.space === "road") return `Travel with ${what} to ${cityName(c, a.path[a.path.length - 1])}.`;
      if (a.space === "city") return `Use ${what} for the ${cityName(c, a.city)} city action${a.times ? ` ×${a.times}` : ""}.`;
      if (a.space === "caravanserai") return `Place ${what} on the Caravanserai and take contract ${a.slot + 1}.`;
      return `Place ${what} on the ${info.spaces[a.space]?.name}.`;
    }
    case "fulfill": return "Deliver a contract — you have the goods.";
    case "reroll": return `Reroll your ${val(a.die)} with an omen.`;
    case "nudge": return `Turn your ${val(a.die)} into a ${val(a.die) + a.delta}.`;
    case "seer": return `Use the Seer's sight: turn your ${val(a.die)} into a ${a.value}.`;
    case "hire_guide": return `Hire a guide die (${info.rules.guide_cost} coins).`;
    case "rest": case "pass": return "Rest for the round and take coins for your unused dice.";
    case "end_turn": return "End your turn.";
    default: return "";
  }
}

// ------------------------------------------------------------------ lessons
const turnReady = (c) => c.g.phase === "play" && c.myTurn;
const placeReady = (c) => c.g.phase === "play" && c.v.canPlace;

function endTurnStep(id, round, title, body) {
  return {
    id, round, kind: "do", title,
    body: (c) => body ? body(c) : [P("You may only place once per turn. When you are done with free actions, end your turn so the next merchant can play.")],
    ready: (c) => c.myTurn && c.g.turn_placed,
    intent: () => ({ type: "end_turn" }),
    done: (c) => !(c.myTurn && c.g.turn_placed),
  };
}

function watchStep(id, round, title, body) {
  return {
    id, round, kind: "watch", title,
    body: (c) => {
      const seat = botSeat(c);
      const fresh = c.g.log.slice(Math.min(c.base.log, c.g.log.length)).filter((e) => e.seat === seat && !/ rolls \[/.test(e.text));
      const lines = fresh.slice(-3);
      return [
        body ? body(c) : P(`${botName(c)} is an AI merchant. It waits a moment before moving so you can follow along.`),
        lines.length ? h("ul", { class: "coach-log" }, lines.map((e) => h("li", {}, e.text)))
          : h("p", { class: "coach-wait" }, ic("hourglass"), `Waiting for ${botName(c)}…`),
      ];
    },
    target: () => "#turn-pill",
    // The lesson continues once it's the learner's move again (or the round/game moved on).
    canNext: (c) => (c.myTurn && !c.g.turn_placed) || c.g.round !== c.base.round || c.g.phase !== "play",
    done: () => false,
  };
}

function buildSteps() {
  return [
    // ---------------------------------------------------------------- setup
    {
      id: "welcome", kind: "info", title: "Welcome, merchant",
      body: (c) => [
        P("This is a real game of ", B("Caravan Road"), " against ", B(botName(c)), ", a gentle AI merchant. Each lesson points at what to tap — you do the moves."),
        P("Use ", B("Show me"), " when you're unsure, ", ic("minus"), " to fold this card away, and ", B("Skip"), " to play on your own at any time."),
      ],
    },
    {
      id: "character", kind: "do", title: "Choose your merchant",
      ready: (c) => c.g.phase === "setup" && !c.me.character,
      body: () => [
        P("Every merchant has a special power. Read the two cards and ", B("tap the one you like"), " — either is a fine first choice."),
        P("Below them are your ", B("secret commissions"), ": pairs of cities. Trading posts there score renown at the end, and only you can see them."),
      ],
      target: () => "#setup .char-choices",
      intent: (c) => (c.me.character_choices?.length ? { type: "choose_character", character: c.me.character_choices[0] } : null),
      done: (c) => !!c.me.character,
      avoid: () => "#setup .char-choices",
    },
    // ---------------------------------------------------------------- tour
    {
      id: "map", kind: "info", round: 1, title: "The Silk Road",
      when: (c) => c.g.phase === "play",
      target: () => "#map-panel",
      body: (c) => [
        P("Your caravan starts in ", B("Constantinople"), ". Each journey on The Road moves it along routes, paying for each route it crosses:"),
        routeCosts(c),
        P("Where a journey ends you found a ", ic("post"), B(" trading post"), " worth the renown ", ic("vp"), " printed on the city. Reaching ",
          B("Chang'an"), ` scores ${c.info.end_city_order_vp.join(" / ")} by arrival order.`),
      ],
    },
    {
      id: "ledger", kind: "info", round: 1, title: "Your ledger",
      when: (c) => c.g.phase === "play",
      target: () => "#player-board",
      body: (c) => [
        P("Your goods: ", ic("coins"), " coins, ", ic("camels"), " camels, ", ic("spice"), " spice, ", ic("silk"), " silk, ", ic("jade"), " jade and ", ic("omens"), " omens. ",
          "Renown ", ic("vp"), " is your score."),
        P("Below are your open contracts (none yet) and your secret commissions — ",
          c.me.commissions.filter((x) => x != null).map((ci) => c.info.commissions[ci].map((x) => cityName(c, x)).join(" & ")).join("; "), "."),
      ],
    },
    {
      id: "dice", kind: "info", round: 1, title: "Your dice",
      when: (c) => c.g.phase === "play",
      target: () => "#tray-dice",
      body: (c) => [
        P("You rolled ", h("span", { class: "coach-dice" }, unusedOwn(c.me).map((d) => die(c, d.value))), " for this round."),
        P("On each turn you place ", B("one"), " die (or a set of equal dice) on a space. A high value earns more. When your dice are gone, you're done for the round."),
      ],
    },
    {
      id: "bazaar", kind: "info", round: 1, title: "The Bazaar",
      when: (c) => c.g.phase === "play",
      target: () => "#bazaar",
      body: (c) => [
        P("Each stall shows what it pays for each die value. The ", B("Spice Stall"), ":"),
        yieldRow(c.info.spaces.bazaar_spice.table),
        P("So a 6 earns ", B(String(c.info.spaces.bazaar_spice.table[6])), " spice and a 1 earns ", B(String(c.info.spaces.bazaar_spice.table[1])), "."),
      ],
    },
    // ---------------------------------------------------------------- round 1
    {
      id: "spice", kind: "do", round: 1, placement: true, title: "Place a die",
      ready: placeReady,
      intent: (c) => {
        const keep = keptSelection(c, (pl) => spaceOK(c, "bazaar_spice", pl.n, pl.value));
        const d = keep ? null : pickDie(c.me, { prefer: 5 });
        return keep || d ? placeAct(keep || [d.id], "bazaar_spice") : null;
      },
      body: (c) => {
        const d = c.intent ? c.me.dice.find((x) => x.id === (c.intent.die ?? c.intent.dice?.[0])) : null;
        const n = c.intent?.dice?.length || 1;
        return [
          P("Let's buy spice. Tap your ", d ? die(c, d.value) : "die", " and then the ", B("Spice Stall"), "."),
          d ? P(n > 1 ? `That set` : `A ${d.value}`, " earns ", B(String(setAmount(c, "bazaar_spice", n, d.value))), " ", ic("spice"), ".") : null,
        ];
      },
      done: (c) => c.g.spaces.bazaar_spice.some((e) => e.seat === c.me.seat),
      showMe: true,
    },
    endTurnStep("end1", 1, "End your turn", (c) => [
      P("Nice — ", ic("spice"), " spice is in your ledger. You get ", B("one placement"), " per turn; free actions (like delivering contracts) can come before or after it."),
      P("Now end your turn."),
    ]),
    watchStep("watch1", 1, `Your rival's turn`),
    {
      id: "contract", kind: "do", round: 1, placement: true, title: "Take a contract",
      ready: placeReady,
      intent: (c) => {
        const m = c.g.contract_market;
        if (!m.length || !spaceOK(c, "caravanserai", 1, 1)) return null;
        const free = unusedOwn(c.me);
        const top = Math.max(0, ...free.map((d) => d.value));
        let slot = m.findIndex((cid, i) => i + 1 <= top && canPay(c.me, c.info.contracts[cid].req));
        if (slot < 0) slot = 0;
        const keep = keptSelection(c, (pl) => pl.n === 1 && pl.value >= slot + 1);
        const d = keep ? null : pickDie(c.me, { prefer: 3, min: slot + 1, mode: "low" });
        return keep || d ? placeAct(keep || [d.id], "caravanserai", { slot }) : null;
      },
      body: (c) => {
        const a = c.intent;
        const cid = a ? c.g.contract_market[a.slot] : null;
        const k = cid != null ? c.info.contracts[cid] : null;
        const d = a ? c.me.dice.find((x) => x.id === a.die) : null;
        return [
          P("Contracts are bought at the ", B("Caravanserai"), ". A die takes any contract from slot 1 up to its value",
            d ? [" — your ", die(c, d.value), ` reaches slots 1–${Math.min(d.value, c.g.contract_market.length)}`] : null, "."),
          k ? P(`Contract ${a.slot + 1} asks for `, chips(k.req), " and pays ", B(`${k.vp}`), " ", ic("vp"),
            Object.keys(k.bonus || {}).length ? [" plus ", chips(k.bonus)] : null,
            canPay(c.me, k.req) ? ". You already have the goods!" : ".") : null,
        ];
      },
      done: (c) => c.me.contracts.length > c.base.contracts || c.me.fulfilled > c.base.fulfilled,
    },
    {
      id: "deliver", kind: "do", round: 1, title: "Deliver it",
      ready: turnReady,
      intent: (c) => {
        const i = c.me.contracts.findIndex((cid) => canDeliver(c.me, c.info.contracts[cid].req, c.info));
        return i >= 0 ? { type: "fulfill", index: i } : null;
      },
      unavailable: (c) => (c.me.contracts.length ? "You don't have the goods for your contract yet — gather them and tap Deliver on a later turn." : "You have no open contract to deliver right now."),
      body: () => [
        P("Delivering is a ", B("free action"), ": any time on your turn, pay the goods shown and earn the renown on the wax seal (and any bonus)."),
      ],
      done: (c) => c.me.fulfilled > c.base.fulfilled,
    },
    endTurnStep("end2", 1, "End your turn"),
    watchStep("watch2", 1, "Watch the road", (c) => P(`${botName(c)} moves next. Keep an eye on The Road.`)),
    {
      id: "travel", kind: "do", round: 1, placement: true, title: "Travel and found a post",
      ready: placeReady,
      intent: (c) => {
        const want = "antioch";
        const has = (pl) => pl.n === 1 && (c.g.travel?.[String(pl.value)] || []).some((o) => o.dest === want);
        const keep = keptSelection(c, has);
        let d = null;
        if (!keep) {
          d = [pickDie(c.me, { prefer: 1, mode: "low" }), ...unusedOwn(c.me).sort((x, y) => x.value - y.value)]
            .find((x) => x && (c.g.travel?.[String(x.value)] || []).some((o) => o.dest === want));
        }
        if (!keep && !d) return null;
        const v = keep ? c.v.placing.value : d.value;
        const opt = (c.g.travel[String(v)] || []).find((o) => o.dest === want);
        return placeAct(keep || [d.id], "road", { path: opt.path });
      },
      unavailable: () => "No die can reach Antioch right now (you may be short of camels). Skip this lesson — you can travel later.",
      body: (c) => {
        const a = c.intent;
        const v = a ? c.me.dice.find((x) => x.id === (a.die ?? a.dice?.[0]))?.value : null;
        const ant = c.info.cities.antioch;
        const toll = v ? c.g.tolls?.road?.[v] || 0 : 0;
        const crowded = c.v.crowded("road");
        return [
          P("The Road moves your caravan: steps by die value ", yieldRow(c.info.spaces.road.table), "."),
          P("Antioch is one road step away. Ending there founds a ", ic("post"), " post worth ", B(`${ant.post_vp}`), " ", ic("vp"),
            ", paying ", chips(ant.income), " every round — and it's on a secret commission!"),
          crowded ? P(ic("coins"), B(" Toll! "), `${botName(c)} is already on The Road, so it's crowded: you pay ${c.info.rules.toll_per_pip ?? 1} coin per pip. `,
            v ? ["Your ", die(c, v), ` costs ${plural(toll, "coin")} — low dice are cheap on crowded spaces.`] : null)
            : P(ic("coins"), " If a rival already had a die here you'd pay a toll of 1 coin per pip of your die."),
        ];
      },
      done: (c) => c.me.location !== c.base.location || c.me.posts.length > c.base.posts,
      showMe: true,
    },
    endTurnStep("end3", 1, "End your turn", (c) => [
      P(ic("post"), " Your first trading post! It counts towards your commission and the end-game post majority."),
      P("End your turn."),
    ]),
    watchStep("watch3", 1, "Your rival's turn"),
    {
      id: "city", kind: "do", round: 1, placement: true, title: "Use a city action",
      ready: placeReady,
      intent: (c) => {
        const city = c.me.posts.find((x) => c.info.cities[x]?.action && !c.g.city_spaces[x] && canPay(c.me, c.info.cities[x].action.pay));
        if (!city) return null;
        const keep = keptSelection(c, (pl) => pl.n === 1);
        const d = keep ? null : pickDie(c.me, { prefer: 4 });
        return keep || d ? placeAct(keep || [d.id], "city", { city }) : null;
      },
      unavailable: () => "No city action is available to you right now (you need a post there, the goods it asks for, and nobody else using it this round).",
      body: (c) => {
        const a = c.intent;
        const city = a ? c.info.cities[a.city] : null;
        const v = a ? c.me.dice.find((x) => x.id === a.die)?.value : null;
        const uses = v ? c.v.cityUses(v) : null;
        return [
          P("A post lets you use that city's ", B("action"), city ? [": in ", B(city.name), " pay ", chips(city.action.pay, "nothing"), " → gain ", chips(city.action.gain), "."] : "."),
          P("Place one die there to repeat it ", [1, 2, 3, 4, 5, 6].map((x) => c.v.cityUses(x)).join("/"), " times by value",
            v ? [" — your ", die(c, v), ` allows up to ${uses}`] : null, ". You'll choose how many. Only one merchant per round can use each city."),
        ];
      },
      done: (c) => Object.values(c.g.city_spaces).some((e) => e && e.seat === c.me.seat),
    },
    endTurnStep("end4", 1, "End your turn"),
    watchStep("watch4", 1, "Your rival's turn"),
    {
      id: "shrine", kind: "do", round: 1, placement: true, title: "Visit the Shrine",
      ready: placeReady,
      intent: (c) => {
        const keep = keptSelection(c, (pl) => pl.n === 1 && spaceOK(c, "temple", 1, pl.value));
        const d = keep ? null : unusedOwn(c.me).sort((x, y) => x.value - y.value).find((x) => spaceOK(c, "temple", 1, x.value));
        return keep || d ? placeAct(keep || [d.id], "temple") : null;
      },
      unavailable: () => "You can't use the Shrine right now. Skip this lesson.",
      body: (c) => [
        P("The ", B("Shrine"), " pays ", ic("omens"), " omens ", yieldRow(c.info.spaces.temple.table), "."),
        c.g.temple_claim == null
          ? P(ic("lead"), " The first merchant here each round ", B("leads the next round"), " — they take the first turn.")
          : P(ic("lead"), ` ${c.g.players[c.g.temple_claim].name} got here first and will lead next round, but omens are still worth having.`),
      ],
      done: (c) => c.g.spaces.temple.some((e) => e.seat === c.me.seat),
    },
    endTurnStep("end5", 1, "End your turn"),
    {
      id: "roundend", kind: "wait", round: 1, title: "End of the round",
      body: (c) => (c.myTurn
        ? [P("You still have dice. Place them, or ", B("Rest"), " to finish your round. (Tap ", B("Show me"), " for a suggestion.)")]
        : [P(`${botName(c)} plays out its remaining dice. When every merchant is done, the round ends and a new one begins.`)]),
      target: (c) => (c.myTurn ? "#tray-dice" : "#turn-pill"),
      done: (c) => c.g.round > c.base.round || c.g.phase !== "play",
    },
    // ---------------------------------------------------------------- round 2
    {
      id: "income", kind: "info", round: 2, title: "A new round: income",
      when: (c) => c.g.phase === "play" && c.g.round >= 2,
      target: () => "#player-board",
      body: (c) => {
        const inc = {};
        for (const x of c.me.posts) for (const [k, n] of Object.entries(c.info.cities[x].income || {})) inc[k] = (inc[k] || 0) + n;
        return [
          P("Each round starts with ", B("income"), ": every post pays its city's goods", Object.keys(inc).length ? [" — you collected ", chips(inc)] : "",
            ", plus any bonus from your merchant's power. Then everyone rolls fresh dice."),
          P(`The ${plural(c.info.rules.contract_churn, "oldest contract")} also left the market. `,
            c.g.start_player === c.me.seat ? [ic("lead"), " You visited the Shrine first, so you lead this round."] : `${c.g.players[c.g.start_player].name} leads this round.`),
          P(`The game lasts ${c.info.num_rounds} rounds.`),
        ];
      },
    },
    {
      id: "pair", kind: "do", round: 2, placement: true, title: "Make a pair",
      ready: placeReady,
      intent: (c) => {
        const by = {};
        for (const d of unusedOwn(c.me)) (by[d.value] ||= []).push(d);
        const vals = Object.keys(by).map(Number).filter((v) => by[v].length >= 2).sort((a, b) => (a === 2 ? -1 : b === 2 ? 1 : b - a));
        for (const v of vals) {
          for (const key of ["treasury", "bazaar_spice", "camels", "bazaar_silk", "road"]) {
            if (key === "road") continue;
            if (spaceOK(c, key, 2, v)) return placeAct(by[v].slice(0, 2).map((d) => d.id), key);
          }
        }
        return null;
      },
      unavailable: () => "You have no two dice showing the same value right now. A guide die or omens can make one — more on those next.",
      body: (c) => {
        const a = c.intent;
        const v = a ? c.me.dice.find((x) => x.id === a.dice[0])?.value : null;
        const bonus = c.info.rules.set_bonus || [0, 0, 1, 2];
        return [
          P("Dice showing the same value can go out together as a ", B("set"), " — still just one placement. A set earns the amount for each die, plus ",
            `+${bonus[2]} for a pair or +${bonus[3]} for a triple.`),
          a ? P("Tap both ", die(c, v), die(c, v), " then the ", B(c.info.spaces[a.space].name), ": ",
            `${c.info.spaces[a.space].table[v]} × 2 + ${bonus[2]} = `, B(String(setAmount(c, a.space, 2, v))), " ", ic(c.info.spaces[a.space].gain), ".") : null,
        ];
      },
      done: (c) => setEntries(c.g, c.me.seat) > c.base.sets,
      showMe: true,
    },
    endTurnStep("end6", 2, "End your turn"),
    watchStep("watch6", 2, "Your rival's turn"),
    {
      id: "guide", kind: "do", round: 2, title: "Hire a guide",
      ready: placeReady,
      intent: (c) => (!c.me.guide_used && c.g.guide_pool > 0 && c.me.coins >= c.info.rules.guide_cost ? { type: "hire_guide" } : null),
      unavailable: (c) => (c.me.guide_used ? "You already hired a guide this round." : c.g.guide_pool <= 0 ? "No guides are left this round."
        : `A guide costs ${c.info.rules.guide_cost} coins and you have ${c.me.coins}. Skip this lesson for now.`),
      body: (c) => [
        P("A ", ic("guide"), B(" guide"), ` is an extra white die for ${c.info.rules.guide_cost} coins (one per merchant per round, ${c.info.rules.guide_dice} for the whole table).`),
        P("Its trick: it's ", B("wild"), " in a set — it matches any value."),
      ],
      done: (c) => !!c.me.guide_used,
    },
    {
      id: "guideset", kind: "do", round: 2, placement: true, title: "A wild pair",
      ready: placeReady,
      intent: (c) => {
        const g = unusedGuide(c.me);
        const d = pickDie(c.me, { prefer: 6 });
        if (!g || !d) return null;
        for (const key of ["bazaar_silk", "bazaar_spice", "camels", "treasury"]) {
          if (spaceOK(c, key, 2, d.value)) return placeAct([d.id, g.id], key);
        }
        return null;
      },
      unavailable: () => "You have no guide die to pair. Skip this lesson.",
      body: (c) => {
        const a = c.intent;
        const v = a ? c.me.dice.find((x) => x.id === a.dice[0])?.value : null;
        const gv = unusedGuide(c.me)?.value;
        return [
          P("Pair your ", v ? die(c, v) : "die", " with the white guide", gv ? [" (it shows ", die(c, gv, true), ", but counts as a ", B(String(v)), ")"] : "", "."),
          a ? P("On the ", B(c.info.spaces[a.space].name), " that pair earns ", B(String(setAmount(c, a.space, 2, v))), " ", ic(c.info.spaces[a.space].gain),
            " — or pick any glowing stall.") : null,
        ];
      },
      done: (c) => setEntries(c.g, c.me.seat, true) > c.base.whiteSets,
      showMe: true,
    },
    endTurnStep("end7", 2, "End your turn"),
    watchStep("watch7", 2, "Your rival's turn"),
    {
      id: "omens", kind: "do", round: 2, title: "Bend fate with omens",
      ready: placeReady,
      intent: (c) => {
        const d = pickDie(c.me, { prefer: 3 });
        if (!d) return null;
        const costs = c.g.costs || { reroll: c.info.rules.reroll_cost, nudge: c.info.rules.nudge_cost };
        const pool = c.me.omens + (c.me.character === "breeder" ? c.me.camels : 0);
        if (pool >= costs.nudge) return { type: "nudge", die: d.id, delta: d.value < 6 ? 1 : -1 };
        if (pool >= costs.reroll) return { type: "reroll", die: d.id };
        if (c.me.character === "seer" && !c.me.seer_used) return { type: "seer", die: d.id, value: 6 };
        return null;
      },
      unavailable: () => "You have no omens to spend (the Shrine pays them). Skip this lesson.",
      body: (c) => {
        const costs = c.g.costs || { reroll: c.info.rules.reroll_cost, nudge: c.info.rules.nudge_cost };
        return [
          P("Before placing, you can spend ", ic("omens"), " omens on a die: select it, then use the tools beside your dice."),
          h("ul", { class: "coach-list" },
            h("li", {}, ic("reroll"), B(" Reroll"), ` — ${plural(costs.reroll, "omen")}, a fresh random value`),
            h("li", {}, ic("plus"), B(" ±1"), ` — ${plural(costs.nudge, "omen")}, change it by one`),
            c.me.character === "seer" ? h("li", {}, ic("omens"), B(" Seer"), " — your power: set it to any face, for free") : null,
            c.me.character === "breeder" ? h("li", {}, ic("camels"), " As the Camel Breeder you may pay camels instead of omens.") : null),
        ];
      },
      done: (c) => c.me.omens < c.base.omens || c.me.camels < c.base.camels || (!!c.me.seer_used && !c.base.seer) || diceSig(c.me) !== c.base.dice,
      showMe: true,
    },
    {
      id: "placeany", kind: "do", round: 2, placement: true, title: "Your choice",
      ready: placeReady,
      body: () => [P("Now place a die wherever you like — it's your caravan. Unsure? Tap ", B("Show me"), " and the AI will suggest a move.")],
      target: () => "#tray-dice",
      done: (c) => placedCount(c.me) > c.base.placed,
    },
    endTurnStep("end8", 2, "End your turn"),
    watchStep("watch8", 2, "Your rival's turn"),
    {
      id: "rest", kind: "do", round: 2, title: "Rest",
      ready: turnReady,
      intent: () => ({ type: "rest" }),
      body: (c) => [
        P(ic("tent"), " ", B("Resting"), ` ends your round early: take ${c.info.rules.rest_coins_per_die ?? 1} coin for each die you could still place. `,
          "It's handy when your last dice are weak or every space is crowded."),
        P("Tap Rest — you'll be asked to confirm."),
      ],
      done: (c) => !!c.me.passed || c.g.round > c.base.round,
    },
    {
      id: "scoring", kind: "info", title: "How the game is won",
      target: () => "#player-board",
      body: (c) => {
        const r = c.info.rules;
        return [
          P(`After ${c.info.num_rounds} rounds, add to the renown you earned during play:`),
          h("ul", { class: "coach-list" },
            h("li", {}, ic("seal"), ` Commissions: ${r.commission_both} for posts in both cities, ${r.commission_one} for one`),
            h("li", {}, ic("post"), ` Most trading posts: ${r.post_majority[0]}`),
            h("li", {}, ic("scroll"), ` Most contracts delivered: ${r.contract_majority}`),
            h("li", {}, ic("coins"), ` 1 per ${r.coins_per_vp} coins and per ${r.goods_per_vp} goods left over`)),
          P("Heading east pays: cities further along are worth more, and so is reaching Chang'an early."),
        ];
      },
    },
    {
      id: "finale", kind: "info", title: "You know the road",
      body: (c) => [
        P(c.g.phase === "finished" ? "The game is over — see the final ledger above." : `The rest of this game is yours. Keep playing against ${botName(c)}.`),
        P("Tap ", ic("compass"), B(" Hint"), " in the top bar for the AI's suggestion, or ", ic("scroll"), B(" Rules"), " for the full reference."),
      ],
      nextLabel: "Play on",
    },
  ];
}

// ------------------------------------------------------------------ the coach
export class Coach {
  constructor(view, { tutorial = false } = {}) {
    this.view = view;
    this.code = view.code;
    this.tutorial = tutorial;
    this.steps = buildSteps();
    const saved = store.get(this.code) || {};
    this.i = Math.min(saved.i || 0, this.steps.length);
    this.base = saved.base || null;
    this.skipped = !!saved.skipped;
    this.minimized = !!saved.minimized;
    this.showMe = false;
    this.hintAct = null;
    this.renderedKey = null;
    this.lastTargetSel = null;
    view.coach = this;
    view.onRender = () => this.sync();
    this.root = document.getElementById("overlay-root");
    this.layer = h("div", { class: "coach-layer" });
    this.root.replaceChildren(this.layer);
    this.queued = false;
    const relayout = () => this.queueLayout();
    window.addEventListener("resize", relayout, { passive: true });
    window.addEventListener("scroll", relayout, { passive: true });
    window.visualViewport?.addEventListener("resize", relayout, { passive: true });
    this.mo = new MutationObserver(() => this.sync());
    this.mo.observe(document.getElementById("modal-root"), { childList: true });
    this.cleanup = () => {
      window.removeEventListener("resize", relayout);
      window.removeEventListener("scroll", relayout);
      window.visualViewport?.removeEventListener("resize", relayout);
      this.mo.disconnect();
    };
  }

  destroy() {
    this.cleanup();
    this.layer.remove();
  }

  get tutorialActive() {
    return this.tutorial && !this.skipped && this.i < this.steps.length;
  }

  save() {
    store.set(this.code, { i: this.i, base: this.base, skipped: this.skipped, minimized: this.minimized });
  }

  ctx() {
    const v = this.view;
    const c = { v, g: v.game, me: v.me, info: v.info, myTurn: v.myTurn, base: this.base };
    return c;
  }

  /** Topbar button: resume the lessons in a tutorial game. */
  statusButton() {
    if (!this.tutorial || !this.view.me) return null;
    if (this.tutorialActive && !this.minimized) return null;
    const label = this.i >= this.steps.length ? "Lessons done" : this.skipped ? "Resume lessons" : "Lessons";
    if (this.i >= this.steps.length) return null;
    return h("button", { class: "btn ghost key-btn lessons-btn", id: "lessons-btn", onclick: () => {
      this.skipped = false; this.minimized = false; this.save(); this.view.renderStatus(); this.sync();
    } }, icon("compass"), h("span", {}, label));
  }

  showHint(action) {
    this.hintAct = action;
    this.hintVersion = this.view.data.version;
    this.showMe = true;
    this.minimized = false;
    this.renderedKey = null;
    this.lastTargetSel = null;
    this.sync();
  }

  // ---------------------------------------------------------------- step machine
  enter(i) {
    this.i = i;
    this.showMe = false;
    this.base = this.view.me ? snapshot(this.ctx()) : null;
    this.renderedKey = null;
    this.lastTargetSel = null;
    this.save();
  }

  advance() { this.enter(this.i + 1); }

  /** The previous info lesson that would still apply now (or -1). */
  backTarget() {
    const g = this.view.game;
    let j = this.i - 1;
    while (j >= 0 && (this.steps[j].kind !== "info" || (this.steps[j].round && g.round > this.steps[j].round))) j -= 1;
    if (j < 0 || this.i - j > 1 && this.steps.slice(j + 1, this.i).some((s) => s.kind !== "info")) return -1;
    return j;
  }

  back() {
    const j = this.backTarget();
    if (j >= 0) { this.enter(j); this.sync(); }
  }

  skipAll() {
    this.skipped = true;
    this.save();
    this.view.renderStatus();
    this.sync();
    toast("Lessons hidden — tap “Resume lessons” in the top bar to continue.", "ok");
  }

  /** Move past finished / stale lessons. */
  settle() {
    const c0 = this.ctx();
    if (!this.base && c0.me) this.enter(this.i);
    for (let guard = 0; guard < 80 && this.i < this.steps.length; guard += 1) {
      const st = this.steps[this.i];
      const c = this.ctx();
      if (c.g.phase === "finished" && st.id !== "finale") { this.enter(this.steps.findIndex((x) => x.id === "finale")); continue; }
      if (st.round && c.g.phase !== "setup" && c.g.round > st.round) { this.advance(); continue; }
      if (st.id === "character" && c.me.character) { this.advance(); continue; }
      if (st.kind !== "info" && st.kind !== "watch" && st.done(c)) { this.advance(); continue; }
      break;
    }
  }

  sync() {
    if (this.syncQueued) return;
    this.syncQueued = true;
    requestAnimationFrame(() => { this.syncQueued = false; this.doSync(); });
  }

  doSync() {
    const v = this.view;
    if (!v.game || !v.me) { this.layer.replaceChildren(); return; }
    if (this.hintAct && v.data.version !== this.hintVersion) { this.hintAct = null; this.showMe = false; }
    if (this.tutorialActive) this.settle();
    const modalOpen = document.getElementById("modal-root").childElementCount > 0;
    this.layer.classList.toggle("hidden", modalOpen);
    let model = null;
    if (this.hintAct) model = this.hintModel();
    else if (this.tutorialActive) model = this.stepModel();
    if (!model) { this.layer.replaceChildren(); this.renderedKey = null; return; }
    this.model = model;
    if (this.minimized && !this.hintAct) model = { ...model, minimized: true };
    const key = JSON.stringify([model.key, model.minimized, this.showMe, model.targetSel, model.tapSel, model.textKey]);
    if (key !== this.renderedKey) {
      this.renderedKey = key;
      this.build(model);
      if (model.scrollSel && model.scrollSel !== this.lastTargetSel) {
        this.lastTargetSel = model.scrollSel;
        this.reveal(model.scrollSel);
      }
    }
    this.layout();
  }

  hintModel() {
    const c = this.ctx();
    const tap = nextTap(this.hintAct, c);
    return {
      key: `hint:${JSON.stringify(this.hintAct)}`, kind: "hint", eyebrow: "Hint", title: "Try this",
      body: [P(describe(this.hintAct, c))], say: tap?.say, targetSel: tap?.sel, tapSel: tap?.sel, dim: 0.28,
      scrollSel: tap?.sel, textKey: tap?.say,
      buttons: [{ label: "Got it", primary: true, on: () => { this.hintAct = null; this.showMe = false; this.sync(); } }],
    };
  }

  stepModel() {
    const st = this.steps[this.i];
    const c = this.ctx();
    const total = this.steps.length;
    const eyebrow = `Lesson ${this.i + 1} of ${total}`;
    const nextBtn = (label = "Next") => ({ label, primary: true, on: () => { this.advance(); this.sync(); } });
    const backBtn = st.kind === "info" && this.backTarget() >= 0 ? { label: "Back", on: () => this.back() } : null;
    const base = { key: `${st.id}:${this.i}`, kind: st.kind, eyebrow, title: st.title };
    let body, buttons = [], targetSel = null, tapSel = null, say = null, dim = 0, note = null;

    if (st.kind === "info") {
      if (st.when && !st.when(c)) {
        body = [P("Waiting for the game to continue…")];
      } else {
        body = st.body(c);
        targetSel = st.target?.(c) || null;
        dim = targetSel ? 0.5 : 0.35;
        buttons = [backBtn, nextBtn(st.nextLabel || (this.i === total - 1 ? "Finish" : "Next"))];
        if (this.i === total - 1) buttons[1].on = () => { this.advance(); this.view.renderStatus(); this.sync(); };
      }
    } else if (st.kind === "watch") {
      body = st.body(c);
      targetSel = st.target(c);
      const ok = st.canNext(c);
      buttons = [ok ? nextBtn("Continue") : null];
      note = ok ? { icon: "check", text: "Your turn again." } : null;
    } else if (st.kind === "wait") {
      body = st.body(c);
      targetSel = st.target?.(c) || null;
      if (c.myTurn) buttons = [{ label: "Show me", on: () => this.fetchHint() }];
    } else { // do
      const ready = st.ready ? st.ready(c) : true;
      c.intent = st.intent ? st.intent(c) : null;
      if (!ready) {
        if (st.placement && c.myTurn && c.g.turn_placed) {
          body = [P("You placed somewhere else this turn — that's fine, it's your game! End your turn and we'll try this on your next turn.")];
          tapSel = targetSel = "#turn-buttons .end-btn";
          say = "Tap End turn";
          buttons = [{ label: "Skip this lesson", on: () => { this.advance(); this.sync(); } }];
          dim = 0.25;
        } else if (c.g.phase === "play" && !c.myTurn) {
          body = [P(`Waiting for ${c.g.players[c.g.current].name} to finish…`)];
          targetSel = "#turn-pill";
          buttons = [{ label: "Skip this lesson", on: () => { this.advance(); this.sync(); } }];
        } else {
          body = [P(st.unavailable ? st.unavailable(c) : "This lesson isn't possible right now.")];
          buttons = [nextBtn("Skip this lesson")];
        }
      } else if (st.intent && !c.intent) {
        body = [P(st.unavailable ? st.unavailable(c) : "This lesson isn't possible right now.")];
        buttons = [nextBtn("Skip this lesson")];
      } else {
        body = st.body(c);
        const tap = c.intent ? nextTap(c.intent, c) : null;
        if (tap && document.querySelector(tap.sel)) { tapSel = tap.sel; say = tap.say; }
        targetSel = st.target?.(c) || tapSel;
        dim = 0.3;
        buttons = [{ label: "Show me", on: () => (c.intent ? this.toggleShowMe(true) : this.fetchHint()) },
          { label: "Skip this lesson", quiet: true, on: () => { this.advance(); this.sync(); } }];
        if (st.showMe && !this.showMeAuto?.[st.id]) { this.showMeAuto = { ...this.showMeAuto, [st.id]: true }; this.showMe = true; }
      }
    }
    const textKey = body.map((n) => (n && n.textContent) || "").join("|");
    const avoidSel = st.avoid?.(c) || null;
    return { ...base, body, buttons: buttons.filter(Boolean), targetSel, tapSel, say, dim, note, scrollSel: targetSel, textKey, avoidSel };
  }

  toggleShowMe(on) {
    this.showMe = on;
    this.renderedKey = null;
    this.lastTargetSel = null;
    this.sync();
  }

  async fetchHint() {
    try {
      const r = await api.hint(this.code);
      this.showHint(r.action);
    } catch (e) { toast(e.message); }
  }

  // ---------------------------------------------------------------- DOM
  build(m) {
    const v = this.view;
    if (m.minimized) {
      this.card = null;
      this.spot = null;
      this.ping = null;
      this.layer.replaceChildren(h("button", { class: "coach-pill", id: "coach-pill", style: { top: `${Math.round(this.safeArea().top)}px` }, onclick: () => { this.minimized = false; this.save(); this.sync(); },
        "aria-label": `Open lesson: ${m.title}` }, icon("compass"), h("span", {}, h("small", {}, m.eyebrow), m.title)));
      return;
    }
    const head = h("div", { class: "coach-head" },
      h("div", { class: "coach-titles" }, h("p", { class: "coach-eyebrow" }, m.eyebrow), h("h3", { id: "coach-title" }, m.title)),
      m.kind === "hint" ? null : h("button", { class: "icon-btn coach-min", "aria-label": "Fold the lesson away", onclick: () => {
        this.minimized = true; this.save(); this.view.renderStatus(); this.sync();
      } }, icon("minus")));
    const say = m.say ? h("p", { class: "coach-say" }, icon("arrow"), h("span", {}, m.say)) : null;
    const note = m.note ? h("p", { class: "coach-note" }, icon(m.note.icon), h("span", {}, m.note.text)) : null;
    const btns = h("div", { class: "coach-buttons" }, m.kind === "hint" ? null : h("button", { class: "coach-skip", onclick: () => this.skipAll() }, "Skip tutorial"), m.buttons.map((b) => h("button", {
      class: `btn${b.primary ? " primary" : ""}${b.quiet ? " ghost quiet" : ""}`, onclick: b.on,
      "aria-pressed": b.label === "Show me" ? String(this.showMe) : null,
    }, b.label)));
    this.arrow = h("span", { class: "coach-arrow", "aria-hidden": "true" });
    const fresh = this.builtKey !== m.key;
    this.builtKey = m.key;
    this.card = h("section", { class: `coach-card coach-${m.kind}${fresh ? " enter" : ""}`, role: "dialog", "aria-modal": "false", "aria-labelledby": "coach-title", id: "coach-card" },
      this.arrow, head, h("div", { class: "coach-body" }, m.body, say, note), btns);
    this.spot = m.targetSel ? h("div", { class: "coach-spot", style: { "--dim": String(m.dim || 0) }, "aria-hidden": "true" }) : null;
    this.ping = m.tapSel && this.showMe ? h("div", { class: "coach-ping", "aria-hidden": "true" }, h("span", { class: "coach-ping-label" }, m.say || "Tap here")) : null;
    this.layer.replaceChildren(...[this.spot, this.ping, this.card].filter(Boolean));
    void v;
  }

  /** Scroll a page target into the free area between the top bar and the dice tray. */
  reveal(sel) {
    const el = document.querySelector(sel);
    if (!el || el.closest("#tray, .topbar")) return;
    const r = el.getBoundingClientRect();
    const safe = this.safeArea();
    const visibleEnough = r.top >= safe.top && r.bottom <= safe.bottom;
    if (visibleEnough) return;
    let dy;
    if (r.height > safe.bottom - safe.top) dy = r.top - safe.top - 8;
    else dy = r.top - (safe.top + (safe.bottom - safe.top - r.height) / 2);
    window.scrollBy({ top: dy, behavior: reducedMotion() ? "auto" : "smooth" });
  }

  safeArea() {
    const top = (document.getElementById("topbar")?.getBoundingClientRect().bottom || 0) + 8;
    const tray = document.getElementById("tray");
    const vh = window.visualViewport?.height || window.innerHeight;
    const bottom = (tray ? tray.getBoundingClientRect().top : vh) - 8;
    return { top, bottom: Math.max(top + 120, bottom), left: 8, right: (document.documentElement.clientWidth || window.innerWidth) - 8 };
  }

  queueLayout() {
    if (this.queued) return;
    this.queued = true;
    requestAnimationFrame(() => { this.queued = false; this.layout(); });
  }

  layout() {
    const m = this.model;
    if (!m || !this.layer.isConnected) return;
    const safe = this.safeArea();
    const targetEl = m.targetSel ? document.querySelector(m.targetSel) : null;
    const tapEl = m.tapSel ? document.querySelector(m.tapSel) : null;
    let t = targetEl ? targetEl.getBoundingClientRect() : null;
    if (t && (t.width === 0 && t.height === 0)) t = null;
    const pad = 6;
    if (this.spot) {
      if (t) {
        Object.assign(this.spot.style, { display: "block", left: `${t.left - pad}px`, top: `${t.top - pad}px`, width: `${t.width + pad * 2}px`, height: `${t.height + pad * 2}px` });
      } else this.spot.style.display = "none";
    }
    if (this.ping) {
      const p = tapEl?.getBoundingClientRect();
      if (p && p.width) {
        Object.assign(this.ping.style, { display: "block", left: `${p.left + p.width / 2}px`, top: `${p.top + p.height / 2}px`,
          width: `${Math.max(48, p.width + 12)}px`, height: `${Math.max(48, p.height + 12)}px` });
        this.ping.classList.toggle("label-below", p.top < safe.top + 60);
        const vw = document.documentElement.clientWidth;
        this.ping.classList.toggle("label-left", p.left + p.width / 2 < 110);
        this.ping.classList.toggle("label-right", p.left + p.width / 2 > vw - 110);
      } else this.ping.style.display = "none";
    }
    const card = this.card;
    if (!card) return;
    const W = Math.min(380, safe.right - safe.left);
    card.style.width = `${W}px`;
    card.style.maxHeight = `${Math.max(160, safe.bottom - safe.top)}px`;
    const H = card.offsetHeight;
    const avoidEl = m.avoidSel ? document.querySelector(m.avoidSel) : null;
    const avoid = avoidEl ? avoidEl.getBoundingClientRect() : tapEl ? tapEl.getBoundingClientRect() : t;
    const gap = 16;
    const clampX = (x) => Math.min(Math.max(x, safe.left), safe.right - W);
    const clampY = (y) => Math.min(Math.max(y, safe.top), Math.max(safe.top, safe.bottom - H));
    const overlap = (x, y, r) => {
      if (!r) return 0;
      const ix = Math.max(0, Math.min(x + W, r.right + 4) - Math.max(x, r.left - 4));
      const iy = Math.max(0, Math.min(y + H, r.bottom + 4) - Math.max(y, r.top - 4));
      return ix * iy;
    };
    let pos = null;
    if (avoid) {
      const cx = avoid.left + avoid.width / 2, cy = avoid.top + avoid.height / 2;
      const cands = [
        { side: "below", x: clampX(cx - W / 2), y: Math.max(avoid.bottom + gap, safe.top) },
        { side: "above", x: clampX(cx - W / 2), y: Math.min(avoid.top - gap, safe.bottom) - H },
        { side: "right", x: avoid.right + gap, y: clampY(cy - H / 2) },
        { side: "left", x: avoid.left - gap - W, y: clampY(cy - H / 2) },
      ];
      // Spotlighted big regions: prefer the side with the most room.
      for (const cand of cands) {
        const fits = cand.x >= safe.left - 0.5 && cand.x + W <= safe.right + 0.5 && cand.y >= safe.top - 0.5 && cand.y + H <= safe.bottom + 0.5;
        if (fits && !overlap(cand.x, cand.y, avoid)) { pos = cand; break; }
      }
      if (!pos) {
        const corners = [
          { side: "none", x: safe.right - W, y: safe.top }, { side: "none", x: safe.left, y: safe.top },
          { side: "none", x: safe.right - W, y: clampY(safe.bottom - H) }, { side: "none", x: safe.left, y: clampY(safe.bottom - H) },
          { side: "none", x: clampX(cx - W / 2), y: safe.top }, { side: "none", x: clampX(cx - W / 2), y: clampY(safe.bottom - H) },
        ];
        pos = corners.reduce((best, cand) => (overlap(cand.x, cand.y, avoid) < overlap(best.x, best.y, avoid) ? cand : best));
      }
    } else {
      pos = { side: "none", x: clampX(safe.left + (safe.right - safe.left - W) / 2), y: clampY(safe.top + (safe.bottom - safe.top - H) / 2) };
    }
    card.style.left = `${Math.round(pos.x)}px`;
    card.style.top = `${Math.round(pos.y)}px`;
    card.dataset.side = pos.side;
    const a = this.arrow;
    a.style.cssText = "";
    const acx = avoid ? avoid.left + avoid.width / 2 : 0, acy = avoid ? avoid.top + avoid.height / 2 : 0;
    const aligned = avoid && (pos.side === "below" || pos.side === "above" ? acx > pos.x + 14 && acx < pos.x + W - 14
      : acy > pos.y + 14 && acy < pos.y + H - 14);
    if (avoid && pos.side !== "none" && aligned) {
      a.style.display = "block";
      if (pos.side === "below" || pos.side === "above") {
        a.style.left = `${Math.min(Math.max(avoid.left + avoid.width / 2 - pos.x, 22), W - 22) - 9}px`;
        a.style[pos.side === "below" ? "top" : "bottom"] = "-10px";
      } else {
        a.style.top = `${Math.min(Math.max(avoid.top + avoid.height / 2 - pos.y, 22), H - 22) - 9}px`;
        a.style[pos.side === "right" ? "left" : "right"] = "-10px";
      }
    } else a.style.display = "none";
  }
}
