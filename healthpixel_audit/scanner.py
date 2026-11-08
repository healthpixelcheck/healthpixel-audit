"""Headless-browser scan of a website's third-party tracking.

The scanner never fills or submits forms and never enters personal data.
Condition "no_interaction": pages are loaded in a fresh browser profile and the
user does nothing (no click on any consent banner).
Condition "accepted": a fresh profile loads the home page, clicks the banner's
"accept" button (only if one is found), then visits the same pages.
"""
import json
import re
import time
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, parse_qsl, urljoin, unquote

import tldextract
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from . import cname, consent, terms, vendors

DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 "
              "HealthPixelAudit/0.1 (+https://github.com/healthpixelcheck/healthpixel-audit)")

ACCEPT_TEXT = re.compile(
    r"^\s*(accept( all)?( cookies)?|allow( all)?( cookies)?|i accept|i agree|agree( and close)?|"
    r"got it!?|ok(ay)?|understood|accept & close|accept and close|allow & continue|"
    r"agree & proceed|yes,? i agree|continue)\s*[.!]?\s*$", re.I)
ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler", "#accept-recommended-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLetsGo", "#CybotCookiebotDialogBodyButtonAccept",
    "#CybotCookiebotDialogBodyLevelButtonAccept",
    ".cky-btn-accept", "#cookie_action_close_header", ".cmplz-accept",
    "#cn-accept-cookie", "#moove_gdpr_cookie_modal .mgbutton", ".osano-cm-accept-all",
    "[data-tid='banner-accept']", "#truste-consent-button", ".iubenda-cs-accept-btn",
    "#didomi-notice-agree-button", "button[aria-label*='ccept']",
]
BANNER_TEXT = re.compile(r"cookie|consent|tracking technolog|your privacy|privacy (choices|preferences|settings)|"
                         r"privacy (policy|notice).{0,60}(consent|agree)|we use .{0,40}technolog", re.I)
DECLINE_TEXT = re.compile(r"^\s*(reject( all)?|decline( all)?|deny( all)?|(only )?necessary( only| cookies)?|"
                          r"essential only|manage( preferences| cookies| settings)?|(cookie )?settings|preferences|"
                          r"customi[sz]e|opt[ -]?out|do not sell.*|show preferences)\s*$", re.I)
# Runs in each frame. Walks the DOM including open shadow roots.
BANNER_JS = """([accSrc, decSrc, banSrc, inFrame]) => {
  const A = new RegExp(accSrc, 'i'), D = new RegExp(decSrc, 'i'), B = new RegExp(banSrc, 'i');
  const vw = innerWidth, vh = innerHeight;
  const all = [];
  const walk = (root) => { for (const e of root.querySelectorAll('*')) { all.push(e); if (e.shadowRoot) walk(e.shadowRoot); } };
  walk(document);
  const visible = (e) => { const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return null;
    const st = getComputedStyle(e); if (st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) return null;
    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) return null; return r; };
  const text = (e) => ((e.innerText || e.textContent || '') + '').replace(/\\s+/g, ' ').trim();
  const buttonsIn = (c) => { const out = []; const w = (root) => { for (const e of root.querySelectorAll('button, [role=button], a, input[type=button], input[type=submit]')) out.push(e);
      for (const e of root.querySelectorAll('*')) if (e.shadowRoot) w(e.shadowRoot); }; w(c); return out; };
  const containers = [];
  for (const e of all) {
    const st = getComputedStyle(e);
    const z = parseInt(st.zIndex) || 0;
    if (!(st.position === 'fixed' || st.position === 'sticky' || (st.position === 'absolute' && z >= 1000) || e.tagName === 'DIALOG' || inFrame)) continue;
    const r = visible(e); if (!r) continue;
    const edge = r.top <= 40 || r.bottom >= vh - 40;
    const modal = (r.width * r.height) >= 0.2 * vw * vh;
    if (!(edge || modal || inFrame)) continue;
    const t = text(e); if (!t || t.length > 3000 || !B.test(t)) continue;
    containers.push([e, edge ? 'fixed overlay at screen edge' : (modal ? 'modal dialog' : 'frame')]);
  }
  for (const [c, how] of containers) {
    let acc = null, dec = false;
    for (const b of buttonsIn(c)) {
      const t = ((b.innerText || b.value || b.textContent || '') + '').trim();
      if (!t || t.length > 40 || !visible(b)) continue;
      if (!acc && A.test(t)) acc = b; else if (!dec && D.test(t) && /reject|decline|deny|necessary|essential|opt/i.test(t)) dec = b;
      else if (!dec && D.test(t)) dec = dec || null;
    }
    if (acc || dec) {
      if (acc) acc.setAttribute('data-hpa-accept', '1');
      if (dec) dec.setAttribute('data-hpa-decline', '1');
      return {banner: true, accept: !!acc, decline: !!dec, how};
    }
    // banner with only "manage/settings" buttons still counts as a banner
    for (const b of buttonsIn(c)) { const t = ((b.innerText || b.value || '') + '').trim(); if (t && t.length < 40 && D.test(t) && visible(b)) return {banner: true, accept: false, how}; }
  }
  // Fallback: an accept-type button anywhere whose surroundings mention cookies/consent.
  for (const e of all) {
    if (!e.matches('button, [role=button], a, input[type=button]')) continue;
    const t = ((e.innerText || e.value || '') + '').trim();
    if (!t || t.length > 40 || !A.test(t) || !visible(e)) continue;
    let p = e; for (let k = 0; k < 6 && p.parentElement; k++) p = p.parentElement;
    if (B.test(text(p).slice(0, 1500))) { e.setAttribute('data-hpa-accept', '1'); return {banner: true, accept: true, how: 'accept button near consent text'}; }
  }
  return {banner: false};
}"""

URL_KEYS = {"dl", "url", "u", "p", "page", "page_url", "pageurl", "href", "location",
            "loc", "su", "fst", "frm", "context.page.url", "context.page.referrer",
            "page_location", "ref", "rl", "r", "referrer", "dr", "tm", "landing_url"}
TITLE_KEYS = {"dt", "tl", "title", "page_title", "pt", "context.page.title", "ti_title"}
EVENT_KEYS = {"ev", "en", "event", "evt", "ea", "event_name", "eventname", "type",
              "event_type", "label"}


def reg_domain(host):
    return tldextract.extract(host or "").top_domain_under_public_suffix or (host or "")


def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten(v, prefix)
    else:
        yield prefix, "" if obj is None else str(obj)


def request_params(url, post):
    """Return list of (key, value) from the query string and the POST body."""
    pairs = parse_qsl(urlparse(url).query, keep_blank_values=True)
    if post:
        text = post if isinstance(post, str) else post.decode("utf-8", "replace")
        text = text.strip()
        parsed = False
        if text[:1] in "{[":
            try:
                pairs += list(_flatten(json.loads(text)))
                parsed = True
            except Exception:
                pass
        if not parsed:
            # Newline-delimited payloads (GA4 batches) or form-encoded bodies.
            for line in text.splitlines():
                if "=" in line and len(line) < 20000:
                    pairs += parse_qsl(line, keep_blank_values=True)
    return [(k, v) for k, v in pairs]


@dataclass
class Hit:
    page: str
    vendor: str
    category: str
    is_hit: bool
    host: str
    path: str
    method: str
    events: list = field(default_factory=list)
    sent_urls: list = field(default_factory=list)
    sent_titles: list = field(default_factory=list)
    custom_params: list = field(default_factory=list)
    health_terms: list = field(default_factory=list)
    condition_terms: list = field(default_factory=list)
    intent_terms: list = field(default_factory=list)
    consent_mode: str = ""
    account_ids: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    cmp_name: str = ""
    first_party_relay: bool = False
    served_via: str = ""


def _is_home(page_url):
    try:
        return urlparse(page_url).path in ("", "/")
    except ValueError:
        return False


def analyze_request(page_url, site_reg, url, method, post, known_hosts=None, override=None):
    """Classify one request. `override` = (vendor, category, is_hit, relay, served_via)
    forces the vendor (used after CNAME resolution)."""
    pu = urlparse(url)
    host = pu.hostname or ""
    path = pu.path or "/"
    cls = vendors.classify(host, path)
    first_party = reg_domain(host) == site_reg
    server_side = None
    cmp_name = ""
    relay = False
    served_via = ""
    if override:
        cls = override[:3]
        relay, served_via = override[3], override[4]
    if not cls:
        fp = vendors.classify_first_party(host, path, pu.query, known_hosts)
        if fp:
            cls = fp[:3]
            cmp_name = fp[3] or ""
            # Only an endpoint on the site's own domain is a first-party relay;
            # the same signature on a vendor's host is an ordinary third party.
            relay = first_party
    if not cls:
        # Server-side tagging on a first-party (sub)domain.
        if first_party and (re.search(r"/g/collect|/gtm\.js|/gtag/js|/j/collect", url)):
            server_side = "server-side GTM (first-party endpoint)"
        return None, server_side
    vendor, cat, is_hit = cls
    params = request_params(url, post)
    h = Hit(page=page_url, vendor=vendor, category=cat, is_hit=is_hit, host=host,
            path=path[:120], method=method, cmp_name=cmp_name,
            first_party_relay=relay, served_via=served_via)
    blob = []
    for k, v in params:
        kl = k.lower()
        v = v[:2000]
        if kl in EVENT_KEYS and v and len(v) < 80:
            h.events.append(v)
        if kl in TITLE_KEYS and v:
            h.sent_titles.append(v[:200])
            # Only the page part of the title counts, never the brand name, and
            # never the home page title (it describes the whole organization).
            page_part = "" if _is_home(page_url) else terms.title_page_part(v, site_reg)
            blob.append(page_part)
            if terms.condition_terms(page_part):
                h.evidence.append(f"title: {v[:150]}")
        if kl.startswith(("cd[", "cd.", "ep.", "epn.", "up.", "custom_data", "properties.", "data.")):
            h.custom_params.append(f"{k}={v[:120]}")
            blob.append(v)
        if kl in ("id", "tid", "pixel_code", "pid", "ti", "sdkid", "label") and v and len(v) < 40:
            h.account_ids.append(f"{k}={v}")
        if kl in ("gcs", "gcd"):
            h.consent_mode += f"{k}={v} "
        if v.startswith(("http://", "https://")) or kl in URL_KEYS:
            try:
                vu = urlparse(unquote(v))
            except ValueError:
                continue
            if vu.hostname and reg_domain(vu.hostname) == site_reg:
                h.sent_urls.append(v[:300])
                pq = (vu.path or "") + " " + (vu.query or "")
                blob.append(pq)
                if terms.condition_terms(pq):
                    h.evidence.append(f"url: {unquote(v)[:200]}")
    text = " ".join(blob)
    h.health_terms = terms.health_terms(text)
    h.condition_terms = terms.condition_terms(text)
    h.intent_terms = terms.intent_terms(text)
    h.events = sorted(set(h.events))[:20]
    h.sent_urls = sorted(set(h.sent_urls))[:10]
    h.sent_titles = sorted(set(h.sent_titles))[:5]
    h.custom_params = sorted(set(h.custom_params))[:30]
    h.account_ids = sorted(set(h.account_ids))[:10]
    h.evidence = sorted(set(h.evidence))[:6]
    return h, server_side


@dataclass
class PageResult:
    url: str
    final_url: str = ""
    status: int = 0
    title: str = ""
    error: str = ""
    role: str = ""


@dataclass
class ConditionResult:
    condition: str
    pages: list = field(default_factory=list)
    hits: list = field(default_factory=list)
    cmp: list = field(default_factory=list)
    server_side: list = field(default_factory=list)
    banner_detected: bool = False
    accept_clicked: str = ""
    banner_how: str = ""
    autoconsent_cmp: str = ""   # CMP name per DuckDuckGo autoconsent rules
    action: str = ""            # what this run did: accept / reject / gpc
    action_result: str = ""
    cnames: dict = field(default_factory=dict)   # first-party host -> CNAME chain
    fp_requests: list = field(default_factory=list)
    screenshot: str = ""        # base64 JPEG of the first screen (only when enabled)
    requests_total: int = 0
    raw_requests: list = field(default_factory=list)


@dataclass
class SiteResult:
    input_url: str
    site_domain: str = ""
    started: str = ""
    duration_s: float = 0
    conditions: list = field(default_factory=list)
    error: str = ""


class Scanner:
    def __init__(self, user_agent=DEFAULT_UA, headless=True, settle=6.0, timeout=45,
                 inner_pages=2, keep_raw=True, log=print, request_guard=None,
                 launch_kwargs=None, screenshots=False, reject_run=True,
                 gpc_run=True, use_autoconsent=True, inner_landing_run=False):
        self.ua = user_agent
        self.headless = headless
        self.settle = settle
        self.timeout = timeout * 1000
        self.inner_pages = inner_pages
        self.keep_raw = keep_raw
        self.log = log
        # Optional callable(url) -> bool. Requests for which it returns False are
        # aborted before they leave the browser (used by the web service against SSRF).
        self.request_guard = request_guard
        self.screenshots = screenshots
        self.reject_run = reject_run
        self.gpc_run = gpc_run
        self.use_autoconsent = use_autoconsent
        # Extra fresh-profile visit that enters the site directly on a service page
        # (like a visitor from an ad or search). Session-level tools such as call
        # tracking record only the entry page, so a home-first crawl misses it.
        self.inner_landing_run = inner_landing_run
        self.blocked = []
        # Extra arguments for chromium.launch(), e.g. an egress proxy.
        self.launch_kwargs = dict(launch_kwargs or {})
        # Sites (and some consent tools) hide banners and tags from automated
        # browsers via navigator.webdriver. Measurement must see what a real
        # visitor sees, so this flag is turned off; the user agent still
        # identifies the tool honestly.
        args = list(self.launch_kwargs.get("args", []))
        if "--disable-blink-features=AutomationControlled" not in args:
            args.append("--disable-blink-features=AutomationControlled")
        self.launch_kwargs["args"] = args

    # ------------------------------------------------------------------ helpers
    def _attach(self, page, cond, current):
        def on_request(req):
            cond.requests_total += 1
            url = req.url
            if not url.startswith("http"):
                return
            try:
                post = req.post_data
            except Exception:
                post = None
            host = urlparse(url).hostname or ""
            path = urlparse(url).path
            cmp_name = vendors.detect_cmp(host, path)
            if cmp_name and cmp_name not in cond.cmp:
                cond.cmp.append(cmp_name)
            hit, ss = analyze_request(current["url"], current["reg"], url, req.method, post,
                                      current.setdefault("known_hosts", {}))
            if hit and hit.cmp_name and hit.cmp_name not in cond.cmp:
                cond.cmp.append(hit.cmp_name)
            if ss and ss not in cond.server_side:
                cond.server_side.append(ss)
            if not hit and reg_domain(host) == current["reg"] and len(cond.fp_requests) < 400:
                # Unclassified first-party request: kept until CNAMEs are resolved.
                cond.fp_requests.append({
                    "page": current["url"], "method": req.method, "url": url[:4000],
                    "post": (post or "")[:4000] if isinstance(post, str) else ""})
            if hit:
                cond.hits.append(hit)
                if self.keep_raw:
                    cond.raw_requests.append({
                        "page": current["url"], "t": round(time.time(), 2),
                        "method": req.method, "url": url[:4000],
                        "post": (post or "")[:4000] if isinstance(post, str) else "",
                        "type": req.resource_type})
        page.on("request", on_request)

    def _settle(self, page):
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PWTimeout:
            pass
        time.sleep(self.settle / 2)
        # Passive presence: move the mouse and scroll with the wheel (no clicks).
        # Many sites delay tag loading until the first user interaction event.
        try:
            page.mouse.move(300, 300)
            page.mouse.move(700, 450, steps=8)
            for _ in range(6):
                page.mouse.wheel(0, 700)
                time.sleep(0.25)
            page.mouse.move(500, 200, steps=5)
        except Exception:
            pass
        time.sleep(self.settle / 2)

    def _goto(self, page, url, role):
        pr = PageResult(url=url, role=role)
        try:
            resp = page.goto(url, wait_until="load", timeout=self.timeout)
            pr.status = resp.status if resp else 0
        except PWTimeout:
            pr.error = "timeout(load)"
        except Exception as e:
            pr.error = str(e).split("\n")[0][:200]
            return pr
        self._settle(page)
        try:
            pr.final_url = page.url
            pr.title = (page.title() or "")[:200]
        except Exception:
            pass
        return pr

    def _resolve_cnames(self, cond, site_reg):
        """Classify first-party requests whose host is a CNAME for a tracker or relay."""
        hosts = {urlparse(r["url"]).hostname for r in cond.fp_requests}
        hosts |= {h.host for h in cond.hits if h.first_party_relay}
        hosts = {h for h in hosts if h and reg_domain(h) == site_reg}
        chains = cname.resolve_hosts(h for h in hosts if h)
        cond.cnames = {h: c for h, c in chains.items() if c}
        cond.hits.extend(apply_cnames(cond.hits, cond.fp_requests, cond.cnames, site_reg))
        if not self.keep_raw:
            cond.fp_requests = []

    @staticmethod
    def _shot(page):
        """First screen as a compressed JPEG, base64 (kept in memory by callers)."""
        import base64
        try:
            return base64.b64encode(page.screenshot(type="jpeg", quality=45, timeout=10000)).decode()
        except Exception:
            return ""

    def _probe_globals(self, page, cond):
        """Detect consent tools / CDPs by their JavaScript globals (works for first-party hosting)."""
        try:
            names = page.evaluate(vendors.GLOBALS_JS)
        except Exception:
            return
        for n in names or []:
            vendor, kind = vendors.GLOBAL_SIGNATURES.get(n, (None, None))
            if kind == "cmp" and vendor not in cond.cmp:
                cond.cmp.append(vendor)
            elif kind == "cdp":
                label = f"{vendor} (page script)"
                if label not in cond.server_side:
                    cond.server_side.append(label)

    def _pick_inner(self, page, site_reg, exclude=(), limit=None):
        try:
            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => [e.href, (e.innerText||'').trim().slice(0,80)])")
        except Exception:
            return []
        seen, service, intent, other = set(), [], [], []
        for href, text in links:
            if not href.startswith("http"):
                continue
            u = urlparse(href)
            if reg_domain(u.hostname) != site_reg:
                continue
            if re.search(r"\.(pdf|jpg|png|docx?)$|^tel:|^mailto:|/wp-admin|/login|/portal|/cart",
                         u.path, re.I):
                continue
            clean = f"{u.scheme}://{u.netloc}{u.path}"
            if (clean.rstrip("/") == f"{u.scheme}://{u.netloc}" or clean in seen
                    or clean.rstrip("/") in exclude):
                continue
            seen.add(clean)
            hay = u.path + " " + text
            if terms.health_terms(u.path):
                service.append((2 + len(terms.condition_terms(u.path)), clean))
            elif terms.INTENT_LINK.search(hay):
                intent.append(clean)
            elif terms.SERVICE_LINK.search(hay):
                service.append((1 if terms.health_terms(text) else 0, clean))
            elif not re.search(r"privacy|terms|career|job|news|blog|event|donat|login|sitemap", hay, re.I):
                other.append(clean)
        service.sort(key=lambda x: -x[0])
        out = []
        if service:
            out.append(("service", service[0][1]))
        if intent:
            out.append(("intent", intent[0]))
        if len(out) < self.inner_pages and len(service) > 1:
            out.append(("service", service[1][1]))
        if not out and other:
            out.append(("other", other[0]))
        return out[: self.inner_pages if limit is None else limit]

    def _banner(self, page):
        """Find a visible consent banner without clicking.

        Returns (banner_detected, accept_locator_or_None, how). Looks for
        position:fixed/sticky overlays at the top/bottom edge or centered
        modals, inside open shadow roots and iframes, that contain consent
        wording and accept/decline/manage buttons. Closed shadow roots cannot
        be inspected.
        """
        for sel in ACCEPT_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    return True, loc, "known consent-tool button"
            except Exception:
                continue
        frames = [page.main_frame] + [f for f in page.frames if f != page.main_frame][:10]
        for i, fr in enumerate(frames):
            try:
                res = fr.evaluate(BANNER_JS, [ACCEPT_TEXT.pattern, DECLINE_TEXT.pattern,
                                              BANNER_TEXT.pattern, i > 0])
            except Exception:
                continue
            if res and res.get("banner"):
                how = res.get("how", "overlay") + (" in iframe" if i > 0 else "")
                loc = fr.locator("[data-hpa-accept='1']").first if res.get("accept") else None
                return True, loc, how
        return False, None, ""

    # --------------------------------------------------------------------- scan
    def scan(self, url, accept_condition=True):
        if "://" not in url:
            url = "https://" + url
        t0 = time.time()
        res = SiteResult(input_url=url, started=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        res.site_domain = reg_domain(urlparse(url).hostname)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, **self.launch_kwargs)
            try:
                a, plan, banner = self._run_condition(browser, url, res, "no_interaction", None)
                res.conditions.append(a)
                if accept_condition and banner:
                    b, _, _ = self._run_condition(browser, url, res, "accepted", plan)
                    res.conditions.append(b)
                    if self.reject_run:
                        c, _, _ = self._run_condition(browser, url, res, "rejected", plan[:1])
                        res.conditions.append(c)
                if accept_condition and self.gpc_run and not (a.pages and a.pages[0].error and not a.pages[0].status):
                    d, _, _ = self._run_condition(browser, url, res, "gpc", plan[:1])
                    res.conditions.append(d)
                entry = next((u for r, u in (plan or []) if r == "service"), None)
                if self.inner_landing_run and entry and urlparse(url).path in ("", "/"):
                    e, _, _ = self._run_condition(browser, entry, res, "inner_landing", [])
                    res.conditions.append(e)
            except Exception as e:
                res.error = str(e).split("\n")[0][:300]
            finally:
                browser.close()
        res.duration_s = round(time.time() - t0, 1)
        return res

    def _run_condition(self, browser, url, res, name, plan):
        extra = {"Sec-GPC": "1"} if name == "gpc" else {}
        ctx = browser.new_context(user_agent=self.ua, viewport={"width": 1366, "height": 900},
                                  ignore_https_errors=True, extra_http_headers=extra,
                                  locale="en-US", timezone_id="America/New_York")
        if name == "gpc":
            ctx.add_init_script(script=consent.GPC_SCRIPT)
        if self.use_autoconsent:
            consent.install(ctx)
        cond = ConditionResult(condition=name)
        if self.request_guard is not None:
            def _guard(route):
                url = route.request.url
                if self.request_guard(url):
                    route.continue_()
                else:
                    self.blocked.append(url[:200])
                    route.abort("blockedbyclient")
            ctx.route("**/*", _guard)
        page = ctx.new_page()
        site_reg = res.site_domain
        current = {"url": url, "reg": site_reg}
        self._attach(page, cond, current)
        banner, loc = False, None
        try:
            landing = urlparse(url).path not in ("", "/")
            home = self._goto(page, url, "landing" if landing else "home")
            if home.error and not home.status and url.startswith("http://"):
                home = self._goto(page, "https://" + url[7:], "home")
            elif home.error and not home.status and "://www." not in url:
                home = self._goto(page, url.replace("://", "://www.", 1), "home")
            cond.pages.append(home)
            self._probe_globals(page, cond)
            if home.error and not home.final_url:
                res.error = res.error or home.error
                return cond, [], False
            # Follow redirects to a different registered domain (e.g. rebrand).
            if home.final_url:
                new_reg = reg_domain(urlparse(home.final_url).hostname)
                if new_reg and new_reg != site_reg:
                    res.site_domain = site_reg = current["reg"] = new_reg
            banner, loc, how = self._banner(page)
            ac_cmp, ac_popup = consent.detected(page) if self.use_autoconsent else ("", False)
            cond.autoconsent_cmp = ac_cmp
            if ac_cmp and not cond.cmp:
                cond.cmp.append(f"{ac_cmp} (autoconsent rule)")
            if ac_popup and not banner:
                banner, how = True, f"autoconsent rule: {ac_cmp}"
            cond.banner_detected = banner
            cond.banner_how = how
            if self.screenshots and name in ("no_interaction", "gpc"):
                cond.screenshot = self._shot(page)
            if name == "accepted":
                cond.action = "accept"
                if loc is not None:
                    try:
                        cond.accept_clicked = (loc.inner_text(timeout=1000) or "button").strip()[:40]
                        loc.click(timeout=5000)
                        cond.action_result = "clicked"
                    except Exception as e:
                        cond.accept_clicked = "click failed: " + str(e)[:60]
                elif ac_popup:
                    r = consent.act(page, "optIn")
                    cond.accept_clicked = "accept (autoconsent)"
                    cond.action_result = "ok" if r else "failed"
                time.sleep(self.settle)
                if self.screenshots:
                    cond.screenshot = self._shot(page)
            elif name == "rejected":
                cond.action = "reject"
                r = consent.act(page, "optOut") if (self.use_autoconsent and ac_popup) else None
                if r is None:
                    dec = page.locator("[data-hpa-decline='1']").first
                    try:
                        if dec.count():
                            cond.accept_clicked = (dec.inner_text(timeout=1000) or "decline").strip()[:40]
                            dec.click(timeout=5000)
                            r = True
                    except Exception:
                        r = False
                else:
                    cond.accept_clicked = "reject (autoconsent)"
                cond.action_result = {True: "ok", False: "failed", None: "no reject option found"}[r]
                time.sleep(self.settle)
                if self.screenshots:
                    cond.screenshot = self._shot(page)
            elif name == "gpc":
                cond.action = "gpc"
            if plan is None:
                if landing:
                    # Entered page first (e.g. an ad landing page), then the
                    # domain's home page, then one typical page.
                    home_url = f"https://{site_reg}/"
                    seen = {url.split("?")[0].rstrip("/"), home_url.rstrip("/")}
                    plan = [("home", home_url)] + self._pick_inner(page, site_reg, seen, limit=1)
                else:
                    plan = self._pick_inner(page, site_reg)
                fill_from_home = landing and len(plan) < 2
            else:
                fill_from_home = False
            visited = []
            for role, inner in list(plan):
                time.sleep(2)
                current["url"] = inner
                cond.pages.append(self._goto(page, inner, role))
                self._probe_globals(page, cond)
                visited.append((role, inner))
                if fill_from_home and role == "home":
                    extra = self._pick_inner(page, site_reg, {url.split("?")[0].rstrip("/")}, limit=1)
                    for r2, u2 in extra:
                        time.sleep(2)
                        current["url"] = u2
                        cond.pages.append(self._goto(page, u2, r2))
                        self._probe_globals(page, cond)
                        visited.append((r2, u2))
            plan = visited
        finally:
            ctx.close()
        self._resolve_cnames(cond, site_reg)
        # The "accepted" run only makes sense when there is an accept button to click.
        return cond, plan, bool(banner and loc is not None)


def apply_cnames(hits, fp_requests, cnames, site_reg):
    """Annotate relay hits and classify stored first-party requests using CNAME chains.

    Returns the new Hit objects (or dicts' equivalents) to append. Works on live
    scans and on saved raw logs (no DNS lookups here).
    """
    def attr(h, k):
        return h[k] if isinstance(h, dict) else getattr(h, k)

    for h in hits:
        host = attr(h, "host")
        if host in cnames and not attr(h, "served_via"):
            m = cname.classify(cnames[host])
            val = f"{host} → {m[3] if m else cnames[host][0]}"
            if isinstance(h, dict):
                h["served_via"] = val
            else:
                h.served_via = val
    new = []
    for r in fp_requests:
        host = urlparse(r["url"]).hostname
        ch = cnames.get(host)
        if not ch:
            continue
        m = cname.classify(ch)
        if not m:
            for name in ch:
                v = vendors.classify(name, urlparse(r["url"]).path)
                if v:
                    m = (v[0], v[1], False, name)
                    break
        if not m:
            continue
        vendor, cat, relay, target = m
        is_hit = not re.search(r"\.(js|css|png|jpe?g|gif|svg|woff2?)$", urlparse(r["url"]).path)
        hit, _ = analyze_request(r["page"], site_reg, r["url"], r["method"], r["post"] or None,
                                 override=(vendor, cat, is_hit, relay, f"{host} → {target}"))
        if hit:
            new.append(hit)
    return new


def to_dict(res):
    return asdict(res)
