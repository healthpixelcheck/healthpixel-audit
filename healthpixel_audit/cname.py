"""Uncover trackers hidden behind first-party subdomains (CNAME cloaking).

A tracker can be served from the provider's own subdomain (op.example.org,
metrics.example.org) that is a DNS CNAME for the vendor (clinic.oursprivacy.com,
x.stape.io). The browser only shows the first-party name. We resolve the CNAME
chain of every first-party host the page contacted and match each name against:
  * our own list of server-side / privacy relays (below, MIT);
  * AdGuard's list of CNAME-cloaked trackers (thirdparty/adguard, MIT);
  * the host rules in vendors.py.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import dns.resolver
except ImportError:          # CNAME checks are skipped without dnspython
    dns = None

HERE = Path(__file__).resolve().parent / "thirdparty" / "adguard"

# Server-side relays / CDPs that providers host on their own subdomain.
# (vendor, category, first_party_relay). Relays forward data under the
# provider's control; disguised trackers send it straight to a third party.
OUR_TARGETS = {
    "oursprivacy.com": ("Ours Privacy", "cdp", True),
    "stape.io": ("Stape (server-side GTM)", "cdp", True),
    "stape.net": ("Stape (server-side GTM)", "cdp", True),
    "taggrs.io": ("TAGGRS (server-side GTM)", "cdp", True),
    "addingwell.com": ("Addingwell (server-side GTM)", "cdp", True),
    "freshpaint.io": ("Freshpaint", "cdp", True),
    "metarouter.io": ("MetaRouter", "cdp", True),
    "getelevar.com": ("Elevar", "cdp", True),
    "edgetag.io": ("EdgeTag", "cdp", True),
    "tealiumiq.com": ("Tealium", "cdp", True),
    "segment.com": ("Segment", "cdp", True),
    "segment.io": ("Segment", "cdp", True),
    "jentis.com": ("JENTIS", "cdp", True),
}
AG_CATEGORY = {"tracker": "analytics", "ad": "ads", "clickthrough": "ads",
               "microsite": "analytics", "mail_tracker": "analytics"}


def _load_adguard():
    out = {}
    try:
        for item in json.loads((HERE / "cloaked-trackers.json").read_text()):
            cat = AG_CATEGORY.get(item.get("type"), "analytics")
            for d in item.get("domains", []):
                out[d.lower()] = (item["company_name"], cat, False)
    except FileNotFoundError:
        pass
    try:
        company = None
        for line in (HERE / "combined_original_trackers.txt").read_text().splitlines():
            if line.startswith("! Company:"):
                company = line.split(":", 1)[1].strip()
            m = re.match(r"^\|\|([a-z0-9.-]+)\^", line)
            if m and company and m.group(1) not in out:
                out[m.group(1)] = (company, "analytics", False)
    except FileNotFoundError:
        pass
    return out


TARGETS = {**_load_adguard(), **OUR_TARGETS}


def match(name):
    """Vendor tuple if `name` (or a parent domain of it) is a known target."""
    name = name.lower().rstrip(".")
    parts = name.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in TARGETS:
            return TARGETS[cand]
    return None


def chain(host, hops=5, timeout=2.0):
    """CNAME chain for `host` (without the host itself). Empty on any error."""
    if dns is None:
        return []
    res = dns.resolver.Resolver()
    res.lifetime = timeout
    out, cur = [], host
    for _ in range(hops):
        try:
            ans = res.resolve(cur, "CNAME")
        except Exception:
            break
        cur = str(ans[0].target).rstrip(".")
        out.append(cur)
    return out


def resolve_hosts(hosts):
    """{host: [cname chain]} for many hosts in parallel."""
    hosts = sorted(set(hosts))[:40]
    if not hosts or dns is None:
        return {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(hosts, ex.map(chain, hosts)))


def classify(cname_chain):
    """(vendor, category, first_party_relay, target) for the first known name in the chain."""
    for name in cname_chain:
        m = match(name)
        if m:
            return (*m, name)
    return None
