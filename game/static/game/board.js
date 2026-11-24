// SVG route map. Pure rendering: callers pass in what is tappable.
// Static illustration comes from terrain.js; this draws routes, cities, posts and caravans.

import { h, s } from "./dom.js";
import { icon, pigment } from "./icons.js";
import { MAP_H, MAP_W, terrainMarkup } from "./terrain.js";

const ROUTE_LAYERS = {
  road: [{ stroke: "#3a2a1c", width: 7 }, { stroke: "#ead6a6", width: 3.4 }],
  desert: [{ stroke: "#e7bf73", width: 8, opacity: .55 }, { stroke: "#8a5a1c", width: 5, dash: "0.1 10" }],
  mountain: [{ stroke: "#f3e6c4", width: 6.5 }, { stroke: "#3a2a1c", width: 3.2, dash: "10 5", cap: "butt" }],
  sea: [{ stroke: "#e2efe6", width: 6.5, opacity: .8 }, { stroke: "#1f4f5e", width: 2.6, dash: "9 6" }],
};

// Hand-placed label offsets where the default (centred above) collides with routes or the frame.
const LABEL_POS = {
  constantinople: { dx: -50, dy: -29, anchor: "start" },
  changan: { dx: 22, dy: -29, anchor: "end" },
  samarkand: { dx: 30, dy: 6, anchor: "start" },
  kashgar: { dx: -28, dy: 6, anchor: "end" },
};
// Where along a route its cost medallion sits (default: midpoint).
const MEDALLION_T = { "constantinople|trebizond": 0.72 };

const use = (name, x, y, size, attrs = {}) =>
  s("use", { href: `#ic-${name}`, x: x - size / 2, y: y - size / 2, width: size, height: size, ...attrs });

/** A small cost medallion: [{n, icon}] pairs laid out horizontally. */
function costBadge(x, y, parts, cls = "") {
  const ICON = 17, GAP = 3, NUM = 9;
  const w = parts.reduce((acc, p) => acc + NUM + ICON + GAP, 0) + 8;
  const g = s("g", { class: `cost-badge ${cls}`.trim(), transform: `translate(${x - w / 2} ${y - 11})` },
    s("rect", { x: 0, y: 0, width: w, height: 22, rx: 11, class: "cost-bg" }));
  let cx = 5;
  for (const p of parts) {
    g.append(s("text", { x: cx + NUM / 2, y: 16, "text-anchor": "middle", class: "cost-num" }, String(p.n)));
    cx += NUM;
    g.append(use(p.icon, cx + ICON / 2, 11, ICON));
    cx += ICON + GAP;
  }
  return g;
}

function costParts({ camels = 0, coins = 0 }) {
  const parts = [];
  if (camels) parts.push({ n: camels, icon: "camels" });
  if (coins) parts.push({ n: coins, icon: "coins" });
  return parts.length ? parts : [{ n: 0, icon: "camels" }];
}

function cityGlyph(id, c) {
  const end = id === "changan", start = id === "constantinople";
  const g = s("g", { class: "city-glyph" });
  g.append(s("circle", { cx: 0, cy: 0, r: end || start ? 24 : 20, class: "city-ring-outer" }));
  g.append(s("circle", { cx: 0, cy: 0, r: end || start ? 20 : 16.5, class: "city-ground" }));
  if (end) {
    // pagoda: three tiers with upswept eaves
    g.append(s("path", { class: "bld", d: "M-7 12V4H7V12Z M-5 4V-3H5V4Z M-3 -3V-9H3V-3Z" }));
    g.append(s("path", { class: "roof-red", d: "M-14 5C-9 4 -6 2 -4 0H4C6 2 9 4 14 5C9 6 -9 6 -14 5Z M-11 -2C-7 -3 -5 -4 -3 -6H3C5 -4 7 -3 11 -2C7 -1 -7 -1 -11 -2Z M-8 -9C-5 -10 -3 -11 -2 -13H2C3 -11 5 -10 8 -9C5 -8 -5 -8 -8 -9Z" }));
    g.append(s("path", { d: "M0 -13V-17", stroke: "#1d140c", "stroke-width": 1.4 }));
  } else if (start) {
    g.append(s("path", { class: "bld", d: "M-12 12V2H12V12Z" }));
    g.append(s("path", { class: "dome", d: "M-9 2A9 9 0 0 1 9 2Z" }));
    g.append(s("path", { class: "dome", d: "M-14 4A3.4 3.4 0 0 1 -7.5 4Z M7.5 4A3.4 3.4 0 0 1 14 4Z" }));
    g.append(s("path", { d: "M-16 12V-6M16 12V-6", stroke: "#1d140c", "stroke-width": 2.2 }));
    g.append(s("path", { d: "M0 -7V-12", stroke: "#1d140c", "stroke-width": 1.4 }));
    g.append(s("path", { d: "M-3 12V7A3 3 0 0 1 3 7V12Z", fill: "#1d140c" }));
  } else {
    g.append(s("path", { class: "bld", d: "M-9 10V1H9V10Z" }));
    g.append(s("path", { class: "dome", d: "M-6.5 1C-6.5 -6 -2 -8 0 -10C2 -8 6.5 -6 6.5 1Z" }));
    g.append(s("path", { d: "M0 -10V-13.5", stroke: "#1d140c", "stroke-width": 1.3 }));
    g.append(s("path", { d: "M-2.4 10V6A2.4 2.4 0 0 1 2.4 6V10Z", fill: "#1d140c" }));
  }
  return g;
}

/**
 * @param {object} info static data
 * @param {object} game public game view
 * @param {object} opts {
 *   reachable: {city: [options]}, onCity(cityId), placing: bool,
 *   cityTargets: Set of cities where a city action can be used now, mySeat }
 */
export function renderMap(info, game, opts = {}) {
  const { cities, routes, route_types: rt } = info;
  const reachable = opts.reachable || {};
  const cityTargets = opts.cityTargets || new Set();
  const placing = !!opts.placing;
  const svg = s("svg", { viewBox: `0 0 ${MAP_W} ${MAP_H}`, class: `map${placing ? " placing" : ""}`,
    role: "group", "aria-label": "Map of the Silk Road. Tap a city for details." });
  const art = s("g", { class: "terrain" });
  art.innerHTML = terrainMarkup();
  svg.append(art);

  // routes
  const routeLayer = s("g", { class: "routes" });
  const medallions = s("g", { class: "medallions" });
  for (const [a, b, kind] of routes) {
    const A = cities[a], B = cities[b];
    for (const L of ROUTE_LAYERS[kind] || ROUTE_LAYERS.road) {
      routeLayer.append(s("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, stroke: L.stroke, "stroke-width": L.width,
        "stroke-dasharray": L.dash, "stroke-linecap": L.cap || "round", opacity: L.opacity }));
    }
    const cost = rt[kind] || {};
    const mt = MEDALLION_T[`${a}|${b}`] ?? 0.5;
    medallions.append(costBadge(A.x + (B.x - A.x) * mt, A.y + (B.y - A.y) * mt, costParts(cost), `route-${kind}`));
  }
  svg.append(routeLayer);

  // highlight every leg of every reachable path
  const legs = new Set();
  for (const options of Object.values(reachable)) {
    for (const o of options) {
      for (let i = 1; i < o.path.length; i++) legs.add([o.path[i - 1], o.path[i]].sort().join("|"));
    }
  }
  if (legs.size) {
    const hl = s("g", { class: "path-glow" });
    for (const leg of legs) {
      const [a, b] = leg.split("|");
      hl.append(s("line", { x1: cities[a].x, y1: cities[a].y, x2: cities[b].x, y2: cities[b].y }));
    }
    svg.append(hl);
  }
  svg.append(medallions);

  const players = game.players;
  const me = opts.mySeat != null ? players[opts.mySeat] : null;
  for (const [id, c] of Object.entries(cities)) {
    const opt = reachable[id];
    const cityAct = cityTargets.has(id);
    const target = !!opt || cityAct;
    const isEnd = id === "changan", isStart = id === "constantinople";
    const big = isEnd || isStart;
    const owners = players.filter((p) => p.posts.includes(id));
    const here = players.filter((p) => p.location === id);
    const label = [c.name, c.post_vp ? `${c.post_vp} VP post` : null,
      opt ? "reachable — tap to travel" : null, cityAct ? "your city action — tap to trade" : null,
      owners.length ? `posts: ${owners.map((p) => p.name).join(", ")}` : null,
      here.length ? `caravans: ${here.map((p) => p.name).join(", ")}` : null].filter(Boolean).join(". ");
    const g = s("g", {
      class: `city${target ? " target" : ""}${opt ? " reachable" : ""}${cityAct ? " can-trade" : ""}${me?.location === id ? " mine" : ""}`,
      transform: `translate(${c.x} ${c.y})`, "data-city": id,
      tabindex: opts.onCity ? 0 : null, role: opts.onCity ? "button" : null, "aria-label": label,
      onclick: opts.onCity ? () => opts.onCity(id) : null,
      onkeydown: opts.onCity ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); opts.onCity(id); } } : null,
    });
    // generous invisible hit zone (≈ 48px+ on an iPad)
    g.append(s("circle", { cx: 0, cy: 0, r: 44, class: "hit" }));
    if (target) {
      g.append(s("circle", { cx: 0, cy: 0, r: big ? 36 : 32, class: "target-glow" }));
      g.append(s("circle", { cx: 0, cy: 0, r: big ? 30 : 26, class: "target-ring" }));
    }
    if (me?.location === id) {
      g.append(s("circle", { cx: 0, cy: 0, r: big ? 27 : 23, class: "you-ring", style: `stroke:${pigment(me.color).fill}` }));
    }
    g.append(cityGlyph(id, c));
    if (c.post_vp) {
      const vg = s("g", { class: "post-vp", transform: `translate(${big ? 18 : 15} ${big ? 14 : 12})` });
      vg.append(use("vp", 0, 0, 24));
      vg.append(s("circle", { cx: 0, cy: 0, r: 6.5, fill: "#b5302a" }));
      vg.append(s("text", { x: 0, y: 4, "text-anchor": "middle", class: "post-vp-num" }, String(c.post_vp)));
      g.append(vg);
    }
    if (isEnd) {
      const vg = s("g", { class: "post-vp", transform: "translate(22 16)" });
      vg.append(use("vp", 0, 0, 26));
      g.append(vg);
    }
    const nameY = -(big ? 29 : 25);
    const lp = LABEL_POS[id] || { dx: 0, dy: nameY, anchor: "middle" };
    g.append(s("text", { x: lp.dx, y: lp.dy, class: `city-name${big ? " big" : ""}`, "text-anchor": lp.anchor }, c.name));

    // trading posts: little towers in the owner's pigment
    owners.forEach((p, i) => {
      const x = (i - (owners.length - 1) / 2) * 17;
      g.append(use("post", x, (big ? 32 : 28), 18, { style: `color:${pigment(p.color).fill}`, class: "post-token" }));
    });
    // caravans here
    here.forEach((p, i) => {
      const x = (big ? 26 : 22) + i * 11, y = -10 - (i % 2) * 3;
      g.append(s("ellipse", { cx: x + 1, cy: y + 13, rx: 11, ry: 3, class: "token-shadow" }));
      g.append(use("caravan", x, y, 28, { style: `color:${pigment(p.color).fill}`, class: "caravan-token" }));
    });
    if (opt) {
      const best = opt.reduce((a, b) => (a.camels + a.coins <= b.camels + b.coins ? a : b));
      const below = c.y < 400;
      g.append(costBadge(0, below ? (owners.length ? 52 : 42) : nameY - 22, costParts(best), "reach-cost"));
    } else if (cityAct) {
      const below = c.y < 400;
      const tg = s("g", { class: "trade-tag", transform: `translate(0 ${below ? (owners.length ? 52 : 42) : nameY - 22})` },
        s("rect", { x: -26, y: -11, width: 52, height: 22, rx: 11 }),
        s("text", { x: 0, y: 5, "text-anchor": "middle" }, "Trade"));
      g.append(tg);
    }
    svg.append(g);
  }
  return h("div", { class: "map-wrap" }, svg);
}

export function mapLegend(info) {
  const rt = info.route_types;
  const costs = (v) => [v.camels ? [h("b", {}, v.camels), icon("camels")] : null, v.coins ? [h("b", {}, v.coins), icon("coins")] : null];
  return h("div", { class: "legend" },
    Object.entries(rt).map(([k, v]) => h("span", { class: "legend-item" }, icon(k, { cls: "legend-glyph" }),
      h("span", { class: "legend-label" }, v.label), h("span", { class: "legend-cost" }, costs(v)))),
    h("span", { class: "legend-item" }, icon("vp", { cls: "legend-glyph" }), h("span", { class: "legend-label" }, "Renown for a new post")),
    h("span", { class: "legend-item hint" }, "Tap a city for its income and trade."));
}
