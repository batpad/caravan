// In-game UI: character draft, the play screen, and final scoring.
// GameView owns only UI-local state (selected die, last-turn flag); the server owns the game.
//
// Stable hooks for overlays / coach-marks (tutorial): every key region carries an id and a
// data-tour attribute — topbar-status, map (#map-panel), action spaces (#bazaar, and
// data-space="<key>" on each stall), city actions (#city-charters), contract market (#market,
// data-slot on each slot), player board (#player-board), merchants (#merchants),
// journal (#journal), dice tray (#tray, #tray-dice, #die-tools, #turn-buttons).
// An empty #overlay-root sits above the app for coach-marks.

import { api } from "./api.js";
import { showRules } from "./rules.js";
import { mapLegend, renderMap } from "./board.js";
import { h, modal, toast } from "./dom.js";
import { CHARACTER_EMBLEM, dieFace, icon, pigment, pipFace, resChips } from "./icons.js";
import {
  canPay, canDeliver, characterCard, commissions, contractCard, finalScore, journal, legendContent,
  merchantRow, resourceCounters, seal,
} from "./parts.js";

const SPACE_ORDER = ["bazaar_spice", "bazaar_silk", "bazaar_jade", "camels", "treasury", "temple", "caravanserai", "road"];
const SPACE_ICON = {
  bazaar_spice: "spice", bazaar_silk: "silk", bazaar_jade: "jade", camels: "camels",
  treasury: "coins", temple: "omens", caravanserai: "scroll", road: "caravan",
};
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export class GameView {
  constructor(root, code, info) {
    this.root = root;
    this.code = code;
    this.info = info;
    this.sel = []; // selected die ids — one die, or a set of 2–3 equal values (guide dice are wild)
    this.busy = false;
    this.wasMyTurn = false;
  }

  async act(action) {
    if (this.busy) return;
    this.busy = true;
    document.documentElement.classList.add("busy");
    try {
      await api.act(this.code, action);
      this.onChanged?.();
    } catch (e) {
      toast(e.message);
    } finally {
      this.busy = false;
      document.documentElement.classList.remove("busy");
    }
  }

  update(data) {
    this.data = data;
    this.game = data.game;
    this.bots = Object.fromEntries((data.players || []).filter((p) => p.is_bot).map((p) => [p.index, p.bot_level || "normal"]));
    this.me = data.seat != null ? this.game.players[data.seat] : null;
    if (this.me) {
      this.sel = this.myTurn ? this.sel.filter((id) => this.me.dice.some((d) => d.id === id && !d.placed)) : [];
    } else this.sel = [];
    // Auto-select when only one die is left to place — saves a tap.
    if (this.canPlace && !this.sel.length) {
      const free = this.me.dice.filter((d) => this.diePlaceable(d));
      if (free.length === 1) this.sel = [free[0].id];
    }
    this.turnStarted = this.myTurn && !this.wasMyTurn;
    this.wasMyTurn = this.myTurn;
    this.render();
  }

  get myTurn() {
    return !!this.me && this.game.phase === "play" && this.game.current === this.me.seat;
  }
  get canPlace() {
    return this.myTurn && !this.game.turn_placed;
  }
  /** Selected dice, in selection order. */
  get selDice() {
    return this.sel.map((id) => this.me?.dice.find((d) => d.id === id)).filter(Boolean);
  }
  /** The die the reroll / nudge / seer tools act on: the last one tapped. */
  get selDie() {
    const d = this.selDice;
    return d[d.length - 1] || null;
  }
  /** The selection as a placement {dice, n, value}, or null when nothing can be placed now. */
  get placing() {
    if (!this.canPlace) return null;
    const dice = this.selDice;
    if (!dice.length) return null;
    const colored = dice.filter((d) => !d.white);
    return { dice, n: dice.length, value: (colored[0] || dice[0]).value };
  }
  /** Back-compat alias used by older render code: the focus die while placing. */
  get placingDie() {
    return this.placing ? this.selDie : null;
  }

  /** Can this die still go out this turn? (Heiress: coloured dice are capped by placements_left.) */
  diePlaceable(d) {
    if (d.placed) return false;
    if (!d.white && this.me.placements_left != null && this.me.placements_left <= 0) return false;
    return true;
  }

  /** Tap a die: toggle it; tapping a matching die grows a set (max 3), a non-matching one starts over. */
  tapDie(id) {
    const d = this.me.dice.find((x) => x.id === id);
    if (this.sel.includes(id)) {
      this.sel = this.sel.filter((x) => x !== id);
    } else if (!this.sel.length || !this.canPlace) {
      this.sel = [id];
    } else {
      const cand = [...this.sel, id].map((x) => this.me.dice.find((y) => y.id === x));
      const colored = cand.filter((x) => !x.white);
      const same = colored.every((x) => x.value === colored[0]?.value);
      const whites = cand.filter((x) => x.white).length;
      const coloredCount = colored.length;
      const capOk = this.me.placements_left == null || coloredCount <= this.me.placements_left;
      const ok = cand.length <= this.maxSet() && same && whites <= 1 && capOk && d;
      this.sel = ok ? cand.map((x) => x.id) : [id];
    }
    this.render();
  }

  maxSet() {
    return Math.max(1, ...Object.values(this.info.spaces).map((sp) => sp.max_dice || 1));
  }

  /** Build a place action for the current selection. */
  placeAction(space, extra = {}) {
    const ids = this.selDice.map((d) => d.id);
    return ids.length === 1 ? { type: "place", die: ids[0], space, ...extra } : { type: "place", dice: ids, space, ...extra };
  }

  setBonus(n) {
    return (this.info.rules.set_bonus || [0, 0, 1, 2])[n] || 0;
  }
  toll(space, value) {
    return this.game.tolls?.[space]?.[value] || 0;
  }
  crowded(space) {
    return (this.game.spaces[space] || []).some((e) => e.seat !== this.me?.seat);
  }
  cityUses(value) {
    const extra = this.me?.character === "quartermaster" ? (this.info.powers?.quartermaster_extra_uses || 0) : 0;
    return this.info.city_action_repeats[value] + extra;
  }

  // ------------------------------------------------------------------ top-level
  render() {
    const g = this.game;
    this.renderStatus();
    document.documentElement.classList.toggle("placing", !!this.placing);
    if (g.phase === "setup") {
      document.documentElement.classList.remove("with-tray");
      this.root.replaceChildren(this.renderSetup());
      this.onRender?.();
      return;
    }
    document.title = this.myTurn ? "● Your turn — Caravan Road" : "Caravan Road";

    const tray = this.me && g.phase === "play" ? this.renderTray() : null;
    document.documentElement.classList.toggle("with-tray", !!tray);
    this.root.replaceChildren(
      h("div", { class: `play${this.placing ? " placing" : ""}`, id: "play" },
        h("div", { class: "board-col" },
          g.phase === "finished" ? finalScore(this.info, g) : null,
          h("section", { class: "panel map-panel", id: "map-panel", "data-tour": "map" },
            this.renderMapSection(), mapLegend(this.info)),
          this.renderBazaar(),
          this.renderMarket(),
        ),
        h("aside", { class: "side-col" },
          this.me ? this.renderMine()
            : h("section", { class: "panel" }, h("p", { class: "muted" }, "You are watching this game.")),
          h("section", { class: "panel", id: "merchants", "data-tour": "players" },
            h("h3", { class: "panel-title" }, "Merchants"),
            g.players.map((p) => merchantRow(this.info, g, p, { bot: this.bots[p.seat] }))),
          h("section", { class: "panel journal", id: "journal", "data-tour": "journal" },
            h("h3", { class: "panel-title" }, "Journal"), journal(g)),
        ),
      ),
      tray,
    );
    if (tray) {
      requestAnimationFrame(() => {
        document.documentElement.style.setProperty("--tray-h", `${tray.offsetHeight}px`);
      });
    }
    this.onRender?.();
  }

  renderStatus() {
    const g = this.game;
    const status = document.getElementById("topbar-status");
    const keyBtn = h("button", { class: "btn ghost key-btn", onclick: () => this.showKey(), "aria-label": "Key and scoring" },
      icon("book"), h("span", {}, "Key"));
    const rulesBtn = h("button", { class: "btn ghost key-btn", id: "rules-btn", onclick: () => showRules(this.info), "aria-label": "How to play" },
      icon("scroll"), h("span", {}, "Rules"));
    const canHint = this.myTurn || (g.phase === "setup" && this.me && !this.me.character);
    const hintBtn = canHint && !this.coach?.tutorialActive ? h("button", { class: "btn ghost key-btn hint-btn", id: "hint-btn", onclick: () => this.hint(),
      "aria-label": "Hint: show me a good move" }, icon("compass"), h("span", {}, "Hint")) : null;
    const extra = this.coach?.statusButton?.() || null;
    if (g.phase === "setup") {
      status.replaceChildren(...[h("span", { class: "pill" }, "Choosing merchants"), extra, hintBtn, rulesBtn, keyBtn].filter(Boolean));
      return;
    }
    const cur = g.players[g.current];
    const rounds = this.info.num_rounds;
    status.replaceChildren(...[
      h("span", { class: "round-track", role: "img", "aria-label": g.phase === "finished" ? "Game over" : `Round ${g.round} of ${rounds}` },
        h("small", {}, g.phase === "finished" ? "Final" : "Round"),
        Array.from({ length: rounds }, (_, i) => h("i", { class: i + 1 < g.round || g.phase === "finished" ? "past" : i + 1 === g.round ? "now" : "" }))),
      g.phase === "play" ? h("span", { class: `pill turn-pill${this.myTurn ? " your-turn" : ""}`, id: "turn-pill", "data-tour": "turn-indicator" },
        seal(cur), this.myTurn ? "Your turn" : `${cur.name}'s turn`, this.bots[cur.seat] ? h("span", { class: "ai-badge" }, "AI") : null) : null,
      h("span", { class: "pill code" }, this.code),
      extra, hintBtn, rulesBtn, keyBtn,
    ].filter(Boolean));
  }

  async hint() {
    try {
      const r = await api.hint(this.code);
      this.coach?.showHint(r.action);
    } catch (e) { toast(e.message); }
  }

  showKey() {
    modal("Key", () => legendContent(this.info), { kind: "wide" });
  }

  // ------------------------------------------------------------------ setup
  renderSetup() {
    const g = this.game, info = this.info;
    const waiting = g.players.filter((p) => !p.character);
    const mine = this.me;
    return h("section", { class: "panel setup", id: "setup", "data-tour": "character-choice" },
      h("p", { class: "eyebrow" }, "Constantinople · before the first caravan leaves"),
      h("h2", {}, mine && !mine.character ? "Choose who you travel as" : "The merchants are choosing"),
      mine && !mine.character ? h("div", { class: "char-choices" }, mine.character_choices.map((c) =>
        characterCard(info, c, { "data-character": c, onclick: () => this.act({ type: "choose_character", character: c }) }))) : null,
      mine?.character ? h("div", { class: "chosen" }, h("span", { class: "char-medallion" }, icon(CHARACTER_EMBLEM[mine.character])),
        h("div", {}, h("p", { class: "eyebrow" }, "You travel as"), h("h3", {}, info.characters[mine.character].name),
          h("p", {}, info.characters[mine.character].text))) : null,
      mine ? h("div", { class: "setup-commissions" }, h("h3", { class: "panel-title" }, "Your secret commissions"),
        h("p", { class: "muted small" }, "Found trading posts in these cities to score at the end. Only you can see them."),
        commissions(info, mine)) : null,
      h("ul", { class: "setup-waiting" }, g.players.map((p) => h("li", { class: p.character ? "ready" : "" }, seal(p), p.name,
        this.bots[p.seat] ? h("span", { class: "ai-badge" }, "AI") : null,
        h("small", {}, p.character ? "ready" : "choosing…")))),
      waiting.length ? null : h("p", { class: "muted" }, "Setting out…"),
    );
  }

  // ------------------------------------------------------------------ map
  reachable() {
    const pl = this.placing;
    const out = {};
    if (!pl || pl.n > (this.info.spaces.road?.max_dice || 1)) return out;
    const table = pl.n === 1 ? this.game.travel : pl.n === 2 ? this.game.travel_pair : null;
    for (const o of table?.[String(pl.value)] || []) (out[o.dest] ||= []).push(o);
    return out;
  }

  /** Cities where the selected die can use a city action right now. */
  cityTargets() {
    const pl = this.placing, me = this.me, out = new Set();
    if (!pl || pl.n !== 1) return out;
    for (const c of me.posts) {
      const act = this.info.cities[c]?.action;
      if (act && !this.game.city_spaces[c] && canPay(me, act.pay)) out.add(c);
    }
    return out;
  }

  renderMapSection() {
    const reachable = this.reachable();
    const cityTargets = this.cityTargets();
    return renderMap(this.info, this.game, {
      reachable, cityTargets, placing: !!this.placing, mySeat: this.me?.seat,
      onCity: (id) => this.onCity(id, reachable, cityTargets),
    });
  }

  async onCity(id, reachable, cityTargets) {
    const canTravel = !!reachable[id], canTrade = cityTargets.has(id);
    if (canTravel && canTrade) {
      const choice = await modal(this.info.cities[id].name, (close) => h("div", { class: "choice-list" },
        h("button", { class: "btn block", onclick: () => close("travel") }, icon("caravan"), "Travel here"),
        h("button", { class: "btn block", onclick: () => close("trade") }, icon("post"), "Use the city action")));
      if (choice === "travel") return this.travelTo(id, reachable[id]);
      if (choice === "trade") return this.useCity(id);
      return;
    }
    if (canTravel) return this.travelTo(id, reachable[id]);
    if (canTrade) return this.useCity(id);
    this.cityInfo(id);
  }

  async travelTo(city, options) {
    const pl = this.placing, die = this.selDie;
    const cost = this.toll("road", pl.value);
    const info = this.info;
    const noPost = info.no_post_cities || ["constantinople", "changan"];
    const c = info.cities[city];
    const route = (path) => h("span", { class: "route-steps" }, path.map((x, i) => [i ? icon("arrow", { cls: "step-arrow" }) : null,
      h("span", { class: i === path.length - 1 ? "dest" : "" }, info.cities[x].name)]));
    const choice = await modal(`Journey to ${c.name}`, (close) => h("div", { class: "journey" },
      h("p", { class: "journey-die" }, pl.dice.map((d) => dieFace(d.value, this.me.color, { white: d.white })),
        h("span", {}, pl.n > 1 ? `Your pair of ${pl.value}s carries the caravan` : `Your ${die.value} carries the caravan`)),
      cost ? h("p", { class: "warn" }, icon("coins"), ` The Road is crowded: toll ${cost} coin${cost > 1 ? "s" : ""}.`) : null,
      this.me.posts.includes(city) || noPost.includes(city) ? null
        : h("p", { class: "gain-note" }, icon("post"), ` Found a trading post here: +${c.post_vp} `, icon("vp")),
      city === "changan" ? h("p", { class: "gain-note" }, icon("vp"), ` Arrival bonus ${info.end_city_order_vp.join(" / ")} by order`) : null,
      h("p", { class: "muted small" }, options.length > 1 ? "Choose your path:" : "Your path:"),
      options.map((o) => h("button", { class: "btn block path-btn", onclick: () => close(o) },
        route(o.path), resChips({ camels: o.camels, coins: o.coins }, { empty: "free" }))),
    ));
    if (!choice) return;
    const extra = { path: choice.path };
    const me = this.me;
    if (me.character === "cartographer" && !me.power_used) {
      const room = info.rules.trading_posts - me.posts.length - (me.posts.includes(city) || noPost.includes(city) ? 0 : 1);
      const eligible = choice.path.slice(1, -1).filter((x) => !me.posts.includes(x) && !noPost.includes(x));
      if (room > 0 && eligible.length) {
        const fee = info.powers?.cartographer_survey_cost || {};
        const after = { ...me, coins: me.coins - choice.coins - cost, camels: me.camels - choice.camels };
        const affordable = canPay(after, fee);
        const pick = await modal("Survey along the way", (close) => h("div", { class: "choice-list" },
          h("p", {}, "Cartographer: also found a surveyed post in one city you pass through (no printed renown)",
            Object.keys(fee).length ? [" for ", resChips(fee)] : null, "."),
          affordable ? null : h("p", { class: "warn" }, icon("coins"), " After this journey you can't afford the survey."),
          eligible.map((x) => h("button", { class: "btn block", disabled: !affordable, onclick: () => close(x) }, icon("post"), info.cities[x].name,
            Object.keys(fee).length ? resChips(fee) : null)),
          h("button", { class: "btn block ghost", onclick: () => close(false) }, "Don't survey this time")));
        if (pick === null) return;
        extra.post_at = pick;
      }
    }
    this.act(this.placeAction("road", extra));
  }

  cityInfo(id) {
    const c = this.info.cities[id];
    const owners = this.game.players.filter((p) => p.posts.includes(id));
    const here = this.game.players.filter((p) => p.location === id);
    modal(c.name, () => h("div", { class: "city-info" },
      c.post_vp ? h("p", { class: "info-row" }, icon("post"), h("span", {}, "Founding a trading post"), h("b", {}, `+${c.post_vp}`), icon("vp")) : null,
      Object.keys(c.income).length ? h("p", { class: "info-row" }, icon("hourglass"), h("span", {}, "Income each round for post owners"), resChips(c.income)) : null,
      c.action ? h("div", { class: "info-row trade" }, icon("scales"), h("span", {}, "City action (post owners)"),
        h("span", { class: "exchange" }, resChips(c.action.pay, { empty: "free" }), icon("arrow", { cls: "step-arrow" }), resChips(c.action.gain))) : null,
      c.action ? h("p", { class: "muted small" }, `Place a die here to repeat it ${this.info.city_action_repeats.slice(1).join("·")} times by value. Once per round.`) : null,
      id === "changan" ? h("p", { class: "info-row" }, icon("vp"), h("span", {}, `Arrival order bonus: ${this.info.end_city_order_vp.join(" / ")}`)) : null,
      id === "constantinople" ? h("p", { class: "muted" }, "Every caravan sets out from here.") : null,
      h("div", { class: "info-owners" },
        owners.length ? owners.map((p) => h("span", { class: "owner" }, seal(p), p.name)) : h("span", { class: "muted" }, "No trading posts yet."),
        here.length ? h("p", { class: "muted small" }, "Caravans here: ", here.map((p) => p.name).join(", ")) : null),
    ));
  }

  // ------------------------------------------------------------------ bazaar (action spaces)
  /** Is this simple space a legal target for the selected die? Returns {ok, why}. */
  spaceState(key) {
    const pl = this.placing;
    if (!pl) return { ok: false };
    const sp = this.info.spaces[key];
    const max = sp.max_dice || 1;
    const toll = this.toll(key, pl.value);
    if (pl.n > max) return { ok: false, why: max === 1 ? "Single dice only" : `Sets of up to ${max}` };
    if (key === "caravanserai") {
      if (!this.game.contract_market.length) return { ok: false, why: "No contracts" };
      return this.me.coins >= toll ? { ok: true, toll } : { ok: false, why: "Can't pay the toll" };
    }
    if (key === "road") {
      const any = Object.keys(this.reachable()).length > 0;
      const steps = sp.table[pl.value] * pl.n + this.setBonus(pl.n);
      return { ok: any, why: "No affordable route", toll, gain: steps };
    }
    const cost = Object.fromEntries(Object.entries(sp.cost || {}).map(([k, v]) => [k, v * pl.n]));
    if (toll) cost.coins = (cost.coins || 0) + toll;
    const gain = sp.table ? sp.table[pl.value] * pl.n + this.setBonus(pl.n) : 0;
    return canPay(this.me, cost) ? { ok: true, toll, gain, cost } : { ok: false, why: "Can't afford", toll, gain };
  }

  renderBazaar() {
    const g = this.game, pl = this.placing, info = this.info;
    const die = pl ? { value: pl.value } : null;
    return h("section", { class: "panel bazaar", id: "bazaar", "data-tour": "action-spaces" },
      h("div", { class: "panel-head" }, h("h3", { class: "panel-title" }, "The Bazaar"),
        h("span", { class: "muted small" }, pl ? (pl.n > 1 ? `Glowing stalls accept your set of ${pl.n}` : "Glowing stalls accept your die")
          : "Yield by die value · sets of equal dice earn a bonus")),
      h("div", { class: "stalls" }, SPACE_ORDER.map((key) => {
        const sp = info.spaces[key];
        if (!sp) return null;
        const st = this.spaceState(key);
        const crowded = this.crowded(key);
        const placed = g.spaces[key] || [];
        let body;
        if (key === "caravanserai") {
          body = h("div", { class: "stall-text" }, "Take a contract from slot 1 up to your die.");
        } else if (key === "road") {
          body = h("div", { class: "yield", "aria-label": `Steps by die value: ${sp.table.slice(1).join(", ")}` },
            sp.table.slice(1).map((n, i) => h("span", { class: `y${die && die.value === i + 1 ? " hit" : ""}` }, pipFace(i + 1), h("b", {}, String(n)))),
            h("span", { class: "y-unit" }, "steps"));
        } else {
          body = h("div", { class: "yield", "aria-label": `Gain ${sp.gain} by die value: ${sp.table.slice(1).join(", ")}` },
            sp.table.slice(1).map((n, i) => h("span", { class: `y${die && die.value === i + 1 ? " hit" : ""}` }, pipFace(i + 1), h("b", {}, String(n)))));
        }
        const max = sp.max_dice || 1;
        const notes = [
          max > 1 ? h("span", { class: "note sets" }, `sets ≤${max}`) : null,
          Object.keys(sp.cost || {}).length ? h("span", { class: "note cost" }, "costs ", resChips(sp.cost), max > 1 ? " each" : "") : null,
          crowded ? h("span", { class: "note occ" }, "crowded · toll ", pl ? [String(st.toll ?? 0), " "] : `${info.rules.toll_per_pip || 1}/pip `, icon("coins")) : null,
          key === "temple" ? h("span", { class: "note" }, g.temple_claim == null ? "First here leads next round" : `${g.players[g.temple_claim].name} leads next round`) : null,
          die && !st.ok && st.why ? h("span", { class: "note why" }, st.why) : null,
        ];
        const tag = st.ok ? "button" : "div";
        return h(tag, {
          class: `stall stall-${key}${st.ok ? " target" : ""}${die && !st.ok ? " blocked" : ""}`,
          "data-space": key, "data-tour": `space-${key}`,
          onclick: st.ok ? () => this.onStall(key) : null,
          "aria-label": st.ok ? `Place die on ${sp.name}` : null,
        },
        h("span", { class: "awning", "aria-hidden": "true" }),
        h("span", { class: "stall-head" }, h("span", { class: "stall-icon" }, icon(SPACE_ICON[key] || "vp")), h("span", { class: "stall-name" }, sp.name)),
        body,
        h("span", { class: "notes" }, notes),
        st.ok && (st.gain || st.toll) && key !== "caravanserai" ? h("span", { class: "preview" },
          st.gain ? [h("b", {}, key === "road" ? `${st.gain} step${st.gain === 1 ? "" : "s"}` : `+${st.gain}`), key === "road" ? null : icon(sp.gain)] : null,
          pl.n > 1 && this.setBonus(pl.n) ? h("small", {}, ` incl. set +${this.setBonus(pl.n)}`) : null,
          st.toll ? h("small", { class: "toll" }, " · toll ", String(st.toll), icon("coins")) : null) : null,
        h("span", { class: "stall-dice" }, this.placedGroups(placed)),
        st.ok ? h("span", { class: "target-flag", "aria-hidden": "true" }, key === "road" ? "Pick a city" : key === "caravanserai" ? "Pick a contract" : "Place here") : null,
        );
      })),
      this.renderCharters(),
    );
  }

  onStall(key) {
    if (key === "road") return this.reveal("map-panel");
    if (key === "caravanserai") return this.reveal("market");
    this.placeSimple(key);
  }

  reveal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
  }

  /** Placed dice, with dice from one set bracketed together. */
  placedGroups(entries) {
    const out = [], sets = new Map();
    for (const e of entries) {
      if (e.set != null) {
        if (!sets.has(e.set)) { const g = h("span", { class: "placed-set" }); sets.set(e.set, g); out.push(g); }
        sets.get(e.set).append(this.placedDie(e));
      } else out.push(this.placedDie(e));
    }
    return out;
  }

  placedDie(e) {
    const p = this.game.players[e.seat];
    return h("span", { class: "placed-die", role: "img", "aria-label": `${p.name}${e.white ? " guide die" : ""}: ${e.value}` },
      dieFace(e.value, p.color, { white: e.white, cls: "mini" }));
  }

  renderCharters() {
    const g = this.game, info = this.info, me = this.me;
    const mine = me ? me.posts.filter((c) => info.cities[c]?.action) : [];
    const others = Object.entries(g.city_spaces).filter(([c, v]) => v && !mine.includes(c));
    if (!mine.length && !others.length) return null;
    const pl = this.placing;
    const die = pl && pl.n === 1 ? pl : null;
    const reps = die ? this.cityUses(die.value) : 0;
    return h("div", { class: "charters", id: "city-charters", "data-tour": "city-actions" },
      h("h4", { class: "sub-title" }, mine.length ? "Your city actions" : "City actions taken",
        mine.length ? h("small", {}, ` · uses ${[1, 2, 3, 4, 5, 6].map((v) => this.cityUses(v)).join("·")} by die · one die · once per round`) : null),
      h("div", { class: "charter-row" },
        mine.map((c) => {
          const city = info.cities[c], taken = g.city_spaces[c];
          const ok = die && !taken && canPay(me, city.action.pay);
          return h(ok ? "button" : "div", { class: `charter${ok ? " target" : ""}${taken ? " taken" : ""}`, "data-city": c,
            onclick: ok ? () => this.useCity(c) : null, "aria-label": ok ? `Trade in ${city.name}` : null },
          h("span", { class: "charter-name" }, city.name),
          h("span", { class: "exchange" }, resChips(city.action.pay, { empty: "free" }), icon("arrow", { cls: "step-arrow" }), resChips(city.action.gain)),
          taken ? h("span", { class: "charter-die" }, this.placedDie(taken)) : ok ? h("span", { class: "target-flag" }, `Trade ×${reps}`) : null);
        }),
        others.map(([c, e]) => h("div", { class: "charter taken other" }, h("span", { class: "charter-name" }, info.cities[c].name), this.placedDie(e))),
      ));
  }

  placeSimple(space) {
    const st = this.spaceState(space);
    if (!st.ok) return toast(st.why || "You cannot place there.");
    this.act(this.placeAction(space));
  }

  // ------------------------------------------------------------------ contracts
  renderMarket() {
    const g = this.game, pl = this.placing;
    const die = pl && pl.n === 1 && this.spaceState("caravanserai").ok ? pl : null;
    const occ = die ? this.toll("caravanserai", die.value) : 0;
    return h("section", { class: "panel market-panel", id: "market", "data-tour": "contract-market" },
      h("div", { class: "panel-head" }, h("h3", { class: "panel-title" }, "Caravanserai · contracts"),
        h("span", { class: "muted small" }, `${g.deck_size} in the deck · the two oldest leave each round`)),
      h("div", { class: "market" }, g.contract_market.map((cid, i) => {
        const reach = this.me?.character === "guildmaster" ? (this.info.powers?.guildmaster_reach || 0) : 0;
        const ok = die && i + 1 <= die.value + reach;
        return h("div", { class: `slot${ok ? " target" : ""}${pl && !ok ? " blocked" : ""}`, "data-slot": i + 1 },
          contractCard(this.info, cid, {
            tag: h("span", { class: "slot-n" }, pipFace(i + 1), h("small", {}, i + 1 === 1 ? "any die" : `die ${i + 1}+`)),
            extra: ok ? h("button", { class: "btn primary take-btn", onclick: () => this.takeContract(i) },
              "Take", occ ? [" · +", occ, " ", icon("coins")] : null) : null,
          }));
      })),
    );
  }

  async takeContract(slot) {
    const me = this.me;
    const max = me.character === "guildmaster" ? (this.info.powers?.guildmaster_contracts || 3) : (this.info.rules.max_open_contracts || 2);
    let discard;
    if (me.contracts.length >= max) {
      const ready = me.contracts.map((cid) => canDeliver(me, this.info.contracts[cid].req, this.info));
      discard = await modal("Your satchel is full", (close) => h("div", { class: "abandon" },
        h("div", { class: "abandon-taking" }, h("p", {}, `You can hold ${max} open contracts. To take contract ${slot + 1}:`),
          contractCard(this.info, this.game.contract_market[slot], { cls: "taking" })),
        ready.some(Boolean) ? h("p", { class: "gain-note" }, icon("check"), " A contract is ready — close this and tap Deliver first (it's free) to make room.") : null,
        h("p", {}, "…or choose an open contract to abandon:"),
        h("div", { class: "discard-list" }, me.contracts.map((cid, i) => h("button", { class: "discard-btn", onclick: () => close(i),
          "aria-label": `Abandon contract ${i + 1}${ready[i] ? " (ready to deliver)" : ""}` },
        contractCard(this.info, cid, { ready: ready[i] }), ready[i] ? h("span", { class: "ready-note" }, "Ready to deliver") : null,
        h("span", { class: "discard-label" }, "Abandon this one"))))));
      if (discard == null) return;
    }
    this.act(this.placeAction("caravanserai", discard == null ? { slot } : { slot, discard }));
  }

  // ------------------------------------------------------------------ my board (side panel)
  renderMine() {
    const me = this.me, g = this.game, info = this.info;
    const turn = this.myTurn;
    const ch = info.characters[me.character];
    const max = me.character === "guildmaster" ? (info.powers?.guildmaster_contracts || 3) : (info.rules.max_open_contracts || 2);
    const contracts = h("div", { class: "my-contracts", id: "my-contracts", "data-tour": "my-contracts" },
      me.contracts.length ? me.contracts.map((cid, i) => {
        const ok = canDeliver(me, info.contracts[cid].req, info);
        return contractCard(info, cid, {
          ready: ok && turn,
          extra: turn ? h("button", { class: "btn primary deliver-btn", disabled: !ok, onclick: () => this.act({ type: "fulfill", index: i }) },
            ok ? "Deliver" : "Need goods") : (ok ? h("span", { class: "ready-note" }, "Ready on your turn") : null),
        });
      }) : h("p", { class: "muted small empty-note" }, "No open contracts — take one at the Caravanserai."));

    return h("section", { class: "panel ledger-board", id: "player-board", "data-tour": "player-panel", style: { "--pc": pigment(me.color).fill } },
      h("div", { class: "ledger-head" },
        seal(me, { emblem: CHARACTER_EMBLEM[me.character], cls: "big" }),
        h("div", { class: "ledger-id" }, h("strong", {}, me.name), h("small", {}, ch?.name || "")),
        h("span", { class: "vp-badge big", role: "img", "aria-label": `${me.vp} renown` }, icon("vp"), h("b", {}, String(me.vp)))),
      ch ? h("p", { class: "char-power" }, ch.text) : null,
      resourceCounters(me, { labelled: true }),
      h("div", { class: "ledger-line" },
        h("span", { class: "posts-track big", role: "img", "aria-label": `${me.posts.length} of ${info.rules.trading_posts} trading posts` },
          Array.from({ length: info.rules.trading_posts }, (_, i) => h("i", { class: i < me.posts.length ? "on" : "" }, i < me.posts.length ? icon("post") : null))),
        h("small", {}, `${me.posts.length}/${info.rules.trading_posts} posts · at ${info.cities[me.location].name}`)),
      h("h4", { class: "sub-title" }, `Open contracts ${me.contracts.length}/${max}`), contracts,
      h("h4", { class: "sub-title" }, "Secret commissions"),
      h("div", { id: "my-commissions", "data-tour": "commissions" }, commissions(info, me)),
    );
  }

  async useCity(city) {
    const act = this.info.cities[city].action;
    const maxReps = this.cityUses(this.selDie.value);
    let times = maxReps;
    if (maxReps > 1) {
      times = await modal(`Trade in ${this.info.cities[city].name}`, (close) => h("div", { class: "choice-list" },
        h("p", {}, "How many times?"),
        Array.from({ length: maxReps }, (_, i) => i + 1).map((n) => {
          const pay = Object.fromEntries(Object.entries(act.pay).map(([k, v]) => [k, v * n]));
          const gain = Object.fromEntries(Object.entries(act.gain).map(([k, v]) => [k, v * n]));
          return h("button", { class: "btn block", disabled: !canPay(this.me, pay), onclick: () => close(n) },
            h("b", { class: "times" }, `×${n}`), h("span", { class: "exchange" }, resChips(pay, { empty: "free" }), icon("arrow", { cls: "step-arrow" }), resChips(gain)));
        })));
      if (!times) return;
    }
    this.act(this.placeAction("city", { city, times }));
  }

  // ------------------------------------------------------------------ dice tray (docked)
  renderTray() {
    const me = this.me, g = this.game, info = this.info;
    const turn = this.myTurn, die = this.selDie, pl = this.placing;
    const unused = me.dice.filter((d) => !d.placed);
    const cur = g.players[g.current];
    const restCoins = (info.rules.rest_coins_per_die ?? 1) *
      (Math.min(unused.filter((d) => !d.white).length, me.placements_left ?? Infinity) + unused.filter((d) => d.white).length);

    let prompt;
    if (!turn) {
      prompt = me.passed
        ? [icon("tent"), h("span", {}, "You are resting this round.")]
        : [seal(cur), h("span", {}, `Waiting for ${cur.name}…`)];
    } else if (g.turn_placed) {
      prompt = [icon("hourglass"), h("span", {}, h("b", {}, "Placed. "), "Deliver contracts if you can, then end your turn.")];
    } else if (!pl) {
      prompt = [icon("arrow"), h("span", {}, h("b", {}, "Your turn. "), "Choose a die — tap more of the same value to make a set.")];
    } else if (pl.n === 1) {
      prompt = [dieFace(die.value, me.color, { white: die.white, cls: "prompt-die" }),
        h("span", {}, h("b", {}, `Placing a ${pl.value}. `), "Tap a glowing stall, contract or city — or add a matching die.")];
    } else {
      prompt = [h("span", { class: "prompt-set" }, pl.dice.map((d) => dieFace(d.value, me.color, { white: d.white, cls: "prompt-die" }))),
        h("span", {}, h("b", {}, `Set of ${pl.n} × ${pl.value}. `), `Bonus +${this.setBonus(pl.n)}. Tap a glowing stall or city.`)];
    }

    const capped = me.placements_left != null && me.placements_left <= 0;
    const dice = h("div", { class: "tray-dice", id: "tray-dice", "data-tour": "dice", role: "group", "aria-label": "Your dice" },
      me.dice.map((d) => {
        const on = this.sel.includes(d.id);
        const blocked = !d.placed && !d.white && capped;
        return h("button", {
          class: `die-btn${d.white ? " white" : ""}${d.placed ? " used" : ""}${on ? " selected" : ""}${blocked ? " capped" : ""}`,
          disabled: d.placed || !turn || (blocked && !on), "aria-pressed": on ? "true" : "false",
          "aria-label": `Die showing ${d.value}${d.white ? " (guide, wild in sets)" : ""}${d.placed ? (d.rested ? ", set aside" : ", placed") : ""}${blocked ? ", over your placement limit" : ""}`,
          "data-die": d.id,
          onclick: () => this.tapDie(d.id),
        }, dieFace(d.value, me.color, { white: d.white }), on && this.sel.length > 1 ? h("span", { class: "set-badge" }, String(this.sel.indexOf(d.id) + 1)) : null);
      }));

    const r = info.rules;
    const costs = g.costs || { reroll: r.reroll_cost, nudge: r.nudge_cost };
    const breeder = me.character === "breeder";
    const canSpend = (n) => me.omens >= n || (breeder && me.omens + me.camels >= n);
    const payWith = (n) => (breeder && me.omens < n ? "camels" : "omens");
    const tools = turn && die ? h("div", { class: "die-tools", id: "die-tools", "data-tour": "die-tools" },
      h("button", { class: "tool", "data-tool": "reroll", disabled: !canSpend(costs.reroll), onclick: () => this.act({ type: "reroll", die: die.id }),
        "aria-label": `Reroll the ${die.value} for ${costs.reroll} ${payWith(costs.reroll)}` },
      icon("reroll"), h("span", {}, "Reroll"), h("small", {}, costs.reroll, icon(payWith(costs.reroll)))),
      h("button", { class: "tool", "data-tool": "down", disabled: !canSpend(costs.nudge) || die.value <= 1, onclick: () => this.act({ type: "nudge", die: die.id, delta: -1 }),
        "aria-label": `Lower the ${die.value} by one for ${costs.nudge} ${payWith(costs.nudge)}` },
      icon("minus"), h("span", {}, "−1"), h("small", {}, costs.nudge, icon(payWith(costs.nudge)))),
      h("button", { class: "tool", "data-tool": "up", disabled: !canSpend(costs.nudge) || die.value >= 6, onclick: () => this.act({ type: "nudge", die: die.id, delta: 1 }),
        "aria-label": `Raise the ${die.value} by one for ${costs.nudge} ${payWith(costs.nudge)}` },
      icon("plus"), h("span", {}, "+1"), h("small", {}, costs.nudge, icon(payWith(costs.nudge)))),
      me.character === "seer" && !me.seer_used ? h("button", { class: "tool seer", "data-tool": "seer", onclick: () => this.seer(die),
        "aria-label": `Seer: set the ${die.value} to any face (${this.seerLeft()} left this round)` },
        icon("omens"), h("span", {}, "Seer"), h("small", {}, this.seerLeft() > 1 ? `set any · ${this.seerLeft()} left` : "set any")) : null,
      this.sel.length ? h("button", { class: "tool clear", "data-tool": "clear", onclick: () => { this.sel = []; this.render(); }, "aria-label": "Clear selection" },
        icon("close"), h("span", {}, "Clear"), h("small", {}, this.sel.length > 1 ? `${this.sel.length} dice` : "1 die")) : null,
    ) : null;

    const turnButtons = turn ? h("div", { class: "turn-buttons", id: "turn-buttons", "data-tour": "turn-buttons" },
      !me.guide_used && g.guide_pool > 0 && !g.turn_placed ? h("button", { class: "btn guide-btn", disabled: me.coins < r.guide_cost,
        onclick: () => this.act({ type: "hire_guide" }) },
      icon("guide"), h("span", {}, "Hire guide", h("small", {}, `${r.guide_cost} coins · ${g.guide_pool} left`, h("span", { class: "long" }, " · wild in sets")))) : null,
      h("button", { class: "btn rest-btn", onclick: () => this.rest(restCoins) }, icon("tent"),
        h("span", {}, "Rest", h("small", {}, `+${restCoins} coin${restCoins === 1 ? "" : "s"}`, h("span", { class: "long" }, " · out for the round")))),
      g.turn_placed ? h("button", { class: "btn primary end-btn", onclick: () => this.act({ type: "end_turn" }) }, icon("hourglass"), "End turn") : null,
    ) : null;

    return h("div", { class: `tray${turn ? " my-turn" : ""}${this.turnStarted ? " turn-start" : ""}${pl ? " has-die" : ""}`,
      id: "tray", "data-tour": "dice-tray", style: { "--pc": pigment(me.color).fill } },
    h("div", { class: "tray-top" },
      h("div", { class: "tray-prompt", role: "status", "aria-live": "polite" }, prompt),
      resourceCounters(me, { compact: true })),
    h("div", { class: "tray-main" }, dice, tools, turnButtons));
  }

  /** Seer: uses of "set any face" left this round (older servers: once per round). */
  seerLeft() {
    const total = this.info.powers?.seer_uses ?? 1;
    return Math.max(0, total - (this.me.seer_uses ?? (this.me.seer_used ? total : 0)));
  }

  async seer(die) {
    const left = this.seerLeft();
    const v = await modal("The Seer's sight", (close) => h("div", {},
      h("p", {}, `Set this ${die.value} to any face`, left > 1 ? ` (${left} uses left this round):` : left === 1 ? " (last use this round):" : ":"),
      h("div", { class: "face-pick" }, [1, 2, 3, 4, 5, 6].map((n) => h("button", {
        class: `die-btn${n === die.value ? " selected" : ""}`, "aria-label": `Set to ${n}`, "aria-pressed": n === die.value ? "true" : "false",
        "data-autofocus": n === die.value ? "" : null, onclick: () => close(n),
      }, dieFace(n, this.me.color, { white: die.white }))))));
    if (v && v !== die.value) this.act({ type: "seer", die: die.id, value: v });
  }

  async rest(n) {
    const ok = await modal("Rest for the round?", (close) => h("div", {},
      h("p", {}, n ? `Make camp: take ${n} coin${n === 1 ? "" : "s"} for the ${n === 1 ? "die" : "dice"} you could still place, and sit out the rest of this round.`
        : "Make camp and sit out the rest of this round (you have no dice left to cash in).", " This ends your turn."),
      h("div", { class: "row" }, h("button", { class: "btn primary", onclick: () => close(true) }, icon("tent"), "Rest"),
        h("button", { class: "btn ghost", onclick: () => close(false) }, "Keep trading"))));
    if (ok) this.act({ type: "rest" });
  }
}
