// Tiny DOM helpers: h() element builder, s() SVG builder, modal, toast.
// Icons, dice faces and resource chips live in icons.js.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith("--")) el.style.setProperty(sk, sv); else el.style[sk] = sv;
      }
    }
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SVGNS = "http://www.w3.org/2000/svg";
export function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function toast(msg, kind = "error") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `show ${kind}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.className = ""; }, 3500);
}

/**
 * Open a modal; `build(close)` returns content. Resolves with whatever close() is called with.
 * Options: { kind } adds a modifier class (e.g. "wide").
 */
export function modal(title, build, { kind = "" } = {}) {
  return new Promise((resolve) => {
    const root = document.getElementById("modal-root");
    const prevFocus = document.activeElement;
    const close = (val) => {
      root.replaceChildren();
      document.removeEventListener("keydown", onKey);
      document.documentElement.classList.remove("modal-open");
      prevFocus?.focus?.({ preventScroll: true });
      resolve(val);
    };
    const onKey = (e) => {
      if (e.key === "Escape") close(null);
      if (e.key === "Tab") { // keep focus inside the dialog
        const f = [...box.querySelectorAll("button:not(:disabled), [href], input, select, [tabindex]:not([tabindex='-1'])")];
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    const closeIcon = s("svg", { viewBox: "0 0 32 32", class: "ic", "aria-hidden": "true" },
      s("path", { d: "M8 8l16 16M24 8L8 24", stroke: "currentColor", "stroke-width": 3, "stroke-linecap": "round" }));
    const box = h("div", { class: `modal ${kind}`.trim(), role: "dialog", "aria-modal": "true", "aria-label": title },
      h("div", { class: "modal-head" }, h("h3", {}, title),
        h("button", { class: "icon-btn", "aria-label": "Close", onclick: () => close(null) }, closeIcon)),
      h("div", { class: "modal-body" }, build(close)));
    root.replaceChildren(h("div", { class: "backdrop", onclick: (e) => { if (e.target === e.currentTarget) close(null); } }, box));
    document.documentElement.classList.add("modal-open");
    (box.querySelector(".modal-body [data-autofocus]:not(:disabled)") || box.querySelector(".modal-body button:not(:disabled)")
      || box.querySelector(".icon-btn"))?.focus({ preventScroll: true });
  });
}
