(function () {
  "use strict";

  const charts = {};
  const colors = {
    accent: "#7b83ff",
    amber: "#f59e0b",
    red: "#ef4444",
    green: "#22c55e",
    blue: "#60a5fa",
    purple: "#a78bfa",
    muted: "#a0a0a0",
    text: "#f5f5f5",
    grid: "rgba(255,255,255,0.06)",
  };

  // Spiky operational series should NOT be spline-smoothed — smoothing hides the
  // exact latency/CPU spikes the dashboard exists to surface.
  const SPIKY = 0;
  const SMOOTH = 0.25;

  const REFRESH_MS = 60000;

  const state = {
    page: "",
    apiUrl: "",
    pageUrl: "",
    data: {},
  };
  let refreshTimer = null;

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  /* ----------------------------------------------------------------- charts */

  function destroyChart(id) {
    if (charts[id]) {
      charts[id].destroy();
      delete charts[id];
    }
  }

  function resetCharts() {
    Object.keys(charts).forEach(destroyChart);
  }

  function labelForTs(ts) {
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) return ts;
    return date.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function chartOptions(extra) {
    return Object.assign(
      {
        maintainAspectRatio: false,
        responsive: true,
        animation: { duration: 350 },
        plugins: {
          legend: { labels: { color: colors.muted, usePointStyle: true } },
          tooltip: { mode: "index", intersect: false },
        },
        scales: {
          x: {
            grid: { color: colors.grid },
            ticks: { color: colors.muted, maxTicksLimit: 8 },
          },
          y: { grid: { color: colors.grid }, ticks: { color: colors.muted } },
        },
      },
      extra || {}
    );
  }

  function ensureCanvasHeight(id, height) {
    const canvas = document.getElementById(id);
    if (!canvas || !canvas.parentElement) return canvas;
    canvas.parentElement.style.height = `${height || 220}px`;
    return canvas;
  }

  function setEmpty(id, isEmpty, message) {
    const canvas = document.getElementById(id);
    if (!canvas || !canvas.parentElement) return;
    const wrap = canvas.parentElement;
    let overlay = wrap.querySelector(".chart-empty");
    if (isEmpty) {
      canvas.style.visibility = "hidden";
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.className = "chart-empty";
        wrap.appendChild(overlay);
      }
      overlay.textContent = message || "No data in this range";
    } else {
      canvas.style.visibility = "";
      if (overlay) overlay.remove();
    }
  }

  // Update-in-place when a compatible chart already exists (smooth, no flash);
  // otherwise build fresh. This is what makes the 60s live refresh seamless.
  function render(id, type, dataObj, extraOptions, height) {
    const canvas = ensureCanvasHeight(id, height);
    if (!canvas || typeof Chart === "undefined") return null;
    const existing = charts[id];
    const nextLen = (dataObj.datasets || []).length;
    if (
      existing &&
      existing.config.type === type &&
      existing.data.datasets.length === nextLen
    ) {
      if ("labels" in dataObj) existing.data.labels = dataObj.labels;
      dataObj.datasets.forEach((ds, i) =>
        Object.assign(existing.data.datasets[i], ds)
      );
      existing.update();
      return existing;
    }
    destroyChart(id);
    charts[id] = new Chart(canvas, {
      type,
      data: dataObj,
      options: chartOptions(extraOptions),
    });
    return charts[id];
  }

  function mkLine(id, labels, datasets, extra, height) {
    return render(id, "line", { labels, datasets }, extra, height);
  }
  function mkBar(id, labels, datasets, extra, height) {
    return render(id, "bar", { labels, datasets }, extra, height);
  }
  function mkScatter(id, datasets, extra, height) {
    return render(id, "scatter", { datasets }, extra, height);
  }

  function flashLive() {
    const dot = $("#liveDot");
    if (dot) {
      dot.classList.remove("flash");
      void dot.offsetWidth;
      dot.classList.add("flash");
      setTimeout(() => dot.classList.remove("flash"), 700);
    }
    const stamp = $("#lastRefresh");
    if (stamp) {
      stamp.textContent = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
    }
  }

  /* ----------------------------------------------------------- url + params */

  function currentParams() {
    return new URLSearchParams(window.location.search);
  }

  function withParams(baseUrl, params) {
    const query = params.toString();
    return query ? `${baseUrl}?${query}` : baseUrl;
  }

  function apiUrlWithParams(params) {
    const url = new URL(state.apiUrl, window.location.origin);
    url.search = params.toString();
    return url.toString();
  }

  /* --------------------------------------------------------- PJAX navigation */

  function topProgress(active) {
    let bar = $("#pjaxBar");
    if (!bar) return;
    if (active) {
      bar.classList.remove("done");
      bar.classList.add("active");
    } else {
      bar.classList.remove("active");
      bar.classList.add("done");
      setTimeout(() => bar.classList.remove("done"), 300);
    }
  }

  function readMeta() {
    const meta = $("#page-meta");
    state.page = meta ? meta.dataset.page || "" : "";
    state.apiUrl = meta ? meta.dataset.apiUrl || "" : "";
    state.pageUrl = meta ? meta.dataset.pageUrl || "" : "";
    const dataEl = $("#page-data");
    if (dataEl) {
      try {
        state.data = JSON.parse(dataEl.textContent || "{}");
      } catch (e) {
        state.data = {};
      }
    } else {
      state.data = {};
    }
  }

  function syncSidebar(pathname) {
    document.querySelectorAll(".nav-btn").forEach((link) => {
      try {
        const linkPath = new URL(link.href, window.location.origin).pathname;
        link.classList.toggle("active", linkPath === pathname);
      } catch (e) {
        /* noop */
      }
    });
  }

  async function navigate(url, opts) {
    opts = opts || {};
    const main = $("#mainCol");
    const scroller = $(".content");
    const fromPath = window.location.pathname;
    const targetPath = new URL(url, window.location.origin).pathname;
    const keepScroll = fromPath === targetPath && scroller;
    const savedScroll = keepScroll ? scroller.scrollTop : 0;

    topProgress(true);
    if (main) main.classList.add("is-loading");
    try {
      const res = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
      if (!res.ok) throw new Error("bad status " + res.status);
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const newMain = doc.querySelector("#mainCol");
      if (!newMain || !main) {
        window.location.assign(url);
        return;
      }
      resetCharts();
      main.innerHTML = newMain.innerHTML;
      if (opts.push !== false) history.pushState({ pjax: true }, "", url);
      syncSidebar(targetPath);
      readMeta();
      initPageCharts();
      const newScroller = $(".content");
      if (newScroller) newScroller.scrollTop = keepScroll ? savedScroll : 0;
    } catch (e) {
      window.location.assign(url);
    } finally {
      if (main) main.classList.remove("is-loading");
      topProgress(false);
    }
  }

  function navParam(key, value) {
    const params = currentParams();
    params.set(key, value);
    navigate(withParams(state.pageUrl || window.location.pathname, params));
  }

  /* --------------------------------------------------------- live refresh */

  async function liveRefresh() {
    if (document.hidden || !state.apiUrl) return;
    try {
      const res = await fetch(apiUrlWithParams(currentParams()), {
        headers: { "X-Requested-With": "fetch" },
      });
      if (!res.ok) return;
      const ctx = await res.json();
      if (ctx.page_data_json) {
        try {
          state.data = JSON.parse(ctx.page_data_json);
        } catch (e) {
          /* keep old */
        }
      }
      initPageCharts();
      updateKpis(ctx);
      flashLive();
    } catch (e) {
      /* silent — next tick retries */
    }
  }

  function startRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(liveRefresh, REFRESH_MS);
  }

  function formatNumber(value) {
    const n = Number(value) || 0;
    if (Math.abs(n) >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(Math.round(n * 10) / 10);
  }

  function animateNumber(el, to, suffix, decimals) {
    const from = parseFloat((el.textContent || "0").replace(/[^0-9.\-]/g, "")) || 0;
    if (from === to) {
      el.textContent = fmtFixed(to, decimals, suffix);
      return;
    }
    const start = performance.now();
    const dur = 500;
    function step(now) {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      const value = from + (to - from) * eased;
      el.textContent = fmtFixed(value, decimals, suffix);
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function fmtFixed(value, decimals, suffix) {
    const big = Math.abs(value) >= 1000;
    const text = big ? formatNumber(value) : value.toFixed(decimals || 0);
    return text + (suffix || "");
  }

  function updateKpis(ctx) {
    document.querySelectorAll("[data-kpi]").forEach((el) => {
      const key = el.dataset.kpi;
      if (!(key in ctx)) return;
      const suffix = el.dataset.kpiSuffix || "";
      const decimals = parseInt(el.dataset.kpiDecimals || "0", 10);
      const next = Number(ctx[key]);
      if (Number.isNaN(next)) return;
      animateNumber(el, next, suffix, decimals);
      el.classList.remove("kpi-bump");
      void el.offsetWidth;
      el.classList.add("kpi-bump");
    });
  }

  /* ------------------------------------------------------------- heatmap */

  function buildHeatmap(heatmapData) {
    const mount = $("#heatmapWrap");
    if (!mount) return;
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    let html = '<div class="heatmap-grid">';
    html +=
      "<div></div>" + days.map((day) => `<div class="hm-day">${day}</div>`).join("");
    for (let hour = 0; hour < 24; hour += 1) {
      html += `<div class="hm-label">${hour}:00</div>`;
      for (let day = 0; day < 7; day += 1) {
        const value = ((heatmapData || [])[day] || [])[hour] || 0;
        const bg =
          value > 70
            ? `rgba(239,68,68,${0.25 + value / 200})`
            : value > 45
              ? `rgba(245,158,11,${0.2 + value / 300})`
              : `rgba(34,197,94,${0.15 + value / 400})`;
        html += `<div class="hm-cell" style="background:${bg}" title="${days[day]} ${hour}:00 — avg CPU ${value.toFixed(1)}%">${value.toFixed(0)}%</div>`;
      }
    }
    html += "</div>";
    mount.innerHTML = html;
  }

  /* ------------------------------------------------------- page chart sets */

  function latencyDatasets(latency) {
    return [
      {
        label: "P50",
        data: latency.map((row) => row.p50),
        borderColor: colors.blue,
        backgroundColor: "rgba(96,165,250,0.12)",
        fill: true,
        tension: SPIKY,
        pointRadius: 0,
      },
      {
        label: "P95",
        data: latency.map((row) => row.p95),
        borderColor: colors.amber,
        tension: SPIKY,
        pointRadius: 0,
      },
      {
        label: "P99",
        data: latency.map((row) => row.p99),
        borderColor: colors.red,
        tension: SPIKY,
        pointRadius: 0,
      },
    ];
  }

  function renderTrafficCharts(data, suffix) {
    const traffic = data.traffic_series || [];
    const labels = traffic.map((row) => labelForTs(row.ts));
    setEmpty("c-throughput" + suffix, traffic.length === 0);
    mkLine("c-throughput" + suffix, labels, [
      {
        label: "Requests (est.)",
        data: traffic.map((row) => row.count),
        borderColor: colors.accent,
        backgroundColor: "rgba(123,131,255,0.14)",
        fill: true,
        tension: SMOOTH,
        pointRadius: 0,
      },
    ]);

    setEmpty("c-errsla" + suffix, traffic.length === 0);
    mkLine(
      "c-errsla" + suffix,
      labels,
      [
        {
          label: "Error rate %",
          data: traffic.map((row) => row.err_rate),
          borderColor: colors.red,
          backgroundColor: "rgba(239,68,68,0.10)",
          fill: true,
          tension: SPIKY,
          pointRadius: 0,
          yAxisID: "y",
        },
        {
          label: "SLA met %",
          data: traffic.map((row) => row.sla),
          borderColor: colors.green,
          tension: SPIKY,
          pointRadius: 0,
          yAxisID: "y2",
        },
      ],
      {
        scales: {
          x: { grid: { color: colors.grid }, ticks: { color: colors.muted, maxTicksLimit: 8 } },
          y: {
            position: "left",
            grid: { color: colors.grid },
            ticks: { color: colors.muted },
            title: { display: true, text: "Error %", color: colors.muted },
            suggestedMax: 10,
          },
          y2: {
            position: "right",
            grid: { display: false },
            ticks: { color: colors.muted },
            title: { display: true, text: "SLA %", color: colors.muted },
            min: 0,
            max: 100,
          },
        },
      }
    );
  }

  function initOverviewCharts(data) {
    const latency = data.latency_series || [];
    setEmpty("c-latency", latency.length === 0);
    mkLine("c-latency", latency.map((row) => labelForTs(row.ts)), latencyDatasets(latency));

    renderTrafficCharts(data, "");

    const errorRows = data.error_by_status || [];
    setEmpty("c-errors", errorRows.length === 0);
    mkBar(
      "c-errors",
      errorRows.map((row) => row.code),
      [
        {
          label: "Errors",
          data: errorRows.map((row) => row.count),
          backgroundColor: errorRows.map((row) =>
            row.code >= 500 ? "rgba(239,68,68,0.65)" : "rgba(245,158,11,0.6)"
          ),
          borderRadius: 6,
        },
      ]
    );
  }

  function initAPICharts(data) {
    const latency = data.latency_series || [];
    const datasets = latencyDatasets(latency);
    datasets.push({
      label: "SLA 300ms",
      data: latency.map(() => 300),
      borderColor: colors.text,
      borderDash: [6, 4],
      pointRadius: 0,
      fill: false,
    });
    setEmpty("c-latency-api", latency.length === 0);
    mkLine("c-latency-api", latency.map((row) => labelForTs(row.ts)), datasets);

    const scatter = data.scatter || [];
    setEmpty("c-scatter", scatter.length === 0);
    mkScatter(
      "c-scatter",
      [
        {
          label: "2xx",
          data: scatter.filter((r) => r.sc < 400).map((r) => ({ x: r.x, y: r.y })),
          backgroundColor: "rgba(34,197,94,0.45)",
        },
        {
          label: "4xx",
          data: scatter.filter((r) => r.sc >= 400 && r.sc < 500).map((r) => ({ x: r.x, y: r.y })),
          backgroundColor: "rgba(245,158,11,0.55)",
        },
        {
          label: "5xx",
          data: scatter.filter((r) => r.sc >= 500).map((r) => ({ x: r.x, y: r.y })),
          backgroundColor: "rgba(239,68,68,0.65)",
        },
      ],
      {
        scales: {
          x: { grid: { color: colors.grid }, ticks: { color: colors.muted }, title: { display: true, text: "Response time (ms)", color: colors.muted } },
          y: { grid: { color: colors.grid }, ticks: { color: colors.muted }, title: { display: true, text: "DB queries", color: colors.muted } },
        },
      }
    );

    const conc = data.conc_series || [];
    setEmpty("c-conc", conc.length === 0);
    mkLine("c-conc", conc.map((row) => labelForTs(row.ts)), [
      {
        label: "Concurrent requests (per worker)",
        data: conc.map((row) => row.v),
        borderColor: colors.purple,
        backgroundColor: "rgba(167,139,250,0.12)",
        fill: true,
        tension: SPIKY,
        pointRadius: 0,
      },
    ]);
  }

  function initWSCharts(data) {
    const lifecycle = data.lifecycle || [];
    setEmpty("c-ws-life", lifecycle.length === 0);
    mkLine("c-ws-life", lifecycle.map((row) => labelForTs(row.ts)), [
      {
        label: "Connects",
        data: lifecycle.map((row) => row.connects),
        borderColor: colors.green,
        backgroundColor: "rgba(34,197,94,0.08)",
        fill: true,
        tension: SPIKY,
        pointRadius: 0,
      },
      {
        label: "Disconnects",
        data: lifecycle.map((row) => row.disconnects),
        borderColor: colors.red,
        tension: SPIKY,
        pointRadius: 0,
      },
    ]);

    const consumerMsgs = data.consumer_msgs || [];
    setEmpty("c-ws-consumer", consumerMsgs.length === 0);
    mkBar(
      "c-ws-consumer",
      consumerMsgs.map((row) => row.consumer_name),
      [
        { label: "Inbound", data: consumerMsgs.map((r) => r.inbound), backgroundColor: "rgba(96,165,250,0.6)", borderRadius: 6 },
        { label: "Outbound", data: consumerMsgs.map((r) => r.outbound), backgroundColor: "rgba(167,139,250,0.6)", borderRadius: 6 },
      ]
    );

    const hist = data.duration_hist || { labels: [], counts: [] };
    setEmpty("c-ws-duration", (hist.counts || []).length === 0);
    mkBar("c-ws-duration", hist.labels || [], [
      { label: "Connections", data: hist.counts || [], backgroundColor: "rgba(123,131,255,0.6)", borderRadius: 6 },
    ]);

    // Per-event processing latency — exposes slow connect events that
    // consumer-level averages hide.
    const ev = (data.event_latency || []).slice(0, 8);
    setEmpty("c-ws-event-lat", ev.length === 0);
    mkBar(
      "c-ws-event-lat",
      ev.map((r) => `${r.consumer} · ${r.event}`),
      [
        { label: "P50", data: ev.map((r) => r.p50 || 0), backgroundColor: "rgba(96,165,250,0.6)", borderRadius: 4 },
        { label: "P95", data: ev.map((r) => r.p95 || 0), backgroundColor: "rgba(245,158,11,0.65)", borderRadius: 4 },
        { label: "P99", data: ev.map((r) => r.p99 || 0), backgroundColor: "rgba(239,68,68,0.7)", borderRadius: 4 },
      ],
      { indexAxis: "y" }
    );
  }

  function thresholdSet(label, value, count, color) {
    return {
      label,
      data: new Array(count).fill(value),
      borderColor: color,
      borderDash: [5, 4],
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
    };
  }

  function initResourceCharts(data) {
    const cpu = data.cpu_series || [];
    setEmpty("c-cpu", cpu.length === 0);
    mkLine(
      "c-cpu",
      cpu.map((row) => labelForTs(row.ts)),
      [
        {
          label: "CPU %",
          data: cpu.map((row) => row.v),
          borderColor: colors.amber,
          backgroundColor: "rgba(245,158,11,0.08)",
          fill: true,
          tension: SPIKY,
          pointRadius: 0,
        },
        thresholdSet("Warn 60%", 60, cpu.length, "rgba(245,158,11,0.5)"),
        thresholdSet("Critical 80%", 80, cpu.length, "rgba(239,68,68,0.6)"),
      ],
      { scales: { y: { suggestedMax: 100, grid: { color: colors.grid }, ticks: { color: colors.muted } }, x: { grid: { color: colors.grid }, ticks: { color: colors.muted, maxTicksLimit: 8 } } } }
    );

    const ram = data.ram_series || [];
    setEmpty("c-ram", ram.length === 0);
    mkLine(
      "c-ram",
      ram.map((row) => labelForTs(row.ts)),
      [
        {
          label: "RAM %",
          data: ram.map((row) => row.pct),
          borderColor: colors.purple,
          backgroundColor: "rgba(167,139,250,0.08)",
          fill: true,
          tension: SPIKY,
          pointRadius: 0,
        },
        thresholdSet("Warn 70%", 70, ram.length, "rgba(245,158,11,0.5)"),
        thresholdSet("Critical 85%", 85, ram.length, "rgba(239,68,68,0.6)"),
      ],
      { scales: { y: { suggestedMax: 100, grid: { color: colors.grid }, ticks: { color: colors.muted } }, x: { grid: { color: colors.grid }, ticks: { color: colors.muted, maxTicksLimit: 8 } } } }
    );

    const fds = data.fds_series || [];
    setEmpty("c-fds", fds.length === 0);
    mkLine("c-fds", fds.map((row) => labelForTs(row.ts)), [
      { label: "Open file descriptors", data: fds.map((r) => r.fds), borderColor: colors.blue, tension: SPIKY, pointRadius: 0 },
      { label: "Threads", data: fds.map((r) => r.threads), borderColor: colors.green, tension: SPIKY, pointRadius: 0 },
    ]);

    buildHeatmap(data.heatmap || []);

    const celeryQueue = data.celery_queue || [];
    setEmpty("c-celeryQ", celeryQueue.length === 0);
    mkLine("c-celeryQ", celeryQueue.map((row) => labelForTs(row.ts)), [
      { label: "Queued tasks", data: celeryQueue.map((r) => r.v), borderColor: colors.red, backgroundColor: "rgba(239,68,68,0.08)", fill: true, tension: SPIKY, pointRadius: 0 },
    ]);

    const celeryTasks = data.celery_tasks || [];
    setEmpty("c-celeryTasks", celeryTasks.length === 0);
    mkBar(
      "c-celeryTasks",
      celeryTasks.map((row) => labelForTs(row.ts)),
      [
        { label: "Active", data: celeryTasks.map((r) => r.active), backgroundColor: "rgba(34,197,94,0.55)", stack: "tasks" },
        { label: "Reserved", data: celeryTasks.map((r) => r.reserved), backgroundColor: "rgba(96,165,250,0.55)", stack: "tasks" },
        { label: "Queued", data: celeryTasks.map((r) => r.queued), backgroundColor: "rgba(239,68,68,0.55)", stack: "tasks" },
      ],
      {
        scales: {
          x: { stacked: true, grid: { color: colors.grid }, ticks: { color: colors.muted, maxTicksLimit: 8 } },
          y: { stacked: true, grid: { color: colors.grid }, ticks: { color: colors.muted } },
        },
      }
    );

    const redisMem = data.redis_mem || [];
    setEmpty("c-redisMem", redisMem.length === 0);
    mkLine("c-redisMem", redisMem.map((row) => labelForTs(row.ts)), [
      { label: "Redis memory MB", data: redisMem.map((r) => r.v), borderColor: colors.accent, backgroundColor: "rgba(123,131,255,0.08)", fill: true, tension: SMOOTH, pointRadius: 0 },
    ]);

    const redisClients = data.redis_clients || [];
    setEmpty("c-redisClients", redisClients.length === 0);
    mkLine("c-redisClients", redisClients.map((row) => labelForTs(row.ts)), [
      { label: "Connected", data: redisClients.map((r) => r.connected), borderColor: colors.blue, tension: SPIKY, pointRadius: 0 },
      { label: "Blocked", data: redisClients.map((r) => r.blocked), borderColor: colors.red, tension: SPIKY, pointRadius: 0 },
    ]);

    const pgConn = data.pg_conn || [];
    setEmpty("c-pgConn", pgConn.length === 0);
    mkLine("c-pgConn", pgConn.map((row) => labelForTs(row.ts)), [
      { label: "Active", data: pgConn.map((r) => r.active), borderColor: colors.green, tension: SPIKY, pointRadius: 0 },
      { label: "Idle", data: pgConn.map((r) => r.idle), borderColor: colors.amber, tension: SPIKY, pointRadius: 0 },
    ]);

    const pgSize = data.pg_size || [];
    setEmpty("c-pgSize", pgSize.length === 0);
    mkLine("c-pgSize", pgSize.map((row) => labelForTs(row.ts)), [
      { label: "DB size MB", data: pgSize.map((r) => r.v), borderColor: colors.green, backgroundColor: "rgba(34,197,94,0.08)", fill: true, tension: SMOOTH, pointRadius: 0 },
    ]);
  }

  function initDBCharts(data) {
    const hist = data.db_hist || { labels: [], counts: [] };
    setEmpty("c-histDb", (hist.counts || []).length === 0);
    mkBar("c-histDb", hist.labels || [], [
      {
        label: "Requests",
        data: hist.counts || [],
        backgroundColor: (hist.counts || []).map((_, idx) =>
          idx > 7 ? "rgba(239,68,68,0.65)" : idx > 4 ? "rgba(245,158,11,0.6)" : "rgba(123,131,255,0.6)"
        ),
        borderRadius: 5,
      },
    ]);

    // DB offenders ranked by estimated TOTAL DB time contribution — shows where
    // query optimization pays off most, not just per-request averages.
    const offenders = (data.db_offenders || []).slice().reverse();
    setEmpty("c-dbOffenders", offenders.length === 0);
    mkBar(
      "c-dbOffenders",
      offenders.map((r) => r.endpoint),
      [
        {
          label: "Est. total DB time (ms)",
          data: offenders.map((r) => r.est_total_db_ms),
          backgroundColor: offenders.map((r) =>
            r.share_pct > 25 ? "rgba(239,68,68,0.7)" : r.share_pct > 10 ? "rgba(245,158,11,0.65)" : "rgba(123,131,255,0.6)"
          ),
          borderRadius: 5,
        },
      ],
      { indexAxis: "y", scales: { y: { ticks: { color: colors.muted, autoSkip: false, font: { size: 10 } }, grid: { display: false } }, x: { grid: { color: colors.grid }, ticks: { color: colors.muted } } } },
      Math.max(220, offenders.length * 26 + 40)
    );

    const scatter = data.db_scatter || [];
    setEmpty("c-dbScatter", scatter.length === 0);
    mkScatter(
      "c-dbScatter",
      [
        { label: "DB < 50% of resp", data: scatter.filter((r) => r.x <= r.y * 0.5), backgroundColor: "rgba(123,131,255,0.5)" },
        { label: "DB > 50% of resp", data: scatter.filter((r) => r.x > r.y * 0.5), backgroundColor: "rgba(239,68,68,0.65)" },
      ],
      {
        scales: {
          x: { grid: { color: colors.grid }, ticks: { color: colors.muted }, title: { display: true, text: "DB time (ms)", color: colors.muted } },
          y: { grid: { color: colors.grid }, ticks: { color: colors.muted }, title: { display: true, text: "Response time (ms)", color: colors.muted } },
        },
      }
    );
  }

  function initCorrCharts(data) {
    const chartData = data.corr_chart || {};
    const labels = (chartData.p99 || []).map((row) => labelForTs(row.ts));
    const cpu = chartData.cpu || [];
    const ram = chartData.ram || [];
    const celery = chartData.celery || [];
    const hasData = (chartData.p99 || []).length || cpu.length;
    setEmpty("c-corr", !hasData);
    mkLine(
      "c-corr",
      labels.length ? labels : cpu.map((row) => labelForTs(row.ts)),
      [
        { label: "P99 ms", data: (chartData.p99 || []).map((r) => r.v), borderColor: colors.accent, backgroundColor: "rgba(123,131,255,0.07)", fill: true, tension: SPIKY, pointRadius: 0, yAxisID: "y" },
        { label: "CPU %", data: cpu.map((r) => r.v), borderColor: colors.amber, tension: SPIKY, pointRadius: 0, yAxisID: "y2" },
        { label: "RAM %", data: ram.map((r) => r.v), borderColor: colors.purple, borderDash: [5, 3], tension: SPIKY, pointRadius: 0, yAxisID: "y2" },
        { label: "Celery queue", data: celery.map((r) => r.v), borderColor: colors.green, borderDash: [3, 4], tension: SPIKY, pointRadius: 0, yAxisID: "y2" },
      ],
      {
        scales: {
          x: { grid: { color: colors.grid }, ticks: { color: colors.muted, maxTicksLimit: 8 } },
          y: { position: "left", grid: { color: colors.grid }, ticks: { color: colors.muted }, title: { display: true, text: "Latency (ms)", color: colors.muted } },
          y2: { position: "right", grid: { display: false }, ticks: { color: colors.muted }, title: { display: true, text: "% / queue", color: colors.muted } },
        },
      }
    );
  }

  function initPageCharts() {
    const data = state.data || {};
    switch (state.page) {
      case "overview":
        initOverviewCharts(data);
        break;
      case "api_performance":
        initAPICharts(data);
        break;
      case "websocket":
        initWSCharts(data);
        break;
      case "system_resources":
        initResourceCharts(data);
        break;
      case "database_queries":
        initDBCharts(data);
        break;
      case "correlation":
        initCorrCharts(data);
        break;
      default:
        break;
    }
  }

  /* ---------------------------------------------------------------- drawer */

  function openDrawer(title, rowsHtml, footerHtml) {
    const drawer = $("#detailDrawer");
    const overlay = $("#drawerOverlay");
    if (!drawer || !overlay) return;
    $("#drawerTitle").textContent = title || "Detail";
    $("#drawerBody").innerHTML = rowsHtml || "";
    $("#drawerFooter").innerHTML = footerHtml || "";
    overlay.classList.remove("hidden");
    drawer.classList.add("open");
  }

  function closeDrawer() {
    const drawer = $("#detailDrawer");
    const overlay = $("#drawerOverlay");
    if (drawer) drawer.classList.remove("open");
    if (overlay) overlay.classList.add("hidden");
  }

  function drawerRow(label, value) {
    if (value === undefined || value === null || value === "") return "";
    return `<div class="drw-row"><span class="drw-k">${label}</span><span class="drw-v">${value}</span></div>`;
  }

  function openRowDrawer(tr) {
    const d = tr.dataset;
    let body = "";
    body += drawerRow("Time", d.time);
    body += drawerRow("Method", d.method);
    body += drawerRow("Endpoint", d.endpoint);
    body += drawerRow("Status", d.status);
    body += drawerRow("Response time", d.response ? d.response + " ms" : "");
    body += drawerRow("DB queries", d.dbq);
    body += drawerRow("DB time", d.dbt ? d.dbt + " ms" : "");
    body += drawerRow("DB share", d.dbpct ? d.dbpct + "%" : "");
    body += drawerRow("Concurrent", d.conc);
    body += drawerRow("Consumer", d.consumer);
    body += drawerRow("Event", d.event);
    body += drawerRow("Direction", d.direction);
    body += drawerRow("Msg size", d.msg ? d.msg + " B" : "");
    body += drawerRow("Proc time", d.proc ? d.proc + " ms" : "");
    let footer = "";
    if (d.endpoint) {
      const params = new URLSearchParams();
      params.set("range", currentParams().get("range") || "24h");
      params.set("endpoint", d.endpoint);
      footer = `<a class="btn-sm" id="drawerCorr" href="/dashboard/correlation/?${params.toString()}">Open in Correlation ↗</a>`;
    }
    openRowDrawerRender(d, body, footer);
  }

  function openRowDrawerRender(d, body, footer) {
    const title = d.endpoint ? d.endpoint : d.consumer ? d.consumer : "Request detail";
    openDrawer(title, body, footer);
  }

  /* ---------------------------------------------------------- interactions */

  function gatherAndNav(map) {
    const params = currentParams();
    Object.keys(map).forEach((param) => {
      const el = $(map[param]);
      params.set(param, el ? el.value : "all");
    });
    navigate(withParams(state.pageUrl || window.location.pathname, params));
  }

  function onClick(event) {
    const navBtn = event.target.closest(".nav-btn");
    if (navBtn && navBtn.href) {
      event.preventDefault();
      navigate(navBtn.href);
      return;
    }

    const rangeBtn = event.target.closest(".range-btn");
    if (rangeBtn) {
      navParam("range", rangeBtn.dataset.range);
      return;
    }

    const tabBtn = event.target.closest("[data-tab]");
    if (tabBtn) {
      navParam("tab", tabBtn.dataset.tab);
      return;
    }

    const svcBtn = event.target.closest("[data-service]");
    if (svcBtn) {
      navParam("service", svcBtn.dataset.service);
      return;
    }

    const pageLink = event.target.closest(".pagination a[href]");
    if (pageLink) {
      event.preventDefault();
      navigate(pageLink.href);
      return;
    }

    if (event.target.closest("#api-filter-apply")) {
      gatherAndNav({ search: "#api-search", method: "#api-method", status: "#api-status", slow: "#api-slow" });
      return;
    }
    if (event.target.closest("#raw-api-apply")) {
      gatherAndNav({ search: "#raw-search", method: "#raw-method", status: "#raw-status", slow: "#raw-slow" });
      return;
    }
    if (event.target.closest("#raw-ws-apply")) {
      gatherAndNav({ consumer: "#raw-ws-consumer", event: "#raw-ws-event" });
      return;
    }
    if (event.target.closest("#corr-analyze")) {
      const params = currentParams();
      const endpoint = $("#corr-endpoint");
      const start = $("#corr-start");
      const end = $("#corr-end");
      if (endpoint) params.set("endpoint", endpoint.value);
      if (start && start.value) params.set("start", start.value);
      if (end && end.value) params.set("end", end.value);
      navigate(withParams(state.pageUrl || window.location.pathname, params));
      return;
    }

    const epRow = event.target.closest("[data-endpoint-nav]");
    if (epRow) {
      const params = new URLSearchParams();
      params.set("range", currentParams().get("range") || "24h");
      params.set("endpoint", epRow.dataset.endpointNav);
      navigate("/dashboard/correlation/?" + params.toString());
      return;
    }

    const drillRow = event.target.closest("tr.js-drilldown");
    if (drillRow) {
      openRowDrawer(drillRow);
      return;
    }

    if (event.target.closest("#drawerClose") || event.target.id === "drawerOverlay") {
      closeDrawer();
      return;
    }

    if (event.target.closest("[data-open-glossary]")) {
      const overlay = $("#glossaryOverlay");
      if (overlay) overlay.classList.remove("hidden");
      return;
    }
    if (event.target.closest("#glossaryClose") || event.target.id === "glossaryOverlay") {
      const overlay = $("#glossaryOverlay");
      if (overlay) overlay.classList.add("hidden");
      return;
    }
  }

  function bindLatencyTip() {
    const tip = $("#perfTip");
    if (!tip) return;
    let hideTimer = null;
    function showTip(btn) {
      clearTimeout(hideTimer);
      const rect = btn.getBoundingClientRect();
      tip.classList.remove("hidden");
      tip.style.top = rect.bottom + 8 + "px";
      const rightGap = window.innerWidth - rect.right;
      tip.style.right = Math.max(8, rightGap) + "px";
      tip.style.left = "auto";
      void tip.offsetWidth;
      tip.classList.add("tip-visible");
    }
    function hideTip() {
      hideTimer = setTimeout(() => {
        tip.classList.remove("tip-visible");
        tip.addEventListener("transitionend", () => tip.classList.add("hidden"), { once: true });
      }, 120);
    }
    document.addEventListener("mouseover", (e) => {
      const btn = e.target.closest("[data-tip-trigger]");
      if (btn) showTip(btn);
    });
    document.addEventListener("mouseout", (e) => {
      if (e.target.closest("[data-tip-trigger]")) hideTip();
    });
    tip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
    tip.addEventListener("mouseleave", hideTip);
  }

  function boot() {
    readMeta();
    flashLive();
    initPageCharts();
    startRefresh();
  }

  document.addEventListener("click", onClick);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    closeDrawer();
    const g = $("#glossaryOverlay");
    if (g) g.classList.add("hidden");
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) liveRefresh();
  });
  window.addEventListener("popstate", () => navigate(window.location.href, { push: false }));

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bindLatencyTip();
      boot();
    });
  } else {
    bindLatencyTip();
    boot();
  }
})();
