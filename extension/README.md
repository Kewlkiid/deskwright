# Agent Browser Bridge (Chrome extension)

Lets the desktop agent work inside your own Chrome through the page itself instead of screenshots: numbered
element overlays, DOM clicks and typing, reading tables and text, running JS, and watching network responses.

## Load and connect

1. Start the agent app (or `python -m engine.cli ...`). On start the engine writes `config.js` here with its
   local address (`ws://127.0.0.1:8777`) and a pairing token kept in `engine/data/browser_token`.
2. In Chrome open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick this
   `extension/` folder.
3. Click the extension's toolbar icon: it shows **Connected to the engine** with a green dot. If it says
   *Engine not running*, start the app; if you loaded the extension before the engine first ran, press the
   reload button on its card in `chrome://extensions` so it picks up the token.

When Chrome is the app in front, SDK actions (`click`, `type_into`, `read_text`, `read_table`, `check`/`expect`,
`scroll_until`) use the page first and fall back to screenshots only when a target isn't in the element map.

Network capture and `page_js` use `chrome.debugger`, so Chrome shows "Agent Browser Bridge started debugging
this browser" while a run that needs them is going; the engine detaches when the run ends.

## Files

| File | What it does |
|---|---|
| `manifest.json` | MV3 manifest. Permissions: `tabs`, `scripting` (inject into tabs opened before install), `debugger` (network + JS), `alarms` (reconnect after the worker sleeps) |
| `config.js` | Written by the engine: engine URL and pairing token |
| `background.js` | Service worker: WebSocket to the engine, command dispatch, CDP network capture and evaluation, teach recording state |
| `content.js` | ISOLATED world: relays commands to the page module and teach events to the worker |
| `overlay.js` | MAIN world page module: the three overlay layers, element maps, DOM actions, tables, teach event capture |
| `popup.html/js` | Toolbar popup: connection state and overlay toggles |

## Message path

```
engine (engine/browser/bridge.py) ──WS {id,type,data}──► background.js ──tabs.sendMessage──► content.js
     ▲                                     │                                                    │ CustomEvent
     └──────────── {id,ok,result} ◄────────┘◄───────────────────────────────────── '__agent_command' / '__agent_response'
                                                                                   (overlay.js, matched by commandId)
```

The engine only accepts `chrome-extension://` origins carrying the pairing token, so web pages can't connect to
it even though it listens on localhost.

## Overlay API (MAIN world)

| Global | Marks | Methods |
|---|---|---|
| `window.__agentOverlay` | interactive elements (mode `interactive`), or page sections (mode `regions`) | `show(mode)`, `hide()`, `toggle()`, `getMap()`, `getRegions()`, `getElement(index)`, `findElement(text)`, `refresh()` |
| `window.__agentStaticOverlay` | static text (modal-aware) | `show()`, `hide()`, `toggle()`, `getMap()`, `getElement(index)`, `refresh()` |
| `window.__agentScrollableOverlay` | scrollable containers | `show()`, `hide()`, `toggle()`, `getMap()`, `getElement(index)` |

Colours: blue buttons, green inputs, purple selects, orange links, pink other clickables, amber static text (`S`
labels), teal scrollable areas, indigo regions (`R` labels). Map entries: `{ index, tag, type, id, classes,
selector, category, rect: {x, y, width, height, centerX, centerY}, text, accessible_name, label, description,
attributes }`.

## Testing it

`python -m engine.tools.browser_check --chrome "<Chrome for Testing or Chromium binary>"` runs the whole check in a
throwaway Chrome with its own copy of this folder (branded Chrome 137+ no longer loads extensions from the command
line, so it needs Chrome for Testing or Chromium). `python -m engine.tools.demo_server` serves the demo invoice
page with a small JSON API on http://127.0.0.1:5050 for trying it by hand.
