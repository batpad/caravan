// Decorative illustration for the home screen: a dusk panorama with a caravan on the dunes.
// Pure SVG, drawn from simple shapes; nothing interactive.

import { s } from "./dom.js";
import { ensureSprite } from "./icons.js";

export function heroPanorama() {
  ensureSprite();
  const W = 1200, H = 320;
  const stars = [[90, 40], [210, 80], [330, 30], [460, 70], [560, 24], [700, 56], [980, 40], [1080, 90], [1140, 30], [620, 110], [400, 120], [150, 130]];
  const star = ([x, y], i) => s("path", { d: `M${x} ${y - 5}L${x + 1.4} ${y - 1.4} ${x + 5} ${y} ${x + 1.4} ${y + 1.4} ${x} ${y + 5} ${x - 1.4} ${y + 1.4} ${x - 5} ${y} ${x - 1.4} ${y - 1.4}Z`,
    fill: "#f3dfa2", opacity: i % 3 ? .7 : 1, class: "twinkle", style: `animation-delay:${(i * 0.37) % 3}s` });
  const camels = [0, 1, 2, 3, 4];
  return s("svg", { class: "hero-art", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMax slice", "aria-hidden": "true" },
    s("defs", {},
      s("linearGradient", { id: "hero-sky", x1: 0, y1: 0, x2: 0, y2: 1 },
        s("stop", { offset: 0, "stop-color": "#111a3d" }), s("stop", { offset: .5, "stop-color": "#24407f" }),
        s("stop", { offset: .82, "stop-color": "#c9773a" }), s("stop", { offset: 1, "stop-color": "#efb658" }))),
    s("rect", { width: W, height: H, fill: "url(#hero-sky)" }),
    stars.map(star),
    // sun with ripple rings
    s("g", { transform: "translate(860 218)" },
      [110, 92, 78].map((r, i) => s("circle", { r, fill: "none", stroke: "#f6cf74", "stroke-width": 1.2, opacity: .25 + i * .15 })),
      s("circle", { r: 62, fill: "#f4c35c" }), s("circle", { r: 62, fill: "none", stroke: "#fff1c0", "stroke-width": 2, opacity: .6 })),
    // far ranges
    s("path", { d: "M0 230L60 200 110 214 170 176 230 206 300 168 360 200 430 160 500 196 560 180 640 210 720 170 790 200 880 160 960 196 1040 172 1120 204 1200 182V320H0Z", fill: "#4a3f6b", opacity: .85 }),
    s("path", { d: "M170 176l-14 12 10-2 4 8 6-10 10 4ZM430 160l-16 14 11-3 5 9 6-11 11 4ZM880 160l-15 13 10-2 5 8 6-10 11 4Z", fill: "#e9dff0", opacity: .7 }),
    // walled city with domes on the left
    s("g", { fill: "#2a2147" },
      s("path", { d: "M30 262V214H52V200H60V214H96V190A20 20 0 0 1 136 190V214H160V170H166V158H170V170H176V214H210V196A14 14 0 0 1 238 196V214H262V262Z" }),
      s("path", { d: "M116 168V158M224 180V172", stroke: "#2a2147", "stroke-width": 3 })),
    s("g", { fill: "#e9a64a", opacity: .9 },
      s("rect", { x: 72, y: 226, width: 5, height: 8, rx: 2.5 }), s("rect", { x: 112, y: 222, width: 5, height: 9, rx: 2.5 }),
      s("rect", { x: 190, y: 228, width: 5, height: 8, rx: 2.5 }), s("rect", { x: 242, y: 230, width: 5, height: 8, rx: 2.5 })),
    // dunes
    s("path", { d: "M0 262C140 240 260 250 380 236C520 220 640 246 780 232C920 218 1060 236 1200 226V320H0Z", fill: "#c98a3a" }),
    s("path", { d: "M380 236C520 220 640 246 780 232", fill: "none", stroke: "#f2c57a", "stroke-width": 2, opacity: .7 }),
    // the caravan walking along the crest
    s("g", { class: "hero-caravan" },
      camels.map((i) => s("use", { href: "#ic-caravan", x: 470 + i * 58, y: 186 + (i % 2) * 3 - (i === 2 ? 4 : 0), width: 52, height: 52, style: "color:#24160c" })),
      camels.map((i) => s("path", { d: `M${492 + i * 58} ${196 + (i % 2) * 3 - (i === 2 ? 4 : 0)}l6 -14 6 14Z`, fill: "#24160c" })),
      s("path", { d: "M778 236V206M778 206l-6 30M778 206l5 30", stroke: "#24160c", "stroke-width": 3, "stroke-linecap": "round" }),
      s("circle", { cx: 778, cy: 201, r: 5, fill: "#24160c" }),
      s("path", { d: "M772 196h12l-6 -6Z", fill: "#24160c" })),
    s("path", { d: "M0 290C160 266 300 282 470 270C640 258 800 284 980 270C1080 262 1150 270 1200 266V320H0Z", fill: "#a8652b" }),
    s("path", { d: "M0 306C200 296 420 312 640 300C860 288 1020 306 1200 298V320H0Z", fill: "#7c4520" }),
  );
}
