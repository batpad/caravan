// Pure render helpers for the play screen: contract documents, commissions, merchant rows,
// journal, final scoring, the key/legend and character cards. No state, no server calls.

import { h } from "./dom.js";
import { CHARACTER_EMBLEM, dieFace, icon, LABELS, pigment, pipFace, resChips } from "./icons.js";

export const RES_ORDER = ["coins", "camels", "spice", "silk", "jade", "omens"];

export function canPay(p, cost) {
  return Object.entries(cost || {}).every(([k, v]) => (p[k] || 0) >= v);
}

/** Mirrors engine._contract_payment: the Camel Breeder may cover missing goods with camels. */
export function contractPayment(p, req, info) {
  if (p.character !== "breeder") return req;
  const per = info?.powers?.breeder_good_camels ?? 2;
  const pay = { ...req };
  let missing = 0;
  for (const g of ["spice", "silk", "jade"]) {
    const short = (req[g] || 0) - (p[g] || 0);
    if (short > 0) { pay[g] -= short; missing += short; }
  }
  if (!missing) return req;
  pay.camels = (pay.camels || 0) + per * missing;
  return pay;
}

export function canDeliver(p, req, info) {
  return canPay(p, contractPayment(p, req, info));
}

/** Player colour seal: a disc in the player's pigment, optionally with an emblem. */
export function seal(p, { emblem = null, cls = "" } = {}) {
  const pg = pigment(p.color);
  return h("span", { class: `seal ${cls}`.trim(), style: { "--pc": pg.fill, "--pd": pg.dark }, "aria-hidden": "true" },
    emblem ? icon(emblem) : null);
}

/** Resource counters: icon over a number (with a visible label in the "labelled" variant). */
export function resourceCounters(p, { labelled = false, compact = false } = {}) {
  return h("div", { class: `counters${compact ? " compact" : ""}${labelled ? " labelled" : ""}` },
    RES_ORDER.map((k) => h("span", { class: `counter counter-${k}`, role: "img", "aria-label": `${p[k]} ${LABELS[k]}` },
      icon(k), h("b", { "aria-hidden": "true" }, String(p[k] ?? 0)), labelled ? h("small", { "aria-hidden": "true" }, LABELS[k]) : null)));
}

/** A contract rendered as a sealed document. `extra` (e.g. a button) goes in the footer. */
export function contractCard(info, cid, { extra = null, ready = false, tag = null, cls = "" } = {}) {
  const c = info.contracts[cid];
  if (!c) return h("div", { class: "contract missing" }, "Unknown contract");
  const bonus = Object.keys(c.bonus || {}).length ? h("div", { class: "doc-bonus" }, h("span", { class: "plus" }, "+"), resChips(c.bonus)) : null;
  return h("div", { class: `contract${ready ? " ready" : ""} ${cls}`.trim() },
    h("div", { class: "doc" },
      tag ? h("div", { class: "doc-tag" }, tag) : null,
      h("div", { class: "doc-req", "aria-label": "Deliver" }, resChips(c.req, { repeat: true })),
      h("div", { class: "doc-rule" }),
      h("div", { class: "doc-reward" },
        h("span", { class: "wax", role: "img", "aria-label": `${c.vp} renown` }, h("b", {}, String(c.vp))),
        bonus),
    ),
    extra ? h("div", { class: "doc-foot" }, extra) : null);
}

export function commissions(info, p) {
  const r = info.rules;
  return h("div", { class: "commissions" }, p.commissions.map((ci) => {
    if (ci == null) return h("div", { class: "firman sealed" }, icon("seal"), h("span", {}, "Sealed commission"));
    const [a, b] = info.commissions[ci];
    const has = (c) => p.posts.includes(c);
    const n = has(a) + has(b);
    return h("div", { class: `firman${n === 2 ? " complete" : ""}` },
      h("div", { class: "firman-cities" }, [a, b].map((c) => h("span", { class: `fc${has(c) ? " done" : ""}` },
        has(c) ? icon("check", { cls: "tick" }) : h("span", { class: "tick-empty" }), info.cities[c].name))),
      h("div", { class: "firman-vp" }, h("span", {}, `both ${r.commission_both}`), h("span", {}, `one ${r.commission_one}`), icon("vp")));
  }));
}

/** Compact merchant summary for the "Merchants" panel. */
export function merchantRow(info, game, p, { bot = null } = {}) {
  const current = p.seat === game.current && game.phase === "play";
  const left = p.dice.filter((d) => !d.placed);
  const ch = p.character ? info.characters[p.character] : null;
  return h("div", { class: `merchant${current ? " current" : ""}${p.passed ? " resting" : ""}`, style: { "--pc": pigment(p.color).fill },
    "data-seat": p.seat },
  h("div", { class: "merchant-head" },
    seal(p, { emblem: p.character ? CHARACTER_EMBLEM[p.character] : null }),
    h("div", { class: "merchant-id" },
      h("strong", {}, p.name, bot ? h("span", { class: "ai-badge", title: `AI opponent (${bot})` }, "AI", h("small", {}, ` · ${bot}`)) : null),
      h("small", {}, ch ? ch.name : "choosing…", " · ", info.cities[p.location].name)),
    p.seat === game.start_player ? h("span", { class: "flag-lead", title: "Leads this round" }, icon("lead"), h("small", {}, "lead")) : null,
    h("span", { class: "vp-badge", role: "img", "aria-label": `${p.vp} renown` }, icon("vp"), h("b", {}, String(p.vp)))),
  resourceCounters(p, { compact: true }),
  h("div", { class: "merchant-foot" },
    h("span", { class: "posts-track", role: "img", "aria-label": `${p.posts.length} of ${info.rules.trading_posts} trading posts` },
      Array.from({ length: info.rules.trading_posts }, (_, i) => h("i", { class: i < p.posts.length ? "on" : "" }))),
    h("span", { class: "small" }, `${p.fulfilled} delivered`),
    game.phase === "play" ? (p.passed
      ? h("span", { class: "tag" }, "resting")
      : h("span", { class: "mini-dice", "aria-label": `${left.length} dice left` }, left.map((d) => dieFace(d.value, p.color, { white: d.white, cls: "mini" }))))
      : null));
}

export function journal(game) {
  const entries = game.log.slice(-80).reverse();
  let lastRound = null;
  const items = [];
  for (const e of entries) {
    if (e.round !== lastRound) {
      items.push(h("li", { class: "round-mark" }, e.round ? `Round ${e.round}` : "Setting out"));
      lastRound = e.round;
    }
    items.push(h("li", { style: e.seat != null ? { "--pc": pigment(game.players[e.seat].color).fill } : null,
      class: e.seat != null ? "by-player" : "" }, e.text));
  }
  return h("ol", { class: "journal-list" }, items);
}

const FINAL_LABELS = {
  during_game: "Journey", commissions: "Commissions", post_majority: "Most posts",
  contract_majority: "Most contracts", coins: "Coins", goods: "Goods",
};

export function finalScore(info, game) {
  const rows = game.final || [];
  const keys = [...new Set([...Object.keys(FINAL_LABELS), ...rows.flatMap((r) => Object.keys(r.breakdown || {}))])]
    .filter((k) => rows.some((r) => k in (r.breakdown || {})));
  const label = (k) => FINAL_LABELS[k] || k.replace(/_/g, " ");
  const winner = rows[0] ? game.players[rows[0].seat] : null;
  return h("section", { class: "panel final", id: "final-score", "data-tour": "final-score" },
    h("div", { class: "final-banner" },
      winner ? seal(winner, { emblem: CHARACTER_EMBLEM[winner.character], cls: "big" }) : null,
      h("div", {}, h("p", { class: "eyebrow" }, "The journey ends"),
        h("h2", {}, rows[0] ? `${rows[0].name} is the greatest merchant of the Silk Road` : "Final scores"))),
    h("div", { class: "table-wrap" }, h("table", { class: "ledger" },
      h("thead", {}, h("tr", {}, h("th", {}, "Merchant"), keys.map((k) => h("th", {}, label(k))), h("th", {}, "Total"))),
      h("tbody", {}, rows.map((r, i) => {
        const p = game.players[r.seat] || {};
        return h("tr", { class: (r.rank ?? i + 1) === 1 ? "winner" : "" },
          h("td", {}, h("span", { class: "who" }, h("span", { class: "rank" }, String(r.rank ?? i + 1)), seal(p), r.name)),
          keys.map((k) => h("td", {}, String(r.breakdown?.[k] ?? 0))),
          h("td", { class: "total" }, icon("vp"), h("b", {}, String(r.total))));
      })))),
    h("a", { class: "btn primary", href: "/" }, "Back to the bazaar"));
}

export function characterCard(info, key, attrs = {}) {
  const c = info.characters[key];
  return h("button", { class: "char-card", ...attrs },
    h("span", { class: "char-medallion" }, icon(CHARACTER_EMBLEM[key] || "vp")),
    h("span", { class: "char-title" }, c.name),
    h("span", { class: "char-text" }, c.text),
    h("span", { class: "char-cta" }, "Travel as this merchant"));
}

/** Content for the "Key" modal — the tap equivalent of every hover hint. */
export function legendContent(info) {
  const rt = info.route_types, r = info.rules;
  return h("div", { class: "key" },
    h("h4", {}, "Goods & resources"),
    h("div", { class: "key-grid" }, [...RES_ORDER, "vp"].map((k) => h("div", { class: "key-item" }, icon(k), h("span", {}, LABELS[k])))),
    h("h4", {}, "Routes"),
    h("div", { class: "key-grid" }, Object.entries(rt).map(([k, v]) => h("div", { class: "key-item" }, icon(k),
      h("span", {}, v.label, " — ", resChips({ camels: v.camels, coins: v.coins }, { empty: "free" }))))),
    h("h4", {}, "Dice"),
    h("div", { class: "key-grid" },
      h("div", { class: "key-item" }, pipFace(4), h("span", {}, "Die value sets how much an action yields (see each stall's table)")),
      h("div", { class: "key-item" }, h("span", { class: "key-dice" }, pipFace(3), pipFace(3)),
        h("span", {}, `Sets: tap 2–3 dice of equal value and place them together where a stall says "sets ≤n" — yield × dice, plus ${(r.set_bonus || [0, 0, 1, 2]).slice(2).map((b) => `+${b}`).join(" / ")}`)),
      h("div", { class: "key-item" }, icon("guide"), h("span", {}, `Guide die: hire for ${r.guide_cost} coins, once per round — wild in a set`)),
      h("div", { class: "key-item" }, icon("reroll"), h("span", {}, `Reroll for ${r.reroll_cost} omen · ±1 for ${r.nudge_cost} omens`)),
      h("div", { class: "key-item" }, icon("coins"), h("span", {}, `Crowded space (a rival's die is there): toll of ${r.toll_per_pip ?? 1} coin per pip, once per placement`)),
      h("div", { class: "key-item" }, icon("post"), h("span", {}, `Trading post (${r.trading_posts} each) — earns that city's income; none in ${(info.no_post_cities || ["constantinople", "changan"]).map((c) => info.cities[c]?.name || c).join(" or ")}`))),
    h("h4", {}, "Scoring at the end"),
    h("ul", { class: "key-list" },
      h("li", {}, `Commissions: ${r.commission_both} renown for posts in both cities, ${r.commission_one} for one`),
      h("li", {}, `Most trading posts: ${r.post_majority.join(" / ")}`),
      h("li", {}, `Most contracts delivered: ${r.contract_majority}`),
      h("li", {}, `1 renown per ${r.coins_per_vp} coins and per ${r.goods_per_vp} goods`),
      h("li", {}, `Reaching Chang'an: ${info.end_city_order_vp.join(" / ")} by arrival order`)));
}
