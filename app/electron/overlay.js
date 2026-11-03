// On-screen overlay: the element being found -> click, cache hits and verdict chips. Same look on screen and in Chrome.
  const stage = document.getElementById("stage");
  const scan = document.getElementById("scan");
  let panelLeft = window.innerWidth;
  let target = null;      // { box, mask, tag, reticle }
  let clearTimer = null;

  const glow = document.getElementById("glow");

  // Boxes and pointer positions arrive in screen coordinates. macOS may keep this window below the menu bar
  // (screenY > 0), so the stage is shifted back by the window's own offset to draw exactly on the target.
  function alignStage() {
    stage.style.transform = `translate(${-window.screenX}px, ${-window.screenY}px)`;
  }
  window.addEventListener("resize", alignStage);

  window.setPanel = (b) => {
    // In "panel" mode the agent occupies the right column; in "pill"/"mini" mode it is a small bar in the corner,
    // so the whole width is the stage. The status bar always stays centred on the screen.
    panelLeft = b.mode !== "panel" ? window.innerWidth : Math.max(200, b.x);
    scan.style.width = panelLeft + "px";
    alignStage();
  };
  setPanel({ x: window.innerWidth });

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const short = (s, n = 48) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");

  // The status bar's words in the app's language (each event carries it: e.lang). English text is the key.
  // [Spanish, French, German, Portuguese]
  const WORDS = {
    "Writing the program": ["Escribiendo el programa", "Écriture du programme", "Schreibe das Programm", "Escrevendo o programa"],
    "Running": ["Ejecutando", "Exécution", "Läuft", "Executando"],
    "{n} lines": ["{n} líneas", "{n} lignes", "{n} Zeilen", "{n} linhas"],
    "Finding": ["Buscando", "Recherche", "Suche", "Procurando"],
    "Cached": ["En caché", "En cache", "Im Cache", "Em cache"],
    "0 model calls": ["0 llamadas al modelo", "0 appel au modèle", "0 Modellaufrufe", "0 chamadas ao modelo"],
    "Position cache": ["Caché de posiciones", "Cache de positions", "Positions-Cache", "Cache de posições"],
    "no model call": ["sin llamada al modelo", "aucun appel au modèle", "kein Modellaufruf", "sem chamada ao modelo"],
    "Not found": ["No encontrado", "Introuvable", "Nicht gefunden", "Não encontrado"],
    "Clicking": ["Haciendo clic", "Clic", "Klicke", "Clicando"],
    "Typing into": ["Escribiendo en", "Saisie dans", "Tippe in", "Digitando em"],
    "Hovering": ["Señalando", "Survol", "Zeige auf", "Passando sobre"],
    "Dragging": ["Arrastrando", "Glisser", "Ziehe", "Arrastando"],
    "Acting on": ["Actuando sobre", "Action sur", "Bediene", "Agindo em"],
    "saw": ["visto", "vu", "gesehen", "visto"],
    "Line {n} failed": ["Falló la línea {n}", "Échec ligne {n}", "Zeile {n} fehlgeschlagen", "Falha na linha {n}"],
    "Known way back": ["Camino de vuelta conocido", "Chemin de retour connu", "Bekannter Rückweg", "Caminho de volta conhecido"],
    "Rewrote line {n}": ["Línea {n} reescrita", "Ligne {n} réécrite", "Zeile {n} neu geschrieben", "Linha {n} reescrita"],
    "resuming": ["continuando", "reprise", "fahre fort", "continuando"],
    "Waiting for your approval": ["Esperando tu aprobación", "En attente de ta validation", "Warte auf deine Freigabe", "Aguardando sua aprovação"],
    "in the Deskwright panel": ["en el panel de Deskwright", "dans le panneau Deskwright", "im Deskwright-Panel", "no painel do Deskwright"],
    "Done": ["Listo", "Terminé", "Fertig", "Pronto"],
    "Stopped": ["Detenido", "Arrêté", "Gestoppt", "Parado"],
    "Failed": ["Falló", "Échec", "Fehlgeschlagen", "Falhou"],
    "Declined": ["Rechazado", "Refusé", "Abgelehnt", "Recusado"],
    "{n} model calls": ["{n} llamadas al modelo", "{n} appels au modèle", "{n} Modellaufrufe", "{n} chamadas ao modelo"],
    "Typing": ["Escribiendo", "Saisie", "Tippe", "Digitando"],
    "Pressing": ["Pulsando", "Touche", "Drücke", "Pressionando"],
    "Shortcut": ["Atajo", "Raccourci", "Kurzbefehl", "Atalho"],
    "Scrolling": ["Desplazando", "Défilement", "Scrolle", "Rolando"],
    "down": ["abajo", "vers le bas", "nach unten", "para baixo"],
    "up": ["arriba", "vers le haut", "nach oben", "para cima"],
    "Recording starts": ["La grabación empieza", "L'enregistrement commence", "Aufnahme beginnt", "A gravação começa"],
    "Recording": ["Grabando", "Enregistrement", "Aufnahme", "Gravando"],
    "{n}% cached": ["{n}% en caché", "{n} % en cache", "{n} % aus dem Cache", "{n}% em cache"],
  };
  let lang = "en";
  const L = (text, n) => {
    const i = ["es", "fr", "de", "pt"].indexOf(lang);
    const out = i >= 0 && WORDS[text] ? WORDS[text][i] : text;
    return n === undefined ? out : out.replace("{n}", n);
  };

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

  const cd = document.getElementById("countdown");
  let cdTimer = null;
  function countdown(seconds) {
    clearInterval(cdTimer);
    if (!seconds) return cd.classList.remove("on");
    const n = cd.querySelector(".n");
    const label = cd.querySelector(".label");
    let left = seconds;
    const show = () => {
      n.textContent = String(left);
      n.classList.remove("tick");
      void n.offsetWidth; // restart the animation
      n.classList.add("tick");
    };
    label.textContent = L("Recording starts");
    show();
    cd.classList.add("on");
    cdTimer = setInterval(() => {
      left -= 1;
      if (left > 0) return show();
      clearInterval(cdTimer);
      n.textContent = "●";
      n.classList.remove("tick");
      label.textContent = L("Recording");
      setTimeout(() => cd.classList.remove("on"), 600);
    }, 1000);
  }

  window.overlay = (e) => {
    alignStage();
    if (e.lang) lang = e.lang;
    switch (e.type) {
      case "run_started":
        glow.classList.add("on");
        break;
      case "countdown":
        countdown(e.seconds);
        break;
      case "vision_scan":
        scan.classList.add("on");
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
        if ((e.source === "dom" || e.source === "ax") && !e.from_cache) {
          newTarget("exact", e.box, `<i></i>${esc(short(e.target, 40))}`);
        } else if (e.from_cache) {
          newTarget("cached", e.box, `<i></i>${L("Cached")} <span class="muted">${L("0 model calls")} · ${esc(short(e.target, 32))}</span>`);
        } else if (!target) {
          newTarget("exact", e.box, `<i></i>${esc(short(e.target, 40))}`);
        }
        break;
      case "vision_miss":
        scan.classList.remove("on");
        break;
      case "pointer": {
        const [x, y] = e.point;
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
        verdict(e.box, false, e.observation ? `${e.expect} · ${L("saw")}: ${e.observation}` : e.expect);
        break;
      case "line_failed":
        scan.classList.remove("on");
        break;
      case "run_finished":
        glow.classList.remove("on");
        scan.classList.remove("on");
        clearTarget();
        break;
    }
  };
