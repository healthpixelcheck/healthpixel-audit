"""Tracker vendor rules.

Each rule matches a network request (host + path) and names the vendor, its
category, and which query/body parameters carry page context.

Categories:
  ads        - advertising / retargeting platform (data can be used for ad targeting)
  analytics  - web analytics
  replay     - session replay / heatmaps (can capture page content and keystrokes)
  tagmgr     - tag manager loader (not a data transmission by itself)
  calltrack  - call tracking / dynamic number insertion
  chat       - chat widgets and chatbots (a third party receives what visitors type)
  cdp        - customer data platform / server-side relay
  cmp        - consent management platform
"""
import re

# (vendor, category, host regex, path regex or None, is_hit)
# is_hit=True means the request itself is a data transmission (beacon), not
# just a library download.
RULES = [
    # --- Meta
    ("Meta Pixel", "ads", r"(^|\.)facebook\.com$", r"^/tr/?", True),
    ("Meta Pixel", "ads", r"(^|\.)facebook\.com$", r"^/privacy_sandbox/pixel", True),
    ("Meta Pixel", "ads", r"(^|\.)connect\.facebook\.net$", r"/fbevents\.js|/signals/", False),
    # --- Google advertising
    ("Google Ads", "ads", r"(^|\.)googleadservices\.com$", r"^/pagead/conversion", True),
    ("Google Ads", "ads", r"(^|\.)googleadservices\.com$", None, False),
    ("Google Ads", "ads", r"^googleads\.g\.doubleclick\.net$", r"^/pagead/", True),
    ("Google Ads", "ads", r"(^|\.)google\.com$", r"^/pagead/1p-(user-list|conversion)/", True),
    ("Google Ads", "ads", r"(^|\.)google\.[a-z.]+$", r"^/ccm/collect", True),
    ("Google DoubleClick/Floodlight", "ads", r"(^|\.)(ad|stats|fls)\.doubleclick\.net$", None, True),
    ("Google DoubleClick/Floodlight", "ads", r"(^|\.)doubleclick\.net$", r"activity", True),
    # --- Google Analytics
    ("Google Analytics 4", "analytics", r"(^|\.)google-analytics\.com$", r"^/g/collect", True),
    ("Google Analytics 4", "analytics", r"^analytics\.google\.com$", r"^/g/collect", True),
    ("Google Analytics (UA)", "analytics", r"(^|\.)google-analytics\.com$", r"^/(r/|j/)?collect", True),
    ("Google Analytics", "analytics", r"(^|\.)google-analytics\.com$", r"\.js$", False),
    ("Google Tag Manager", "tagmgr", r"^www\.googletagmanager\.com$", r"^/(gtm|gtag/js|gtag/destination)", False),
    # --- Other ad platforms
    ("TikTok Pixel", "ads", r"^analytics\.tiktok\.com$", r"^/api/v2/(pixel|monitor)", True),
    ("TikTok Pixel", "ads", r"^analytics\.tiktok\.com$", None, False),
    ("LinkedIn Insight", "ads", r"^px\.ads\.linkedin\.com$", None, True),
    ("LinkedIn Insight", "ads", r"(^|\.)linkedin\.com$", r"^/(px|collect|attribution_trigger)", True),
    ("LinkedIn Insight", "ads", r"^snap\.licdn\.com$", None, False),
    ("Microsoft UET (Bing Ads)", "ads", r"^bat\.bing\.(com|net)$", r"^/action/", True),
    ("Microsoft UET (Bing Ads)", "ads", r"^bat\.bing\.(com|net)$", None, False),
    ("X/Twitter Pixel", "ads", r"(^|\.)ads-twitter\.com$", None, False),
    ("X/Twitter Pixel", "ads", r"^(analytics\.twitter\.com|t\.co|ads-api\.twitter\.com|ads-api\.x\.com)$", r"i/adsct|1/i/adsct", True),
    ("Pinterest Tag", "ads", r"^ct\.pinterest\.com$", None, True),
    ("Pinterest Tag", "ads", r"^s\.pinimg\.com$", r"/ct/", False),
    ("Snap Pixel", "ads", r"^tr(-shadow)?\.snapchat\.com$", None, True),
    ("Snap Pixel", "ads", r"^sc-static\.net$", None, False),
    ("Reddit Pixel", "ads", r"^(alb|pixel-config)\.reddit\.com$", None, True),
    ("Reddit Pixel", "ads", r"^www\.redditstatic\.com$", r"/ads/", False),
    ("Nextdoor Pixel", "ads", r"(^|\.)nextdoor\.com$", r"/ads|pixel", True),
    ("Criteo", "ads", r"(^|\.)criteo\.(com|net)$", None, True),
    ("Taboola", "ads", r"(^|\.)taboola\.com$", None, True),
    ("Outbrain", "ads", r"(^|\.)outbrain\.com$", None, True),
    ("AdRoll", "ads", r"(^|\.)adroll\.com$", None, True),
    ("StackAdapt", "ads", r"(^|\.)srv\.stackadapt\.com$", None, True),
    ("Simpli.fi", "ads", r"(^|\.)simpli\.fi$", None, True),
    ("The Trade Desk", "ads", r"(^|\.)adsrvr\.org$", None, True),
    ("Quantcast", "ads", r"(^|\.)quantserve\.com$|(^|\.)quantcount\.com$", None, True),
    ("Basis/Centro", "ads", r"(^|\.)sitescout\.com$", None, True),
    ("Yahoo/Verizon Ads", "ads", r"(^|\.)(analytics\.yahoo\.com|ads\.yahoo\.com)$", None, True),
    ("Amazon Ads", "ads", r"(^|\.)(amazon-adsystem\.com)$", None, True),
    ("Spotify Pixel", "ads", r"^pixel\.byspotify\.com$", None, True),
    ("Vibe/Steelhouse (MNTN)", "ads", r"(^|\.)(steelhousemedia\.com|mountain\.com)$", None, True),
    ("Podscribe", "ads", r"(^|\.)podscribe\.com$", None, True),
    ("Programmatic ad tech", "ads", r"(^|\.)(rubiconproject\.com|openx\.net|id5-sync\.com|3lift\.com|liadm\.com|"
     r"smartadserver\.com|33across\.com|creativecdn\.com|turn\.com|media\.net|lijit\.com|sharethrough\.com|"
     r"bidr\.io|dotomi\.com|gumgum\.com|1rx\.io|teads\.tv|pippio\.com|360yield\.com|adform\.net|"
     r"blismedia\.com|rfihub\.com|contextweb\.com|intentiq\.com|sonobi\.com|unrulymedia\.com|yieldmo\.com|"
     r"ipredictive\.com|loopme\.me|kargo\.com|2mdn\.net|googlesyndication\.com|adsymptotic\.com|"
     r"tremorhub\.com|serving-sys\.com|eyeota\.net|bluekai\.com|exelator\.com|krxd\.net|"
     r"doubleverify\.com|adsafeprotected\.com|moatads\.com|deepintent\.com|adentifi\.com|smaato\.net|"
     r"mfadsrvr\.com|fwmrm\.net|adkernel\.com|indexww\.com|casalemedia\.com|rkdms\.com|thrtle\.com|"
     r"undertone\.com|imrworldwide\.com|googletagservices\.com)$", None, True),
    ("Klaviyo", "analytics", r"(^|\.)klaviyo\.com$", None, True),
    ("comScore", "analytics", r"(^|\.)scorecardresearch\.com$", None, True),
    ("Agency/ID-graph pixel", "ads", r"(^|\.)(ml314\.com|bidswitch\.net|rlcdn\.com|pubmatic\.com|casalemedia\.com|adnxs\.com|demdex\.net|everesttech\.net|agkn\.com|tapad\.com|crwdcntrl\.net|zemanta\.com|mathtag\.com)$", None, True),
    # --- Session replay / heatmaps
    ("Microsoft Clarity", "replay", r"(^|\.)clarity\.ms$", r"^/collect", True),
    ("Microsoft Clarity", "replay", r"(^|\.)clarity\.ms$", None, False),
    ("Hotjar", "replay", r"(^|\.)hotjar\.(com|io)$", None, True),
    ("FullStory", "replay", r"(^|\.)fullstory\.com$", None, True),
    ("Lucky Orange", "replay", r"(^|\.)luckyorange\.(com|net)$", None, True),
    ("Mouseflow", "replay", r"(^|\.)mouseflow\.com$", None, True),
    ("Crazy Egg", "replay", r"(^|\.)crazyegg\.com$", None, True),
    ("Smartlook", "replay", r"(^|\.)smartlook\.(com|cloud)$", None, True),
    ("Inspectlet", "replay", r"(^|\.)inspectlet\.com$", None, True),
    # --- Analytics / marketing automation
    ("HubSpot", "analytics", r"(^|\.)(hs-analytics\.net|hs-scripts\.com|hubspot\.com|hsforms\.com|hs-banner\.com|hscollectedforms\.net|hsadspixel\.net)$", None, True),
    ("Adobe Analytics", "analytics", r"(^|\.)(omtrdc\.net|2o7\.net)$", None, True),
    ("Segment", "cdp", r"^(api|cdn)\.segment\.(io|com)$", None, True),
    ("Heap", "analytics", r"(^|\.)heapanalytics\.com$", None, True),
    ("Mixpanel", "analytics", r"(^|\.)mixpanel\.com$", None, True),
    ("Amplitude", "analytics", r"(^|\.)amplitude\.com$", None, True),
    ("Yandex Metrica", "analytics", r"^mc\.yandex\.(ru|com)$", None, True),
    ("Matomo/Piwik PRO", "analytics", r"(^|\.)(matomo\.cloud|piwik\.pro|containers\.piwik\.pro)$", None, True),
    ("Salesforce Marketing/Pardot", "analytics", r"(^|\.)(pardot\.com|pi\.pardot\.com|exacttarget\.com|igodigital\.com)$", None, True),
    ("Marketo", "analytics", r"(^|\.)(marketo\.net|mktoresp\.com)$", None, True),
    # --- Chat widgets / chatbots (presence: the vendor's widget loaded or connected)
    ("LivePerson", "chat", r"(^|\.)(liveperson\.net|lpsnmedia\.net)$", None, True),
    ("Intercom", "chat", r"(^|\.)(intercom\.io|intercomcdn\.com)$", None, True),
    ("Drift", "chat", r"(^|\.)(drift\.com|driftt\.com)$", None, True),
    ("Zendesk Chat", "chat", r"(^|\.)(zopim\.com|zdassets\.com)$", None, True),
    ("Salesforce Chat", "chat", r"(^|\.)(salesforceliveagent\.com|salesforce-scrt\.com)$", None, True),
    ("HubSpot Chat", "chat", r"(^|\.)usemessages\.com$", None, True),
    ("LiveChat", "chat", r"(^|\.)(livechatinc\.com|livechat\.com)$", None, True),
    ("Tidio", "chat", r"(^|\.)(tidio\.co|tidiochat\.com)$", None, True),
    ("tawk.to", "chat", r"(^|\.)tawk\.to$", None, True),
    ("Olark", "chat", r"(^|\.)olark\.com$", None, True),
    ("Freshchat", "chat", r"(^|\.)freshchat\.com$", None, True),
    ("Crisp", "chat", r"(^|\.)crisp\.chat$", None, True),
    ("Podium", "chat", r"(^|\.)podium\.com$", None, True),
    ("Birdeye", "chat", r"(^|\.)birdeye\.com$", None, True),
    ("Hyro", "chat", r"(^|\.)hyro\.ai$", None, True),
    # --- Call tracking (sees which page a caller came from)
    ("CallRail", "calltrack", r"(^|\.)(callrail\.com)$", None, True),
    ("CallTrackingMetrics", "calltrack", r"(^|\.)(tctm\.co|calltrackingmetrics\.com)$", None, True),
    ("Invoca", "calltrack", r"(^|\.)(invoca\.net|invocacdn\.com)$", None, True),
    ("WhatConverts", "calltrack", r"(^|\.)whatconverts\.com$", None, True),
    ("Marchex", "calltrack", r"(^|\.)marchex\.io$", None, True),
    ("Ringba", "calltrack", r"(^|\.)ringba\.com$", None, True),
    ("Liine", "calltrack", r"(^|\.)liine\.com$", None, True),
    ("DialogTech", "calltrack", r"(^|\.)dialogtech\.com$", None, True),
    ("CallSource", "calltrack", r"(^|\.)callsource\.com$", None, True),
    ("Convirza", "calltrack", r"(^|\.)convirza\.com$", None, True),
    ("Retreaver", "calltrack", r"(^|\.)retreaver\.com$", None, True),
    ("Nimbata", "calltrack", r"(^|\.)nimbata\.com$", None, True),
    ("Phonexa", "calltrack", r"(^|\.)phonexa\.com$", None, True),
    # --- Privacy-oriented / server-side relays (presence noted, not counted as leak)
    ("Ours Privacy", "cdp", r"(^|\.)oursprivacy\.com$", None, True),
    ("Freshpaint", "cdp", r"(^|\.)freshpaint\.io$", None, True),
    ("Stape (server GTM host)", "cdp", r"(^|\.)stape\.(io|net)$", None, True),
    ("Tealium", "cdp", r"(^|\.)(tiqcdn\.com|tealiumiq\.com)$", None, True),
    ("Elevar", "cdp", r"(^|\.)getelevar\.com$", None, True),
    ("LiveRamp/ATS", "ads", r"(^|\.)(ats\.rlcdn\.com|launchpad\.privacymanager\.io)$", None, True),
]

CMP_RULES = [
    ("OneTrust", r"(^|\.)(cookielaw\.org|onetrust\.com|cookiepro\.com)$"),
    ("Cookiebot", r"(^|\.)(cookiebot\.com|cookiebot\.eu)$"),
    ("Osano", r"(^|\.)osano\.com$"),
    ("Termly", r"(^|\.)termly\.io$"),
    ("iubenda", r"(^|\.)iubenda\.com$"),
    ("CookieYes", r"(^|\.)cookieyes\.com$"),
    ("TrustArc", r"(^|\.)(trustarc\.com|truste\.com)$"),
    ("Usercentrics", r"(^|\.)usercentrics\.(eu|com)$"),
    ("Didomi", r"(^|\.)(privacy-center\.org|didomi\.io)$"),
    ("Ketch", r"(^|\.)ketchcdn\.com$|(^|\.)ketchjs\.com$"),
    ("Transcend", r"(^|\.)transcend\.io$"),
    ("Enzuzo", r"(^|\.)enzuzo\.com$"),
    ("Securiti", r"(^|\.)securiti\.ai$"),
    ("Complianz", r"/wp-content/plugins/complianz"),
    ("CookieYes (WP)", r"/wp-content/plugins/cookie-law-info"),
    ("Cookie Notice (WP)", r"/wp-content/plugins/cookie-notice"),
    ("GDPR Cookie Compliance (WP)", r"/wp-content/plugins/gdpr-cookie-compliance"),
    ("Borlabs (WP)", r"/wp-content/plugins/borlabs-cookie"),
    ("Real Cookie Banner (WP)", r"/wp-content/plugins/real-cookie-banner"),
    ("Ours Privacy CMP", r"(^|\.)oursprivacy\.com$"),
]

_compiled = [(v, c, re.compile(h), re.compile(p) if p else None, hit) for v, c, h, p, hit in RULES]
_cmp_compiled = [(v, re.compile(p)) for v, p in CMP_RULES]


def classify(host, path):
    """Return (vendor, category, is_hit) or None."""
    host = host.lower()
    for v, c, h, p, hit in _compiled:
        if h.search(host) and (p is None or p.search(path)):
            return v, c, hit
    return None


def detect_cmp(host, path):
    full = host.lower() + path
    for v, rx in _cmp_compiled:
        if rx.pattern.startswith("/"):
            if rx.search(path):
                return v
        elif rx.search(host.lower()):
            return v
    return None


# Vendors whose beacons go to platforms that use data for advertising.
AD_CATEGORIES = {"ads"}


# ------------------------------------------------- first-party / CNAME tracking
# Many privacy-oriented and server-side setups load from the site's own
# subdomain (e.g. op.example.org, sgtm.example.org) via a CNAME, so the host
# says nothing. These signatures match on path + query instead. A host that
# matches a "marks host" signature is remembered for the rest of the visit, so
# its other endpoints (/main.js, /ingest, ...) are attributed to the same vendor.
# (vendor, category, path regex, query regex or None, is_hit, cmp name or None, marks_host)
PATH_SIGNATURES = [
    ("Ours Privacy", "cdp", r"^/cmp-init$", r"(^|&)token=", False, "Ours Privacy CMP", True),
    ("Ours Privacy", "cdp", r"^/tag-manager-init$", r"(^|&)token=", False, None, True),
    ("Server-side GTM", "cdp", r"^/gtm\.js$", r"(^|&)id=GTM-", False, None, True),
    ("Server-side GTM", "cdp", r"^/gtag/js$", r"(^|&)id=(G|AW|DC)-", False, None, True),
    ("Server-side GTM", "cdp", r"^/(g|j)/collect$", r"(^|&)(tid=G-|v=2)", True, None, True),
    ("Segment (proxied)", "cdp", r"^/analytics\.js/v1/[^/]+/analytics(\.min)?\.js$", None, False, None, True),
    ("Segment (proxied)", "cdp", r"^/v1/projects/[^/]+/settings$", None, False, None, True),
    ("Tealium", "cdp", r"/utag(\.sync)?\.js$", None, False, None, True),
    ("Matomo/Piwik PRO", "analytics", r"/(matomo|piwik)\.(js|php)$", None, True, None, True),
]
_path_sig = [(v, c, re.compile(p), re.compile(q) if q else None, hit, cmp, mark)
             for v, c, p, q, hit, cmp, mark in PATH_SIGNATURES]
GOOGLE_HOSTS = re.compile(r"(^|\.)(google|googletagmanager|google-analytics|doubleclick|googleadservices|"
                          r"googlesyndication|gstatic)\.[a-z.]+$")


def classify_first_party(host, path, query, known_hosts):
    """Signature match for hosts not covered by RULES.

    known_hosts: dict host -> vendor, updated in place (per visit).
    Returns (vendor, category, is_hit, cmp_name) or None.
    """
    host = host.lower()
    if GOOGLE_HOSTS.search(host):
        return None
    for v, c, p, q, hit, cmp, mark in _path_sig:
        if p.search(path) and (q is None or q.search(query or "")):
            if mark and known_hosts is not None:
                known_hosts[host] = (v, c)
            return v, c, hit, cmp
    if known_hosts and host in known_hosts:
        v, c = known_hosts[host]
        # Anything else on a remembered host: collection endpoints count as data hits.
        is_hit = not re.search(r"\.(js|css|png|svg|woff2?)$", path)
        return v, c, is_hit, None
    return None


# JavaScript globals that reveal a consent tool or a customer-data platform even
# when it is served first-party. name -> (vendor, kind) where kind is "cmp" or "cdp".
GLOBAL_SIGNATURES = {
    "ours_consent": ("Ours Privacy CMP", "cmp"),
    "OneTrust": ("OneTrust", "cmp"), "OptanonActiveGroups": ("OneTrust", "cmp"),
    "Cookiebot": ("Cookiebot", "cmp"), "CookieConsent": ("Cookie-consent library", "cmp"),
    "Osano": ("Osano", "cmp"), "Termly": ("Termly", "cmp"),
    "UC_UI": ("Usercentrics", "cmp"), "Didomi": ("Didomi", "cmp"),
    "truste": ("TrustArc", "cmp"), "getCkyConsent": ("CookieYes", "cmp"),
    "ketch": ("Ketch", "cmp"), "airgap": ("Transcend", "cmp"),
    "complianz": ("Complianz", "cmp"), "__tcfapi": ("IAB TCF consent API", "cmp"),
    "__gpp": ("IAB GPP consent API", "cmp"),
    "freshpaint": ("Freshpaint", "cdp"), "rudderanalytics": ("RudderStack", "cdp"),
    "utag": ("Tealium", "cdp"),
}
# Expression evaluated in the page; returns the names of the globals present.
GLOBALS_JS = (
    "() => { const names = %s; const out = names.filter(n => { try { return typeof window[n] !== 'undefined' && window[n] !== null; } catch (e) { return false; } });"
    " try { if (window.analytics && typeof window.analytics.track === 'function' && window.analytics.VERSION) out.push('__segment'); } catch (e) {}"
    " return out; }"
)
GLOBAL_SIGNATURES["__segment"] = ("Segment", "cdp")
GLOBALS_JS = GLOBALS_JS % (str(sorted(k for k in GLOBAL_SIGNATURES if k != "__segment")),)
