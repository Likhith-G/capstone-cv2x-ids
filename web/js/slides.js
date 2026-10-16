/* slides.js: the visual on each walkthrough slide. Every value drawn comes
   from window.SITE (written by analysis/make_site_data.py from the run logs);
   motion that only illustrates a mechanism carries no numbers. */
(function () {
  "use strict";
  const K = window.Deck, D = K.data;
  const TEAL = "#4cb5ac", RUST = "#e0703f", INK = "#eef3f8", INK2 = "#a8bccd", INK3 = "#6a8199", INK4 = "#34495f",
    AMBER = "#f5c66a", LINE = "rgba(150,185,215,.16)";
  const SANS = '"Helvetica Neue",Helvetica,Arial,sans-serif';
  const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
  const font = (px, w = 400, f = SANS) => `${w} ${px}px ${f}`;
  function rr(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h); }
  function car(ctx, x, y, w, h, fill, glow) {
    if (glow) { ctx.shadowColor = glow; ctx.shadowBlur = 18; }
    rr(ctx, x - w / 2, y - h / 2, w, h, h * 0.32); ctx.fillStyle = fill; ctx.fill();
    ctx.shadowBlur = 0;
  }
  function ghost(ctx, x, y, w, h, a = 1) {
    ctx.globalAlpha = a; rr(ctx, x - w / 2, y - h / 2, w, h, h * 0.32);
    ctx.fillStyle = rgba(RUST, 0.16); ctx.fill(); ctx.setLineDash([5, 4]); ctx.lineWidth = 2; ctx.strokeStyle = RUST; ctx.stroke(); ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }
  function tether(ctx, x1, y1, x2, y2, a = 1) {
    ctx.globalAlpha = a; ctx.setLineDash([6, 6]); ctx.strokeStyle = RUST; ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
  }
  function ringAt(ctx, x, y, r, a, color = TEAL, lw = 2) {
    ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.strokeStyle = rgba(color, a); ctx.lineWidth = lw; ctx.stroke();
  }

  /* ---------- 2: the signed message ---------- */
  K.visual("message", (box) => {
    const E = D.example, px = box.querySelector(".px"), pos = box.querySelector(".pos");
    const real = box.querySelector(".carbox.real"), gh = box.querySelector(".carbox.ghost");
    const tr = box.querySelector(".t-real"), tg = box.querySelector(".t-ghost");
    const lo = Math.min(E.true.x, E.claimed.x), hi = Math.max(E.true.x, E.claimed.x), pad = (hi - lo) * 0.45;
    const at = (x) => (8 + 84 * (x - (lo - pad)) / (hi - lo + 2 * pad)) + "%";
    let timers = [];
    function reset() {
      timers.forEach(clearTimeout); timers = [];
      px.textContent = K.fmt(E.true.x, 1); pos.classList.remove("lie");
      real.style.left = gh.style.left = tr.style.left = tg.style.left = at(E.true.x);
      gh.classList.remove("on"); tg.style.opacity = 0;
    }
    reset();
    return {
      enter() {
        reset();
        timers.push(setTimeout(() => {
          // the position field rolls to the false value; the seal does not change
          const t0 = performance.now(), from = E.true.x, to = E.claimed.x;
          pos.classList.add("lie"); gh.classList.add("on");
          gh.style.left = tg.style.left = at(to); tg.style.opacity = 1;
          const roll = (now) => {
            const u = K.ease((now - t0) / 1400);
            px.textContent = K.fmt(from + (to - from) * u, 1);
            if (u < 1) requestAnimationFrame(roll);
          };
          requestAnimationFrame(roll);
        }, 1600));
      },
      leave: reset,
    };
  });

  /* ---------- 5: the dataset as a field of dots ---------- */
  K.visual("dataset", (box) => {
    const C = K.canvas(box, { label: "The dataset's windows as dots, one per ten thousand, coloured by scenario" });
    const ctx = C.ctx, F = D.facts, PER = 10000;
    const NAMES = { highway_sparse: "Highway, normal traffic", highway_dense: "Highway, dense traffic", magnitude_sweep: "Sweep of lie sizes",
      bursty_attackers: "Attackers lying in bursts", offset_receivers: "Receivers moved" };
    const COLS = [TEAL, "#2e7d7d", "#6aa8f0", "#a68bf0", AMBER];
    const sc = Object.entries(F.scenario_windows);
    const dots = [];
    sc.forEach(([name, n], k) => { for (let i = 0; i < Math.round(n / PER); i++) dots.push(k); });
    let t = 0;
    return {
      enter() { t = K.still ? 9 : 0; },
      tick(dt) {
        t += dt;
        const W = C.w, H = C.h, cols = 36, gap = W / cols, r = gap * 0.32, top = 30;
        ctx.clearRect(0, 0, W, H);
        const shown = K.reduced ? dots.length : Math.floor(dots.length * K.ease(t / 2.4));
        for (let i = 0; i < dots.length; i++) {
          const x = (i % cols) * gap + gap / 2, y = top + Math.floor(i / cols) * gap + gap / 2;
          ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
          ctx.fillStyle = i < shown ? COLS[dots[i]] : "rgba(150,185,215,.06)"; ctx.fill();
        }
        const rows = Math.ceil(dots.length / cols), ly = top + rows * gap + 46;
        ctx.font = font(22); ctx.textBaseline = "middle";
        let lx = 0, row = 0;
        sc.forEach(([name, n], k) => {
          const label = NAMES[name] || name, w = ctx.measureText(label).width + 56;
          if (lx + w > W) { lx = 0; row++; }
          ctx.beginPath(); ctx.arc(lx + 9, ly + row * 40, 9, 0, 7); ctx.fillStyle = COLS[k]; ctx.fill();
          ctx.fillStyle = INK2; ctx.fillText(label, lx + 26, ly + row * 40);
          lx += w;
        });
        ctx.fillStyle = INK3; ctx.font = font(22, 400);
        ctx.fillText("Each dot is 10,000 windows", 0, top - 4);
      },
    };
  });

  /* ---------- 6: ten attacks ---------- */
  const PLAIN = {
    1: "Steady position lie, large", 3: "Random position, every message", 4: "Replaying old positions", 5: "Speed lie",
    6: "Fake identities", 7: "Flooding", 8: "Slot hoarding", 11: "Steady position lie, small", 12: "Low-rate flooding",
    13: "Steady position lie, medium",
  };
  K.visual("attacks", (box) => {
    const per = D.facts.per_class;
    const ids = Object.keys(PLAIN).map(Number).sort((a, b) => per[b].flagged - per[a].flagged);
    const tiles = ids.map((id, i) => {
      const f = per[id].flagged, inert = id === 8;
      const el = document.createElement("div");
      el.className = "atk-t" + (inert ? " inert" : "");
      el.setAttribute("data-in", String(Math.min(8, 3 + Math.floor(i / 2))));
      el.innerHTML = `<h3>${PLAIN[id]}</h3>` +
        (inert ? `<div class="why">inert in this simulator</div>` : "") +
        `<div class="pct">${Math.round(f * 100)}<small>% flagged</small></div><div class="meter"><i></i></div>`;
      box.appendChild(el);
      const cv = K.canvas(el, {});
      el.insertBefore(cv.cv, el.firstChild);
      return { id, f, el, C: cv, bar: el.querySelector(".meter i") };
    });
    let t = 0;
    function glyph(T, time) {
      const { ctx, w: W, h: H } = T.C, id = T.id, y = H / 2;
      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = LINE; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(0, y + 16); ctx.lineTo(W, y + 16); ctx.stroke();
      const cx = ((time * 34) % (W + 60)) - 30;
      const cw = 26, ch = 13;
      if (id === 7 || id === 12) {
        const per = id === 7 ? 0.22 : 0.6;
        for (let k = 0; k < 4; k++) { const u = ((time / per + k / 4) % 1); ringAt(ctx, cx, y, 6 + u * 46, (1 - u) * 0.8, AMBER, 1.6); }
      } else if (id === 6) {
        [[-46, -16], [40, -20], [58, 12], [-30, 18]].forEach(([dx, dy], k) => {
          const a = 0.5 + 0.5 * Math.sin(time * 3 + k * 1.7);
          ghost(ctx, cx + dx, y + dy * 0.8, cw * 0.8, ch * 0.8, a);
        });
      } else if (id === 3) {
        const k = Math.floor(time * 2.2), rx = Math.sin(k * 12.9898) * 60, ry = Math.sin(k * 78.233) * 22;
        tether(ctx, cx, y, cx + rx, y + ry, 0.7); ghost(ctx, cx + rx, y + ry, cw, ch);
      } else if ([1, 11, 13].includes(id)) {
        const off = id === 1 ? 70 : id === 13 ? 40 : 12;
        tether(ctx, cx, y, cx + off, y, 0.8); ghost(ctx, cx + off, y, cw, ch);
      } else if (id === 4) {
        const lag = ((time * 34 - 46) % (W + 60)) - 30;
        tether(ctx, cx, y, lag, y, 0.7); ghost(ctx, lag, y, cw, ch);
      } else if (id === 5) {
        const off = 30 * Math.sin(time * 2.1);
        ghost(ctx, cx + 20 + off, y, cw, ch);
      } else if (id === 8) {
        for (let k = 0; k < 8; k++) { rr(ctx, 10 + k * (W - 20) / 8, 10, (W - 20) / 8 - 6, 18, 4); ctx.fillStyle = k % 3 === 0 ? "rgba(150,185,215,.22)" : "rgba(150,185,215,.07)"; ctx.fill(); }
      }
      car(ctx, cx, y, cw, ch, "#d8e2ec");
    }
    return {
      enter() {
        t = K.still ? 9 : 0;
        tiles.forEach((T) => { T.bar.style.width = "0%"; });
        setTimeout(() => tiles.forEach((T) => {
          T.bar.style.width = T.f * 100 + "%";
          T.bar.style.background = T.f >= 0.5 ? TEAL : RUST;
        }), 400);
      },
      tick(dt) { t += dt; tiles.forEach((T, i) => glyph(T, t + i * 0.37)); },
    };
  });

  /* ---------- 7: one second ---------- */
  K.visual("second", (box) => {
    const fill = box.querySelector(".fill"), inf = box.querySelector(".inf");
    let t = 0;
    return {
      enter() { t = K.still ? 9 : 0; },
      tick(dt) {
        t += dt;
        const u = (t % 1.6) / 1.2;
        fill.style.width = Math.min(100, u * 100) + "%";
        inf.style.opacity = u >= 1 ? 1 : 0.35;
      },
    };
  });

  /* ---------- 8: one receiver, a fade and a lie read the same ---------- */
  K.visual("onerx", (box) => {
    const C = K.canvas(box, { label: "One receiver hears an honest car in a fade and a liar claiming to be farther away, and reads the same power from both" });
    const ctx = C.ctx;
    let t = 0;
    /* both cars claim the same spot; the honest one is there in a fade, the
       liar is really farther away, so the receiver hears the same weak signal */
    function lane(y, label, liar) {
      const W = C.w, rx = 110, claimX = W * 0.47, cx = liar ? W * 0.84 : claimX;
      ctx.fillStyle = "rgba(13,27,41,.9)"; rr(ctx, 0, y - 100, W, 200, 26); ctx.fill();
      ctx.font = font(25, 500); ctx.fillStyle = INK3; ctx.textBaseline = "alphabetic";
      ctx.fillText(label, 28, y - 62);
      ctx.fillStyle = TEAL; ctx.beginPath(); ctx.moveTo(rx, y - 30); ctx.lineTo(rx + 19, y + 24); ctx.lineTo(rx - 19, y + 24); ctx.fill();
      ctx.font = font(21, 400); ctx.fillStyle = INK3; ctx.textAlign = "center"; ctx.fillText("receiver", rx, y + 56); ctx.textAlign = "left";
      for (let k = 0; k < 6; k++) {
        const u = ((t * 0.6 + k / 6) % 1), x = cx - (cx - rx) * u;
        const a = 0.8 * (1 - u * 0.75) * (liar ? 1 : (x < (rx + claimX) / 2 + 60 ? 0.45 : 1));
        ctx.strokeStyle = rgba(TEAL, a); ctx.lineWidth = 2.6;
        ctx.beginPath(); ctx.arc(x, y, 26, Math.PI * 0.68, Math.PI * 1.32); ctx.stroke();
      }
      if (!liar) {
        const fx = (rx + claimX) / 2 + 30;
        const g = ctx.createRadialGradient(fx, y, 0, fx, y, 90);
        g.addColorStop(0, "rgba(106,129,153,.42)"); g.addColorStop(1, "rgba(106,129,153,0)");
        ctx.fillStyle = g; ctx.fillRect(fx - 90, y - 90, 180, 180);
        ctx.font = font(22, 400); ctx.fillStyle = INK2; ctx.textAlign = "center"; ctx.fillText("a fade", fx, y + 62); ctx.textAlign = "left";
      } else {
        tether(ctx, cx, y, claimX, y, 0.9); ghost(ctx, claimX, y, 64, 32);
        ctx.font = font(22, 400); ctx.fillStyle = RUST; ctx.textAlign = "center"; ctx.fillText("claims to be here", claimX, y + 62);
        ctx.fillStyle = INK2; ctx.fillText("really here", cx, y + 62); ctx.textAlign = "left";
      }
      car(ctx, cx, y, 64, 32, "#d8e2ec", "rgba(216,226,236,.4)");
    }
    function meter(x, y, h) {
      ctx.fillStyle = "rgba(150,185,215,.10)"; rr(ctx, x, y - h / 2, 26, h, 13); ctx.fill();
      const lvl = 0.42 + 0.03 * Math.sin(t * 2);
      ctx.fillStyle = TEAL; rr(ctx, x, y + h / 2 - h * lvl, 26, h * lvl, 13); ctx.fill();
    }
    return {
      enter() { t = K.still ? 9 : 0; },
      tick(dt) {
        t += dt;
        const W = C.w, H = C.h;
        ctx.clearRect(0, 0, W, H);
        const y1 = H * 0.24, y2 = H * 0.68, mw = 26;
        const L = W - 150;
        ctx.save(); ctx.beginPath(); ctx.rect(0, 0, L, H); ctx.clip();
        C.w = L; lane(y1, "An honest car, its signal weakened by fading", false); lane(y2, "A lying car, really farther away, claiming to be here", true); C.w = W;
        ctx.restore();
        meter(W - 100, y1, 150); meter(W - 100, y2, 150);
        ctx.font = font(22, 500); ctx.fillStyle = INK3; ctx.textAlign = "center";
        ctx.fillText("Power", W - 87, y1 - 98); ctx.fillText("Power", W - 87, y2 - 98);
        ctx.font = font(64, 300); ctx.fillStyle = INK; ctx.fillText("=", W - 87, (y1 + y2) / 2 + 22);
        ctx.font = font(26, 600); ctx.fillStyle = INK; ctx.fillText("The receiver measures the same power from both", (W - 150) / 2, H * 0.95); ctx.textAlign = "left";
        void mw;
      },
    };
  });

  /* ---------- 9: the floor ---------- */
  K.visual("floor", (box) => {
    const C = K.canvas(box, { label: "Share of lying cars caught by lie size: one receiver catches none at any size; pooled receivers rise past 47.3 metres" });
    const ctx = C.ctx, F = D.floor, XMAX = 250;
    let t = 0;
    return {
      enter() { t = K.still ? 9 : 0; },
      tick(dt) {
        t += dt;
        const W = C.w, H = C.h, L = 92, R = 30, T = 90, B = 110, pw = W - L - R, ph = H - T - B;
        const X = (m) => L + (Math.min(m, XMAX) / XMAX) * pw, Y = (v) => T + (1 - v) * ph;
        ctx.clearRect(0, 0, W, H);
        // grid and axes
        ctx.font = font(23, 400); ctx.fillStyle = INK3; ctx.strokeStyle = LINE; ctx.lineWidth = 1;
        for (const v of [0, 0.25, 0.5, 0.75, 1]) {
          ctx.beginPath(); ctx.moveTo(L, Y(v)); ctx.lineTo(W - R, Y(v)); ctx.stroke();
          ctx.textAlign = "right"; ctx.fillText(Math.round(v * 100) + "%", L - 14, Y(v) + 6);
        }
        ctx.textAlign = "center";
        for (const m of [0, 50, 100, 150, 200, 250]) ctx.fillText(String(m), X(m), H - B + 36);
        ctx.fillStyle = INK2; ctx.font = font(22);
        ctx.fillText("size of the lie, metres", L + pw / 2, H - B + 78);
        ctx.save(); ctx.translate(26, T + ph / 2); ctx.rotate(-Math.PI / 2); ctx.fillText("lying cars caught", 0, 0); ctx.restore();
        // honest GPS error, 95th percentile
        ctx.fillStyle = "rgba(150,185,215,.10)"; ctx.fillRect(L, T, X(+F.benign95) - L, ph);
        // the crossing and its interval
        const g = K.ease((t - 0.9) / 1);
        ctx.fillStyle = rgba(TEAL, 0.12 * g); ctx.fillRect(X(+F.lo), T, X(+F.hi) - X(+F.lo), ph);
        ctx.strokeStyle = rgba(INK, 0.8 * g); ctx.setLineDash([6, 6]); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(X(+F.cross), T); ctx.lineTo(X(+F.cross), T + ph); ctx.stroke(); ctx.setLineDash([]);
        ctx.globalAlpha = g; ctx.fillStyle = INK; ctx.font = font(24, 600); ctx.textAlign = "left";
        ctx.fillText(F.cross + " m", X(+F.cross) - 14 - ctx.measureText(F.cross + " m").width, Y(0.62)); ctx.globalAlpha = 1;
        // pooled bars, one per band of lie size
        const grow = K.ease(t / 1.4);
        F.pooled.forEach(([a, b, v], i) => {
          const x0 = X(a) + 4, x1 = X(b == null ? XMAX : b) - 4, gv = v * K.ease((t - i * 0.08) / 1.2);
          rr(ctx, x0, Y(gv), x1 - x0, Y(0) - Y(gv), 8); ctx.fillStyle = rgba(TEAL, 0.78); ctx.fill();
        });
        // one receiver: zero at every size
        ctx.strokeStyle = RUST; ctx.lineWidth = 5; ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(X(F.single[0][0]), Y(0)); ctx.lineTo(X(F.single[0][0]) + (X(XMAX) - X(F.single[0][0])) * grow, Y(0)); ctx.stroke();
        ctx.lineCap = "butt";
        // legend, clear of the bars: top left of the plot, above the short bands
        ctx.font = font(21); ctx.textAlign = "left";
        const lx = L + 10, lyy = T - 30;
        ctx.fillStyle = rgba(TEAL, 0.78); rr(ctx, lx, lyy - 18, 22, 22, 5); ctx.fill(); ctx.fillStyle = INK2; ctx.fillText("receivers pooled", lx + 32, lyy);
        ctx.fillStyle = RUST; ctx.fillRect(lx + 230, lyy - 9, 22, 5); ctx.fillStyle = INK2; ctx.fillText("one receiver", lx + 262, lyy);
        ctx.fillStyle = "rgba(150,185,215,.25)"; ctx.fillRect(lx + 420, lyy - 18, 22, 22); ctx.fillStyle = INK2; ctx.fillText("honest GPS error", lx + 452, lyy);
      },
    };
  });

  /* ---------- 10: geometry and the map check ---------- */
  K.visual("geometry", (box) => {
    const C = K.canvas(box, { label: "Receivers along the road measure position across it worst; a sideways lie slips past the radio, and a map check catches it" });
    const ctx = C.ctx, F = D.facts, ang = (+F.weak_axis_deg * Math.PI) / 180;
    const RX = [-260, -190, -130, -75, -30, 20, 70, 120, 175, 240].map((x, i) => [x, i % 2 ? 6 : -6]);
    let t = 0;
    return {
      enter() { t = K.still ? 9 : 0; },
      tick(dt) {
        t += dt;
        const W = C.w, H = C.h, cx = W / 2, cy = H * 0.46, s = Math.min(W / 640, H / 520);
        const P = (x, y) => [cx + x * s, cy + y * s];
        ctx.clearRect(0, 0, W, H);
        const cyc = t % 12, phase = cyc < 4 ? 0 : cyc < 8 ? 1 : 2; // along, sideways, map on
        const mapOn = phase === 2;
        // the map check: everything off the carriageway is rejected
        if (mapOn) {
          const a = K.ease((cyc - 8) / 0.8);
          ctx.fillStyle = rgba(RUST, 0.10 * a);
          ctx.fillRect(0, 0, W, P(0, -12)[1]); ctx.fillRect(0, P(0, 12)[1], W, H);
          ctx.font = font(23, 500); ctx.fillStyle = rgba(RUST, a); ctx.fillText("Rejected by the map check: off the road", 24, 40);
        }
        // road
        const [, ry0] = P(0, -12), [, ry1] = P(0, 12);
        ctx.fillStyle = "#0d1b29"; ctx.fillRect(0, ry0, W, ry1 - ry0);
        ctx.strokeStyle = "rgba(220,230,240,.35)"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(0, ry0); ctx.lineTo(W, ry0); ctx.moveTo(0, ry1); ctx.lineTo(W, ry1); ctx.stroke();
        // receivers in a line along it
        RX.forEach(([x, y]) => { const [a, b] = P(x, y); ctx.beginPath(); ctx.arc(a, b, 7, 0, 7); ctx.fillStyle = TEAL; ctx.fill(); ringAt(ctx, a, b, 14, 0.35); });
        // the error ellipse at the car: long across the road, at the logged angle
        const maj = +F.ellipse_major_m, min = +F.ellipse_minor_m;
        ctx.save(); ctx.translate(cx, cy); ctx.rotate(-ang);
        ctx.beginPath(); ctx.ellipse(0, 0, maj * s, min * s, 0, 0, 7);
        ctx.fillStyle = rgba(TEAL, 0.10); ctx.fill(); ctx.strokeStyle = rgba(TEAL, 0.7); ctx.lineWidth = 2; ctx.stroke(); ctx.restore();
        // where a brute-force search put the best lie
        const lo = (F.search_lo_deg * Math.PI) / 180, hi = (F.search_hi_deg * Math.PI) / 180, R = 210 * s;
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, R, -hi, -lo); ctx.closePath();
        ctx.fillStyle = rgba(AMBER, 0.08); ctx.fill();
        ctx.font = font(22, 400); ctx.fillStyle = rgba(AMBER, 0.8);
        ctx.fillText("Where a search found the best lie", cx + 30 * s, cy - R - 12);
        // the attacker's ghost: along the road (caught), then sideways
        const u = K.ease(((cyc % 4) - 0.3) / 1.6);
        const dir = phase === 0 ? 0 : ang, dist = 150 * u;
        const gx = cx + Math.cos(dir) * dist * s, gy = cy - Math.sin(dir) * dist * s;
        tether(ctx, cx, cy, gx, gy, u);
        ghost(ctx, gx, gy, 40, 20, Math.min(1, u * 2));
        car(ctx, cx, cy, 40, 20, "#d8e2ec", "rgba(216,226,236,.4)");
        if (u > 0.95) {
          const caught = phase !== 1;
          ringAt(ctx, gx, gy, 34, 0.9, caught ? RUST : TEAL, 3);
          ctx.font = font(26, 700); ctx.fillStyle = caught ? RUST : TEAL; ctx.textAlign = "center";
          ctx.fillText(phase === 0 ? "Caught by the radio check" : phase === 1 ? "Missed by the radio check" : "Caught by the map check", gx, gy + (phase === 0 ? 66 : -50));
          ctx.textAlign = "left";
        }
        ctx.font = font(22, 400); ctx.fillStyle = INK3; ctx.fillText("Receivers along the road", 24, ry1 + 34);
      },
    };
  });

  /* ---------- 11: federated rounds and the validation curve ---------- */
  K.visual("fed", (box) => {
    const C = K.canvas(box, { label: "Roadside units send model updates to a server and receive the average; the federated validation score approaches central training's" });
    const ctx = C.ctx, F = D.fed, N = F.clients;
    let t = 0;
    const lit = new Uint8Array(N);
    let roundShown = 0, lastRound = -1;
    const T_END = 11;
    function roundAt(tt) { return Math.max(1, Math.round(Math.pow(F.rounds, K.clamp(tt / T_END, 0, 1)))); }
    return {
      enter() { t = K.still ? 11.5 : 0; lastRound = -1; },
      tick(dt) {
        t += dt; if (t > T_END + 5) t = 0;
        const W = C.w, H = C.h;
        ctx.clearRect(0, 0, W, H);
        const r = roundAt(t);
        if (r !== lastRound) { for (let i = 0; i < N; i++) lit[i] = Math.random() < 0.5 ? 1 : 0; lastRound = r; }
        roundShown = r;
        // network: server above an arc of units
        const sx = W / 2, sy = 60, ay = H * 0.27;
        const unit = (i) => { const a = Math.PI * (0.06 + 0.88 * i / (N - 1)); return [W / 2 - Math.cos(a) * W * 0.46, ay - Math.sin(a) * 120 + 120]; };
        const ph = (t * 1.6) % 1;
        for (let i = 0; i < N; i++) {
          const [x, y] = unit(i);
          if (lit[i] && t < T_END) {
            const up = ph < 0.5, u = up ? ph * 2 : (ph - 0.5) * 2;
            const px = up ? x + (sx - x) * u : sx + (x - sx) * u, py = up ? y + (sy - y) * u : sy + (y - sy) * u;
            ctx.beginPath(); ctx.arc(px, py, 2.6, 0, 7); ctx.fillStyle = up ? rgba(TEAL, 0.85) : rgba(INK, 0.7); ctx.fill();
          }
          ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fillStyle = lit[i] && t < T_END ? TEAL : INK4; ctx.fill();
        }
        ctx.save(); ctx.translate(sx, sy); ctx.beginPath();
        for (let k = 0; k < 6; k++) { const a = Math.PI / 6 + k * Math.PI / 3; k ? ctx.lineTo(Math.cos(a) * 30, Math.sin(a) * 30) : ctx.moveTo(Math.cos(a) * 30, Math.sin(a) * 30); }
        ctx.closePath(); ctx.fillStyle = "#10233a"; ctx.fill(); ctx.strokeStyle = TEAL; ctx.lineWidth = 2.5; ctx.stroke(); ctx.restore();
        ctx.font = font(22, 500); ctx.fillStyle = INK3; ctx.textAlign = "center";
        ctx.fillText("The server sees only model updates", sx, sy + 58);
        ctx.fillText(`${N} roadside units`, W / 2, ay + 156);
        // the curve: central every epoch, federated at its four checkpoints
        const L = 80, R = 20, T = H * 0.58, B = 60, pw = W - L - R, phh = H - T - B;
        const lo = 0.38, hi = 0.6;
        const X = (e) => L + (Math.log(e) / Math.log(F.rounds)) * pw, Y = (v) => T + (1 - (v - lo) / (hi - lo)) * phh;
        ctx.strokeStyle = LINE; ctx.lineWidth = 1; ctx.font = font(21, 400); ctx.fillStyle = INK3; ctx.textAlign = "right";
        for (const v of [0.4, 0.5, 0.6]) { ctx.beginPath(); ctx.moveTo(L, Y(v)); ctx.lineTo(W - R, Y(v)); ctx.stroke(); ctx.fillText(v.toFixed(1), L - 10, Y(v) + 6); }
        ctx.textAlign = "center";
        for (const e of [1, 10, 100, F.rounds]) ctx.fillText(String(e), X(e), H - B + 28);
        ctx.fillText("Training rounds (federated) or epochs (central)", L + pw / 2, H - 8);
        ctx.strokeStyle = INK3; ctx.lineWidth = 2.4; ctx.beginPath();
        F.epochs.forEach((e, i) => { if (e > roundShown) return; const x = X(e), y = Y(F.central[i]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
        ctx.stroke();
        const pts = F.checkpoints.map((c, i) => [c, F.fedavg[i]]).filter(([c]) => c <= roundShown);
        ctx.strokeStyle = TEAL; ctx.lineWidth = 3.5; ctx.beginPath();
        pts.forEach(([c, v], i) => (i ? ctx.lineTo(X(c), Y(v)) : ctx.moveTo(X(c), Y(v)))); ctx.stroke();
        pts.forEach(([c, v]) => { ctx.beginPath(); ctx.arc(X(c), Y(v), 7, 0, 7); ctx.fillStyle = TEAL; ctx.fill(); });
        ctx.textAlign = "left"; ctx.font = font(20); ctx.fillStyle = INK2;
        ctx.fillText("central training", L + 12, Y(lo) - 10);
        ctx.fillStyle = TEAL; ctx.fillText("federated", L + 210, Y(lo) - 10);
        ctx.textAlign = "right"; ctx.font = font(26, 600); ctx.fillStyle = INK;
        ctx.fillText(`Round ${roundShown}`, W - R, T - 18);
        ctx.font = font(20, 400); ctx.fillStyle = INK3; ctx.fillText("Validation macro F1", W - R, T - 44);
        ctx.textAlign = "left";
      },
    };
  });

  /* ---------- 12: three changes of road ---------- */
  K.visual("shifts", (box) => {
    const S = D.shifts;
    const cards = [...box.querySelectorAll(".card")].map((el) => {
      const k = el.querySelector("canvas").dataset.k, cv = el.querySelector("canvas");
      cv.remove(); const C = K.canvas(el, {}); el.insertBefore(C.cv, el.firstChild);
      return { k, el, C, bar: el.querySelector(".g-before"), ceil: el.querySelector(".g-ceil") };
    });
    // each card on its own scale (its retrained ceiling plus headroom), so the three are not read as a ranking
    const MAXOF = (k) => +S[k]["in-dist"].f1 * 1.15;
    let t = 0, timer = null;
    function draw(c, time) {
      const { ctx, w: W, h: H } = c.C, y = H / 2;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = "#0b1825"; ctx.fillRect(0, y - 36, W, 72);
      if (c.k === "density") {
        for (let i = 0; i < 26; i++) { const x = ((i * 47 + time * (40 + (i % 3) * 12)) % (W + 40)) - 20; car(ctx, x, y - 22 + (i % 3) * 22, 22, 11, "#c9d5e0"); }
      } else if (c.k === "radio") {
        const x = W * 0.3;
        for (let k = 0; k < 3; k++) { const u = (time * 0.8 + k / 3) % 1; ringAt(ctx, x, y, 8 + u * 60, (1 - u) * 0.75, TEAL, 2); }
        car(ctx, x, y, 30, 15, "#d8e2ec");
        ctx.fillStyle = TEAL; ctx.beginPath(); ctx.moveTo(W * 0.78, y - 18); ctx.lineTo(W * 0.78 + 12, y + 14); ctx.lineTo(W * 0.78 - 12, y + 14); ctx.fill();
      } else {
        const x = ((time * 50) % (W + 60)) - 30, on = Math.floor(time * 1.3) % 5 === 0;
        if (on) { tether(ctx, x, y, x + 60, y, 0.8); ghost(ctx, x + 60, y, 30, 15); }
        car(ctx, x, y, 30, 15, "#d8e2ec");
      }
    }
    return {
      enter() {
        t = K.still ? 9 : 0; clearTimeout(timer);
        cards.forEach((c) => {
          const s = S[c.k];
          c.bar.style.transition = "none"; c.bar.style.width = "0%"; c.bar.style.background = RUST;
          const MAX = MAXOF(c.k);
          c.ceil.style.left = (+s["in-dist"].f1 / MAX) * 100 + "%";
          requestAnimationFrame(() => { c.bar.style.transition = ""; c.bar.style.width = (+s.transfer.f1 / MAX) * 100 + "%"; });
        });
        timer = setTimeout(() => cards.forEach((c) => {
          const s = S[c.k]; c.bar.style.width = (+s["label-free"].f1 / MAXOF(c.k)) * 100 + "%";
          c.bar.style.background = s["label-free"].recovered > 0 ? TEAL : RUST;
        }), 2200);
      },
      leave() { clearTimeout(timer); },
      tick(dt) { t += dt; cards.forEach((c) => draw(c, t)); },
    };
  });
})();
