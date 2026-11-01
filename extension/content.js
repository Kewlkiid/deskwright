// Content script (ISOLATED world): relays commands between the background worker and the MAIN-world page module
// (overlay.js), and forwards teach-mode events. MAIN-world globals aren't reachable from here, so commands go out
// as a window CustomEvent and come back matched by commandId.
(function () {
  'use strict';
  if (window.__agentContentLoaded) return;
  window.__agentContentLoaded = true;

  let ready = false;
  const waiting = [];
  window.addEventListener('__agent_ready', () => {
    ready = true;
    waiting.splice(0).forEach((cb) => cb());
  });

  function whenReady(timeout) {
    // The page module may load after us (document_end) or already be there (re-injection): ask it to say hello.
    if (ready) return Promise.resolve();
    return new Promise((resolve) => {
      const timer = setTimeout(resolve, timeout); // try anyway; the command times out if nobody answers
      waiting.push(() => { clearTimeout(timer); resolve(); });
      window.dispatchEvent(new CustomEvent('__agent_hello'));
    });
  }

  let nextId = 0;
  function callPage(cmd, params, timeout = 8000) {
    return whenReady(2000).then(() => new Promise((resolve) => {
      const commandId = `${Date.now()}-${++nextId}`;
      const timer = setTimeout(() => {
        window.removeEventListener('__agent_response', onResponse);
        resolve({ error: 'timeout: the page module did not answer' });
      }, timeout);
      function onResponse(event) {
        const d = event.detail;
        if (!d || d.__agent !== 'response' || d.commandId !== commandId) return;
        clearTimeout(timer);
        window.removeEventListener('__agent_response', onResponse);
        resolve(d.error ? { error: d.error } : { result: d.result });
      }
      window.addEventListener('__agent_response', onResponse);
      window.dispatchEvent(new CustomEvent('__agent_command', { detail: { __agent: 'command', commandId, cmd, params: params || {} } }));
    }));
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.__agent !== 'page') return false;
    callPage(msg.cmd, msg.params, msg.timeout).then(sendResponse);
    return true; // async response
  });

  window.addEventListener('__agent_teach_event', (event) => {
    chrome.runtime.sendMessage({ __agent: 'teach_event', event: event.detail }).catch(() => {});
  });
})();
