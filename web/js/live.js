/* live.js: the booth's live dashboard. Plays the eight recorded drives of the
   release's reference scenario in real time, one after another, and loops.
   Every car's verdict comes from analysis/make_live_export.py: a detector
   trained without that car (out of fold by physical transmitter). Nothing here
   is simulated in the browser; it replays what the export recorded. */
(function () {
  "use strict";
  const D = document, SITE = window.SITE || {}, META = SITE.live_meta, DRIVES = SITE.drives || {};
  const $ = (id) => D.getElementById(id);
  if (!META) { $("drive").textContent = "data missing: run analysis/make_live_export.py"; return; }

  const CLASSES = META.classes, FPS = 1000 / META.frame_ms, ROAD = META.road_m;
  const ALERT_SHARE = 0.5; // most receivers that heard the car say attack
  const COL = { 1: "#ee6d3d", 3: "#ee6d3d", 11: "#ee6d3d", 13: "#ee6d3d", 4: "#a68bf0", 5: "#f08fb8", 6: "#6aa8f0", 7: "#f5c66a", 12: "#f5c66a", 8: "#6a8199", 0: "#a8bccd" };
  const NAME = { 0: "Honest", 1: "Position lie, large", 3: "Random position", 4: "Replay", 5: "Speed lie", 6: "Fake identities",
    7: "Flooding", 8: "Slot hoarding", 11: "Position lie, small", 12: "Low-rate flooding", 13: "Position lie, medium" };
  const ORDER = [7, 3, 12, 6, 5, 1, 4, 13, 11, 8];
  const fmt = (v, d) => Number(v).toLocaleString("en-AU", { minimumFractionDigits: d, maximumFractionDigits: d });
  const F = SITE.facts || {};
  $("pub-f1").textContent = F.baseline_f1 || "?";
  $("pub-mcc").textContent = F.baseline_mcc || "?";
  $("km").textContent = fmt(ROAD / 1000, 0);

  /* stage scaling, as in the walkthrough */
  const stage = D.querySelector(".stage");
  const fit = () => stage.style.setProperty("--s", Math.min(innerWidth / 1920, innerHeight / 1080));
  addEventListener("resize", fit); fit();

  /* canvases at device resolution, drawn in stage pixels */
  function canvas(cv) {
    const o = { cv, ctx: cv.getContext("2d"), w: 1, h: 1 };
    o.fit = () => {
      const r = cv.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, 2);
      o.w = cv.offsetWidth; o.h = cv.offsetHeight;
      const k = r.width / o.w || 1;
      cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
      o.ctx.setTransform(dpr * k, 0, 0, dpr * k, 0, 0);
      if (o.redraw) o.redraw(); // resizing a canvas clears it
    };
    new ResizeObserver(o.fit).observe(cv); addEventListener("resize", o.fit); o.fit();
    return o;
  }
  const R = canvas($("road")), SP = canvas($("spark"));

  /* scoreboard rows */
  const score = $("score"), bars = {};
  [...ORDER, 0].forEach((c) => {
    const row = D.createElement("div");
    row.className = "row" + (c === 0 ? " honest" : "");
    row.innerHTML = `<span>${c === 0 ? "Honest cars, wrongly alerted" : NAME[c]}</span><div class="bar"><i style="background:${c === 0 ? "#6a8199" : COL[c]}"></i></div><span class="pct">0%</span>`;
    score.appendChild(row);
    bars[c] = { bar: row.querySelector("i"), pct: row.querySelector(".pct") };
  });

  /* state */
  const nDrives = Object.keys(DRIVES).length;
  let d = 1, drive = null, t = 0, lastSec = -1, seconds = null, alertNow = new Map(), prevAlert = new Set();
  let conf, seen, alerted, spark;
  function resetLoop() {
    conf = CLASSES.map(() => CLASSES.map(() => 0));
    seen = {}; alerted = {}; spark = [];
    $("feed").innerHTML = "";
  }
  function load(n) {
    drive = DRIVES[n];
    t = drive.f0; lastSec = -1; prevAlert = new Set(); alertNow = new Map();
    seconds = new Map();
    for (const s of drive.seconds) { if (!seconds.has(s[0])) seconds.set(s[0], []); seconds.get(s[0]).push(s); }
    drive.byId = new Map(drive.stations.map((s) => [s.id, s]));
    $("drive").textContent = `Drive ${n} of ${nDrives}`;
  }

  /* running scores from the cumulative confusion matrix, as sklearn computes them */
  function scores() {
    const K = CLASSES.length, row = Array(K).fill(0), col = Array(K).fill(0);
    let s = 0, c = 0;
    for (let i = 0; i < K; i++) for (let j = 0; j < K; j++) { row[i] += conf[i][j]; col[j] += conf[i][j]; s += conf[i][j]; }
    let f1 = 0, labels = 0;
    for (let i = 0; i < K; i++) {
      c += conf[i][i];
      if (row[i] === 0 && col[i] === 0) continue;
      labels++;
      const p = col[i] ? conf[i][i] / col[i] : 0, r = row[i] ? conf[i][i] / row[i] : 0;
      f1 += p + r ? (2 * p * r) / (p + r) : 0;
    }
    let pt = 0, pp = 0, tt = 0;
    for (let i = 0; i < K; i++) { pt += col[i] * row[i]; pp += col[i] * col[i]; tt += row[i] * row[i]; }
    const den = Math.sqrt((s * s - pp) * (s * s - tt));
    return { f1: labels ? f1 / labels : 0, mcc: den ? (c * s - pt) / den : 0 };
  }

  function second(w) {
    const list = seconds.get(w) || [];
    const now = new Map();
    let dec = 0, al = 0;
    for (const [win, sid, n, k, top, truth] of list) {
      dec += n;
      const alert = n > 0 && k >= Math.ceil(ALERT_SHARE * n) && top !== 0;
      seen[truth] = (seen[truth] || 0) + 1;
      if (alert) {
        al++; now.set(sid, top); alerted[truth] = (alerted[truth] || 0) + 1;
        if (!prevAlert.has(sid)) feed(win, sid, top, truth, k, n);
      }
    }
    prevAlert = new Set(now.keys()); alertNow = now;
    for (const [i, j, n] of drive.conf[w] || []) conf[i][j] += n;
    const sc = scores();
    if (list.length) { spark.push(sc.f1); if (spark.length > 240) spark.shift(); }
    $("f1").textContent = fmt(sc.f1, 3); $("mcc").textContent = fmt(sc.mcc, 3);
    $("dps").textContent = fmt(dec, 0); $("aps").textContent = fmt(al, 0);
    $("us").textContent = drive.us[w] != null ? fmt(drive.us[w], 1) : "?";
    $("fa").textContent = fmt(100 * (alerted[0] || 0) / Math.max(1, seen[0] || 0), 2) + "%";
    for (const c of [...ORDER, 0]) {
      const v = (alerted[c] || 0) / Math.max(1, seen[c] || 0);
      bars[c].bar.style.width = Math.min(100, (c === 0 ? 10 : 1) * 100 * v) + "%";
      bars[c].pct.textContent = seen[c] ? fmt(100 * v, c === 0 ? 1 : 0) + "%" : "none yet";
    }
    drawSpark();
  }

  function feed(win, sid, top, truth, k, n) {
    const st = drive.byId.get(sid), f = Math.max(0, Math.min(drive.f1, win * FPS) - drive.f0);
    const x = st ? st.pos[f * 4 + 2] / 10 : NaN;
    const tag = truth === 0 ? ["fa", "false alarm"] : truth === top ? ["ok", "correct"] : ["type", "other attack"];
    const li = D.createElement("li");
    li.innerHTML = `<span class="tm">${Math.floor(win / 60)}:${String(win % 60).padStart(2, "0")}</span>` +
      `<span class="km">${isNaN(x) ? "" : fmt((((x % ROAD) + ROAD) % ROAD) / 1000, 2) + " km"}</span>` +
      `<span class="cls"><i style="background:${COL[top]}"></i>${NAME[top]} <small>${k} of ${n} receivers</small></span>` +
      `<span class="tag ${tag[0]}">${tag[1]}</span>`;
    const ul = $("feed");
    ul.insertBefore(li, ul.firstChild);
    while (ul.children.length > 9) ul.removeChild(ul.lastChild);
  }

  function drawSpark() {
    const { ctx, w: W, h: H } = SP;
    ctx.clearRect(0, 0, W, H);
    if (spark.length < 2) return;
    const lo = 0.3, hi = 0.7, X = (i) => (i / (spark.length - 1)) * W, Y = (v) => H - 6 - ((v - lo) / (hi - lo)) * (H - 12);
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "rgba(69,189,180,.28)"); g.addColorStop(1, "rgba(69,189,180,0)");
    ctx.beginPath(); spark.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v))));
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath(); ctx.fillStyle = g; ctx.fill();
    ctx.beginPath(); spark.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v))));
    ctx.strokeStyle = "#45bdb4"; ctx.lineWidth = 2.5; ctx.stroke();
    const ref = Number(F.baseline_f1);
    if (ref) {
      ctx.setLineDash([5, 5]); ctx.strokeStyle = "rgba(238,243,248,.45)"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(0, Y(ref)); ctx.lineTo(W, Y(ref)); ctx.stroke(); ctx.setLineDash([]);
      ctx.font = '13px ui-monospace,"SF Mono",Menlo,monospace'; ctx.fillStyle = "rgba(238,243,248,.6)";
      ctx.fillText("published baseline", 4, Y(ref) - 6);
    }
  }

  /* the highway: three rows of 2 km, across the road widened so lanes show */
  const ROWS = 3, SEG = ROAD / ROWS;
  function drawRoad(time) {
    const { ctx, w: W, h: H } = R;
    ctx.clearRect(0, 0, W, H);
    const L = 8, Rr = 8, rowH = H / ROWS, ACROSS = 2.1;
    const map = (x, y) => {
      const xm = ((x % ROAD) + ROAD) % ROAD, r = Math.min(ROWS - 1, Math.floor(xm / SEG));
      return [L + ((xm - r * SEG) / SEG) * (W - L - Rr), r * rowH + rowH * 0.45 + y * ACROSS, r];
    };
    for (let r = 0; r < ROWS; r++) {
      const cy = r * rowH + rowH * 0.45;
      ctx.fillStyle = "#0d1b29"; ctx.fillRect(L, cy - 13 * ACROSS, W - L - Rr, 26 * ACROSS);
      ctx.strokeStyle = "rgba(220,230,240,.28)"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(L, cy - 12 * ACROSS); ctx.lineTo(W - Rr, cy - 12 * ACROSS); ctx.moveTo(L, cy + 12 * ACROSS); ctx.lineTo(W - Rr, cy + 12 * ACROSS); ctx.stroke();
      ctx.strokeStyle = "rgba(245,198,106,.30)"; ctx.beginPath(); ctx.moveTo(L, cy); ctx.lineTo(W - Rr, cy); ctx.stroke();
      ctx.font = '14px ui-monospace,"SF Mono",Menlo,monospace'; ctx.fillStyle = "#6a8199"; ctx.textAlign = "center";
      for (let m = 0; m <= SEG; m += 500) {
        const x = L + (m / SEG) * (W - L - Rr);
        ctx.fillText(fmt((r * SEG + m) / 1000, 1) + " km", Math.min(W - 34, Math.max(30, x)), cy + 13 * ACROSS + 22);
      }
      ctx.textAlign = "left";
    }
    for (const [x, y] of drive.rsu) {
      const [px, py] = map(x, y);
      ctx.fillStyle = "#45bdb4"; ctx.beginPath(); ctx.moveTo(px, py - 8); ctx.lineTo(px + 7, py + 5); ctx.lineTo(px - 7, py + 5); ctx.fill();
      const u = (time * 0.6 + x / 1000) % 1;
      ctx.strokeStyle = `rgba(69,189,180,${0.45 * (1 - u)})`; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(px, py, 6 + u * 26, 0, 7); ctx.stroke();
    }
    const fi = Math.floor(t - drive.f0), u = t - drive.f0 - fi;
    const at = (s, k) => {
      const a = s.pos[fi * 4 + k], b = s.pos[(fi + 1) * 4 + k];
      if (a === undefined || a === -99999) return null;
      return (b === undefined || b === -99999 || Math.abs(b - a) > 2000 ? a : a + (b - a) * u) / 10;
    };
    const pulse = 0.5 + 0.5 * Math.sin(time * 9);
    for (const s of drive.stations) {
      const tx = at(s, 0), ty = at(s, 1), cx = at(s, 2), cy = at(s, 3);
      if (tx === null) continue;
      const [ax, ay, ar] = map(tx, ty);
      if (s.attack !== 0 && cx !== null && Math.hypot(cx - tx, cy - ty) > 8) {
        const [gx, gy, gr] = map(cx, cy);
        if (gr === ar) {
          ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(238,109,61,.55)"; ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(gx, gy); ctx.stroke(); ctx.setLineDash([]);
        }
        ctx.strokeStyle = "rgba(238,109,61,.85)"; ctx.lineWidth = 1.4; ctx.setLineDash([3, 2]);
        ctx.strokeRect(gx - 6, gy - 3, 12, 6); ctx.setLineDash([]);
      }
      ctx.fillStyle = "#d8e2ec"; ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(ax - 6, ay - 3, 12, 6, 2) : ctx.rect(ax - 6, ay - 3, 12, 6); ctx.fill();
      const cls = alertNow.get(s.id);
      if (cls) {
        const [rx, ry] = cx !== null ? map(cx, cy) : [ax, ay];
        ctx.strokeStyle = COL[cls]; ctx.globalAlpha = 0.55 + 0.45 * pulse; ctx.lineWidth = 2.4;
        ctx.beginPath(); ctx.arc(rx, ry, 11 + 3 * pulse, 0, 7); ctx.stroke(); ctx.globalAlpha = 1;
      }
    }
  }

  /* the loop: real time, drive after drive */
  let last = performance.now(), switching = 0;
  const SPEED = Math.max(1, +(location.search.match(/[?&]speed=(\d+)/) || [0, 1])[1]); // ?speed=N, for testing only
  const still = /[?&]still\b/.test(location.search);
  function frame(now) {
    // one bad record must not freeze the booth screen: skip ahead to the next drive
    try { step(now); } catch (err) { console.error(err); t = drive.f1; }
    requestAnimationFrame(frame);
  }
  function step(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (switching > 0) {
      switching -= dt;
      if (switching <= 0) { $("switch").classList.remove("on"); }
    } else {
      t += dt * FPS * SPEED;
      if (t >= drive.f1) {
        d = d % nDrives + 1;
        if (d === 1) resetLoop();
        load(d);
        $("sw-d").textContent = `Drive ${d} of ${nDrives}`;
        $("switch").classList.add("on"); switching = 1.6;
      }
    }
    const w = Math.floor(t / FPS);
    if (w !== lastSec) { for (let s = lastSec < 0 ? w : lastSec + 1; s <= w; s++) second(s); lastSec = w; }
    const el = Math.max(0, t / FPS); // simulation time, the same clock the alert feed uses
    $("time").textContent = `${Math.floor(el / 60)}:${String(Math.floor(el % 60)).padStart(2, "0")}`;
    $("prog").style.width = (100 * (t - drive.f0)) / (drive.f1 - drive.f0) + "%";
    drawRoad(now / 1000);
  }
  SP.redraw = drawSpark;
  if (/[?&]still\b/.test(location.search)) D.documentElement.classList.add("still");
  // ?drive=N starts on drive N, for rehearsing and for checking every drive
  d = Math.min(nDrives, Math.max(1, +(location.search.match(/[?&]drive=(\d+)/) || [0, 1])[1]));
  resetLoop(); load(d);
  if (still) { // screenshots: jump forty seconds into the first drive, played through
    const end = drive.f0 + 40 * FPS;
    for (let s = Math.floor(drive.f0 / FPS); s <= Math.floor(end / FPS); s++) second(s);
    t = end; lastSec = Math.floor(end / FPS);
  }
  requestAnimationFrame(frame);

  /* booth: full screen on F, the screen stays awake */
  addEventListener("keydown", (e) => {
    if (e.key === "f" || e.key === "F") {
      if (!D.fullscreenElement) D.documentElement.requestFullscreen && D.documentElement.requestFullscreen().catch(() => {});
      else D.exitFullscreen();
    }
  });
  let lock = null;
  const wake = async () => { try { if ("wakeLock" in navigator && !lock) { lock = await navigator.wakeLock.request("screen"); lock.addEventListener("release", () => (lock = null)); } } catch (e) { /* not granted */ } };
  D.addEventListener("visibilitychange", () => D.visibilityState === "visible" && wake());
  addEventListener("pointerdown", wake); wake();
})();
