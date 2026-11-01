// Background service worker: one WebSocket to the local agent engine. The engine sends {id, type, data}; we answer
// {id, ok, result} or {id, ok: false, error}. Page work goes to the active tab's content script, which relays it to
// the MAIN-world page module (overlay.js). Network capture and JS evaluation use chrome.debugger (CDP).
importScripts('config.js');

const VERSION = chrome.runtime.getManifest().version;
const RESTRICTED = /^(chrome|chrome-extension|edge|about|devtools|view-source):/;

// ---------------------------------------------------------------- engine connection
let ws = null;
let connected = false;
let retryMs = 1000;
let pingTimer = null;

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket(ENGINE_WS_URL);
  } catch (e) {
    scheduleReconnect();
    return;
  }
  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'hello', token: ENGINE_TOKEN, version: VERSION, ua: navigator.userAgent }));
  };
  ws.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch (e) { return; }
    if (msg.type === 'welcome') {
      connected = true;
      retryMs = 1000;
      clearInterval(pingTimer);
      // WebSocket traffic keeps an MV3 service worker alive (Chrome 116+); ping so an idle link still counts.
      pingTimer = setInterval(() => send({ type: 'ping' }), 20000);
      return;
    }
    if (msg.id !== undefined) handleCommand(msg);
  };
  ws.onclose = () => {
    connected = false;
    clearInterval(pingTimer);
    ws = null;
    scheduleReconnect();
  };
  ws.onerror = () => {}; // onclose follows
}

function scheduleReconnect() {
  setTimeout(connect, retryMs);
  retryMs = Math.min(retryMs * 2, 10000);
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

// Reconnect after the worker was suspended and woken up again.
chrome.alarms.create('agent-keepalive', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === 'agent-keepalive') connect(); });
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();

// ---------------------------------------------------------------- tabs and the page module
async function activeTab(tabId) {
  if (tabId) return chrome.tabs.get(tabId);
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab) throw new Error('no active tab');
  return tab;
}

async function inject(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
  await chrome.scripting.executeScript({ target: { tabId }, files: ['overlay.js'], world: 'MAIN' });
}

// Send a command to the page module in the tab's top frame. Tabs opened before the extension was loaded have no
// content script yet: inject it once and retry.
async function page(cmd, params = {}, tabId = null, timeout = 8000) {
  const tab = await activeTab(tabId);
  if (!tab.url || RESTRICTED.test(tab.url)) throw new Error(`can't access this page (${tab.url || 'blank'})`);
  const msg = { __agent: 'page', cmd, params, timeout };
  let res;
  try {
    res = await chrome.tabs.sendMessage(tab.id, msg, { frameId: 0 });
  } catch (e) {
    await inject(tab.id);
    res = await chrome.tabs.sendMessage(tab.id, msg, { frameId: 0 });
  }
  if (!res) throw new Error('no answer from the page');
  if (res.error) throw new Error(res.error);
  return res.result;
}

function waitForLoad(tabId, timeoutMs = 20000) {
  return new Promise((resolve) => {
    const timer = setTimeout(done, timeoutMs);
    function done() {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      chrome.tabs.get(tabId).then(resolve, () => resolve(null));
    }
    function onUpdated(id, info) { if (id === tabId && info.status === 'complete') done(); }
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs.get(tabId).then((t) => { if (t.status === 'complete' && t.url !== 'about:blank') done(); }, done);
  });
}

// ---------------------------------------------------------------- CDP: network capture and evaluation
const net = { tabId: null, attached: false, seq: 0, entries: [], byId: new Map() };
const NET_MAX = 400;
const BODY_MAX = 100000;

function cdp(method, params = {}) {
  return chrome.debugger.sendCommand({ tabId: net.tabId }, method, params);
}

async function attach(tabId) {
  if (net.attached && net.tabId === tabId) return;
  if (net.attached) await detach();
  await chrome.debugger.attach({ tabId }, '1.3');
  net.tabId = tabId;
  net.attached = true;
  await cdp('Network.enable', { maxPostDataSize: 65536 });
}

async function detach() {
  if (!net.attached) return;
  try { await chrome.debugger.detach({ tabId: net.tabId }); } catch (e) { /* already gone */ }
  net.attached = false;
}

chrome.debugger.onDetach.addListener((source) => {
  if (source.tabId === net.tabId) net.attached = false; // tab closed, or the user dismissed the debugging bar
});

chrome.debugger.onEvent.addListener((source, method, p) => {
  if (source.tabId !== net.tabId) return;
  if (method === 'Network.requestWillBeSent') {
    const e = { seq: ++net.seq, id: p.requestId, url: p.request.url, method: p.request.method, type: p.type || 'Other',
      post: p.request.postData ? p.request.postData.substring(0, 4000) : null, t: Date.now(), status: null, mime: null,
      done: false, failed: false };
    net.entries.push(e);
    net.byId.set(p.requestId, e);
    if (net.entries.length > NET_MAX) net.byId.delete(net.entries.shift().id);
  } else if (method === 'Network.responseReceived') {
    const e = net.byId.get(p.requestId);
    if (e) { e.status = p.response.status; e.mime = p.response.mimeType; }
  } else if (method === 'Network.loadingFinished') {
    const e = net.byId.get(p.requestId);
    if (e) {
      e.done = true;
      // While teaching, keep JSON API bodies right away: they may be gone after the page navigates.
      if (teach.on && isApi(e) && teach.bodies < 30) { teach.bodies++; fetchBody(e); }
    }
  } else if (method === 'Network.loadingFailed') {
    const e = net.byId.get(p.requestId);
    if (e) { e.done = true; e.failed = true; }
  }
});

function isApi(e) {
  return (e.type === 'XHR' || e.type === 'Fetch') && /json|text\/plain|graphql/.test(e.mime || '');
}

async function fetchBody(e) {
  if (e.body !== undefined) return e.body;
  try {
    const r = await cdp('Network.getResponseBody', { requestId: e.id });
    let text = r.base64Encoded ? new TextDecoder().decode(Uint8Array.from(atob(r.body), (c) => c.charCodeAt(0))) : r.body;
    text = text.substring(0, BODY_MAX);
    try { e.body = JSON.parse(text); } catch (err) { e.body = text; }
  } catch (err) {
    e.body = null;
  }
  return e.body;
}

function matches(e, q) {
  if (q.since && e.seq <= q.since) return false;
  if (q.url_contains && !e.url.includes(q.url_contains)) return false;
  if (q.method && e.method.toUpperCase() !== q.method.toUpperCase()) return false;
  if (q.types && !q.types.includes(e.type)) return false;
  return true;
}

function summary(e) {
  const { id, ...rest } = e;
  return rest;
}

// Wait up to wait_ms for finished requests matching the query; newest first, bodies for the first `bodies`.
async function netQuery(q) {
  const until = Date.now() + (q.wait_ms || 0);
  for (;;) {
    const hits = net.entries.filter((e) => e.done && matches(e, q)).reverse().slice(0, q.limit || 20);
    if (hits.length || Date.now() >= until) {
      for (const e of hits.slice(0, q.bodies === undefined ? 1 : q.bodies)) await fetchBody(e);
      return { entries: hits.map(summary), seq: net.seq, attached: net.attached };
    }
    await new Promise((r) => setTimeout(r, 150));
  }
}

async function evaluate(code, tabId) {
  const tab = await activeTab(tabId);
  await attach(tab.id);
  const body = /\breturn\b/.test(code) ? `(async () => { ${code} })()` : `(async () => (${code}))()`;
  const r = await cdp('Runtime.evaluate', { expression: body, returnByValue: true, awaitPromise: true, userGesture: true });
  if (r.exceptionDetails) {
    throw new Error((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text);
  }
  return r.result.value === undefined ? null : r.result.value;
}

// ---------------------------------------------------------------- teach recording
const teach = { on: false, events: [], since: 0, bodies: 0 };

async function setTeaching(on) {
  const tabs = await chrome.tabs.query({});
  await Promise.all(tabs.filter((t) => t.url && !RESTRICTED.test(t.url)).map((t) =>
    chrome.tabs.sendMessage(t.id, { __agent: 'page', cmd: 'teach', params: { on } }, { frameId: 0 }).catch(() => {})));
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.__agent === 'teach_event') {
    if (teach.on) teach.events.push({ ...msg.event, tabId: sender.tab && sender.tab.id });
    return false;
  }
  if (msg && msg.__agent === 'popup') {
    popup(msg).then(sendResponse, (e) => sendResponse({ error: String(e.message || e) }));
    return true;
  }
  return false;
});

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (!teach.on) return;
  if (info.url && !RESTRICTED.test(info.url)) teach.events.push({ kind: 'navigate', t: Date.now(), url: info.url, tabId });
  // A page that finished loading during the recording starts with recording off: switch it on.
  if (info.status === 'complete' && tab.url && !RESTRICTED.test(tab.url)) {
    chrome.tabs.sendMessage(tabId, { __agent: 'page', cmd: 'teach', params: { on: true } }, { frameId: 0 }).catch(() => {});
  }
});

async function teachStart() {
  teach.on = true;
  teach.events = [];
  teach.bodies = 0;
  try {
    const tab = await activeTab();
    await attach(tab.id);
    teach.events.push({ kind: 'navigate', t: Date.now(), url: tab.url, tabId: tab.id, initial: true });
  } catch (e) { /* recording still works without network capture */ }
  teach.since = net.seq;
  await setTeaching(true);
  return { teaching: true };
}

async function teachStop() {
  teach.on = false;
  await setTeaching(false);
  const calls = net.entries.filter((e) => e.seq > teach.since && e.done && isApi(e));
  for (const e of calls.slice(-30)) await fetchBody(e);
  return { events: teach.events, network: calls.map(summary) };
}

// ---------------------------------------------------------------- command dispatch
let lastCapture = 0;

async function status() {
  let tab = null;
  let focused = false;
  try {
    const w = await chrome.windows.getLastFocused();
    focused = !!w.focused;
    const t = await activeTab();
    tab = { id: t.id, url: t.url, title: t.title, status: t.status };
  } catch (e) { /* no window */ }
  return { connected, version: VERSION, focused, tab, debugger: net.attached, teaching: teach.on };
}

async function run(type, d) {
  switch (type) {
    case 'status': return status();
    case 'tabs': return (await chrome.tabs.query({})).map((t) => ({ id: t.id, url: t.url, title: t.title, active: t.active, windowId: t.windowId }));
    case 'navigate': {
      const tab = d.new_tab ? await chrome.tabs.create({ url: d.url }) : await chrome.tabs.update((await activeTab(d.tabId)).id, { url: d.url });
      if (d.focus) await chrome.windows.update(tab.windowId, { focused: true });
      const done = await waitForLoad(tab.id, d.timeout_ms || 20000);
      return { id: tab.id, url: done && done.url, title: done && done.title, status: done && done.status };
    }
    case 'wait_load': {
      const tab = await activeTab(d.tabId);
      const done = await waitForLoad(tab.id, d.timeout_ms || 10000);
      return { url: done && done.url, status: done && done.status };
    }
    case 'page': return page(d.cmd, d.params || {}, d.tabId, d.timeout_ms || 8000);
    case 'screenshot': {
      // Chrome allows about two captures per second.
      const wait = lastCapture + 600 - Date.now();
      if (wait > 0) await new Promise((r) => setTimeout(r, wait));
      lastCapture = Date.now();
      const tab = await activeTab(d.tabId);
      return { data_url: await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' }) };
    }
    case 'eval': return evaluate(d.code, d.tabId);
    case 'net_start': {
      const tab = await activeTab(d.tabId);
      await attach(tab.id);
      return { seq: net.seq, tabId: tab.id };
    }
    case 'focus': {
      const tab = await activeTab(d.tabId);
      await chrome.windows.update(tab.windowId, { focused: true });
      return { focused: true, windowId: tab.windowId };
    }
    case 'net_mark': return { seq: net.seq, attached: net.attached };
    case 'net_query': return netQuery(d);
    case 'net_stop': if (!teach.on) await detach(); return { attached: net.attached };
    case 'teach_start': return teachStart();
    case 'teach_stop': return teachStop();
    default: throw new Error(`unknown command ${type}`);
  }
}

async function handleCommand(msg) {
  try {
    send({ id: msg.id, ok: true, result: await run(msg.type, msg.data || {}) });
  } catch (e) {
    send({ id: msg.id, ok: false, error: String((e && e.message) || e) });
  }
}

// ---------------------------------------------------------------- toolbar popup
async function popup(msg) {
  if (msg.op === 'status') return status();
  if (msg.op === 'overlay') {
    const params = { layer: msg.layer, mode: msg.mode, show: msg.show };
    return page(msg.show ? 'show' : 'hide', params);
  }
  throw new Error(`unknown popup op ${msg.op}`);
}
