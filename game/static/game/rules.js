// "How to play": a compact, illustrated rules reference. Every number is read from the
// server's static data, so balance changes in data.py show up here automatically.

import { h, modal } from "./dom.js";
import { CHARACTER_EMBLEM, icon, LABELS, pipFace, resChips } from "./icons.js";

const SIMPLE = ["bazaar_spice", "bazaar_silk", "bazaar_jade", "camels", "treasury", "temple"];
const SPACE_ICON = { bazaar_spice: "spice", bazaar_silk: "silk", bazaar_jade: "jade", camels: "camels", treasury: "coins", temple: "omens" };

const sec = (id, ic, title, ...body) => h("section", { class: "rule-sec", id: `rule-${id}` },
  h("span", { class: "rule-medallion", "aria-hidden": "true" }, typeof ic === "string" ? icon(ic) : ic),
  h("div", { class: "rule-body" }, h("h4", {}, title), body));

const yields = (table, unit) => h("span", { class: "yield rule-yield", role: "img",
  "aria-label": `${unit} by die value: ${table.slice(1).join(", ")}` },
table.slice(1).map((n, i) => h("span", { class: "y" }, pipFace(i + 1), h("b", {}, String(n)))));

export function rulesContent(info) {
  const r = info.rules, sp = info.spaces, rt = info.route_types;
  const setBonus = r.set_bonus || [0, 0, 1, 2];
  const toll = r.toll_per_pip ?? 1;
  const noPost = (info.no_post_cities || []).map((c) => info.cities[c]?.name || c).join(" and ");
  const reps = info.city_action_repeats.slice(1);
  const sections = [
    sec("goal", "vp", "The goal",
      h("p", {}, `Over ${info.num_rounds} rounds, lead your caravan east from Constantinople towards Chang'an. Earn the most `,
        h("b", {}, "renown"), " ", icon("vp"), " by founding trading posts, delivering contracts and fulfilling your secret commissions.")),
    sec("round", "hourglass", "A round",
      h("ol", { class: "rule-steps" },
        h("li", {}, h("b", {}, "Income. "), "Collect the income of every city where you have a trading post, plus your character's bonus. Then everyone rolls their dice. ",
          `A poor roll (total under ${r.low_roll_per_die} × dice) pays up to ${r.low_roll_max} coins.`),
        h("li", {}, h("b", {}, "Turns. "), "Starting with the lead player, take turns. Each turn make ", h("b", {}, "one placement"),
          " — one die, or a set of equal dice — plus any free actions before or after. Then end your turn, or rest."),
        h("li", {}, h("b", {}, "End of round. "), `When everyone is out of dice or resting, the ${r.contract_churn} oldest contracts leave the market.`))),
    sec("dice", "spice", "Dice and the bazaar",
      h("p", {}, "A die's value sets what a stall yields. Higher is better:"),
      h("div", { class: "rule-table" }, SIMPLE.filter((k) => sp[k]).map((k) => h("div", { class: "rule-row" },
        h("span", { class: "rule-row-name" }, icon(SPACE_ICON[k]), sp[k].name),
        yields(sp[k].table, LABELS[sp[k].gain] || sp[k].gain),
        h("small", { class: "muted" }, (sp[k].max_dice || 1) > 1 ? `sets ≤${sp[k].max_dice}` : "single die",
          Object.keys(sp[k].cost || {}).length ? [" · costs ", resChips(sp[k].cost), " each"] : null))))),
    sec("toll", "coins", "Crowded spaces: the toll",
      h("p", {}, "If a ", h("b", {}, "rival"), ` already has a die on a space, you pay ${toll} coin per pip of the value you place there. `,
        "A set pays once. Your own dice never crowd you, and city actions are never shared."),
      h("p", { class: "rule-example" }, pipFace(5), h("span", {}, `A 5 on a crowded stall costs ${5 * toll} coins; a 1 costs ${toll}. Low dice are cheap anywhere.`))),
    sec("sets", h("span", { class: "key-dice" }, pipFace(3), pipFace(3)), "Sets and the guide die",
      h("p", {}, "Place 2–3 dice showing the same value together where a stall allows sets. You get the single-die amount for each die, plus ",
        setBonus.slice(2).map((b, i) => `+${b} for a ${i ? "triple" : "pair"}`).join(" and "), "."),
      h("p", { class: "rule-example" }, icon("guide"), h("span", {}, `Hire a white guide die for ${r.guide_cost} coins (once per round, ${r.guide_dice} per round for the table). It is `,
        h("b", {}, "wild"), " in a set, or can be placed alone at its own value."))),
    sec("omens", "omens", "Omens",
      h("p", {}, `Spend omens on your dice before placing: reroll a die for ${r.reroll_cost}, or change it by ±1 for ${r.nudge_cost}. The Shrine yields omens.`)),
    sec("road", "caravan", "The Road and travel",
      h("p", {}, "Place on The Road to move your caravan. Steps by die value (a pair travels double plus its bonus):"),
      yields(sp.road.table, "Steps"),
      h("div", { class: "key-grid rule-routes" }, Object.entries(rt).map(([k, v]) => h("div", { class: "key-item" }, icon(k),
        h("span", {}, h("b", {}, v.label), " ", resChips({ camels: v.camels, coins: v.coins }, { empty: "free" }), " per route")))),
      h("p", {}, "Where the journey ends you found a ", h("b", {}, "trading post"), " (", icon("post"),
        `, ${r.trading_posts} each) worth the renown printed on the city. No posts in ${noPost}. `,
        `Ending a journey in Chang'an scores ${info.end_city_order_vp.join(" / ")} by arrival order.`)),
    sec("posts", "post", "Posts, income and city actions",
      h("p", {}, "Each post pays its city's income at the start of every round. If you have a post in a city, you may place one die there to use its exchange ",
        `${reps.join("/")} times (by die value). Each city's action can be used by only one merchant per round.`)),
    sec("contracts", "scroll", "Contracts",
      h("p", {}, "Place a die on the Caravanserai to take a contract from slot 1 up to your die's value. ",
        `You may hold ${r.max_open_contracts} open contracts; to take another you must abandon one. `,
        "Delivering is a free action: pay the goods shown to earn the renown on the wax seal and any bonus.")),
    sec("commissions", "seal", "Secret commissions",
      h("p", {}, `You hold two secret commissions, each naming two cities. At the end, posts in both cities score ${r.commission_both}, in one city ${r.commission_one}.`)),
    sec("shrine", "lead", "The Shrine and the lead",
      h("p", {}, "The first merchant to visit the Shrine in a round leads the next round. If nobody visits, the lead passes clockwise.")),
    sec("rest", "tent", "Resting",
      h("p", {}, `Instead of placing (or straight after placing), you may rest: take ${r.rest_coins_per_die} coin per die you could still place and sit out the rest of the round.`)),
    sec("characters", "compass", "Characters",
      h("div", { class: "rule-chars" }, Object.entries(info.characters).map(([k, c]) => h("div", { class: "rule-char" },
        h("span", { class: "char-medallion small" }, icon(CHARACTER_EMBLEM[k] || "vp")),
        h("div", {}, h("b", {}, c.name), h("p", {}, c.text)))))),
    sec("scoring", "vp", "Final scoring",
      h("ul", { class: "key-list" },
        h("li", {}, "Renown earned during play (posts, contracts, city actions, Chang'an)"),
        h("li", {}, `Commissions: ${r.commission_both} for both cities, ${r.commission_one} for one`),
        h("li", {}, `Most trading posts: ${r.post_majority.join(" / ")}`, " (second place only with 3+ merchants)"),
        h("li", {}, `Most contracts delivered: ${r.contract_majority}`),
        h("li", {}, `1 renown per ${r.coins_per_vp} coins and per ${r.goods_per_vp} goods left over`)),
      h("p", { class: "muted small" }, "Ties go to the merchant with more coins, then more goods.")),
  ];
  const nav = h("nav", { class: "rule-nav", "aria-label": "Sections" }, sections.map((el) => {
    const title = el.querySelector("h4").textContent;
    return h("button", { class: "rule-chip", type: "button",
      onclick: () => el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }) }, title);
  }));
  return h("div", { class: "rules" }, nav, sections);
}

export function showRules(info) {
  return modal("How to play", () => rulesContent(info), { kind: "wide rules-modal" });
}
