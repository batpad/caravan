// Static, hand-placed map illustration (seas, coasts, rivers, dunes, mountain ranges,
// portolan rhumb lines, compass rose, cartouche, frame). Built once as an SVG string and
// reused on every render — the dynamic board (routes, cities, tokens) is drawn by board.js.
// Coordinates share the city coordinate space from data.py (1150 × 520).

export const MAP_W = 1150;
export const MAP_H = 520;

// Deterministic pseudo-random so the art is identical on every client.
function rng(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const r1 = (n) => Math.round(n * 10) / 10;

const SEAS = {
  black: "M84 160C120 156 160 146 195 130C220 118 236 110 248 108C262 106 276 104 290 96C312 84 318 60 296 44C260 22 180 18 120 30C80 40 52 70 56 104C58 130 66 152 84 160Z",
  med: "M0 205C30 210 70 235 105 255C130 268 148 285 150 305C152 335 135 365 110 390C85 415 50 440 0 450Z",
  caspian: "M410 12C440 2 470 20 466 60C462 90 446 110 456 140C466 170 450 190 426 188C402 186 396 160 405 130C412 100 396 80 398 50C400 30 400 16 410 12Z",
  gulf: "M318 392C340 398 370 420 395 440C410 452 425 462 432 470C445 478 470 482 500 490C560 500 620 495 690 520L330 520C345 490 330 470 322 450C312 428 305 400 318 392Z",
  aral: "M512 40C530 30 556 40 554 60C552 76 534 82 518 76C502 70 498 50 512 40Z",
  yellow: "M1150 170C1135 220 1142 280 1128 340C1118 390 1132 450 1150 500Z",
};
const LAKES = [[905, 262, 9, 6], [966, 252, 10, 6]];

const RIVERS = [
  "M332 196C322 250 312 300 306 330C312 362 326 384 340 398",
  "M246 214C258 262 280 306 300 336",
  "M660 330C640 292 602 262 578 218C562 182 546 124 532 80",
  "M748 140C708 118 664 104 556 62",
  "M700 398C694 430 704 470 690 516",
  "M948 332C976 304 996 284 1020 272C1058 248 1088 262 1100 298C1110 336 1128 332 1146 322",
  "M790 262C822 282 868 292 898 268",
];

// Mountain ranges: [x, y, size]
const MOUNTAINS = [
  [335, 58, 18], [358, 70, 15], [382, 58, 14],
  [128, 214, 16], [158, 226, 19], [190, 220, 15], [214, 238, 14],
  [284, 142, 17], [308, 128, 21], [330, 152, 16], [300, 166, 14],
  [386, 248, 16], [402, 278, 20], [418, 306, 17], [396, 318, 14], [428, 342, 16], [410, 372, 13],
  [584, 328, 17], [610, 340, 21], [636, 326, 16], [600, 384, 15], [630, 390, 14],
  [706, 238, 17], [730, 252, 22], [754, 236, 16], [712, 284, 18], [738, 292, 21], [762, 274, 15], [700, 322, 14],
  [762, 152, 15], [790, 164, 19], [820, 150, 17], [850, 166, 16], [880, 150, 15], [906, 162, 13],
  [780, 492, 15], [815, 480, 19], [850, 494, 15], [885, 476, 18], [920, 492, 16], [955, 480, 15], [990, 494, 13],
  [946, 290, 14], [972, 302, 13], [1000, 376, 14], [1026, 386, 12],
];

// Dune fields: [cx, cy, spreadX, spreadY, count, seed]
const DESERTS = [
  [235, 452, 78, 40, 11, 3], [548, 178, 46, 26, 7, 5], [652, 70, 50, 22, 6, 7],
  [482, 330, 36, 26, 5, 11], [856, 300, 56, 46, 13, 13], [1040, 168, 80, 40, 11, 17],
  [1090, 236, 30, 18, 4, 19], [545, 440, 34, 18, 4, 23],
];

// Soft colour washes under the terrain (radial gradients, no filters → cheap on tablets).
const WASHES = [
  ["sand", 235, 450, 120, 70], ["sand", 548, 180, 80, 50], ["sand", 856, 300, 95, 80], ["sand", 1040, 175, 120, 70],
  ["sand", 652, 72, 70, 36], ["sand", 482, 330, 60, 45],
  ["umber", 730, 270, 90, 80], ["umber", 410, 310, 50, 80], ["umber", 610, 355, 60, 45], ["umber", 885, 488, 130, 34],
  ["umber", 835, 158, 95, 30], ["green", 300, 300, 60, 70], ["green", 1060, 300, 80, 60], ["green", 590, 160, 60, 70],
];

function mountain(x, y, sz) {
  const w = sz * 0.95, hgt = sz * 1.25;
  const peak = [x + sz * 0.05, y - hgt];
  const L = [x - w, y], R = [x + w, y];
  const shade = `M${r1(peak[0])} ${r1(peak[1])}L${r1(R[0])} ${y}L${r1(x + sz * 0.15)} ${y}Z`;
  const hatch = [];
  for (let i = 1; i <= 4; i++) {
    const t = i / 5;
    const ax = peak[0] + (R[0] - peak[0]) * t, ay = peak[1] + (y - peak[1]) * t;
    hatch.push(`M${r1(ax)} ${r1(ay)}l${r1(-sz * 0.28)} ${r1(sz * 0.5 * (1 - t) + 2)}`);
  }
  const snow = sz > 15 ? `<path d="M${r1(peak[0])} ${r1(peak[1])}l${r1(-sz * .28)} ${r1(sz * .36)} ${r1(sz * .14)} ${r1(-sz * .06)} ${r1(sz * .1)} ${r1(sz * .1)} ${r1(sz * .14)} ${r1(-sz * .12)}Z" fill="#fbf4e2"/>` : "";
  return `<path d="M${r1(L[0])} ${y}L${r1(peak[0])} ${r1(peak[1])}L${r1(R[0])} ${y}Z" fill="#cdb58c"/>
    <path d="${shade}" fill="#9c7f55"/>${snow}
    <path d="${hatch.join("")}" stroke="#4a3624" stroke-width=".9" fill="none" opacity=".7"/>
    <path d="M${r1(L[0])} ${y}L${r1(peak[0])} ${r1(peak[1])}L${r1(R[0])} ${y}" fill="none" stroke="#3a2a1c" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>`;
}

function duneField([cx, cy, sx, sy, n, seed]) {
  const rand = rng(seed);
  let out = "";
  for (let i = 0; i < n; i++) {
    const x = cx + (rand() * 2 - 1) * sx, y = cy + (rand() * 2 - 1) * sy;
    const w = 12 + rand() * 12, hgt = 5 + rand() * 4;
    out += `<path d="M${r1(x - w)} ${r1(y)}Q${r1(x - w * .2)} ${r1(y - hgt * 2)} ${r1(x + w)} ${r1(y)}" fill="#e7bf73" stroke="#8a5a1c" stroke-width="1.2" stroke-linecap="round"/>`;
    out += `<path d="M${r1(x - w * .1)} ${r1(y - hgt * .95)}Q${r1(x + w * .35)} ${r1(y - hgt * .4)} ${r1(x + w * .8)} ${r1(y)}" fill="none" stroke="#b88435" stroke-width="1"/>`;
    for (let k = 0; k < 4; k++) {
      out += `<circle cx="${r1(x - w * .7 + rand() * w * 1.4)}" cy="${r1(y + 2 + rand() * 4)}" r=".9" fill="#8a5a1c" opacity=".6"/>`;
    }
  }
  return out;
}

function waves(seaKey, pts) {
  return pts.map(([x, y]) => `<path d="M${x} ${y}q4 -4 8 0t8 0" fill="none" stroke="#2f6878" stroke-width="1.2" stroke-linecap="round" opacity=".55"/>`).join("");
}

function compassRose(cx, cy, r) {
  const pts = (rad, inner, rot) => {
    const out = [];
    for (let i = 0; i < 16; i++) {
      const a = (Math.PI / 8) * i + rot, rr = i % 2 ? inner : rad;
      out.push(`${r1(cx + Math.cos(a) * rr)} ${r1(cy + Math.sin(a) * rr)}`);
    }
    return `M${out.join("L")}Z`;
  };
  return `<g class="compass">
    <circle cx="${cx}" cy="${cy}" r="${r + 6}" fill="none" stroke="#3a2a1c" stroke-width="1"/>
    <circle cx="${cx}" cy="${cy}" r="${r + 2}" fill="none" stroke="#3a2a1c" stroke-width=".6" stroke-dasharray="2 3"/>
    <path d="${pts(r * .72, r * .2, Math.PI / 8 - Math.PI / 2)}" fill="#2c4f9e" stroke="#1d140c" stroke-width=".8" opacity=".9"/>
    <path d="${pts(r, r * .22, -Math.PI / 2)}" fill="#e3b23c" stroke="#1d140c" stroke-width="1"/>
    <path d="M${cx} ${cy - r}L${cx + r * .12} ${cy}L${cx} ${cy + r}Z" fill="#b5302a"/>
    <circle cx="${cx}" cy="${cy}" r="4" fill="#fbf4e2" stroke="#1d140c"/>
    <text x="${cx}" y="${cy - r - 10}" text-anchor="middle" class="map-compass-n">N</text>
  </g>`;
}

function rhumbLines(cx, cy) {
  let d = "";
  for (let i = 0; i < 16; i++) {
    const a = (Math.PI / 8) * i;
    d += `M${cx} ${cy}L${r1(cx + Math.cos(a) * 1400)} ${r1(cy + Math.sin(a) * 1400)}`;
  }
  return `<path d="${d}" stroke="#5a3b1a" stroke-width=".7" opacity=".14" fill="none"/>`;
}

function frame() {
  const W = MAP_W, H = MAP_H;
  const corner = (x, y) => `<g transform="translate(${x} ${y})">
    <rect x="-11" y="-11" width="22" height="22" fill="#1b2a57" stroke="#c99a3a" stroke-width="1.5"/>
    <path d="M0 -8L2.4 -2.4 8 0 2.4 2.4 0 8 -2.4 2.4 -8 0 -2.4 -2.4Z" fill="#e3b23c"/></g>`;
  return `<g class="frame" pointer-events="none">
    <rect x="3" y="3" width="${W - 6}" height="${H - 6}" fill="none" stroke="#1b2a57" stroke-width="6"/>
    <rect x="3" y="3" width="${W - 6}" height="${H - 6}" fill="none" stroke="#c99a3a" stroke-width="1.4" stroke-dasharray="1 5" stroke-linecap="round"/>
    <rect x="10" y="10" width="${W - 20}" height="${H - 20}" fill="none" stroke="#3a2a1c" stroke-width="1"/>
    ${corner(8, 8)}${corner(W - 8, 8)}${corner(8, H - 8)}${corner(W - 8, H - 8)}
  </g>`;
}

function cartouche(x, y) {
  return `<g class="cartouche" transform="translate(${x} ${y})">
    <path d="M-120 -20H120L132 0 120 20H-120L-132 0Z" fill="#f4e7c4" stroke="#3a2a1c" stroke-width="1.4"/>
    <path d="M-114 -15H114L123 0 114 15H-114L-123 0Z" fill="none" stroke="#b5302a" stroke-width=".9"/>
    <text x="0" y="-1" text-anchor="middle" class="map-title">The Road to Chang'an</text>
    <text x="0" y="12" text-anchor="middle" class="map-sub">a merchant's chart of the silk routes</text>
  </g>`;
}

function ship(x, y) {
  return `<g transform="translate(${x} ${y})" class="ship">
    <path d="M-13 2H13L9 8H-9Z" fill="#7b4a26" stroke="#1d140c" stroke-width="1.1" stroke-linejoin="round"/>
    <path d="M0 2V-16" stroke="#1d140c" stroke-width="1.2"/>
    <path d="M1 -15C9 -10 10 -3 2 0Z" fill="#f4e7c4" stroke="#1d140c" stroke-width="1"/>
    <path d="M-1 -12C-7 -8 -8 -3 -2 -1Z" fill="#f4e7c4" stroke="#1d140c" stroke-width="1"/>
    <path d="M-16 11q4 -3 8 0t8 0 8 0 8 0" fill="none" stroke="#2f6878" stroke-width="1"/></g>`;
}

function palm(x, y) {
  return `<g transform="translate(${x} ${y})"><path d="M0 0C1 -6 0 -10 -1 -14" stroke="#5a3b1a" stroke-width="1.6" fill="none"/>
    <path d="M-1 -14C-6 -16 -9 -13 -10 -10M-1 -14C3 -17 7 -15 9 -11M-1 -14C-3 -19 -1 -21 2 -21M-1 -14C-5 -13 -7 -10 -7 -7M-1 -14C3 -13 5 -10 5 -7" stroke="#3d6b3a" stroke-width="1.7" fill="none" stroke-linecap="round"/></g>`;
}

let cached = null;
/** SVG markup (string) for the static map art, layered under the routes. */
export function terrainMarkup() {
  if (cached) return cached;
  const W = MAP_W, H = MAP_H;
  const seaPaths = Object.values(SEAS).join(" ");
  const washes = WASHES.map(([k, x, y, rx, ry]) =>
    `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="url(#wash-${k})"/>`).join("");
  const mtns = [...MOUNTAINS].sort((a, b) => a[1] - b[1]).map(([x, y, sz]) => mountain(x, y, sz)).join("");
  const dunes = DESERTS.map(duneField).join("");
  const wavePts = [[110, 60], [190, 46], [230, 80], [150, 96], [30, 300], [70, 410], [100, 280], [420, 60], [430, 140],
    [380, 470], [520, 505], [600, 506], [1132, 260], [1128, 420], [255, 40]];
  cached = `
  <defs>
    <radialGradient id="wash-sand"><stop offset="0" stop-color="#e6b65e" stop-opacity=".45"/><stop offset="1" stop-color="#e6b65e" stop-opacity="0"/></radialGradient>
    <radialGradient id="wash-umber"><stop offset="0" stop-color="#8f6a3e" stop-opacity=".28"/><stop offset="1" stop-color="#8f6a3e" stop-opacity="0"/></radialGradient>
    <radialGradient id="wash-green"><stop offset="0" stop-color="#7c9a5a" stop-opacity=".3"/><stop offset="1" stop-color="#7c9a5a" stop-opacity="0"/></radialGradient>
    <radialGradient id="vignette" cx="50%" cy="50%" r="70%"><stop offset=".6" stop-color="#5a3b1a" stop-opacity="0"/><stop offset="1" stop-color="#5a3b1a" stop-opacity=".35"/></radialGradient>
    <clipPath id="sea-clip"><path d="${seaPaths}"/></clipPath>
    <clipPath id="map-clip"><rect x="0" y="0" width="${W}" height="${H}"/></clipPath>
  </defs>
  <g clip-path="url(#map-clip)">
    ${rhumbLines(62, 340)}${rhumbLines(1000, 120)}
    ${washes}
    <g class="seas">
      <path d="${seaPaths}" fill="#a9c9c0"/>
      <g clip-path="url(#sea-clip)" fill="none">
        <path d="${seaPaths}" stroke="#d4e5d8" stroke-width="26" opacity=".7"/>
        <path d="${seaPaths}" stroke="#7fb0ab" stroke-width="9" opacity=".7"/>
        <path d="${seaPaths}" stroke="#2f6878" stroke-width="3" opacity=".35" stroke-dasharray="1 4" stroke-linecap="round"/>
      </g>
      <path d="${seaPaths}" fill="none" stroke="#24505c" stroke-width="1.6"/>
      ${LAKES.map(([x, y, rx, ry]) => `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="#a9c9c0" stroke="#24505c" stroke-width="1.2"/>`).join("")}
      ${waves(null, wavePts)}
    </g>
    <g class="rivers" fill="none" stroke-linecap="round">
      ${RIVERS.map((d) => `<path d="${d}" stroke="#f3e6c4" stroke-width="4.5"/><path d="${d}" stroke="#3f7f90" stroke-width="1.8"/>`).join("")}
    </g>
    <g class="dunes">${dunes}</g>
    <g class="mountains">${mtns}</g>
    <g class="trees">${palm(325, 368)}${palm(560, 382)}${palm(842, 420)}${palm(948, 226)}${palm(620, 200)}</g>
    ${ship(112, 128)}${ship(560, 506)}
    ${compassRose(62, 340, 34)}
    ${cartouche(1010, 40)}
    <rect x="0" y="0" width="${W}" height="${H}" fill="url(#vignette)" pointer-events="none"/>
  </g>
  ${frame()}`;
  return cached;
}
