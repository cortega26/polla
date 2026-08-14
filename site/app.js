/* Pozos Chile — dashboard renderer. Dependency-free, progressive enhancement. */
(() => {
  "use strict";

  const fmtCLP = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 });
  const fmtPct = new Intl.NumberFormat("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtDate = new Intl.DateTimeFormat("es-CL", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const fmtDateTime = new Intl.DateTimeFormat("es-CL", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const $ = (id) => document.getElementById(id);

  const CONFIDENCE_LABELS = {
    full: "consenso completo",
    degraded: "parcial",
    single_source: "fuente única",
  };

  function stampState(value) {
    if (value === "full") return "ok";
    if (value === "single_source") return "warn";
    return "bad";
  }

  function relativeTime(iso) {
    const then = new Date(iso);
    const diff = Math.max(0, Date.now() - then.getTime());
    const min = Math.floor(diff / 60000);
    if (min < 1) return "recién actualizado";
    if (min < 60) return `actualizado hace ${min} min`;
    const hours = Math.floor(min / 60);
    if (hours < 24) return `actualizado hace ${hours} h`;
    const days = Math.floor(hours / 24);
    return `actualizado hace ${days} d`;
  }

  function countUp(el, target, duration = 900) {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      el.textContent = fmtCLP.format(target);
      return;
    }
    const start = performance.now();
    const step = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmtCLP.format(Math.round(target * eased));
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function renderTicket(section, prefix, accent) {
    const totalEl = $(`${prefix}-total`);
    $(`${prefix}-sorteo`).textContent = section.sorteo ?? "—";
    $(`${prefix}-fecha`).textContent = section.fecha
      ? fmtDate.format(new Date(section.fecha + "T12:00:00"))
      : "—";
    $(`${prefix}-src`).textContent = section.fuente || "";
    $(`${prefix}-confidence`).textContent =
      CONFIDENCE_LABELS[section.confidence] || section.confidence || "—";
    $(`${prefix}-confidence`).className =
      `stamp stamp--${stampState(section.confidence)}`;

    const cats = $(`${prefix}-cats`);
    cats.textContent = "";
    for (const [label, millones] of Object.entries(section.pozos_millones || {})) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = label;
      const value = document.createElement("span");
      value.className = "mono";
      value.textContent = `$${millones} MM`;
      li.append(name, value);
      cats.append(li);
    }

    countUp(totalEl, Number((section.total_millones || "0").replace(/[.,\s]/g, "")) || 0);
  }

  function renderHistory(history) {
    const body = $("history-body");
    const empty = $("history-empty");
    body.textContent = "";
    if (!history || history.length === 0) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    for (const row of history) {
      const entries = Object.entries(row.pozos_millones || {});
      const first = entries[0] || ["—", "—"];
      const tr = document.createElement("tr");
      const fecha = document.createElement("td");
      fecha.className = "mono";
      fecha.textContent = row.fecha ? fmtDate.format(new Date(row.fecha + "T12:00:00")) : "—";
      const sorteo = document.createElement("td");
      sorteo.className = "mono";
      sorteo.textContent = row.sorteo ?? "—";
      const cat = document.createElement("td");
      cat.textContent = first[0];
      const pozo = document.createElement("td");
      pozo.className = "tbl__num";
      pozo.textContent = `$${first[1]} MM`;
      tr.append(fecha, sorteo, cat, pozo);
      body.append(tr);
    }
  }

  /* ---------- Stats ---------- */

  let statsData = null;
  let statsFilter = "Todos";
  let statsSort = { key: null, dir: 1 };

  function cell(value, cls = "") {
    const td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = value ?? "—";
    return td;
  }

  const KINO_TAG = /^kino/i;

  function gameTag(game) {
    const span = document.createElement("span");
    span.className = `game-tag${KINO_TAG.test(game) ? " game-tag--kino" : ""}`;
    span.textContent = game;
    return span;
  }

  function statRows() {
    const rows = [];
    for (const [game, gameRows] of Object.entries(statsData.games)) {
      if (statsFilter !== "Todos" && game !== statsFilter) continue;
      for (const row of gameRows) {
        rows.push({ game, row });
      }
    }
    return rows;
  }

  function renderStats() {
    const body = $("stats-body");
    const empty = $("stats-empty");
    body.textContent = "";
    if (!statsData || !statsData.games) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;

    let rows = statRows();
    if (statsSort.key) {
      const { key, dir } = statsSort;
      rows.sort((a, b) => {
        const av = a.row[key];
        const bv = b.row[key];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
      });
    }

    for (const { game, row } of rows) {
      const tr = document.createElement("tr");
      const odds = row["Probabilidad de ganar"];
      const premio = row["premio_real_clp"];
      const retorno = row["retorno_real_pct"];
      const apuesta = row["precio_real_clp"];
      const acumulado = row["precio_acumulado_clp"];
      const esBase = apuesta != null && apuesta === acumulado;
      const apuestaTxt =
        apuesta != null ? `${esBase ? "" : "+"}$${fmtCLP.format(apuesta)}` : "—";

      const gameTd = document.createElement("td");
      gameTd.append(gameTag(game));
      tr.append(
        gameTd,
        cell(row["Categoría"] || "—"),
        cell(apuestaTxt, "tbl__num"),
        cell(acumulado != null ? `$${fmtCLP.format(acumulado)}` : "—", "tbl__num"),
        cell(
          row["Combinaciones totales (num)"] != null
            ? fmtCLP.format(row["Combinaciones totales (num)"])
            : "—",
          "tbl__num"
        ),
        cell(odds ? odds : "—", "tbl__num"),
        cell(premio != null ? `$${fmtCLP.format(premio)}` : "—", "tbl__num"),
        cell(retorno != null ? `${fmtPct.format(retorno)}%` : "—", "tbl__num")
      );
      body.append(tr);
    }
  }

  function renderStatsPills() {
    const pillsEl = $("stats-pills");
    pillsEl.textContent = "";
    if (!statsData || !statsData.games) return;
    const games = ["Todos", ...Object.keys(statsData.games).sort()];
    for (const game of games) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pill";
      btn.textContent = game;
      btn.setAttribute("aria-pressed", String(game === statsFilter));
      if (KINO_TAG.test(game)) btn.classList.add("pill--kino");
      btn.addEventListener("click", () => {
        statsFilter = game;
        renderStatsPills();
        renderStats();
      });
      pillsEl.append(btn);
    }
  }

  const SORTABLE_KEYS = {
    apuesta: "precio_real_clp",
    acumulado: "precio_acumulado_clp",
    combinaciones: "Combinaciones totales (num)",
    premio: "premio_real_clp",
    retorno: "retorno_real_pct",
  };

  function wireStatsSorting() {
    document.querySelectorAll("#stats-section th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = SORTABLE_KEYS[th.dataset.sort];
        if (!key) return;
        if (statsSort.key === key) {
          statsSort.dir *= -1;
        } else {
          statsSort = { key, dir: 1 };
        }
        document.querySelectorAll("#stats-section th").forEach((h) =>
          h.removeAttribute("aria-sort")
        );
        th.setAttribute("aria-sort", statsSort.dir === 1 ? "ascending" : "descending");
        renderStats();
      });
    });
  }

  async function main() {
    let data;
    try {
      const res = await fetch("data.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (err) {
      const meta = document.querySelector(".masthead__meta");
      meta.textContent = "Datos no disponibles todavía — el pipeline aún no ha publicado.";
      $("last-decision").className = "stamp stamp--bad";
      return;
    }

    const updated = $("last-updated");
    updated.dateTime = data.generated_at || "";
    updated.textContent = data.generated_at
      ? relativeTime(data.generated_at)
      : "desconocido";
    if (data.generated_at) {
      updated.title = fmtDateTime.format(new Date(data.generated_at));
    }

    const decision = data.last_decision || {};
    const status = decision.status || "unknown";
    const decisionEl = $("last-decision");
    decisionEl.textContent =
      status === "publish"
        ? "publicado"
        : status === "quarantine"
          ? "en cuarentena"
          : status === "skip"
            ? "sin cambios"
            : "desconocido";
    decisionEl.className = `stamp stamp--${
      status === "publish" ? "ok" : status === "quarantine" ? "bad" : "warn"
    }`;

    if (data.loto) renderTicket(data.loto, "loto", false);
    if (data.kino) renderTicket(data.kino, "kino", true);

    renderHistory(data.history);

    $("footer-sources").textContent =
      [...new Set(["polla.cl", "openloto.cl", "pendon-kino.loteria.cl"])].join(", ");
    $("footer-api").textContent = `api ${data.api_version || "?"}`;
  }

  async function loadStats() {
    try {
      const res = await fetch("stats.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      statsData = await res.json();
    } catch (err) {
      statsData = null;
    }
    renderStatsPills();
    renderStats();
    wireStatsSorting();
  }

  main();
  loadStats();
})();
