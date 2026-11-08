"""Turn raw scan results into findings and a human-readable report."""
from collections import defaultdict

from . import terms


def summarize_condition(cond):
    c = cond if isinstance(cond, dict) else cond.__dict__
    hits = [h if isinstance(h, dict) else h.__dict__ for h in c["hits"]]
    by_cat = defaultdict(set)
    loaded = defaultdict(set)
    events = defaultdict(set)
    ids = defaultdict(set)
    url_sent = defaultdict(set)
    health_url = defaultdict(set)
    condition_url = defaultdict(set)
    intent_url = defaultdict(set)
    health_custom = defaultdict(set)
    consent_mode = set()
    for h in hits:
        v, cat = h["vendor"], h["category"]
        loaded[cat].add(v)
        if not h["is_hit"]:
            continue
        by_cat[cat].add(v)
        events[v].update(h["events"])
        ids[v].update(h["account_ids"])
        if h["consent_mode"]:
            consent_mode.add(h["consent_mode"].strip())
        if h["sent_urls"] or h["sent_titles"]:
            url_sent[v].update(h["sent_urls"][:3])
        # A server-side relay on the site's own (sub)domain is not a third party
        # receiving the data; it is reported separately (cdp / server_side).
        if h.get("first_party_relay"):
            continue
        if h["health_terms"]:
            health_url[v].update(h["sent_urls"][:3] or h["sent_titles"][:2])
        if h["condition_terms"]:
            condition_url[v].update(h.get("evidence") or h["sent_urls"][:3] or h["sent_titles"][:2])
        if h["intent_terms"]:
            intent_url[v].update(h["sent_urls"][:3])
        for cp in h["custom_params"]:
            if terms.health_terms(cp.split("=", 1)[-1]):
                health_custom[v].add(cp)
    ok_pages = [p if isinstance(p, dict) else p.__dict__ for p in c["pages"]]
    cloaked = sorted({f"{h['vendor']}: {h['served_via']}" for h in hits if h.get("served_via")})
    return {
        "condition": c["condition"],
        "pages": [{"role": p["role"], "url": p["final_url"] or p["url"], "status": p["status"],
                   "error": p["error"], "title": p["title"]} for p in ok_pages],
        "pages_ok": sum(1 for p in ok_pages if p["status"] and p["status"] < 400),
        "cmp": c["cmp"],
        "banner_detected": c["banner_detected"],
        "banner_how": c.get("banner_how", ""),
        "autoconsent_cmp": c.get("autoconsent_cmp", ""),
        "action": c.get("action", ""),
        "action_result": c.get("action_result", ""),
        "cname_findings": cloaked,
        "banner_note": banner_note(c),
        "screenshot": c.get("screenshot", ""),
        "accept_clicked": c["accept_clicked"],
        "server_side": c["server_side"],
        "ads": sorted(by_cat["ads"]),
        "ads_loaded": sorted(loaded["ads"]),
        "analytics": sorted(by_cat["analytics"]),
        "replay": sorted(by_cat["replay"]),
        "calltrack": sorted(by_cat["calltrack"]),
        "chat": sorted(by_cat["chat"]),
        "cdp": sorted(by_cat["cdp"]),
        "tagmgr": sorted(loaded["tagmgr"]),
        "events": {k: sorted(v) for k, v in events.items() if v},
        "ads_condition": sorted(set(condition_url) & by_cat["ads"]),
        "ads_url": sorted(set(url_sent) & by_cat["ads"]),
        "account_ids": {k: sorted(v) for k, v in ids.items() if v},
        "url_sent": {k: sorted(v) for k, v in url_sent.items()},
        "health_url": {k: sorted(v) for k, v in health_url.items()},
        "condition_url": {k: sorted(v) for k, v in condition_url.items()},
        "intent_url": {k: sorted(v) for k, v in intent_url.items()},
        "health_custom": {k: sorted(v)[:10] for k, v in health_custom.items()},
        "consent_mode": sorted(consent_mode)[:5],
    }


NOT_SHOWN = ("Consent tool loaded, but no banner was shown to our browser "
             "(this may depend on the visitor's region or on timing).")


def banner_note(c):
    if c["cmp"] and not c["banner_detected"]:
        return NOT_SHOWN
    return ""


BLOCK_TITLES = ("just a moment", "attention required", "access denied", "checking your browser",
                "verify you are human", "are you a robot", "403 forbidden", "request blocked")


def inconclusive_reasons(conds):
    """Loading problems that make a clean result untrustworthy (bot checks, errors)."""
    out = []
    a = next((c for c in conds if c["condition"] == "no_interaction"), None)
    if not a:
        return ["The site could not be loaded."]
    bad = [p for p in a["pages"] if not p["status"] or p["status"] in (403, 429, 503) or p["status"] >= 500]
    if any(any(t in (p["title"] or "").lower() for t in BLOCK_TITLES) for p in a["pages"]):
        out.append("The site showed a bot-check page to our browser.")
    if bad:
        codes = ", ".join(sorted({str(p["status"] or p["error"][:30]) for p in bad}))
        out.append(f"Some pages could not be loaded normally ({codes}).")
    if a["pages_ok"] < max(1, len(a["pages"]) // 2 + (1 if len(a["pages"]) > 1 else 0)):
        out.append("Fewer than half of the planned pages loaded.")
    return out


def caveats(conds):
    """Facts that qualify the result but do not make it unreliable."""
    out = []
    a = next((c for c in conds if c["condition"] == "no_interaction"), None)
    if a and a["cmp"] and not a["banner_detected"]:
        out.append(NOT_SHOWN)
    for c in conds:
        if c["condition"] == "rejected" and c["action_result"] == "no reject option found":
            out.append("The cookie banner offers no reject option that our browser could find.")
        elif c["condition"] in ("accepted", "rejected") and (
                c["action_result"] == "failed" or (c["accept_clicked"] or "").startswith("click failed")):
            out.append(f"The '{c['action']}' click on the cookie banner did not complete.")
    return out


def summarize(site):
    s = site if isinstance(site, dict) else site.__dict__
    conds = [summarize_condition(c) for c in s["conditions"]]
    return {"site": s["site_domain"], "input_url": s["input_url"], "started": s["started"],
            "error": s["error"], "duration_s": s["duration_s"],
            "inconclusive_reasons": inconclusive_reasons(conds),
            "caveats": caveats(conds),
            "conditions": conds}


AD_LABEL = "advertising platforms"


def text_report(summary):
    out = []
    w = out.append
    w(f"HealthPixel Audit — {summary['site']}   ({summary['started']})")
    w("=" * 72)
    if summary["error"] and not summary["conditions"]:
        w(f"Could not scan: {summary['error']}")
        return "\n".join(out)
    for c in summary["conditions"]:
        label = {
            "no_interaction": "BEFORE any consent interaction (visitor only moved the mouse and scrolled)",
            "accepted": f"AFTER accepting cookies ('{c['accept_clicked']}')",
            "rejected": f"AFTER rejecting cookies ('{c['accept_clicked'] or 'reject'}': {c['action_result']})",
            "gpc": "With the Global Privacy Control signal on (Sec-GPC: 1), no clicks",
            "inner_landing": "ENTERING directly on a service page (fresh browser, as from an ad or search), no clicks",
        }.get(c["condition"], c["condition"])
        w("")
        w(f"## {label}")
        for p in c["pages"]:
            st = p["status"] or p["error"]
            w(f"   page [{p['role']}] {p['url']}  ({st})")
        w(f"   Consent tool detected: {', '.join(c['cmp']) or 'none'}; banner visible: "
          f"{'yes (' + c['banner_how'] + ')' if c['banner_detected'] else 'no'}")
        if c["banner_note"]:
            w(f"   Note: {c['banner_note']}")
        if c["ads"]:
            w(f"[!] Data sent to {AD_LABEL}: {', '.join(c['ads'])}")
        else:
            w(f"[ok] No data sent to {AD_LABEL}.")
        for v, urls in c["condition_url"].items():
            w(f"[!!] {v} received URLs/titles naming a condition, substance or medication:")
            for u in urls[:3]:
                w(f"       {u}")
        for v, urls in c["health_url"].items():
            if v in c["condition_url"]:
                continue
            w(f"[!] {v} received care-related page URLs/titles:")
            for u in urls[:3]:
                w(f"       {u}")
        for v, cps in c["health_custom"].items():
            w(f"[!!] {v} received custom parameters with health terms: {'; '.join(cps[:4])}")
        if c["events"]:
            w("   Events observed: " + "; ".join(f"{k}: {', '.join(v[:6])}" for k, v in c["events"].items()))
        if c["replay"]:
            w(f"[!] Session-replay / heatmap tools active: {', '.join(c['replay'])} "
              "(can record page content and form typing)")
        if c["calltrack"]:
            w(f"   Call tracking: {', '.join(c['calltrack'])}")
        if c.get("chat"):
            w(f"   Chat widgets: {', '.join(c['chat'])}")
        if c["analytics"]:
            w(f"   Analytics: {', '.join(c['analytics'])}")
        for f in c["cname_findings"]:
            w(f"   Served from a first-party subdomain (CNAME): {f}")
        if c["condition"] == "rejected" and c["ads"]:
            w(f"[!!] Advertising platforms still receive data after the visitor REJECTED cookies: {', '.join(c['ads'])}")
        if c["condition"] == "gpc" and c["ads"]:
            w(f"[!] Advertising platforms receive data although the browser sent Global Privacy Control: {', '.join(c['ads'])}")
        if c["cdp"] or c["server_side"]:
            w(f"   Server-side / privacy relay signals: {', '.join(c['cdp'] + c['server_side'])}")
        if c["consent_mode"]:
            w(f"   Google Consent Mode signals: {', '.join(c['consent_mode'])}")
    if summary.get("inconclusive_reasons"):
        w("")
        w("Result may be INCONCLUSIVE because:")
        for r in summary["inconclusive_reasons"]:
            w(f"   - {r}")
    for r in summary.get("caveats", []):
        w(f"   Note: {r}")
    w("")
    w("What this means")
    w("-" * 72)
    first = summary["conditions"][0] if summary["conditions"] else None
    ads_cond = first and (first["ads_condition"] or set(first["health_custom"]) & set(first["ads"]))
    other_cond = first and first["condition_url"]
    if ads_cond:
        w("Advertising platforms receive, together with the visitor's browser identifiers and")
        w("cookies, the address or title of pages about specific conditions or treatments.")
        w("For a health-care provider this can reveal that a person is seeking care for a")
        w("specific condition. Review HHS OCR guidance on online tracking technologies and the")
        w("FTC Health Breach Notification Rule with counsel; consider removing ad pixels from")
        w("care pages, stripping URL paths/titles server-side, and gating tags on consent.")
    elif other_cond:
        w("No condition-specific data reached advertising platforms, but other third parties")
        w("(analytics, call tracking, session replay) received page addresses or titles that name")
        w("conditions or treatments. Check each vendor's contract (BAA) and data-use terms.")
    elif first and first["ads"]:
        w("Advertising platforms are contacted on page load. Even without condition names in the")
        w("URL, a visit to a treatment provider's site can itself be sensitive. Consider consent")
        w("gating and a server-side relay that removes identifiers before data leaves your site.")
    else:
        w("No advertising-platform transmissions were observed before any consent choice.")
        after = summary["conditions"][1] if len(summary["conditions"]) > 1 else None
        if after and after["ads"]:
            w(f"After accepting cookies, {', '.join(after['ads'])} receive data"
              + (" including page addresses or titles that name conditions or treatments."
                 if after["ads_condition"] else "."))
            w("Consent is not a HIPAA authorization; check with counsel whether care-page data")
            w("should reach advertising platforms even after a visitor accepts cookies.")
    w("")
    w("Limitations: automated scan of a few public pages; no forms submitted, no logged-in areas;")
    w("server-to-server transfers (e.g. Conversions API) are invisible to a browser. Not legal advice.")
    return "\n".join(out)
