// Router + polling loop. URL "/" = home, "/g/CODE/" = a game (lobby or play).

import { api } from "./api.js";
import { GameView } from "./game.js";
import { h, toast } from "./dom.js";
import { ensureSprite } from "./icons.js";
import { renderHome, renderWaiting } from "./lobby.js";
import { Coach } from "./tutorial.js";

const root = document.getElementById("app");
let info = null;
let generation = 0;     // bumps on every navigation; stale loops notice and stop
let homeInterval = null;
let coach = null;       // coach marks (tutorial lessons + hints) for the current game view

function navigate(code, push = true) {
  const url = code ? `/g/${code}/` : "/";
  if (push && location.pathname !== url) history.pushState({}, "", url);
  route();
}

function codeFromPath() {
  const m = location.pathname.match(/^\/g\/([A-Za-z0-9]+)\/?$/);
  return m ? m[1].toUpperCase() : null;
}

async function route() {
  generation += 1;
  clearInterval(homeInterval);
  document.getElementById("modal-root").innerHTML = "";
  coach?.destroy();
  coach = null;
  document.getElementById("overlay-root").replaceChildren();
  document.getElementById("topbar-status").replaceChildren();
  document.title = "Caravan Road";
  document.documentElement.classList.remove("with-tray", "placing");
  const code = codeFromPath();
  if (!code) { homeInterval = renderHome(root, navigate); return; }
  root.replaceChildren(h("p", { class: "loading center" }, "Loading caravan…"));
  try { info ||= await api.staticInfo(); } catch (e) { toast(e.message); return; }
  watch(code, generation);
}

function watch(code, gen) {
  let version = null, failures = 0, timeout = null, view = null, inflight = false, again = false;

  const tick = async () => {
    if (gen !== generation) return;
    if (inflight) { again = true; return; }
    clearTimeout(timeout);
    inflight = true;
    try {
      const data = await api.state(code, version);
      if (gen !== generation) return;
      failures = 0;
      if (!data.unchanged) {
        version = data.version;
        if (!data.game) {
          view = null;
          renderWaiting(root, data, navigate);
        } else {
          if (!view) {
            view = new GameView(root, code, info);
            view.onChanged = () => tick();
            coach = new Coach(view, { tutorial: !!data.tutorial });
          }
          view.update(data);
        }
      }
    } catch (e) {
      if (gen !== generation) return;
      failures += 1;
      if (/404|not found/i.test(e.message)) {
        root.replaceChildren(h("section", { class: "panel center" }, h("h2", {}, "Game not found"),
          h("a", { class: "btn", href: "/" }, "Back to lobby")));
        return;
      }
      if (failures === 3) toast("Connection trouble — retrying…");
    } finally {
      inflight = false;
    }
    if (gen !== generation) return;
    if (again) { again = false; tick(); return; }
    timeout = setTimeout(tick, document.hidden ? 5000 : 1200);
  };
  tick();
}

window.addEventListener("popstate", () => route());
ensureSprite();
route();
