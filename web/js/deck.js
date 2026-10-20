/* deck.js: the walkthrough's engine. Scales the 1920 x 1080 stage to the
   screen, steps through the slides (clicker, arrow keys, Page Up and Down,
   swipe, click), fills every number from window.SITE so none is typed into
   the page, and starts each slide's visual when it comes on. Keys 1 to 5 jump
   to the five pitch parts, B or . blanks the screen, F goes full screen. With ?auto
   (or A to toggle) it steps on by itself after 90 s without input. Classic
   script, no modules, so it opens from file:// with no network. */
(function () {
  "use strict";
  const D = document;
  const Deck = (window.Deck = {});
  Deck.data = window.SITE || {};
  Deck.reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  Deck.still = /[?&]still\b/.test(location.search); // screenshots: every animation at its end state
  Deck.portrait = () => matchMedia("(max-aspect-ratio: 1/1)").matches;
  Deck.clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
  Deck.ease = (t) => 1 - Math.pow(1 - Deck.clamp(t, 0, 1), 3);
  Deck.fmt = (v, d = 0) => Number(v).toLocaleString("en-AU", { minimumFractionDigits: d, maximumFractionDigits: d });
  Deck.get = (path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), Deck.data);

  /* a canvas that fills its box at device resolution, in on-screen pixels */
  Deck.canvas = (box, opts = {}) => {
    const cv = D.createElement("canvas");
    if (opts.label) { cv.setAttribute("role", "img"); cv.setAttribute("aria-label", opts.label); }
    box.appendChild(cv);
    const o = { cv, ctx: cv.getContext("2d"), w: 1, h: 1, onresize: null };
    /* drawing coordinates are stage pixels, so canvas text scales with the
       page text; the backing store is sized to the screen for sharpness */
    const fit = () => {
      const r = cv.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
      o.w = Math.max(1, cv.offsetWidth); o.h = Math.max(1, cv.offsetHeight);
      const k = r.width / o.w || 1;
      cv.width = Math.max(1, Math.round(r.width * dpr)); cv.height = Math.max(1, Math.round(r.height * dpr));
      o.ctx.setTransform(dpr * k, 0, 0, dpr * k, 0, 0);
      if (o.onresize) o.onresize();
    };
    new ResizeObserver(fit).observe(cv);
    Deck.onscale.push(fit);
    fit();
    return o;
  };
  Deck.onscale = [];

  /* count a number up into an element */
  Deck.count = (el, to, d = 0, dur = 1400, suffix = "") => {
    if (Deck.reduced || Deck.still) { el.textContent = Deck.fmt(to, d) + suffix; return; }
    const t0 = performance.now();
    const step = (now) => {
      const u = Deck.ease((now - t0) / dur);
      el.textContent = Deck.fmt(to * u, d) + suffix;
      if (u < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  /* visuals register here; each returns {enter, leave, tick} */
  const makers = {};
  Deck.visual = (id, fn) => (makers[id] = fn);

  const slides = [...D.querySelectorAll(".slide")];
  const deck = D.querySelector(".deck");
  const ctl = new Map();
  let cur = -1;

  /* fill numbers: data-n="facts.windows", optional data-x (multiply) and
     data-d (decimals); data-count counts it up each time the slide comes on */
  function fill() {
    D.querySelectorAll("[data-n]").forEach((el) => {
      let v = Deck.get(el.dataset.n);
      if (v == null) { el.textContent = "?"; el.classList.add("missing"); console.error("missing", el.dataset.n); return; }
      if (el.dataset.x) v = Number(v) * Number(el.dataset.x);
      el.dataset.v = typeof v === "string" ? v.replace(/,/g, "") : v;
      el.textContent = el.dataset.d != null ? Deck.fmt(Number(String(v).replace(/,/g, "")), +el.dataset.d) : String(v);
    });
  }

  function scale() {
    if (Deck.portrait()) { deck.style.removeProperty("--s"); return; }
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    deck.style.setProperty("--s", s);
    Deck.onscale.forEach((f) => f());
  }

  function show(i, instant) {
    i = Deck.clamp(i, 0, slides.length - 1);
    if (i === cur) return;
    const prev = slides[cur];
    if (prev) {
      prev.classList.remove("on");
      const c = ctl.get(prev); c && c.leave && c.leave();
    }
    cur = i;
    const s = slides[i];
    s.classList.add("on");
    s.querySelectorAll("[data-count]").forEach((el) => {
      const v = Number(el.dataset.v), d = el.dataset.d != null ? +el.dataset.d : 0;
      if (!isNaN(v)) Deck.count(el, v, d, 1600);
    });
    const c = ctl.get(s); c && c.enter && c.enter();
    chrome();
    if (!instant && history.replaceState) history.replaceState(null, "", "#" + (i + 1));
  }
  Deck.show = show;
  Deck.next = () => show(cur + 1);
  Deck.prev = () => show(cur - 1);

  /* footer chrome: the five parts and the slide number */
  const PARTS = ["The problem", "What we built", "The result", "Deployment", "What is new"];
  const bar = D.querySelector(".bar");
  const parts = D.querySelector(".chrome .parts");
  const num = D.querySelector(".chrome .num");
  if (parts) PARTS.forEach((p) => parts.appendChild(Object.assign(D.createElement("span"), { textContent: p })));
  function chrome() {
    const part = +slides[cur].dataset.part;
    if (parts) [...parts.children].forEach((el, k) => el.classList.toggle("on", k + 1 === part));
    if (num) num.textContent = String(cur + 1).padStart(2, "0") + " / " + String(slides.length).padStart(2, "0");
    if (bar) bar.style.width = ((cur + 1) / slides.length) * 100 + "%";
    D.querySelector(".chrome").style.opacity = slides[cur].classList.contains("hero") ? 0 : 1;
  }

  /* the loop: only the slide on screen animates (every slide, stacked, on a phone) */
  let last = performance.now();
  function loop(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (Deck.portrait()) {
      for (const [s, c] of ctl) if (c.tick && s.dataset.vis === "1") c.tick(dt, now / 1000);
    } else {
      const c = ctl.get(slides[cur]);
      try { c && c.tick && c.tick(dt, now / 1000); } catch (err) { console.error(err); ctl.delete(slides[cur]); }
    }
    requestAnimationFrame(loop);
  }

  /* input */
  const blank = D.querySelector(".blank");
  let idle = 0, auto = false;
  const poke = () => { idle = 0; auto = false; };
  addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    poke();
    const k = e.key;
    if (blank.classList.contains("on") && !["b", "B", "."].includes(k)) return;
    if (["PageDown", "ArrowRight", "ArrowDown", " ", "Enter"].includes(k)) { e.preventDefault(); Deck.next(); }
    else if (["PageUp", "ArrowLeft", "ArrowUp", "Backspace"].includes(k)) { e.preventDefault(); Deck.prev(); }
    else if (k === "Home") show(0);
    else if (k === "End") show(slides.length - 1);
    else if (k >= "1" && k <= "5") { const j = slides.findIndex((s) => s.dataset.part === k); if (j >= 0) show(j); }
    else if (k === "b" || k === "B" || k === ".") blank.classList.toggle("on");
    else if (k === "f" || k === "F") {
      if (!D.fullscreenElement) D.documentElement.requestFullscreen && D.documentElement.requestFullscreen().catch(() => {});
      else D.exitFullscreen();
    }
  });
  let tx = null;
  addEventListener("pointerdown", (e) => { poke(); tx = [e.clientX, e.clientY]; }, { passive: true });
  addEventListener("pointerup", (e) => {
    if (!tx || Deck.portrait()) return;
    const dx = e.clientX - tx[0], dy = e.clientY - tx[1];
    if (e.target.closest("a,button,[data-visual=hero]")) { tx = null; return; }
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) dx < 0 ? Deck.next() : Deck.prev();
    else if (Math.abs(dx) < 8 && Math.abs(dy) < 8) e.clientX > innerWidth * 0.3 ? Deck.next() : Deck.prev();
    tx = null;
  });
  addEventListener("wheel", poke, { passive: true });
  /* stepping on by itself is opt-in (?auto, or press A), so it never moves on
     while a presenter is still answering a question */
  let autoOK = /[?&]auto\b/.test(location.search);
  addEventListener("keydown", (e) => { if (e.key === "a" || e.key === "A") { autoOK = !autoOK; idle = 0; } });
  setInterval(() => {
    if (Deck.portrait() || !autoOK) return;
    idle++;
    if (idle >= 90) auto = true;
    if (auto && idle % 12 === 0) show(cur + 1 >= slides.length ? 0 : cur + 1);
  }, 1000);

  /* keep the screen awake at the booth */
  let lock = null;
  const wake = async () => { try { if ("wakeLock" in navigator && !lock) { lock = await navigator.wakeLock.request("screen"); lock.addEventListener("release", () => (lock = null)); } } catch (e) { /* not granted */ } };
  D.addEventListener("visibilitychange", () => D.visibilityState === "visible" && wake());
  addEventListener("pointerdown", wake, { once: true });

  /* start */
  addEventListener("DOMContentLoaded", () => {
    if (/[?&]still\b/.test(location.search)) D.documentElement.classList.add("still");
    fill();
    slides.forEach((s) => {
      const box = s.querySelector("[data-visual]");
      // one broken visual must not take the rest of the deck down with it
      if (box && makers[box.dataset.visual]) {
        try { ctl.set(s, makers[box.dataset.visual](box, s) || {}); } catch (err) { console.error("visual", box.dataset.visual, err); }
      }
    });
    scale();
    addEventListener("resize", scale);
    // on a phone every slide is on screen in turn as it scrolls past
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (!Deck.portrait()) return;
      e.target.dataset.vis = e.isIntersecting ? "1" : "0";
      if (e.isIntersecting) e.target.dataset.shown = "1"; // on a phone a slide builds once and stays built
      const c = ctl.get(e.target);
      if (e.isIntersecting && c && c.enter && !e.target.dataset.seen) { e.target.dataset.seen = "1"; c.enter(); }
    }), { threshold: 0.25 });
    slides.forEach((s) => io.observe(s));
    const h = parseInt(location.hash.slice(1), 10);
    show(h >= 1 && h <= slides.length ? h - 1 : 0, true);
    if (Deck.portrait() && h > 1 && h <= slides.length) slides[h - 1].scrollIntoView();
    // ?solo=n shows only slide n on a phone (headless screenshots do not keep a scroll position)
    const solo = +(location.search.match(/[?&]solo=(\d+)/) || [])[1];
    if (solo && Deck.portrait()) slides.forEach((s, i) => { if (i !== solo - 1) s.style.display = "none"; else { s.dataset.vis = s.dataset.shown = "1"; const c = ctl.get(s); c && c.enter && c.enter(); } });
    wake();
    requestAnimationFrame(loop);
  });
})();
