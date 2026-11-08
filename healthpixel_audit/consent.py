"""Consent-banner automation via DuckDuckGo autoconsent (MPL-2.0, bundled unmodified).

Two init scripts are added to every frame before page scripts run:
  1. a small bridge (ours) that holds the rules and answers autoconsent's
     messages inside the page: it replies to "init" with our configuration and
     to "eval" requests by evaluating the rule snippet; every message is kept
     in window.__hpaAC so Python can read it;
  2. autoconsent.playwright.js exactly as published.

Configuration: no automatic action (detect only), no pre-hiding and no
cosmetic hiding, so the banner stays visible for screenshots and for our own
DOM detection. Python asks for "optIn" / "optOut" explicitly when a run needs it.
"""
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent / "thirdparty" / "autoconsent"
_SCRIPT = None

CONFIG = {
    "enabled": True, "autoAction": None, "disabledCmps": [], "enablePrehide": False,
    "enableCosmeticRules": False, "enableGeneratedRules": True, "detectRetries": 20,
    "isMainWorld": True, "prehideTimeout": 2000, "enableHeuristicDetection": True,
    "enablePopupMutationObserver": False, "visualTest": False,
    "logs": {"lifecycle": False, "rulesteps": False, "detectionsteps": False, "evals": False,
             "errors": False, "messages": False, "waits": False},
    "performanceLoggingEnabled": False, "heuristicPopupSearchTimeout": 5000, "heuristicMode": "tier2",
}

BRIDGE = """(() => {
  if (window.__hpaAC) return;
  const msgs = window.__hpaAC = [];
  const rules = %s, config = %s;
  window.autoconsentSendMessage = async (m) => {
    try { msgs.push(JSON.parse(JSON.stringify(m))); } catch (e) { msgs.push({type: m && m.type}); }
    if (m.type === 'init') {
      setTimeout(() => window.autoconsentReceiveMessage({type: 'initResp', config, rules: {autoconsent: rules}}), 0);
    } else if (m.type === 'eval') {
      let result = false;
      try { result = !!(0, eval)(m.code); } catch (e) { result = false; }
      setTimeout(() => window.autoconsentReceiveMessage({id: m.id, type: 'evalResp', result}), 0);
    }
  };
})();"""

GPC_SCRIPT = """Object.defineProperty(Navigator.prototype, 'globalPrivacyControl',
  {get: () => true, configurable: true});"""


def init_scripts():
    """Return the two init scripts (bridge + autoconsent)."""
    global _SCRIPT
    if _SCRIPT is None:
        rules = json.loads((HERE / "rules.json").read_text())["autoconsent"]
        bridge = BRIDGE % (json.dumps(rules, separators=(",", ":")), json.dumps(CONFIG))
        _SCRIPT = (bridge, (HERE / "autoconsent.playwright.js").read_text())
    return _SCRIPT


def install(context):
    for s in init_scripts():
        context.add_init_script(script=s)


def messages(page):
    """All autoconsent messages from the main frame and iframes."""
    out = []
    for fr in [page.main_frame] + [f for f in page.frames if f != page.main_frame][:10]:
        try:
            out += fr.evaluate("() => (window.__hpaAC || []).slice()") or []
        except Exception:
            continue
    return out


def detected(page):
    """Return (cmp_name or '', popup_visible) from autoconsent's own detection."""
    cmp, popup = "", False
    for m in messages(page):
        if m.get("type") == "cmpDetected" and not cmp:
            cmp = m.get("cmp") or ""
        if m.get("type") == "popupFound":
            popup = True
            cmp = m.get("cmp") or cmp
    return cmp, popup


def act(page, action, timeout=12):
    """Ask autoconsent to opt in/out in every frame where a popup was found.

    action: "optIn" or "optOut". Returns True / False / None (None = no popup).
    """
    frames = []
    for fr in [page.main_frame] + [f for f in page.frames if f != page.main_frame][:10]:
        try:
            if fr.evaluate("() => (window.__hpaAC || []).some(m => m.type === 'popupFound')"):
                frames.append(fr)
        except Exception:
            continue
    if not frames:
        return None
    want = "optInResult" if action == "optIn" else "optOutResult"
    for fr in frames:
        try:
            fr.evaluate(f"() => window.autoconsentReceiveMessage({{type: '{action}'}})")
        except Exception:
            pass
    t0 = time.time()
    while time.time() - t0 < timeout:
        for fr in frames:
            try:
                res = fr.evaluate(f"() => (window.__hpaAC || []).filter(m => m.type === '{want}').map(m => m.result)")
            except Exception:
                res = []
            if res:
                return bool(res[-1])
        page.wait_for_timeout(500)
    return False
