// Toolbar popup: connection state and overlay toggles for the active tab.
const err = document.getElementById('err');

function ask(msg) {
  return chrome.runtime.sendMessage({ __agent: 'popup', ...msg }).then((r) => {
    if (r && r.error) throw new Error(r.error);
    return r;
  });
}

ask({ op: 'status' }).then((s) => {
  document.getElementById('dot').classList.toggle('on', s.connected);
  document.getElementById('state').textContent = s.connected ? 'Connected to the engine' : 'Engine not running';
  document.getElementById('tab').textContent = s.tab ? s.tab.title || s.tab.url : '';
}).catch((e) => { err.textContent = e.message; });

document.querySelectorAll('button[data-layer]').forEach((b) => {
  b.addEventListener('click', async () => {
    const show = !b.classList.contains('on');
    err.textContent = '';
    try {
      const r = await ask({ op: 'overlay', layer: b.dataset.layer, mode: b.dataset.mode || 'interactive', show });
      // The interactive layer has two modes but one set of boxes: showing one mode replaces the other.
      if (b.dataset.layer === 'interactive') document.querySelectorAll('button[data-layer="interactive"]').forEach((o) => {
        o.classList.remove('on');
        o.textContent = 'Show';
      });
      b.classList.toggle('on', show);
      b.textContent = show ? `Hide (${(r.elements || []).length})` : 'Show';
    } catch (e) {
      err.textContent = e.message;
    }
  });
});
