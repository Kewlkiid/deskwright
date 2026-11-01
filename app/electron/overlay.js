// On-screen overlay: the element being found -> click, cache hits and verdict chips. Same look on screen and in Chrome.
  const stage = document.getElementById("stage");
  const hud = document.getElementById("hud");
  const scan = document.getElementById("scan");
  let panelLeft = window.innerWidth;
  let target = null;      // { box, mask, tag, reticle }
  let hudTimer = null;
  let clearTimer = null;

  const glow = document.getElementById("glow");

  // Boxes and pointer positions arrive in screen coordinates. macOS may keep this window below the menu bar
  // (screenY > 0), so the stage is shifted back by the window's own offset to draw exactly on the target.
  function alignStage() {
    stage.style.transform = `translate(${-window.screenX}px, ${-window.screenY}px)`;
  }
  window.addEventListener("resize", alignStage);

  window.setPanel = (b) => {
    // In "panel" mode the agent occupies the right column; in "pill" mode it is a small bar in the corner,
    // so the whole width is the stage. The status bar always stays centred on the screen.
    panelLeft = b.mode === "pill" ? window.innerWidth : Math.max(200, b.x);
    scan.style.width = panelLeft + "px";
    alignStage();
  };
  setPanel({ x: window.innerWidth });

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const short = (s, n = 48) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");

  function setHud(color, html, busy = false, ttl = 0) {
    clearTimeout(hudTimer);
    hud.querySelector(".dot").style.background = color;
    hud.querySelector(".txt").innerHTML = html;
    hud.classList.toggle("busy", busy);
    hud.classList.add("on");
    if (ttl) hudTimer = setTimeout(() => hud.classList.remove("on"), ttl);
  }

  function place(el, b) {
    el.style.left = b[0] + "px";
    el.style.top = b[1] + "px";
    el.style.width = Math.max(4, b[2] - b[0]) + "px";
    el.style.height = Math.max(4, b[3] - b[1]) + "px";
  }

  function pad(b, p) { return [b[0] - p, b[1] - p, b[2] + p, b[3] + p]; }

  function clearTarget(delay = 0) {
    const t = target;
    target = null;
    if (!t) return;
    setTimeout(() => {
      for (const el of [t.box, t.mask, t.reticle]) if (el) { el.classList.add("fade"); el.classList.remove("on"); }
      setTimeout(() => { for (const el of [t.box, t.mask, t.reticle]) el && el.remove(); }, 400);
    }, delay);
  }

  function newTarget(kind, b, tagHtml) {
    clearTarget();
    const box = document.createElement("div");
    box.className = "box " + kind;
    place(box, pad(b, 4));
    const tag = document.createElement("div");
    tag.className = "tag" + (kind === "cached" ? " cache" : "");
    tag.innerHTML = tagHtml;
    box.appendChild(tag);
    stage.appendChild(box);
    target = { box, tag, mask: null, reticle: null };
    clearTimeout(clearTimer);
    clearTimer = setTimeout(() => clearTarget(), 2600);
    return target;
  }

  function verdict(b, ok, text) {
    if (!b) return;
    const v = document.createElement("div");
    v.className = "verdict " + (ok ? "ok" : "bad");
    v.innerHTML = `<span class="mark">${ok ? "✓" : "✕"}</span><span>${esc(short(text, 60))}</span>`;
    v.style.top = b[3] + 10 + "px";
    stage.appendChild(v);
    // Keep the chip on screen: near the right edge it would run off past the element's left side.
    v.style.left = Math.max(8, Math.min(b[0], window.innerWidth - v.offsetWidth - 8)) + "px";
    requestAnimationFrame(() => v.classList.add("on"));
    setTimeout(() => { v.classList.remove("on"); setTimeout(() => v.remove(), 300); }, 2200);
  }

  window.overlay = (e) => {
    alignStage();
    switch (e.type) {
      case "run_started":
        glow.classList.add("on");
        setHud("#0d0d0d", `<b>Writing the program</b><span class="sub">${esc(short(e.task, 56))}</span>`, true);
        break;
      case "script_generated":
        if (!e.draft) setHud("#0d0d0d", `<b>Running</b><span class="sub">${e.script.split("\n").length} lines</span>`, true);
        break;
      case "vision_scan":
        scan.classList.add("on");
        setHud("var(--spark)", `<b>Finding</b><span class="sub">“${esc(short(e.target))}”</span>`, true);
        break;
      case "sam_mask": {
        scan.classList.remove("on");
        newTarget("exact", e.box, "");
        const t = target;
        t.box.className = "box exact";
        place(t.box, pad(e.box, 3));
        t.tag.innerHTML = `<i></i>${esc(short(e.target, 40))}`;
        if (e.mask) {
          const m = document.createElement("img");
          m.className = "mask";
          m.src = e.mask.png;
          place(m, e.mask.rect);
          stage.insertBefore(m, t.box);
          t.mask = m;
          requestAnimationFrame(() => m.classList.add("on"));
        }
        break;
      }
      case "element_found":
        scan.classList.remove("on");
        if (!e.box) break;
        // Elements found in a Chrome page look exactly like ones found on screen.
        if (e.source === "dom" && !e.from_cache) {
          newTarget("exact", e.box, `<i></i>${esc(short(e.target, 40))}`);
        } else if (e.from_cache) {
          newTarget("cached", e.box, `<i></i>Cached <span class="muted">0 model calls · ${esc(short(e.target, 32))}</span>`);
          setHud("var(--cache)", `<b>Position cache</b><span class="sub">“${esc(short(e.target))}” · no model call</span>`, true);
        } else if (!target) {
          newTarget("exact", e.box, `<i></i>${esc(short(e.target, 40))}`);
        }
        break;
      case "vision_miss":
        scan.classList.remove("on");
        setHud("var(--bad)", `<b>Not found</b><span class="sub">“${esc(short(e.target))}”</span>`, false);
        break;
      case "pointer": {
        const [x, y] = e.point;
        const verb = { click: "Clicking", type: "Typing into", hover: "Hovering", drag: "Dragging" }[e.kind] || "Acting on";
        const label = target?.tag?.querySelector(".muted")?.textContent || "";
        setHud("#0d0d0d", `<b>${verb}</b><span class="sub">${esc(short(label.replace(/^0 model calls · /, "")))}</span>`, true);
        const r = document.createElement("div");
        r.className = "reticle";
        r.style.left = x + "px";
        r.style.top = y + "px";
        stage.appendChild(r);
        requestAnimationFrame(() => r.classList.add("on"));
        if (target) target.reticle = r; else setTimeout(() => r.remove(), 1200);
        if (e.kind !== "hover") {
          setTimeout(() => {
            const p = document.createElement("div");
            p.className = "ripple";
            p.style.left = x + "px";
            p.style.top = y + "px";
            stage.appendChild(p);
            setTimeout(() => p.remove(), 800);
          }, 280);
        }
        clearTarget(650);
        break;
      }
      case "expect_met":
        verdict(e.box, true, e.expect);
        break;
      case "expect_failed":
        verdict(e.box, false, e.observation ? `${e.expect} · saw: ${e.observation}` : e.expect);
        break;
      case "line_failed":
        scan.classList.remove("on");
        setHud("var(--bad)", `<b>Line ${e.line} failed</b><span class="sub">${esc(short(e.error?.message, 56))}</span>`);
        break;
      case "detour":
        setHud("#b45309", `<b>Known way back</b><span class="sub">${esc(short(e.when, 50))}</span>`, true);
        break;
      case "line_rewritten":
        setHud("#b45309", `<b>Rewrote line ${e.failed_line}</b><span class="sub">resuming</span>`, true);
        break;
      case "confirm_request":
        setHud("#b45309", `<b>Waiting for your approval</b><span class="sub">in the Agent panel</span>`, true);
        break;
      case "run_finished": {
        glow.classList.remove("on");
        scan.classList.remove("on");
        clearTarget();
        const m = e.metrics || {};
        const ok = e.status === "succeeded";
        const bits = [`${(m.elapsed || 0).toFixed(1)}s`, `${m.model_calls || 0} model calls`];
        if (m.cache_hits) bits.push(`${Math.round((m.cache_hit_rate || 0) * 100)}% cached`);
        setHud(ok ? "var(--ok)" : "var(--bad)", `<b>${ok ? "Done" : e.status[0].toUpperCase() + e.status.slice(1)}</b><span class="sub">${bits.join(" · ")}</span>`, false, 5000);
        break;
      }
    }
  };
