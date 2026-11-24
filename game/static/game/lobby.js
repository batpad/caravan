// Home screen (create / join / open games list) and the pre-game waiting room.

import { api, seats } from "./api.js";
import { heroPanorama } from "./art.js";
import { h, toast } from "./dom.js";
import { icon, pigment } from "./icons.js";
import { showRules } from "./rules.js";

const SEAT_COLORS = ["#c0392b", "#2471a3", "#239b56", "#b7950b"];
const lastName = () => { try { return localStorage.getItem("caravan:name") || ""; } catch { return ""; } };
const saveName = (n) => { try { localStorage.setItem("caravan:name", n); } catch { /* ignore */ } };

const field = (id, label, input) => h("div", { class: "field" }, h("label", { for: id }, label), input);
const LEVELS = ["easy", "normal", "hard"];
const lastLevel = () => { try { return LEVELS.includes(localStorage.getItem("caravan:level")) ? localStorage.getItem("caravan:level") : "normal"; } catch { return "normal"; } };
const saveLevel = (l) => { try { localStorage.setItem("caravan:level", l); } catch { /* ignore */ } };

/** A segmented single-choice control (radio group of ≥44px buttons). */
function segmented(label, options, value, onChange, { id = null } = {}) {
  const el = h("div", { class: "seg", role: "radiogroup", "aria-label": label, id }, options.map(([v, text]) => h("button", {
    type: "button", role: "radio", "aria-checked": v === value ? "true" : "false", class: v === value ? "on" : "", "data-value": v,
    onclick: (e) => {
      for (const b of el.children) { const on = b === e.currentTarget; b.classList.toggle("on", on); b.setAttribute("aria-checked", on); }
      onChange(v);
    },
  }, text)));
  return el;
}

let staticInfo = null;
async function openRules() {
  try { staticInfo ||= await api.staticInfo(); showRules(staticInfo); } catch (e) { toast(e.message); }
}

export function renderHome(root, navigate) {
  document.documentElement.classList.remove("with-tray", "placing");
  const nameInput = h("input", { id: "pname", maxlength: 30, placeholder: "e.g. Rustam", value: lastName(), autocomplete: "nickname" });
  const gameName = h("input", { id: "gname", maxlength: 60, placeholder: "optional" });
  let maxPlayers = 4, botCount = 1, botLevel = lastLevel();
  const seatsPick = segmented("Seats", [[2, "2"], [3, "3"], [4, "4"]], maxPlayers, (n) => { maxPlayers = n; });
  const botsPick = segmented("AI opponents", [[1, "1"], [2, "2"], [3, "3"]], botCount, (n) => { botCount = n; }, { id: "ai-count" });
  const levelPick = segmented("AI level", LEVELS.map((l) => [l, l[0].toUpperCase() + l.slice(1)]), botLevel,
    (l) => { botLevel = l; saveLevel(l); }, { id: "ai-level" });
  const codeInput = h("input", { id: "gcode", maxlength: 8, placeholder: "ABCDE", autocapitalize: "characters", autocomplete: "off", spellcheck: "false", class: "code-input" });
  const list = h("div", { class: "open-games", id: "open-games" }, h("p", { class: "muted" }, "Loading…"));

  const needName = () => {
    const n = nameInput.value.trim();
    if (!n) { toast("Enter your name first."); nameInput.focus(); return null; }
    saveName(n);
    return n;
  };

  async function join(code) {
    const n = needName(); if (!n) return;
    if (!code.trim()) { toast("Enter a game code."); codeInput.focus(); return; }
    try {
      const r = await api.join(code.trim().toUpperCase(), n);
      seats.set(r.code, { token: r.token, seat: r.seat });
      navigate(r.code);
    } catch (e) { toast(e.message); }
  }

  async function create() {
    const n = needName(); if (!n) return;
    try {
      const r = await api.createGame(n, gameName.value, maxPlayers);
      seats.set(r.code, { token: r.token, seat: r.seat });
      navigate(r.code);
    } catch (e) { toast(e.message); }
  }

  async function playAI() {
    const n = needName(); if (!n) return;
    try {
      const r = await api.createVsBots(n, botCount, botLevel);
      seats.set(r.code, { token: r.token, seat: r.seat });
      navigate(r.code);
    } catch (e) { toast(e.message); }
  }

  async function learn() {
    const n = nameInput.value.trim() || "Traveller";
    if (nameInput.value.trim()) saveName(n);
    try {
      const r = await api.createTutorial(n);
      seats.set(r.code, { token: r.token, seat: r.seat, tutorial: true });
      navigate(r.code);
    } catch (e) { toast(e.message); }
  }

  async function refresh() {
    try {
      const { games } = await api.listGames();
      list.replaceChildren(...(games.length ? games.map((g) => h("div", { class: "open-game" },
        h("div", { class: "og-seats", "aria-hidden": "true" }, Array.from({ length: g.max_players }, (_, i) =>
          h("span", { class: `seat-dot${i < g.players.length ? " taken" : ""}`, style: { "--pc": pigment(SEAT_COLORS[i]).fill } }))),
        h("div", { class: "og-info" }, h("strong", {}, g.name), h("small", {},
          `${g.players.map((p) => p.name).join(", ")} · ${g.players.length}/${g.max_players}`)),
        h("button", { class: "btn", disabled: g.players.length >= g.max_players, onclick: () => join(g.code) }, "Join"),
      )) : [h("p", { class: "muted empty-note" }, "No caravans are gathering. Start one!")]));
    } catch (e) { list.replaceChildren(h("p", { class: "muted" }, e.message)); }
  }

  root.replaceChildren(h("section", { class: "home" },
    h("div", { class: "hero" },
      heroPanorama(),
      h("div", { class: "hero-text" },
        h("p", { class: "eyebrow" }, "A dice-placement journey for 2–4 merchants"),
        h("h1", {}, "Caravan Road"),
        h("p", {}, "Roll your dice, haggle in the bazaar and lead your caravan from Constantinople to Chang'an. ",
          "Found trading posts, seal contracts and become the greatest merchant of the Silk Road."))),
    h("div", { class: "panel learn-band", id: "learn-panel", "data-tour": "learn" },
      h("span", { class: "char-medallion learn-medallion", "aria-hidden": "true" }, icon("compass")),
      h("div", { class: "learn-text" },
        h("p", { class: "eyebrow" }, "New to the road?"),
        h("h2", {}, "Learn to play"),
        h("p", { class: "muted" }, "A guided first game against a gentle AI merchant. Each lesson shows you what to tap, step by step — about 15 minutes.")),
      h("div", { class: "learn-actions" },
        h("button", { class: "btn primary", id: "learn-btn", onclick: learn }, icon("compass"), "Start the tutorial"),
        h("button", { class: "btn", id: "rules-home-btn", onclick: openRules }, icon("scroll"), "How to play"))),
    h("div", { class: "home-grid" },
      h("div", { class: "panel", id: "create-panel" },
        h("h2", { class: "panel-title" }, "Set out"),
        field("pname", "Your name", nameInput),
        h("div", { class: "sub-panel" },
          h("h3", { class: "sub-title" }, "Play against the AI"),
          h("div", { class: "seg-row" },
            h("div", { class: "field" }, h("span", { class: "label" }, "Opponents"), botsPick),
            h("div", { class: "field" }, h("span", { class: "label" }, "Level"), levelPick)),
          h("button", { class: "btn primary wide", id: "play-ai-btn", onclick: playAI }, icon("scales"), "Play vs AI")),
        h("div", { class: "sub-panel" },
          h("h3", { class: "sub-title" }, "Play with friends"),
          field("gname", "Caravan name", gameName),
          h("div", { class: "field" }, h("span", { class: "label" }, "Seats"), seatsPick),
          h("button", { class: "btn primary wide", onclick: create }, icon("caravan"), "Create game")),
        h("div", { class: "divider" }, h("span", {}, "or join by code")),
        h("div", { class: "row" }, codeInput, h("button", { class: "btn", onclick: () => join(codeInput.value) }, "Join")),
      ),
      h("div", { class: "panel" },
        h("div", { class: "panel-head" }, h("h2", { class: "panel-title" }, "Caravans gathering"),
          h("button", { class: "btn ghost", onclick: refresh, "aria-label": "Refresh list" }, icon("reroll"), "Refresh")),
        list,
      ),
    ),
  ));
  refresh();
  return setInterval(refresh, 5000);
}

export function renderWaiting(root, data, navigate) {
  document.documentElement.classList.remove("with-tray", "placing");
  const mine = seats.get(data.code);
  const seated = data.seat != null;
  const url = `${location.origin}/g/${data.code}/`;
  const nameInput = h("input", { maxlength: 30, placeholder: "Your name", value: lastName(), "aria-label": "Your name" });
  const byIndex = Object.fromEntries(data.players.map((p) => [p.index, p]));

  root.replaceChildren(h("section", { class: "waiting panel", id: "waiting-room", "data-tour": "waiting-room" },
    h("p", { class: "eyebrow" }, "The caravan gathers"),
    h("h2", {}, data.name),
    h("div", { class: "invite" },
      h("div", { class: "code-tile" }, h("small", {}, "Game code"), h("b", {}, data.code)),
      h("div", { class: "invite-link" },
        h("p", { class: "muted small" }, "Share the code, or this link:"),
        h("div", { class: "row" }, h("input", { readonly: true, value: url, "aria-label": "Invite link", onfocus: (e) => e.target.select() }),
          h("button", { class: "btn", onclick: () => navigator.clipboard?.writeText(url).then(() => toast("Link copied", "ok"), () => toast("Copy failed")) }, "Copy")))),
    h("h3", { class: "panel-title" }, `Merchants ${data.players.length}/${data.max_players}`),
    h("ul", { class: "seat-list" }, Array.from({ length: data.max_players }, (_, i) => {
      const p = byIndex[i];
      const pg = pigment(SEAT_COLORS[i]);
      return h("li", { class: p ? "taken" : "open", style: { "--pc": pg.fill } },
        h("span", { class: "seal", style: { "--pc": pg.fill, "--pd": pg.dark } }, p ? icon("caravan") : null),
        p ? h("span", { class: "seat-name" }, p.name) : h("span", { class: "muted" }, "awaiting a merchant…"),
        p?.is_host ? h("span", { class: "tag" }, "host") : null,
        p?.is_bot ? h("span", { class: "ai-badge" }, "AI", h("small", {}, ` · ${p.bot_level || "normal"}`)) : null,
        p && p.index === data.seat ? h("span", { class: "tag you" }, "you") : null,
        h("small", { class: "seat-colour" }, pg.name),
        p?.is_bot && data.is_host ? h("button", { class: "icon-btn remove-seat", "aria-label": `Remove ${p.name}`, "data-remove": p.index,
          onclick: async () => { try { await api.removeSeat(data.code, p.index); } catch (e) { toast(e.message); } } }, icon("close")) : null);
    })),
    seated ? h("div", { class: "row" },
      data.is_host
        ? h("button", { class: "btn primary", disabled: data.players.length < 2, onclick: async () => {
          try { await api.start(data.code); } catch (e) { toast(e.message); }
        } }, icon("caravan"), data.players.length < 2 ? "Waiting for players…" : "Start the journey")
        : h("p", { class: "muted" }, "Waiting for the host to start…"),
      data.is_host && data.players.length < data.max_players ? h("div", { class: "add-bot-group" },
        segmented("AI level", LEVELS.map((l) => [l, l[0].toUpperCase() + l.slice(1)]), lastLevel(), (l) => saveLevel(l), { id: "bot-level" }),
        h("button", { class: "btn", id: "add-bot", "data-tour": "add-bot",
          onclick: async () => { try { await api.addBot(data.code, lastLevel()); } catch (e) { toast(e.message); } } }, icon("guide"), "Add AI merchant")) : null,
      h("button", { class: "btn ghost", onclick: async () => {
        try { await api.leave(data.code); seats.clear(data.code); navigate(null); } catch (e) { toast(e.message); }
      } }, "Leave"),
    ) : (data.players.length < data.max_players ? h("div", { class: "row" }, nameInput,
      h("button", { class: "btn primary", onclick: async () => {
        const n = nameInput.value.trim(); if (!n) return toast("Enter your name.");
        saveName(n);
        try { const r = await api.join(data.code, n); seats.set(r.code, { token: r.token, seat: r.seat }); navigate(r.code); }
        catch (e) { toast(e.message); }
      } }, "Take a seat")) : h("p", { class: "muted" }, "This game is full.")),
    mine && !seated ? h("p", { class: "muted small" }, "Your saved seat is no longer valid.") : null,
  ));
}
