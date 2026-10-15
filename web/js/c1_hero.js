/* Chapter: Signed, and still lying. A night highway seen from just above the
   traffic. Every car broadcasts its position (the teal rings). One car signs a
   false position: its broadcasts come from a rust ghost ahead of it while the
   signature stays valid. Illustrative motion only, no data and no numbers. */
(function () {
  "use strict";
  const S = window.Deck;

  S.visual("hero", (stage) => {
      const C = S.canvas(stage, { label: "A highway at night. Cars broadcast their positions; one car broadcasts a false one." });
      const { ctx } = C;

      /* sprites: soft glows, drawn once and scaled */
      const sprite = (rgb) => {
        const c = document.createElement("canvas"); c.width = c.height = 64;
        const g = c.getContext("2d"), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
        r.addColorStop(0, `rgba(${rgb},1)`); r.addColorStop(0.25, `rgba(${rgb},.55)`); r.addColorStop(1, `rgba(${rgb},0)`);
        g.fillStyle = r; g.fillRect(0, 0, 64, 64); return c;
      };
      const GLOW = { red: sprite("255,60,50"), white: sprite("255,244,220"), amber: sprite("255,196,110"),
        teal: sprite("69,189,180"), rust: sprite("238,109,61") };

      /* the world: x across (left of the median is our direction, as in
         Australia), z ahead of the camera, metres */
      const LANES_AWAY = [-2.25, -5.75, -9.25], LANES_ON = [2.25, 5.75, 9.25];
      const ZMAX = 210, VCAM = 27;
      let rnd = 7;
      const rand = () => ((rnd = (rnd * 16807) % 2147483647) / 2147483647);
      const PAINT = ["#1c2a3b", "#2a313c", "#233244", "#363d48", "#1a2533", "#2d3a4a", "#3b3f46"];
      const cars = [];
      for (let i = 0; i < 34; i++) {
        cars.push({ x: LANES_AWAY[i % 3] + (rand() - 0.5) * 0.5, z: 6 + rand() * (ZMAX - 6), v: (rand() - 0.5) * 4,
          on: false, paint: PAINT[i % PAINT.length], phase: rand() * 1.3, period: 1.1 + rand() * 0.4 });
      }
      for (let i = 0; i < 9; i++) {
        cars.push({ x: LANES_ON[i % 3] + (rand() - 0.5) * 0.4, z: 20 + rand() * 300, v: -(VCAM + 24 + rand() * 6),
          on: true, paint: PAINT[(i + 3) % PAINT.length], phase: rand() * 1.3, period: 1.1 + rand() * 0.4 });
      }
      // the first liar sits in the middle lane, close enough to read
      const first = cars[0]; first.x = -5.75; first.z = 23; first.v = 0;
      let liar = first, lie = 0, lying = false, retiring = null, retireLie = 0;
      const stars = Array.from({ length: 70 }, () => [rand(), rand() * 0.9, rand() * 0.6 + 0.2]);

      // the vanishing point sits right of centre so the title on the left keeps clear of the traffic
      let W, H, hy, f, camX = -3.2, VX = 0.5;
      const CAMH = 6.2;
      C.onresize = () => {
        W = C.w; H = C.h;
        const portrait = H > W;
        hy = H * (portrait ? 0.34 : 0.36);
        f = Math.min((H - hy) * 5 / CAMH, W * (portrait ? 0.95 : 0.7));
        camX = portrait ? -4.2 : -3.2;
        VX = portrait ? 0.5 : 0.64;
      };
      C.onresize();
      const P = (x, z, y = 0) => { const s = f / z; return [W * VX + (x - camX) * s, hy + (CAMH - y) * s, s]; };
      const fog = (z) => S.clamp(1 - (z - 110) / 150, 0, 1);

      function quad(x1, x2, z1, z2, y = 0) {
        const a = P(x1, z1, y), b = P(x2, z1, y), c = P(x2, z2, y), d = P(x1, z2, y);
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(c[0], c[1]); ctx.lineTo(d[0], d[1]); ctx.closePath();
      }
      function glow(img, x, y, size, a = 1) {
        if (a <= 0.01 || size < 0.5) return;
        ctx.globalAlpha = a; ctx.drawImage(img, x - size / 2, y - size / 2, size, size); ctx.globalAlpha = 1;
      }
      function hull(pts) {
        pts.sort((p, q) => p[0] - q[0] || p[1] - q[1]);
        const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
        const lo = [], up = [];
        for (const p of pts) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
        for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
        return lo.slice(0, -1).concat(up.slice(0, -1));
      }
      function poly(pts) { ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath(); }

      /* a car as a lit box: x centre, z of its rear (or front, oncoming) */
      function drawCar(c, x, z, ghost) {
        if (z < 1.2) return;
        const a = fog(z); if (a <= 0) return;
        const w = 0.92, L = 4.5, h = 1.42;
        const z0 = c.on ? z - L : z, z1 = c.on ? z : z + L; // near and far ends
        const near = z0 > 1.2 ? z0 : 1.2;
        const corners = [];
        for (const zz of [near, z1]) for (const xx of [x - w, x + w]) for (const yy of [0, h]) corners.push(P(xx, zz, yy));
        const sh = P(x, (near + z1) / 2);
        ctx.globalAlpha = a;
        if (!ghost) { // contact shadow
          ctx.fillStyle = "rgba(0,0,0,.55)"; ctx.beginPath();
          ctx.ellipse(sh[0], sh[1], 1.4 * sh[2], 0.55 * sh[2] * CAMH / ((near + z1) / 2), 0, 0, 7); ctx.fill();
        }
        const body = hull(corners.map((p) => [p[0], p[1]]));
        poly(body);
        if (ghost) {
          ctx.fillStyle = "rgba(238,109,61,.16)"; ctx.fill();
          ctx.setLineDash([]); ctx.lineWidth = 1.4; ctx.strokeStyle = `rgba(238,109,61,${0.9 * a})`; ctx.stroke();
        } else { ctx.fillStyle = c.paint; ctx.fill(); }
        // roof
        const r0 = near + (c.on ? 1.3 : 1.1), r1 = z1 - (c.on ? 1.0 : 1.3);
        if (r1 > r0) {
          const rf = [P(x - w * 0.82, r0, h), P(x + w * 0.82, r0, h), P(x + w * 0.82, r1, h), P(x - w * 0.82, r1, h)];
          poly(rf); ctx.fillStyle = ghost ? "rgba(238,109,61,.22)" : "rgba(160,190,220,.10)"; ctx.fill();
        }
        // the face the camera sees, and its lights
        const fy0 = 0.35, fy1 = 1.0;
        const fl = P(x - w * 0.78, near, fy0), fr = P(x + w * 0.78, near, fy0), tl = P(x - w * 0.78, near, fy1);
        if (!ghost) { ctx.fillStyle = "rgba(0,0,0,.28)"; ctx.fillRect(fl[0], tl[1], fr[0] - fl[0], fl[1] - tl[1]); }
        ctx.globalAlpha = 1;
        const ly = P(x, near, 0.78)[1], s = P(x, near)[2];
        const img = ghost ? GLOW.rust : c.on ? GLOW.white : GLOW.red;
        const sz = (c.on ? 2.6 : 1.5) * s;
        glow(img, fl[0] + s * 0.12, ly, sz, a); glow(img, fr[0] - s * 0.12, ly, sz, a);
        if (c.on && !ghost) { // headlight beams on the road
          const b0 = P(x - 0.8, near), b1 = P(x + 0.8, near), b2 = P(x + 2.4, Math.max(1.3, near - 22)), b3 = P(x - 2.4, Math.max(1.3, near - 22));
          const g = ctx.createLinearGradient(0, b0[1], 0, b2[1]);
          g.addColorStop(0, `rgba(255,236,200,${0.13 * a})`); g.addColorStop(1, "rgba(255,236,200,0)");
          ctx.fillStyle = g; poly([b0, b1, b2, b3]); ctx.fill();
        }
      }

      function ring(x, z, r, alpha, color) {
        ctx.beginPath();
        let pen = false;
        for (let i = 0; i <= 48; i++) {
          const t = (i / 48) * Math.PI * 2, zz = z + Math.sin(t) * r;
          if (zz < 1.3) { pen = false; continue; }
          const p = P(x + Math.cos(t) * r, zz);
          pen ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); pen = true;
        }
        ctx.strokeStyle = color.replace("A", alpha.toFixed(3)); ctx.lineWidth = 1.3; ctx.stroke();
      }

      let dist = 0, time = 0, demo = false, demoT = 0, armed = 0;
      const ghostOf = (c, l) => ({ x: c.x + 3.5 * l, z: c.z + 27 * l });

      function draw() {
        // sky and ground
        const sky = ctx.createLinearGradient(0, 0, 0, hy);
        sky.addColorStop(0, "#03080f"); sky.addColorStop(1, "#0c2132");
        ctx.fillStyle = sky; ctx.fillRect(0, 0, W, hy + 1);
        for (const [sx, sy, sa] of stars) { ctx.fillStyle = `rgba(200,220,240,${sa * 0.5})`; ctx.fillRect(sx * W, sy * hy, 1.2, 1.2); }
        const hz = ctx.createRadialGradient(W * VX, hy, 0, W * VX, hy, W * 0.6);
        hz.addColorStop(0, "rgba(69,189,180,.16)"); hz.addColorStop(1, "rgba(69,189,180,0)");
        ctx.fillStyle = hz; ctx.fillRect(0, hy - W * 0.3, W, W * 0.3);
        const gr = ctx.createLinearGradient(0, hy, 0, H);
        gr.addColorStop(0, "#081522"); gr.addColorStop(1, "#03080e");
        ctx.fillStyle = gr; ctx.fillRect(0, hy, W, H - hy);

        // road
        quad(-11.6, 11.6, 1.2, 900); const rg = ctx.createLinearGradient(0, hy, 0, H);
        rg.addColorStop(0, "#0d1b29"); rg.addColorStop(1, "#0a1520"); ctx.fillStyle = rg; ctx.fill();
        // street lights: pools on the road, then poles
        const LS = 55, lo = dist % LS;
        for (let k = 0; k < 7; k++) {
          const z = k * LS - lo + 8; if (z < 2) continue;
          for (const side of [-12.6, 12.6]) {
            const c0 = P(side * 0.55, z), a = fog(z);
            const rx = 10 * c0[2], ry = rx * CAMH / z;
            ctx.save(); ctx.translate(c0[0], c0[1]); ctx.scale(1, Math.max(0.05, ry / rx));
            const pg = ctx.createRadialGradient(0, 0, 0, 0, 0, rx);
            pg.addColorStop(0, `rgba(255,196,110,${0.075 * a})`); pg.addColorStop(1, "rgba(255,196,110,0)");
            ctx.fillStyle = pg; ctx.beginPath(); ctx.arc(0, 0, rx, 0, 7); ctx.fill(); ctx.restore();
          }
        }
        // lines: edges, median, dashes
        ctx.fillStyle = "rgba(220,230,240,.42)";
        for (const x of [-11.2, 11.2]) { quad(x - 0.08, x + 0.08, 1.2, 900); ctx.fill(); }
        ctx.fillStyle = "rgba(245,198,106,.38)";
        for (const x of [-0.45, 0.45]) { quad(x - 0.07, x + 0.07, 1.2, 900); ctx.fill(); }
        ctx.fillStyle = "rgba(220,230,240,.30)";
        const DL = 12, doff = dist % DL;
        for (let k = 0; k < 40; k++) {
          const z = k * DL - doff; if (z + 3 < 1.2) continue;
          for (const x of [-4, -7.5, 4, 7.5]) { quad(x - 0.07, x + 0.07, Math.max(1.2, z), z + 3); ctx.fill(); }
        }
        // poles and lamp heads, from a little way ahead (a pole beside the camera fills the frame)
        for (let k = 0; k < 7; k++) {
          const z = k * LS - lo + 8; if (z < 14) continue;
          const a = fog(z);
          for (const side of [-12.6, 12.6]) {
            const b = P(side, z), t = P(side, z, 9);
            ctx.strokeStyle = `rgba(120,140,160,${0.35 * a})`; ctx.lineWidth = Math.max(0.6, 0.12 * b[2]);
            ctx.beginPath(); ctx.moveTo(b[0], b[1]); ctx.lineTo(t[0], t[1]); ctx.stroke();
            const hd = P(side * 0.86, z, 9);
            ctx.beginPath(); ctx.moveTo(t[0], t[1]); ctx.lineTo(hd[0], hd[1]); ctx.stroke();
            if (z > 14) glow(GLOW.amber, hd[0], hd[1], Math.min(60, 2.4 * hd[2]), 0.9 * a);
          }
        }

        // broadcasts first, under the cars
        const items = [];
        for (const c of cars) {
          const isL = c === liar || c === retiring;
          const l = c === liar ? lie : c === retiring ? retireLie : 0;
          const src = isL && l > 0.02 ? ghostOf(c, l) : c;
          const cz = c.on ? src.z - 2.2 : src.z + 2.2;
          if (cz > 150 || cz < 2) continue;
          const u = ((time + c.phase) % c.period) / c.period;
          const al = Math.pow(1 - u, 1.6) * 0.55 * fog(cz);
          ring(src.x, cz, 1 + u * 30, al, isL && l > 0.5 ? "rgba(69,189,180,A)" : "rgba(69,189,180,A)");
        }
        // tether between a liar and its ghost
        for (const [c, l] of [[liar, lie], [retiring, retireLie]]) {
          if (!c || l < 0.02) continue;
          const g = ghostOf(c, l), a = P(c.x, c.z + 2.2), b = P(g.x, g.z + 2.2);
          ctx.setLineDash([6, 6]); ctx.lineDashOffset = -time * 20;
          ctx.strokeStyle = `rgba(238,109,61,${0.85 * Math.min(1, l * 2)})`; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); ctx.setLineDash([]);
        }
        // cars, far to near
        for (const c of cars) items.push({ z: c.on ? c.z - 4.5 : c.z, c });
        for (const [c, l] of [[liar, lie], [retiring, retireLie]]) if (c && l > 0.02) items.push({ z: ghostOf(c, l).z, c, ghost: l });
        items.sort((a, b) => b.z - a.z);
        for (const it of items) {
          if (it.ghost) { const g = ghostOf(it.c, it.ghost); ctx.globalAlpha = Math.min(1, it.ghost * 1.5); drawCar(it.c, g.x, g.z, true); ctx.globalAlpha = 1; }
          else drawCar(it.c, it.c.x, it.c.z, false);
        }
        // the seal on the lie, and where the car really is
        if (lie > 0.6) {
          const a = S.clamp((lie - 0.6) / 0.4, 0, 1), g = ghostOf(liar, lie);
          const p = P(g.x, g.z + 2.2, 3.4), q = P(liar.x, liar.z + 2.2, 2.6);
          label(p[0], p[1], "signature valid", "teal", a, true);
          label(q[0], q[1], "really here", "dim", a, false);
        }
      }
      function label(x, y, text, tone, a, check) {
        ctx.globalAlpha = a;
        ctx.font = '500 12px ui-monospace,"SF Mono",Menlo,monospace';
        const tw = ctx.measureText(text).width, pw = tw + (check ? 34 : 20), ph = 26;
        const bx = x - pw / 2, by = y - ph;
        ctx.fillStyle = "rgba(6,14,24,.86)"; ctx.strokeStyle = tone === "teal" ? "rgba(69,189,180,.9)" : "rgba(150,185,215,.35)";
        ctx.lineWidth = 1; ctx.beginPath(); ctx.roundRect ? ctx.roundRect(bx, by, pw, ph, 13) : ctx.rect(bx, by, pw, ph); ctx.fill(); ctx.stroke();
        let tx = bx + 10;
        if (check) {
          ctx.strokeStyle = "#45bdb4"; ctx.lineWidth = 2; ctx.beginPath();
          ctx.moveTo(tx + 1, by + 13); ctx.lineTo(tx + 5, by + 17); ctx.lineTo(tx + 12, by + 9); ctx.stroke(); tx += 18;
        }
        ctx.fillStyle = tone === "teal" ? "#45bdb4" : "#a8bccd"; ctx.textBaseline = "middle"; ctx.fillText(text, tx, by + ph / 2 + 0.5);
        ctx.globalAlpha = 1; ctx.textBaseline = "alphabetic";
      }

      function step(dt) {
        time += dt; dist += VCAM * dt;
        for (const c of cars) {
          if (c === liar || c === retiring) { c.v *= 0.96; }
          c.z += c.v * dt;
          if (!c.on) { if (c.z > ZMAX) c.z = 3; if (c.z < 2.5) c.z = ZMAX - 2; }
          else if (c.z < -3) { c.z = 300 + Math.random() * 60; }
        }
        // keep same-lane cars from overlapping: the follower takes the leader's speed
        const away = cars.filter((c) => !c.on).sort((a, b) => a.z - b.z);
        for (let i = 0; i < away.length; i++) for (let j = i + 1; j < away.length; j++) {
          const a = away[i], b = away[j];
          if (Math.abs(a.x - b.x) < 1.5 && b.z - a.z < 7) { if (a.v > b.v) a.v = b.v - 0.2; a.z = Math.min(a.z, b.z - 7); }
        }
        const target = lying ? 1 : 0;
        lie += (target - lie) * Math.min(1, dt * (lying ? 1.3 : 3));
        retireLie += (0 - retireLie) * Math.min(1, dt * 3);
        if (retireLie < 0.01) retiring = null;
        if (demo) { demoT += dt; if (demoT > 6.5) { demoT = 0; pickRandom(); } }
        if (armed > 0) { armed -= dt; if (armed <= 0) lying = true; }
      }
      function pick(c) {
        if (c === liar) { lying = !lying; return; }
        retiring = liar; retireLie = lie; liar = c; lie = 0; lying = true;
      }
      function pickRandom() {
        const opts = cars.filter((c) => !c.on && c.z > 14 && c.z < 60 && c !== liar);
        if (opts.length) pick(opts[Math.floor(Math.random() * opts.length)]);
      }
      C.cv.addEventListener("pointerdown", (e) => {
        const r = C.cv.getBoundingClientRect(), mx = (e.clientX - r.left) * C.w / r.width, my = (e.clientY - r.top) * C.h / r.height;
        let best = null, bd = 1e9;
        for (const c of cars) {
          if (c.on || c.z < 3 || c.z > 140) continue;
          const p = P(c.x, c.z + 2.2, 0.7), d = Math.hypot(p[0] - mx, p[1] - my), reach = Math.max(34, p[2] * 3);
          if (d < reach && d < bd) { bd = d; best = c; }
        }
        if (best) pick(best);
      });

      demo = true; // a new car starts lying every few seconds while the slide is up
      return {
        enter() { if (!lying && !S.reduced) armed = 1.4; if (S.reduced) { lying = true; lie = 1; } demoT = 0; },
        leave() {},
        tick(dt) { if (!S.reduced) step(dt); else if (time === 0) step(0.016); draw(); },
      };
  });
})();
