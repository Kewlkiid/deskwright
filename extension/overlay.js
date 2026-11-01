// Agent page module (MAIN world): element overlays, element maps, DOM actions and teach recording.
//
// Three overlay layers share one set of helpers:
//   window.__agentOverlay            interactive elements ('interactive' mode) or page sections ('regions' mode)
//   window.__agentStaticOverlay      static text
//   window.__agentScrollableOverlay  scrollable containers
// Each draws colour-coded boxes with numbered labels and keeps an element map:
//   { index, tag, type, id, classes, selector, category, rect: {x, y, width, height, centerX, centerY}, text, ... }
//
// content.js talks to this module with a window CustomEvent '__agent_command' {commandId, cmd, params};
// the answer comes back as '__agent_response' with the same commandId. Handling is synchronous on purpose:
// an async handler would dispatch the response in a microtask, where page scripts can intercept it.
(function () {
  'use strict';
  if (window.__agentOverlay) return;

  // ---------------------------------------------------------------- shared helpers
  const COLORS = {
    button: { border: 'rgba(59, 130, 246, 0.6)', bg: 'rgba(59, 130, 246, 0.05)', label: '#3b82f6' },
    input: { border: 'rgba(34, 197, 94, 0.6)', bg: 'rgba(34, 197, 94, 0.05)', label: '#22c55e' },
    textarea: { border: 'rgba(34, 197, 94, 0.6)', bg: 'rgba(34, 197, 94, 0.05)', label: '#22c55e' },
    select: { border: 'rgba(168, 85, 247, 0.6)', bg: 'rgba(168, 85, 247, 0.05)', label: '#a855f7' },
    a: { border: 'rgba(249, 115, 22, 0.6)', bg: 'rgba(249, 115, 22, 0.05)', label: '#f97316' },
    link: { border: 'rgba(249, 115, 22, 0.6)', bg: 'rgba(249, 115, 22, 0.05)', label: '#f97316' },
    clickable: { border: 'rgba(236, 72, 153, 0.6)', bg: 'rgba(236, 72, 153, 0.05)', label: '#ec4899' },
    structural: { border: 'rgba(107, 114, 128, 0.4)', bg: 'rgba(107, 114, 128, 0.03)', label: '#6b7280' },
    region: { border: 'rgba(99, 102, 241, 0.5)', bg: 'rgba(99, 102, 241, 0.05)', label: '#6366f1' },
    static: { border: 'rgba(245, 158, 11, 0.6)', bg: 'rgba(245, 158, 11, 0.05)', label: '#f59e0b' },
    scrollable: { border: 'rgba(20, 184, 166, 0.7)', bg: 'rgba(20, 184, 166, 0.1)', label: '#14b8a6' },
    default: { border: 'rgba(156, 163, 175, 0.5)', bg: 'rgba(156, 163, 175, 0.05)', label: '#9ca3af' },
  };
  const CONTAINER_IDS = ['__agent-overlay-container__', '__agent-static-overlay-container__', '__agent-scrollable-overlay-container__'];

  function rectOf(r) {
    return {
      x: Math.round(r.left), y: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height),
      centerX: Math.round(r.left + r.width / 2), centerY: Math.round(r.top + r.height / 2),
    };
  }

  function parentInComposedTree(el) {
    const root = el.getRootNode();
    return root instanceof ShadowRoot ? root.host : el.parentElement;
  }

  // el.contains() stops at shadow roots; this walks the composed tree.
  function isComposedContainedBy(el, ancestor) {
    for (let cur = el; cur; cur = parentInComposedTree(cur)) if (cur === ancestor) return true;
    return false;
  }

  function safeQueryAll(root, selector) {
    try {
      return Array.from(root.querySelectorAll(selector));
    } catch (e) {
      const out = [];
      selector.split(',').forEach((s) => {
        try { root.querySelectorAll(s.trim()).forEach((el) => out.push(el)); } catch (e2) { /* invalid selector */ }
      });
      return out;
    }
  }

  // Elements matching `selector` in the document and every (nested) shadow root, deduplicated.
  function collectDeep(selector, root = document, out = new Set()) {
    safeQueryAll(root, selector).forEach((el) => out.add(el));
    (root.querySelectorAll ? root.querySelectorAll('*') : []).forEach((el) => {
      if (el.shadowRoot) collectDeep(selector, el.shadowRoot, out);
    });
    return root === document ? Array.from(out) : out;
  }

  function generateSelector(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const classes = Array.from(el.classList)
      .filter((c) => !/^(active|focus|hover|disabled|selected|hidden|visible|show|hide)/i.test(c))
      .slice(0, 2);
    if (classes.length) {
      const sel = `${el.tagName.toLowerCase()}.${classes.map((c) => CSS.escape(c)).join('.')}`;
      if (document.querySelectorAll(sel).length === 1) return sel;
    }
    const path = [];
    let cur = el;
    while (cur && cur !== document.body) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) {
        path.unshift(`#${CSS.escape(cur.id)}`);
        break;
      }
      const parent = cur.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter((c) => c.tagName === cur.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(cur) + 1})`;
      }
      path.unshift(part);
      cur = parent;
    }
    return path.join(' > ');
  }

  function shownAndSized(el, minW, minH) {
    if (el.hidden) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width >= minW && r.height >= minH;
  }

  function inViewport(r) {
    return !(r.top > window.innerHeight || r.bottom < 0 || r.left > window.innerWidth || r.right < 0);
  }

  function sameRect(a, b, tol) {
    return Math.abs(a.left - b.left) < tol && Math.abs(a.top - b.top) < tol &&
      Math.abs(a.width - b.width) < tol && Math.abs(a.height - b.height) < tol;
  }

  function overlapShare(r1, r2) {
    const x = Math.max(0, Math.min(r1.right, r2.right) - Math.max(r1.left, r2.left));
    const y = Math.max(0, Math.min(r1.bottom, r2.bottom) - Math.max(r1.top, r2.top));
    return (x * y) / (r1.width * r1.height);
  }

  // Light page: black label with white text; dark page: the opposite.
  function labelStyle() {
    let bg = getComputedStyle(document.documentElement).backgroundColor;
    if (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') bg = getComputedStyle(document.body).backgroundColor;
    const m = bg && bg.match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (!m || bg === 'rgba(0, 0, 0, 0)') return { bg: '#ffffff', text: '#000000' };
    const lum = (0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]) / 255;
    return lum > 0.5 ? { bg: '#000000', text: '#ffffff' } : { bg: '#ffffff', text: '#000000' };
  }

  // Simple modal finder used by the static and scrollable layers: first visible match wins.
  function firstVisibleModal({ deep, extraSelectors }) {
    const all = (sel) => (deep ? collectDeep(sel) : Array.from(document.querySelectorAll(sel)));
    const visible = (el) => shownAndSized(el, 0.0001, 0.0001);
    for (const el of all('[aria-modal="true"]')) if (visible(el)) return el;
    for (const el of all('[role="dialog"], [role="alertdialog"]')) {
      if (el.getAttribute('aria-modal') !== 'false' && visible(el)) return el;
    }
    for (const el of all('dialog[open]')) if (visible(el)) return el;
    for (const sel of extraSelectors || []) for (const el of all(sel)) if (visible(el)) return el;
    return null;
  }

  function modalScope(modal) {
    const root = modal.getRootNode();
    return root instanceof ShadowRoot ? root.host : modal;
  }

  // ---------------------------------------------------------------- layer rendering
  function makeLayer({ containerId, labelSize, padding, fontSize, attempts, prefix, scan }) {
    let container = null;
    let map = [];
    let visible = false;

    function remove() {
      if (container) container.remove();
      container = null;
      visible = false;
    }

    function render(elements, labelPrefix) {
      remove();
      const ls = labelStyle();
      container = document.createElement('div');
      container.id = containerId;
      container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;' +
        "z-index:2147483647;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:10px;line-height:1;";
      const placed = [];
      for (const el of elements) {
        const c = COLORS[el.category] || COLORS.default;
        const box = document.createElement('div');
        box.style.cssText = `position:absolute;left:${el.rect.x}px;top:${el.rect.y}px;width:${el.rect.width}px;` +
          `height:${el.rect.height}px;border:2px solid ${c.border};background:${c.bg};border-radius:3px;box-sizing:border-box;`;
        container.appendChild(box);

        // Numbered circle above the element's top-left corner; shift right, then down, until it doesn't collide.
        const lr = { left: el.rect.x - labelSize / 1.8, top: el.rect.y - labelSize / 1.1 };
        lr.right = lr.left + labelSize;
        lr.bottom = lr.top + labelSize;
        for (let i = 0; i < attempts; i++) {
          const hit = placed.some((p) => !(lr.right <= p.left || lr.left >= p.right || lr.bottom <= p.top || lr.top >= p.bottom));
          if (!hit) break;
          lr.left += labelSize + padding;
          lr.right += labelSize + padding;
          if (lr.right > window.innerWidth) {
            lr.left = el.rect.x;
            lr.right = el.rect.x + labelSize;
            lr.top += labelSize + padding;
            lr.bottom += labelSize + padding;
          }
        }
        placed.push({ ...lr });
        const label = document.createElement('div');
        label.textContent = `${labelPrefix}${el.index}`;
        label.style.cssText = `position:absolute;background:${ls.bg};color:${ls.text};border:2px solid ${c.label};` +
          `width:${labelSize}px;height:${labelSize}px;border-radius:50%;display:flex;align-items:center;justify-content:center;` +
          `font-size:${fontSize}px;font-weight:600;box-shadow:0 2px 4px rgba(0,0,0,0.3);line-height:1;white-space:nowrap;overflow:hidden;` +
          `left:${Math.max(0, Math.min(lr.left, window.innerWidth - labelSize))}px;top:${Math.max(0, lr.top)}px;`;
        container.appendChild(label);
      }
      document.body.appendChild(container);
      visible = true;
      return elements;
    }

    return {
      get visible() { return visible; },
      get map() { return map; },
      // Regions mode draws page sections but keeps the element map (getMap/findElement) as it was.
      scan(opts) {
        const els = scan(opts || {});
        if ((opts || {}).mode !== 'regions') map = els;
        return els;
      },
      show(opts) { return render(this.scan(opts), typeof prefix === 'function' ? prefix(opts || {}) : prefix); },
      hide() { remove(); return []; },
      ensure() { if (!map.length) this.scan({}); return map; },
    };
  }

  // ---------------------------------------------------------------- interactive layer
  const MIN_W = 12;
  const MIN_H = 12;
  const INTERACTIVE_SELECTORS = [
    'button', 'input:not([type="hidden"])', 'textarea', 'select', 'a[href]',
    '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]', '[role="tab"]', '[role="menuitem"]',
    '[role="vote"]', '[role="img"][tabindex]', '[role="spinbutton"]',
    '[onclick]', '[ng-click]', '[v-on\\:click]', '[onmouseenter]', '[onmouseover]', '[data-hover]',
    '[tabindex]:not([tabindex="-1"])', '[aria-label][tabindex]', 'svg[tabindex]', '[data-clickable]', '[inputmode]',
    '[contenteditable="true"]', 'shreddit-button', 'faceplate-number-input', 'faceplate-text-input', 'faceplate-button',
    'button[aria-label]', 'button[data-test]', '[data-test="form-submit-button"]', 'input[name]',
  ].join(', ');
  const STRUCTURAL_TAGS = ['header', 'nav', 'main', 'footer', 'section', 'article', 'aside'];
  const NOISE_CLASSES = ['nav', 'menu', 'sidebar', 'footer', 'header', 'comment', 'ad', 'banner', 'popup', 'modal'];

  function category(el) {
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || '';
    if (tag === 'button' || role === 'button') return 'button';
    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
    if (/upvote|downvote|vote|like|share|save|comment|reply/.test(aria)) return 'button';
    if (tag.includes('button') || tag.startsWith('shreddit-') ||
        (tag.startsWith('faceplate-') && !/input|form|text|helper/.test(tag))) return 'button';
    if (tag === 'a' || role === 'link') return 'a';
    if (tag === 'input' || tag === 'textarea') return 'input';
    if (tag === 'select') return 'select';
    if (tag === 'svg' && el.hasAttribute('tabindex')) return 'button';
    if (el.onclick || el.getAttribute('onclick') || el.getAttribute('ng-click') || el.getAttribute('v-on:click')) return 'clickable';
    if (el.getAttribute('tabindex') !== null) return 'clickable';
    if (STRUCTURAL_TAGS.includes(tag)) return 'structural';
    return 'default';
  }

  function matchesType(cat, type) {
    if (!type) return true;
    switch (type.toLowerCase()) {
      case 'click': case 'clickable': return cat === 'clickable' || cat === 'button';
      case 'link': case 'a': return cat === 'a' || cat === 'link';
      case 'textarea': return false; // the reference's check could never match; kept as is
      case 'checkbox': case 'radio': return cat === 'input';
      default: return cat === type.toLowerCase();
    }
  }

  function textPreview(el, max = 30) {
    return (el.innerText || el.value || el.placeholder || '').trim().substring(0, max).replace(/\s+/g, ' ');
  }

  function accessibleName(el) {
    return el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') ||
      el.getAttribute('placeholder') || (el.innerText || '').trim().substring(0, 50).replace(/\s+/g, ' ') ||
      el.value || null;
  }

  // Label text for form fields (<label for>, wrapping <label>, aria-labelledby): lets "Customer field" match an
  // input whose only name is its label.
  function fieldLabel(el) {
    const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    const byIds = ids.map((id) => document.getElementById(id)).filter(Boolean).map((n) => n.innerText).join(' ').trim();
    if (byIds) return byIds.substring(0, 80);
    const labels = el.labels ? Array.from(el.labels).map((l) => l.innerText).join(' ').trim() : '';
    return labels ? labels.substring(0, 80).replace(/\s+/g, ' ') : null;
  }

  function describe(el, cat, name) {
    const names = { button: 'button', input: 'input field', textarea: 'text area', select: 'dropdown', a: 'link',
      link: 'link', clickable: 'clickable', structural: 'section', default: 'element' };
    const parts = [names[cat] || 'element'];
    const text = (el.innerText || '').trim().substring(0, 30).replace(/\s+/g, ' ');
    if (name) parts.push(`"${name}"`);
    else if (text) parts.push(`"${text}"`);
    if (el.tagName.toLowerCase() === 'input' && el.type) parts.unshift(el.type);
    if (el.disabled) parts.push('(disabled)');
    return parts.join(' ');
  }

  // Ancestors that make a role=dialog node "infrastructure" (mounted but hidden, or our own overlays).
  function isInfrastructureModal(el) {
    const seen = new Set();
    for (let cur = el; cur && cur.nodeType === 1 && !seen.has(cur); cur = parentInComposedTree(cur)) {
      seen.add(cur);
      const id = (cur.id || '').toLowerCase();
      const cls = (typeof cur.className === 'string' ? cur.className : '').toLowerCase();
      const name = cur.getAttribute('data-nametag') || '';
      const testId = cur.getAttribute('data-testid') || '';
      const tag = (cur.tagName || '').toLowerCase();
      if (id.startsWith('onetrust') && id !== 'onetrust-banner-sdk' && id !== 'onetrust-pc-sdk' &&
          cur.getAttribute('aria-hidden') === 'true') return true;
      if (name === 'shop-portal-provider' || testId.startsWith('authorize-modal') ||
          id === 'web-pixels-manager-sandbox-container' || id.startsWith('__agent-') ||
          /shop-portal|authorize-modal|web-pixel/.test(cls) || /shop-login-button|shop-cart-sync|shop-portal/i.test(tag)) return true;
      if (cur.getAttribute('aria-hidden') === 'true' || cur.hasAttribute('inert')) return true;
    }
    return false;
  }

  function usableModal(el) {
    const no = { usable: false };
    if (!el || el.nodeType !== 1 || isInfrastructureModal(el)) return no;
    let minOpacity = 1;
    let zIndex = 0;
    const seen = new Set();
    for (let cur = el; cur && cur.nodeType === 1 && !seen.has(cur); cur = parentInComposedTree(cur)) {
      seen.add(cur);
      if (cur.hidden || cur.hasAttribute('inert') || cur.getAttribute('aria-hidden') === 'true') return no;
      let s;
      try { s = getComputedStyle(cur); } catch (e) { return no; }
      if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse') return no;
      const op = parseFloat(s.opacity);
      if (!Number.isNaN(op)) minOpacity = Math.min(minOpacity, op);
      if (minOpacity < 0.05) return no;
      if (s.pointerEvents === 'none' && cur === el) return no;
      const zi = parseInt(s.zIndex, 10);
      if (!Number.isNaN(zi)) zIndex = Math.max(zIndex, zi);
      if ((cur.tagName || '').toLowerCase() === 'dialog' && cur.open === false) return no;
    }
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.height < 20) return no;
    const vw = window.innerWidth || document.documentElement.clientWidth || 0;
    const vh = window.innerHeight || document.documentElement.clientHeight || 0;
    if (!(r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw)) return no;
    const area = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    if (area < 400) return no;
    const details = el.closest && el.closest('details');
    if (details && !details.open) return no;
    const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
    const id = (el.id || '').toLowerCase();
    if (/drawer|search-modal|predictive-search|header__search-inner|cart-drawer/.test(cls) || id.includes('cartdrawer') || id === 'cart-drawer') {
      const openish = /(^|\s)(is-open|open|active|show|visible)(\s|$)/.test(cls) || el.getAttribute('open') != null ||
        el.getAttribute('aria-expanded') === 'true' || el.getAttribute('aria-hidden') === 'false';
      if (!openish && el.getAttribute('aria-modal') !== 'true') return no;
    }
    if (/\b(opacity-0|invisible|hidden|ot-hide)\b/.test(cls) && el.getAttribute('aria-modal') !== 'true') return no;
    return { usable: true, area, zIndex };
  }

  // Scored modal finder for the interactive layer: many sites keep hidden role=dialog nodes mounted, so only a
  // truly usable, user-facing dialog may scope the scan.
  function activeModal() {
    const cands = [];
    collectDeep('[aria-modal="true"]').forEach((el) => cands.push([el, 1]));
    collectDeep('[role="dialog"], [role="alertdialog"]').forEach((el) => {
      if (el.getAttribute('aria-modal') !== 'false') cands.push([el, 2]);
    });
    collectDeep('dialog[open]').forEach((el) => cands.push([el, 3]));
    ['.modal.show', '.modal.open', '.modal.visible', '.dialog.show', '.dialog.open', '.dialog.visible',
      '[class*="modal"][class*="open"]', '[class*="modal"][class*="show"]', '[class*="dialog"][class*="open"]',
      '[class*="dialog"][class*="show"]'].forEach((sel) => collectDeep(sel).forEach((el) => cands.push([el, 4])));
    let best = null;
    let bestScore = -Infinity;
    for (const [el, prio] of cands) {
      const info = usableModal(el);
      if (!info.usable) continue;
      const score = (5 - prio) * 1e12 + info.area * 1e3 + info.zIndex;
      if (score > bestScore) { bestScore = score; best = el; }
    }
    return best;
  }

  function interactiveVisible(el, modal, offscreen) {
    if (el.hidden || el.type === 'hidden') return false;
    if (!shownAndSized(el, MIN_W, MIN_H)) return false;
    if (!offscreen && !inViewport(el.getBoundingClientRect())) return false;
    return !modal || isComposedContainedBy(el, modalScope(modal));
  }

  let byIndex = new Map(); // index -> live element, from the latest interactive scan

  function entryFor(el, index, cat, offscreen) {
    const r = el.getBoundingClientRect();
    const name = accessibleName(el);
    return {
      index, tag: el.tagName.toLowerCase(), type: el.type || null, id: el.id || null,
      classes: Array.from(el.classList).slice(0, 5), selector: generateSelector(el), category: cat,
      rect: rectOf(r), text: textPreview(el), accessible_name: name, label: fieldLabel(el),
      description: describe(el, cat, name),
      offscreen: offscreen ? !inViewport(r) : false,
      attributes: {
        placeholder: el.placeholder || null, value: el.value || null, href: el.href || null,
        disabled: el.disabled || false, readonly: el.readOnly || false,
        aria_label: el.getAttribute('aria-label') || null, title: el.getAttribute('title') || null,
        alt: el.getAttribute('alt') || null, name: el.getAttribute('name') || null,
        role: el.getAttribute('role') || null,
      },
    };
  }

  // offscreen=true (agent lookups only) also returns elements scrolled out of view; the overlay never does.
  function scanInteractive({ element_type, exclude_types, hover, offscreen }) {
    const out = [];
    const seen = [];
    const excluded = new Set((exclude_types || []).map((t) => t.toLowerCase()));
    const modal = activeModal();
    const all = collectDeep(INTERACTIVE_SELECTORS);
    byIndex = new Map();

    // Pass 1: global indices over every shown element, so an element keeps its number while the page scrolls.
    const globalIdx = new Map();
    let next = 0;
    for (const el of all) {
      if (el.hidden || el.type === 'hidden') continue;
      const s = getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width < MIN_W || r.height < MIN_H) continue;
      globalIdx.set(el, next++);
    }
    const dup = (r) => seen.some((s) => sameRect(r, s.rect, 3));

    // Pass 2: elements in the viewport (and inside the active modal, if any), keeping their global index.
    for (const el of all) {
      if (!interactiveVisible(el, modal, offscreen)) continue;
      const idx = globalIdx.get(el);
      if (idx === undefined) continue;
      const r = el.getBoundingClientRect();
      const cat = category(el);
      if (!matchesType(cat, element_type) || excluded.has(cat) || dup(r)) continue;
      out.push(entryFor(el, idx, cat, offscreen));
      byIndex.set(idx, el);
      seen.push({ rect: r, category: cat });
    }

    // Pass 3 (hover scans only): plain elements whose only interactivity signal is cursor:pointer.
    if (hover) {
      for (const el of collectDeep('*')) {
        if (el.hidden || el.type === 'hidden' || globalIdx.has(el)) continue;
        const tag = el.tagName.toLowerCase();
        if (['html', 'body', 'head', 'script', 'style', 'link', 'meta'].includes(tag)) continue;
        const r = el.getBoundingClientRect();
        if (r.width < MIN_W || r.height < MIN_H) continue;
        if (r.width > window.innerWidth * 0.9 || r.height > window.innerHeight * 0.9) continue;
        const s = getComputedStyle(el);
        if (s.cursor !== 'pointer' || s.pointerEvents === 'none') continue;
        if (!interactiveVisible(el, modal, false) || dup(r)) continue;
        const cat = category(el) === 'structural' ? 'clickable' : category(el);
        if (excluded.has(cat)) continue;
        const idx = next++;
        out.push(entryFor(el, idx, cat, false));
        byIndex.set(idx, el);
        seen.push({ rect: r, category: cat });
      }
    }

    // Structural sections, numbered after the interactive range.
    let sIdx = next;
    for (const tag of STRUCTURAL_TAGS) {
      for (const el of document.querySelectorAll(tag)) {
        if (!interactiveVisible(el, modal, false)) continue;
        const r = el.getBoundingClientRect();
        if (seen.filter((s) => s.category !== 'structural' && !(r.right < s.rect.left || r.left > s.rect.right ||
            r.bottom < s.rect.top || r.top > s.rect.bottom)).length > 3) continue;
        if (r.width > window.innerWidth * 0.9 || r.height > window.innerHeight * 0.8) continue;
        const idx = sIdx++;
        out.push({
          index: idx, tag: el.tagName.toLowerCase(), type: null, id: el.id || null,
          classes: Array.from(el.classList).slice(0, 5), selector: generateSelector(el), category: 'structural',
          rect: rectOf(r), text: textPreview(el, 50), accessible_name: el.getAttribute('aria-label') || null,
          label: null, description: `${el.tagName.toLowerCase()} section`, offscreen: false, attributes: {},
        });
        byIndex.set(idx, el);
        seen.push({ rect: r, category: 'structural' });
      }
    }
    return out;
  }

  // ---------------------------------------------------------------- regions mode
  function isNoise(el) {
    const s = `${el.className || ''} ${el.id || ''}`.toLowerCase();
    return NOISE_CLASSES.some((n) => s.includes(n));
  }

  function regionScore(el) {
    const text = (el.innerText || '').trim();
    let score = Math.min(text.length / 5, 150) + el.querySelectorAll('h1,h2,h3,h4,h5,h6').length * 20 +
      el.querySelectorAll('p').length * 10 + Math.min(el.querySelectorAll('img').length * 3, 30) +
      Math.min(el.querySelectorAll('a').length * 2, 40);
    if (isNoise(el)) score *= 0.3;
    return Math.round(score);
  }

  function regionEntry(el, text, description) {
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(), id: el.id || null, classes: Array.from(el.classList).slice(0, 5),
      selector: generateSelector(el), category: 'region', rect: rectOf(r), text,
      text_length: (el.innerText || '').length, has_images: el.querySelectorAll('img').length > 0,
      has_links: el.querySelectorAll('a').length > 0, description, score: regionScore(el),
    };
  }

  function boxOf(rect) {
    return { left: rect.x, top: rect.y, right: rect.x + rect.width, bottom: rect.y + rect.height, width: rect.width, height: rect.height };
  }

  function scanRegions() {
    const main = document.querySelector('main') || document.querySelector('[role="main"]') || document.body;
    const regions = [];
    const parents = new Set();
    for (const h of main.querySelectorAll('h1, h2, h3, h4')) {
      let p = h.parentElement;
      while (p && p !== main && !['DIV', 'SECTION', 'ARTICLE'].includes(p.tagName)) p = p.parentElement;
      if (!p || p === main) {
        p = h.parentElement;
        if (!p || p === main) continue;
      }
      if (parents.has(p)) continue;
      parents.add(p);
      const r = p.getBoundingClientRect();
      if (r.width < 50 || r.height < 50) continue;
      const t = (h.innerText || '').trim().substring(0, 50) || p.id || 'Section';
      regions.push(regionEntry(p, t, `"${t}" section`));
    }
    if (regions.length < 3) {
      const cr = main.getBoundingClientRect();
      for (const child of main.children) {
        if (!interactiveVisible(child, null, false) || isNoise(child)) continue;
        const r = child.getBoundingClientRect();
        if (r.width < 100 || r.height < 50) continue;
        if (r.left < cr.left + 20 && r.width > cr.width * 0.8) continue;
        const t = (child.innerText || '').trim().substring(0, 80) || child.tagName.toLowerCase();
        const entry = regionEntry(child, t.substring(0, 60), t ? `"${t.substring(0, 40)}..."` : `${child.tagName.toLowerCase()} section`);
        if (!regions.some((e) => overlapShare(boxOf(e.rect), boxOf(entry.rect)) > 0.5)) regions.push(entry);
      }
    }
    regions.sort((a, b) => a.rect.y - b.rect.y);
    const out = [];
    for (const r of regions) {
      if (out.some((o) => overlapShare(boxOf(r.rect), boxOf(o.rect)) > 0.6)) continue;
      r.index = out.length;
      out.push(r);
    }
    return out.slice(0, 15);
  }

  // ---------------------------------------------------------------- static text layer
  const STATIC_SELECTORS = ['p', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'label', 'li', 'td', 'th', 'strong',
    'em', 'b', 'i', 'small', 'blockquote', 'figcaption', 'dt', 'dd', 'a:not([href])', 'caption'].join(', ');
  const STATIC_MODAL_EXTRA = ['.modal.show', '.modal.open', '.modal.visible', '.dialog.show', '.dialog.open',
    '.dialog.visible', '[class*="modal"][class*="open"]', '[class*="modal"][class*="show"]',
    '[class*="dialog"][class*="open"]', '[class*="dialog"][class*="show"]', '.ReactModal__Overlay',
    '[class*="Modal"][class*="open"]', '[class*="Modal"][class*="show"]', '[class*="modal"][class*="after-open"]'];

  function isTextContainer(el) {
    const tag = el.tagName.toLowerCase();
    if (['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'label', 'li', 'dt', 'dd', 'figcaption', 'caption', 'blockquote'].includes(tag)) return true;
    if (!['span', 'div', 'td', 'th', 'small', 'strong', 'em', 'b', 'i', 'a'].includes(tag)) return false;
    for (const n of el.childNodes) if (n.nodeType === Node.TEXT_NODE && n.textContent.trim()) return true;
    const kids = Array.from(el.children);
    if (!kids.length) return (el.innerText || '').trim().length >= 2;
    return kids.every((c) => ['span', 'strong', 'em', 'b', 'i', 'small', 'a'].includes(c.tagName.toLowerCase()) ||
      c.tagName.toLowerCase().startsWith('h'));
  }

  function scanStatic() {
    const out = [];
    const seen = [];
    const modal = firstVisibleModal({ deep: true, extraSelectors: STATIC_MODAL_EXTRA });
    for (const el of collectDeep(STATIC_SELECTORS)) {
      if (!shownAndSized(el, MIN_W, MIN_H) || !inViewport(el.getBoundingClientRect())) continue;
      if (modal && !isComposedContainedBy(el, modalScope(modal))) continue;
      if ((el.innerText || '').trim().length < 2 || !isTextContainer(el)) continue;
      const r = el.getBoundingClientRect();
      if (seen.some((s) => sameRect(r, s, 5)) || seen.some((s) => overlapShare(r, s) > 0.8)) continue;
      const text = (el.innerText || '').trim().substring(0, 50).replace(/\s+/g, ' ');
      out.push({
        index: out.length, tag: el.tagName.toLowerCase(), id: el.id || null, classes: Array.from(el.classList).slice(0, 5),
        selector: generateSelector(el), category: 'static', rect: rectOf(r), text,
        text_length: (el.innerText || '').length, description: `text "${text.substring(0, 30)}"`, attributes: {},
      });
      seen.push(r);
    }
    return out;
  }

  // ---------------------------------------------------------------- scrollable layer
  function scanScrollable() {
    const out = [];
    const seen = [];
    const modal = firstVisibleModal({ deep: false });
    for (const el of collectDeep('*')) {
      const s = getComputedStyle(el);
      const canV = (s.overflowY === 'scroll' || s.overflowY === 'auto') && el.scrollHeight > el.clientHeight + 5;
      const canH = (s.overflowX === 'scroll' || s.overflowX === 'auto') && el.scrollWidth > el.clientWidth + 5;
      if (!canV && !canH) continue;
      if (!shownAndSized(el, 30, 30) || !inViewport(el.getBoundingClientRect())) continue;
      // Inside the modal, or an ancestor of it (scrollable modal wrappers).
      if (modal && !isComposedContainedBy(el, modalScope(modal)) && !isComposedContainedBy(modal, el)) continue;
      const r = el.getBoundingClientRect();
      if (seen.some((p) => Math.abs(r.left - p.left) < 5 && Math.abs(r.top - p.top) < 5)) continue;
      const v = el.scrollHeight > el.clientHeight + 5;
      const h = el.scrollWidth > el.clientWidth + 5;
      const parts = [];
      if (el.id) parts.push(`#${el.id}`);
      if (typeof el.className === 'string' && el.className.trim()) parts.push(`.${el.className.split(' ').filter(Boolean).slice(0, 2).join('.')}`);
      parts.push(v && h ? '(scrolls both directions)' : v ? '(scrolls vertically)' : '(scrolls horizontally)');
      out.push({
        index: out.length, tag: el.tagName.toLowerCase(), id: el.id || null, classes: Array.from(el.classList).slice(0, 5),
        selector: generateSelector(el), category: 'scrollable', rect: rectOf(r),
        scrollDirections: { vertical: v, horizontal: h },
        scrollPosition: { top: el.scrollTop, left: el.scrollLeft, maxTop: el.scrollHeight - el.clientHeight, maxLeft: el.scrollWidth - el.clientWidth },
        description: parts.join(' '),
      });
      seen.push({ left: r.left, top: r.top });
    }
    return out;
  }

  // ---------------------------------------------------------------- the three layers
  let mode = 'interactive';
  let excludeTypes = null;
  const interactive = makeLayer({
    containerId: CONTAINER_IDS[0], labelSize: 40, padding: 5, fontSize: 18, attempts: 100,
    prefix: () => (mode === 'regions' ? 'R' : ''),
    scan: (o) => (o.mode === 'regions' ? scanRegions() : scanInteractive(o)),
  });
  const staticLayer = makeLayer({ containerId: CONTAINER_IDS[1], labelSize: 36, padding: 4, fontSize: 16, attempts: 100, prefix: 'S', scan: scanStatic });
  const scrollLayer = makeLayer({ containerId: CONTAINER_IDS[2], labelSize: 40, padding: 5, fontSize: 18, attempts: 50, prefix: '', scan: scanScrollable });
  let regionMap = [];

  function showInteractive(show, m = 'interactive', exclude, hover) {
    if (show === undefined) show = !interactive.visible;
    if (!show) return interactive.hide();
    mode = m;
    excludeTypes = exclude;
    const els = interactive.show({ mode: m, exclude_types: exclude, hover });
    if (m === 'regions') regionMap = els;
    return els;
  }

  function findByText(text) {
    const q = String(text || '').toLowerCase();
    return interactive.ensure().find((e) =>
      (e.text && e.text.toLowerCase().includes(q)) ||
      (e.accessible_name && e.accessible_name.toLowerCase().includes(q)) ||
      (e.description && e.description.toLowerCase().includes(q)));
  }

  function refreshInteractive() {
    return interactive.visible ? showInteractive(true, mode, excludeTypes) : interactive.scan({ exclude_types: excludeTypes });
  }

  window.__agentOverlay = {
    toggle: showInteractive,
    show: (m) => showInteractive(true, m),
    hide: () => showInteractive(false),
    getMap: () => interactive.ensure(),
    getRegions: () => (regionMap.length ? regionMap : (regionMap = scanRegions())),
    getElement: (index) => interactive.ensure().find((e) => e.index === index),
    findElement: findByText,
    refresh: refreshInteractive,
  };
  window.__agentStaticOverlay = {
    toggle: (f) => ((f === undefined ? !staticLayer.visible : f) ? staticLayer.show() : staticLayer.hide()),
    show: () => staticLayer.show(),
    hide: () => staticLayer.hide(),
    getMap: () => staticLayer.ensure(),
    getElement: (index) => staticLayer.ensure().find((e) => e.index === index),
    refresh: () => (staticLayer.visible ? staticLayer.show() : staticLayer.scan()),
  };
  window.__agentScrollableOverlay = {
    toggle: (f) => ((f === undefined ? !scrollLayer.visible : f) ? scrollLayer.show() : scrollLayer.hide()),
    show: () => scrollLayer.show(),
    hide: () => scrollLayer.hide(),
    getMap: () => scrollLayer.ensure(),
    getElement: (index) => scrollLayer.ensure().find((e) => e.index === index),
  };

  // ---------------------------------------------------------------- DOM actions
  function resolveTarget(p) {
    let el = null;
    if (p.index !== undefined && p.index !== null) el = byIndex.get(p.index) || null;
    if (!el && p.selector) {
      try { el = document.querySelector(p.selector); } catch (e) { el = null; }
      if (!el) el = collectDeep(p.selector)[0] || null;
    }
    if (!el && p.text) {
      const hit = findByText(p.text);
      el = hit ? byIndex.get(hit.index) : null;
    }
    if (!el) throw new Error('element not found');
    return el;
  }

  function reveal(el) {
    const r = el.getBoundingClientRect();
    if (!inViewport(r) || r.top < 0 || r.bottom > window.innerHeight) el.scrollIntoView({ block: 'center', inline: 'nearest' });
    return el.getBoundingClientRect();
  }

  function mouse(el, type, r, extra = {}) {
    const init = { bubbles: true, cancelable: true, composed: true, view: window, clientX: r.left + r.width / 2,
      clientY: r.top + r.height / 2, button: extra.button || 0, buttons: 1, detail: extra.detail || 1 };
    const Ctor = type.startsWith('pointer') ? PointerEvent : MouseEvent;
    return el.dispatchEvent(new Ctor(type, { pointerId: 1, isPrimary: true, ...init }));
  }

  function info(el) {
    return { tag: el.tagName.toLowerCase(), selector: generateSelector(el), rect: rectOf(el.getBoundingClientRect()),
      name: accessibleName(el), label: fieldLabel(el), value: 'value' in el ? el.value : null, url: location.href };
  }

  function clickEl(el, kind) {
    const r = reveal(el);
    if (kind === 'hover') {
      ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'pointermove', 'mousemove'].forEach((t) => mouse(el, t, r));
      return info(el);
    }
    if (kind === 'right') {
      mouse(el, 'pointerdown', r, { button: 2 });
      mouse(el, 'mousedown', r, { button: 2 });
      mouse(el, 'pointerup', r, { button: 2 });
      mouse(el, 'mouseup', r, { button: 2 });
      mouse(el, 'contextmenu', r, { button: 2 });
      return info(el);
    }
    mouse(el, 'pointerdown', r);
    mouse(el, 'mousedown', r);
    if (typeof el.focus === 'function') el.focus({ preventScroll: true });
    mouse(el, 'pointerup', r);
    mouse(el, 'mouseup', r);
    mouse(el, 'click', r); // a dispatched click still runs default activation (links, checkboxes, submit)
    if (kind === 'double') {
      mouse(el, 'click', r, { detail: 2 });
      mouse(el, 'dblclick', r, { detail: 2 });
    }
    return info(el);
  }

  // Setting .value directly bypasses React's tracker; the prototype setter plus an input event does not.
  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, value);
  }

  function typeInto(el, text, clear) {
    reveal(el);
    if (typeof el.focus === 'function') el.focus({ preventScroll: true });
    const tag = el.tagName.toLowerCase();
    if (tag === 'select') {
      const want = String(text).trim().toLowerCase();
      const opt = Array.from(el.options).find((o) => o.text.trim().toLowerCase() === want || o.value.toLowerCase() === want) ||
        Array.from(el.options).find((o) => o.text.trim().toLowerCase().includes(want));
      if (!opt) throw new Error(`no option "${text}"`);
      setNativeValue(el, opt.value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return info(el);
    }
    if (el.isContentEditable) {
      if (clear) document.execCommand('selectAll', false);
      document.execCommand('insertText', false, String(text));
      return info(el);
    }
    if (!('value' in el)) throw new Error(`<${tag}> is not a text field`);
    const value = (clear ? '' : el.value || '') + String(text);
    setNativeValue(el, value);
    el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, inputType: 'insertText', data: String(text) }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return info(el);
  }

  function readEl(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' && (el.type === 'checkbox' || el.type === 'radio')) return { value: el.checked, ...info(el) };
    if ('value' in el && ['input', 'textarea', 'select'].includes(tag)) return { value: el.value, ...info(el) };
    return { value: (el.innerText || el.textContent || '').trim(), ...info(el) };
  }

  // Is the element at `selector` still there, visible, and still the same element (same name)?
  function probe(selector, name) {
    let el = null;
    try { el = document.querySelector(selector); } catch (e) { return { found: false }; }
    if (!el || !shownAndSized(el, 2, 2)) return { found: false };
    const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const want = clean(name);
    // Fields are remembered by their label (their accessible name can be the typed value).
    return { found: !want || [fieldLabel(el), accessibleName(el)].some((n) => clean(n) === want), ...info(el) };
  }

  function nearbyHeading(el) {
    for (let cur = el; cur && cur !== document.body; cur = cur.parentElement) {
      for (let sib = cur.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (/^H[1-4]$/.test(sib.tagName)) return sib.innerText.trim().substring(0, 80);
        const h = sib.querySelector && sib.querySelector('h1, h2, h3, h4');
        if (h) return h.innerText.trim().substring(0, 80);
      }
    }
    return null;
  }

  function cellText(c) {
    const field = c.querySelector('input, select, textarea');
    return ((field && field.value) || c.innerText || '').replace(/\s+/g, ' ').trim();
  }

  // Every visible <table> and ARIA grid, with headers and rows (capped), for read_table().
  function tables() {
    const out = [];
    for (const t of collectDeep('table, [role="grid"], [role="table"]')) {
      if (!shownAndSized(t, 10, 10)) continue;
      const isTable = t.tagName === 'TABLE';
      const rows = isTable ? Array.from(t.rows) : collectDeep('[role="row"]', t);
      if (!rows.length) continue;
      const cellsOf = (r) => (isTable ? Array.from(r.cells) : Array.from(r.querySelectorAll('[role="cell"], [role="gridcell"], [role="columnheader"], [role="rowheader"]')));
      let headers = [];
      let start = 0;
      const thead = isTable && t.tHead && t.tHead.rows.length ? t.tHead.rows[t.tHead.rows.length - 1] : null;
      if (thead) {
        headers = cellsOf(thead).map(cellText);
        start = rows.indexOf(thead) + 1;
      } else if (cellsOf(rows[0]).every((c) => c.tagName === 'TH' || c.getAttribute('role') === 'columnheader')) {
        headers = cellsOf(rows[0]).map(cellText);
        start = 1;
      }
      const body = rows.slice(start, start + 500).map((r) => cellsOf(r).map(cellText)).filter((r) => r.some((v) => v));
      out.push({
        index: out.length, selector: generateSelector(t), rect: rectOf(t.getBoundingClientRect()),
        caption: (isTable && t.caption ? t.caption.innerText.trim() : '') || t.getAttribute('aria-label') || '',
        heading: nearbyHeading(t), id: t.id || null, headers, rows: body, total_rows: rows.length - start,
      });
    }
    return out;
  }

  function pageText(max) {
    const parts = [];
    const modal = activeModal();
    if (modal) parts.push('[dialog] ' + (modal.innerText || '').trim());
    parts.push((document.body.innerText || '').trim());
    return { url: location.href, title: document.title, text: parts.join('\n\n').substring(0, max || 8000) };
  }

  // ---------------------------------------------------------------- teach recording
  // Only trusted (real user) events are recorded, so the agent's own dispatched events never show up.
  let teaching = false;
  const lastInput = new WeakMap();

  function teachTarget(node) {
    let el = node && node.nodeType === 1 ? node : node && node.parentElement;
    for (let cur = el; cur; cur = parentInComposedTree(cur)) {
      try { if (cur.matches && cur.matches(INTERACTIVE_SELECTORS)) return cur; } catch (e) { break; }
    }
    return el;
  }

  function teachEvent(kind, el, extra) {
    if (!teaching || !el) return;
    const isPassword = el.type === 'password';
    const cat = category(el);
    const name = fieldLabel(el) || accessibleName(el);
    window.dispatchEvent(new CustomEvent('__agent_teach_event', { detail: {
      kind, t: Date.now(), url: location.href, title: document.title, selector: generateSelector(el),
      tag: el.tagName.toLowerCase(), type: el.type || null, role: el.getAttribute('role') || null, category: cat,
      name: name ? String(name).substring(0, 80) : null, text: textPreview(el, 60), description: describe(el, cat, name),
      ...(extra || {}), ...(isPassword && extra && 'value' in extra ? { value: '', secret: true } : {}),
    } }));
  }

  document.addEventListener('click', (e) => {
    if (e.isTrusted) teachEvent(e.button === 2 ? 'right_click' : 'click', teachTarget(e.composedPath()[0] || e.target));
  }, true);
  document.addEventListener('dblclick', (e) => { if (e.isTrusted) teachEvent('double_click', teachTarget(e.target)); }, true);
  document.addEventListener('input', (e) => {
    if (e.isTrusted && e.target && 'value' in e.target) lastInput.set(e.target, e.target.value);
  }, true);
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (!e.isTrusted || !el || !('value' in el)) return;
    const value = el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.value;
    teachEvent(el.tagName === 'SELECT' ? 'select' : 'input', el, { value });
  }, true);
  document.addEventListener('keydown', (e) => {
    if (!e.isTrusted || !['Enter', 'Escape', 'Tab'].includes(e.key)) return;
    const el = e.target;
    // Enter often submits before 'change' fires: report the typed value first.
    if (e.key === 'Enter' && el && lastInput.has(el)) teachEvent('input', el, { value: lastInput.get(el) });
    teachEvent('key', el, { key: e.key });
  }, true);

  // ---------------------------------------------------------------- command handler
  function viewport() {
    return { screenX: window.screenX, screenY: window.screenY, innerWidth: window.innerWidth, innerHeight: window.innerHeight,
      outerWidth: window.outerWidth, outerHeight: window.outerHeight, devicePixelRatio: window.devicePixelRatio,
      scrollX: window.scrollX, scrollY: window.scrollY, url: location.href, title: document.title };
  }

  const LAYERS = { interactive: window.__agentOverlay, static: window.__agentStaticOverlay, scrollable: window.__agentScrollableOverlay };

  function handle(cmd, p) {
    switch (cmd) {
      case 'show':
        if ((p.layer || 'interactive') === 'interactive') return { elements: showInteractive(true, p.mode || 'interactive', p.exclude_types, !!p.hover) };
        return { elements: LAYERS[p.layer].show() };
      case 'hide':
        if (p.layer && p.layer !== 'all') return { elements: LAYERS[p.layer].hide() };
        Object.values(LAYERS).forEach((l) => l.hide());
        return { elements: [] };
      case 'toggle':
        if ((p.layer || 'interactive') === 'interactive') return { elements: showInteractive(p.show, p.mode || 'interactive', p.exclude_types, !!p.hover) };
        return { elements: LAYERS[p.layer].toggle(p.show) };
      case 'get_map':
        if ((p.layer || 'interactive') === 'interactive') {
          return { elements: interactive.scan({ element_type: p.element_type, offscreen: !!p.offscreen, exclude_types: p.exclude_types }) };
        }
        return { elements: (p.layer === 'static' ? staticLayer : scrollLayer).scan() };
      case 'get_regions': return { elements: window.__agentOverlay.getRegions() };
      case 'get_element': {
        const el = (LAYERS[p.layer || 'interactive']).getElement(p.index);
        if (!el) throw new Error('Element not found');
        return { element: el };
      }
      case 'find_element': return { element: findByText(p.text) || null };
      case 'refresh': return { elements: (p.layer && p.layer !== 'interactive') ? LAYERS[p.layer].refresh() : refreshInteractive() };
      case 'reveal': { const el = resolveTarget(p); reveal(el); return info(el); }
      case 'click': return clickEl(resolveTarget(p), p.kind || 'single');
      case 'type': return typeInto(resolveTarget(p), p.text == null ? '' : p.text, !!p.clear);
      case 'read': return readEl(resolveTarget(p));
      case 'probe': return probe(p.selector, p.name);
      case 'tables': return { tables: tables() };
      case 'page_text': return pageText(p.max);
      case 'signature': {
        // Cheap "did the page change" fingerprint: URL, DOM size, visible text length, focused field's value.
        const a = document.activeElement;
        return { url: location.href, nodes: document.getElementsByTagName('*').length,
          text: (document.body.innerText || '').length, focus: a && 'value' in a ? String(a.value).length : -1,
          dialog: !!activeModal() };
      }
      case 'viewport': return viewport();
      case 'teach': teaching = !!p.on; return { teaching };
      case 'ping': return { ok: true, url: location.href };
      default: throw new Error(`Unknown command: ${cmd}`);
    }
  }

  window.addEventListener('__agent_command', (event) => {
    const d = event.detail;
    if (!d || d.__agent !== 'command') return;
    const response = { __agent: 'response', commandId: d.commandId };
    try {
      response.result = handle(d.cmd, d.params || {});
    } catch (err) {
      response.error = String((err && err.message) || err);
    }
    window.dispatchEvent(new CustomEvent('__agent_response', { detail: response }));
  });

  const announce = () => window.dispatchEvent(new CustomEvent('__agent_ready', { detail: { __agent: 'ready' } }));
  window.addEventListener('__agent_hello', announce);
  announce();
})();
