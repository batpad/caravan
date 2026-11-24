// Original inline-SVG iconography for Caravan Road: an SVG <symbol> sprite injected once,
// plus helpers for icons, custom dice faces and player pigments.
// Style: flat ink outlines with mineral pigments, like a painted manuscript margin.

import { h, s } from "./dom.js";

const INK = "#1d140c";

// Shared silhouette for the two-humped camel (used by the resource icon and caravan pawns).
const CAMEL_BODY = "M5 16.5C5 13 6.5 9.5 8.5 8.6C10.5 7.6 12.6 9 13.4 11.4C14 12.6 15 12.6 15.5 11.2C16.3 8.6 18.6 7.4 20.2 9.2C21 10.2 21.4 12 22.2 13.2C23 12.6 23.8 11 24.2 9C24.6 6.8 25.6 5.6 27.4 5.6C28.6 5.6 29.6 6.4 30 7.4C30.2 8.2 29.4 8.8 28.4 8.8C27.4 8.8 26.8 9.4 26.6 10.6C26.2 13.4 25.4 16.6 23.6 18.6C21.6 20.4 18 20.6 15 20.6C11.4 20.6 8.4 20.4 6.6 19.2C5.4 18.4 5 17.4 5 16.5Z";
const CAMEL_LEGS = "M8.6 19.4L8 29M12.2 20.4L12.6 29M19.6 20.4L20.1 29M23.2 18.6L23.8 29M5.4 15.6L3.6 20";
const camel = (fill, stroke = INK) => `
  <path d="${CAMEL_LEGS}" stroke="${stroke}" stroke-width="3.6" stroke-linecap="round" fill="none"/>
  <path d="${CAMEL_LEGS}" stroke="${fill}" stroke-width="1.8" stroke-linecap="round" fill="none"/>
  <path d="${CAMEL_BODY}" fill="${fill}" stroke="${stroke}" stroke-width="1.3" stroke-linejoin="round"/>
  <circle cx="27.6" cy="6.9" r=".8" fill="${stroke}"/>`;

// 8-pointed star (two squares) — drawn stroke-first so inner seams disappear.
const star8 = (cx, cy, r, fill, stroke, sw = 2) => {
  const a = r * 0.707;
  const sq1 = `M${cx - a} ${cy - a}H${cx + a}V${cy + a}H${cx - a}Z`;
  const sq2 = `M${cx} ${cy - r}L${cx + r} ${cy}L${cx} ${cy + r}L${cx - r} ${cy}Z`;
  return `<path d="${sq1}${sq2}" fill="none" stroke="${stroke}" stroke-width="${sw * 2}" stroke-linejoin="round"/>
          <path d="${sq1}${sq2}" fill="${fill}"/>`;
};

const SYMBOLS = {
  coins: `
    <circle cx="16" cy="16" r="13" fill="#e2b04a" stroke="#5c3d0c" stroke-width="1.8"/>
    <circle cx="16" cy="16" r="9.6" fill="none" stroke="#a7781f" stroke-width="1.2"/>
    <rect x="12.6" y="12.6" width="6.8" height="6.8" fill="#4a300a"/>
    <path d="M16 7.6v2.6M16 21.8v2.6M7.6 16h2.6M21.8 16h2.6" stroke="#8a5f14" stroke-width="1.6"/>
    <path d="M7.4 11.4A10 10 0 0 1 12.6 6.6" stroke="#fff1c2" stroke-width="1.6" fill="none" stroke-linecap="round" opacity=".85"/>`,
  camels: camel("#c99256"),
  caravan: camel("currentColor"),
  spice: `
    <path d="M5.5 19C7.5 12.5 11.2 7.6 16 7.6S24.5 12.5 26.5 19Z" fill="#c8431f" stroke="#5a170a" stroke-width="1.2"/>
    <circle cx="13" cy="13.5" r="1" fill="#f39a4a"/><circle cx="18.5" cy="11.5" r="1" fill="#f39a4a"/>
    <circle cx="20.5" cy="16" r="1" fill="#f39a4a"/><circle cx="11" cy="17" r=".9" fill="#f39a4a"/>
    <circle cx="16" cy="15.6" r=".9" fill="#7c1e0c"/>
    <path d="M3 18.6h26c-.6 6.2-5.6 9.6-13 9.6S3.6 24.8 3 18.6Z" fill="#7b4a26" stroke="#2e1a0b" stroke-width="1.2"/>
    <path d="M5 21.6h22" stroke="#e0ac5e" stroke-width="1.5"/>
    <path d="M9 24.4l2 1.6 2-1.6 2 1.6 2-1.6 2 1.6 2-1.6 2 1.6" stroke="#e0ac5e" stroke-width="1" fill="none"/>`,
  silk: `
    <path d="M7 20.5C9 26 14 23 17.5 27C19.5 29.4 24 28 28.5 29L27.5 23.6C23.4 22.6 20.5 24 18.6 20.5Z" fill="#7a3d8c" stroke="#2a1033" stroke-width="1.1"/>
    <path d="M20 26.4c2 .9 4.6.6 7.6 1.2" stroke="#e6c15a" stroke-width="1.1" fill="none"/>
    <rect x="4" y="7.5" width="18" height="13.5" rx="2.4" fill="#8e4aa1" stroke="#2a1033" stroke-width="1.2"/>
    <path d="M8.6 7.6v13.2M13 7.6v13.2M17.4 7.6v13.2" stroke="#e6c15a" stroke-width="1.3"/>
    <path d="M10.8 7.6v13.2M15.2 7.6v13.2" stroke="#5c2a6c" stroke-width=".9"/>
    <ellipse cx="22" cy="14.25" rx="3.6" ry="6.75" fill="#b673c7" stroke="#2a1033" stroke-width="1.2"/>
    <path d="M22 9.8c1.6 0 2 2 2 4.4s-.6 4.2-2 4.2-1.9-1.8-1.9-4.2.5-2.4 1.5-2.4" fill="none" stroke="#5c2a6c" stroke-width="1"/>`,
  jade: `
    <path fill-rule="evenodd" d="M16 2.8a13.2 13.2 0 1 0 .01 0ZM16 11.4a4.6 4.6 0 1 1-.01 0Z" fill="#3f9a72" stroke="#173f2c" stroke-width="1.3"/>
    <circle cx="16" cy="16" r="8.8" fill="none" stroke="#9ad7b5" stroke-width="1.1"/>
    <g fill="#bfeacf"><circle cx="16" cy="6.2" r="1"/><circle cx="25.8" cy="16" r="1"/><circle cx="16" cy="25.8" r="1"/><circle cx="6.2" cy="16" r="1"/>
    <circle cx="22.9" cy="9.1" r=".8"/><circle cx="22.9" cy="22.9" r=".8"/><circle cx="9.1" cy="22.9" r=".8"/><circle cx="9.1" cy="9.1" r=".8"/></g>
    <path d="M6.4 11.2A11 11 0 0 1 11.4 5.6" stroke="#e5fff0" stroke-width="1.5" fill="none" stroke-linecap="round" opacity=".7"/>`,
  omens: `
    <circle cx="16" cy="16" r="13.2" fill="#2449a3" stroke="#0e1f4e" stroke-width="1.4"/>
    <circle cx="16" cy="16" r="9.4" fill="#f6f1e2"/>
    <circle cx="16" cy="16" r="6.2" fill="#62acdc"/>
    <circle cx="16" cy="16" r="3.2" fill="#0d1120"/>
    <ellipse cx="11.6" cy="10.4" rx="2.4" ry="1.4" fill="#fff" opacity=".8" transform="rotate(-35 11.6 10.4)"/>`,
  vp: `${star8(16, 16, 14, "#e3b23c", "#5c3d0c", 1.1)}
    <circle cx="16" cy="16" r="6" fill="#b8322a" stroke="#5c3d0c" stroke-width="1.2"/>
    <circle cx="16" cy="16" r="2.4" fill="#f5d27a"/>`,
  post: `
    <path d="M8 29.5V13.5L6 11.4V5.8h4v2.6h3V5.8h6v2.6h3V5.8h4v5.6l-2 2.1v16Z" fill="currentColor" stroke="${INK}" stroke-width="1.4" stroke-linejoin="round"/>
    <path d="M13.4 29.5v-5.6a2.6 2.6 0 0 1 5.2 0v5.6Z" fill="${INK}"/>
    <path d="M8 15h16" stroke="${INK}" stroke-width="1" opacity=".5"/>`,
  // --- interface glyphs (single colour, currentColor)
  reroll: `<path d="M25 11.5A10 10 0 0 0 7.2 12M7 20.5A10 10 0 0 0 24.8 20" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>
    <path d="M26.5 5.5v7h-7M5.5 26.5v-7h7" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  tent: `<path d="M3 27L16 5l13 22Z" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/>
    <path d="M16 5v22M12 27l4-9 4 9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M2 27h28" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>`,
  hourglass: `<path d="M8 4h16M8 28h16M10 4c0 7 12 7 12 12S10 21 10 28M22 4c0 7-12 7-12 12s12 5 12 12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M12.5 25.5h7L16 22Z" fill="currentColor"/>`,
  guide: `<rect x="5" y="5" width="22" height="22" rx="5" fill="#fbf6ea" stroke="currentColor" stroke-width="2.2"/>
    <circle cx="11" cy="11" r="2" fill="currentColor"/><circle cx="21" cy="21" r="2" fill="currentColor"/>
    <path d="M21 8v6M18 11h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
  book: `<path d="M16 8C12 5 7 5 3.5 6.5V26C7 24.6 12 24.6 16 27.5C20 24.6 25 24.6 28.5 26V6.5C25 5 20 5 16 8ZM16 8v19.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>`,
  close: `<path d="M8 8l16 16M24 8L8 24" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>`,
  check: `<path d="M6 17l6.5 6.5L26 9" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>`,
  arrow: `<path d="M3 16h21" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>
    <path d="M17 8.5l9 7.5-9 7.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="5" cy="16" r="2.6" fill="currentColor"/>`,
  minus: `<path d="M7 16h18" stroke="currentColor" stroke-width="3.4" stroke-linecap="round"/>`,
  plus: `<path d="M7 16h18M16 7v18" stroke="currentColor" stroke-width="3.4" stroke-linecap="round"/>`,
  lead: `<path d="M8 29V4" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M9 5h16l-4 5.5 4 5.5H9Z" fill="currentColor"/>`,
  scroll: `<path d="M8 5h17a3 3 0 0 1 0 6h-2v14a3 3 0 0 1-3 3H6a3 3 0 0 1 0-6h2Z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>
    <path d="M12 12h7M12 16h7M12 20h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
  // --- terrain glyphs for the legend
  road: `<path d="M2 22C9 22 10 10 17 10S26 18 30 14" fill="none" stroke="#6b4423" stroke-width="5" stroke-linecap="round"/>
    <path d="M2 22C9 22 10 10 17 10S26 18 30 14" fill="none" stroke="#efe0bb" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="3 3"/>`,
  desert: `<path d="M2 24c5-7 10-7 14 0M14 24c5-9 11-9 16 0" fill="#e6bd6c" stroke="#8a5a1c" stroke-width="1.6"/>
    <g fill="#8a5a1c"><circle cx="8" cy="12" r="1.4"/><circle cx="13" cy="9" r="1.4"/><circle cx="18" cy="11" r="1.4"/><circle cx="23" cy="8" r="1.4"/></g>`,
  mountain: `<path d="M2 27L12 8l6 10 3-5 9 14Z" fill="#b9a382" stroke="#3b2c20" stroke-width="1.6" stroke-linejoin="round"/>
    <path d="M12 8l-2 19M12 8l-5 19" stroke="#3b2c20" stroke-width="1"/><path d="M12 8l-2.6 5 2 1 1.6-2 1.6 2" fill="#fbf6ea"/>`,
  sea: `<path d="M2 12q3.5-4 7 0t7 0 7 0 7 0M2 20q3.5-4 7 0t7 0 7 0 7 0M6 28q3.5-4 7 0t7 0 7 0" fill="none" stroke="#2d6f8f" stroke-width="2" stroke-linecap="round"/>`,
  // --- character emblems
  compass: `${star8(16, 16, 13, "#f3e6c4", INK, .9)}<path d="M16 2.5L19 16 16 29.5 13 16Z" fill="#b8322a" stroke="${INK}" stroke-width="1"/>
    <path d="M2.5 16L16 13 29.5 16 16 19Z" fill="#2b4f9e" stroke="${INK}" stroke-width="1"/><circle cx="16" cy="16" r="2.2" fill="#e3b23c" stroke="${INK}"/>`,
  scales: `<path d="M16 4v23M9 27h14M6 9h20" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M6 9l-4 9h8ZM26 9l-4 9h8Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
    <path d="M2 18a4 2.6 0 0 0 8 0ZM22 18a4 2.6 0 0 0 8 0Z" fill="currentColor"/><circle cx="16" cy="4" r="2" fill="currentColor"/>`,
  seal: `<path d="M16 3.5c2.2 0 2.8 2 4.6 2.6s3.6-.6 5 .9-.2 3.3.6 5.1 2.8 2.4 2.8 4.6-2 2.8-2.6 4.6.6 3.6-.9 5-3.3-.2-5.1.6-2.4 2.8-4.6 2.8-2.8-2-4.6-2.6-3.6.6-5-.9.2-3.3-.6-5.1-2.8-2.4-2.8-4.6 2-2.8 2.6-4.6-.6-3.6.9-5 3.3.2 5.1-.6S13.8 3.5 16 3.5Z" fill="#a8281f" stroke="#4d0f0a" stroke-width="1.2"/>
    <circle cx="16" cy="16" r="7" fill="none" stroke="#e48a72" stroke-width="1.2"/>`,
  crate: `<rect x="4" y="11" width="24" height="16" rx="1.5" fill="#b9874a" stroke="${INK}" stroke-width="1.6"/>
    <path d="M4 19h24M12 11v16M20 11v16" stroke="${INK}" stroke-width="1.2"/>
    <path d="M7 11l4-6h10l4 6" fill="#d6a866" stroke="${INK}" stroke-width="1.4" stroke-linejoin="round"/>`,
  footprints: `<g fill="currentColor"><ellipse cx="9" cy="23" rx="3" ry="4.2"/><ellipse cx="17" cy="15" rx="3" ry="4.2"/><ellipse cx="25" cy="7" rx="3" ry="4.2"/></g>
    <path d="M2 30c6-3 10-3 14 0s8 3 14 0" fill="none" stroke="currentColor" stroke-width="1.6"/>`,
};

let injected = false;
/** Inject the sprite once (idempotent). */
export function ensureSprite() {
  if (injected) return;
  injected = true;
  const defs = Object.entries(SYMBOLS).map(([k, body]) => `<symbol id="ic-${k}" viewBox="0 0 32 32">${body}</symbol>`).join("");
  const holder = document.createElement("div");
  holder.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true"><defs>${defs}</defs></svg>`;
  document.body.prepend(holder.firstChild);
}

export const LABELS = {
  coins: "Coins", camels: "Camels", spice: "Spice", silk: "Silk", jade: "Jade", omens: "Omens", vp: "Renown (VP)",
};

/** An icon from the sprite. `label` makes it announced; otherwise decorative. */
export function icon(name, { cls = "", label = null } = {}) {
  ensureSprite();
  const known = name in SYMBOLS;
  return s("svg", { class: `ic ic-${name} ${cls}`.trim(), viewBox: "0 0 32 32", role: label ? "img" : null,
    "aria-label": label, "aria-hidden": label ? null : "true", focusable: "false" },
  label ? s("title", {}, label) : null,
  known ? s("use", { href: `#ic-${name}` }) : s("text", { x: 16, y: 21, "text-anchor": "middle", "font-size": 14 }, name.slice(0, 2)));
}

// ------------------------------------------------------------------ player pigments
// The server gives plain hex colours; we render them as mineral pigments that suit the art.
const PIGMENTS = {
  "#c0392b": { fill: "#b5302a", pip: "#fbf1dc", dark: "#5a1410", name: "Vermilion" },
  "#2471a3": { fill: "#2c4f9e", pip: "#fbf1dc", dark: "#111f45", name: "Lapis" },
  "#239b56": { fill: "#2c7d57", pip: "#fbf1dc", dark: "#0f3523", name: "Jade" },
  "#b7950b": { fill: "#d79c1d", pip: "#2a1708", dark: "#5c3d06", name: "Saffron" },
};
export function pigment(color) {
  return PIGMENTS[(color || "").toLowerCase()] || { fill: color || "#888", pip: "#fff", dark: "#222", name: "" };
}

// ------------------------------------------------------------------ dice
const PIP_AT = { tl: [11, 11], tr: [29, 11], ml: [11, 20], c: [20, 20], mr: [29, 20], bl: [11, 29], br: [29, 29] };
const FACES = [[], ["c"], ["tl", "br"], ["tl", "c", "br"], ["tl", "tr", "bl", "br"], ["tl", "tr", "c", "bl", "br"], ["tl", "tr", "ml", "mr", "bl", "br"]];

/** A die face as SVG. White (guide) dice are ivory with pips in the owner's pigment. */
export function dieFace(value, color, { white = false, cls = "" } = {}) {
  const pg = pigment(color);
  const body = white ? "#fbf6ea" : pg.fill;
  const pip = white ? pg.fill : pg.pip;
  const edge = white ? pg.fill : pg.dark;
  return s("svg", { class: `dieface ${cls}`.trim(), viewBox: "0 0 40 40", "aria-hidden": "true", focusable: "false" },
    s("rect", { x: 2, y: 3, width: 36, height: 36, rx: 8, fill: edge }),
    s("rect", { x: 2, y: 1.5, width: 36, height: 35, rx: 8, fill: body, stroke: edge, "stroke-width": white ? 2.4 : 1.6 }),
    s("path", { d: "M8 4.5h24", stroke: "#fff", "stroke-opacity": white ? 0 : .35, "stroke-width": 2, "stroke-linecap": "round" }),
    (FACES[value] || []).map((k) => s("circle", { cx: PIP_AT[k][0], cy: PIP_AT[k][1] - 1, r: value === 1 ? 4.6 : 3.7, fill: pip })),
    !FACES[value] ? s("text", { x: 20, y: 26, "text-anchor": "middle", "font-size": 18, "font-weight": 700, fill: pip }, String(value)) : null,
  );
}

/** A neutral die outline (for tables: "a die showing n"). */
export function pipFace(value, cls = "") {
  return s("svg", { class: `pipface ${cls}`.trim(), viewBox: "0 0 40 40", "aria-hidden": "true", focusable: "false" },
    s("rect", { x: 2.5, y: 2.5, width: 35, height: 35, rx: 8, fill: "none", stroke: "currentColor", "stroke-width": 3 }),
    (FACES[value] || []).map((k) => s("circle", { cx: PIP_AT[k][0], cy: PIP_AT[k][1], r: 4, fill: "currentColor" })));
}

export const CHARACTER_EMBLEM = {
  cartographer: "compass", breeder: "camels", seer: "omens", heiress: "silk",
  moneylender: "scales", guildmaster: "seal", pathfinder: "footprints", quartermaster: "crate",
};

// ------------------------------------------------------------------ resource chips

/** Render a resource dict like {silk: 2, vp: 3} as count+icon chips (labels for screen readers). */
export function resChips(res, { empty = "—", repeat = false } = {}) {
  const entries = Object.entries(res || {}).filter(([, v]) => v);
  if (!entries.length) return h("span", { class: "chips empty" }, empty);
  return h("span", { class: `chips${repeat ? " repeat" : ""}` }, entries.map(([k, v]) => {
    const label = `${v} ${LABELS[k] || k}`;
    if (repeat && v <= 5) {
      return h("span", { class: `chip rep chip-${k}`, role: "img", "aria-label": label },
        Array.from({ length: v }, () => icon(k)));
    }
    return h("span", { class: `chip chip-${k}`, role: "img", "aria-label": label },
      h("b", { "aria-hidden": "true" }, String(v)), icon(k));
  }));
}
