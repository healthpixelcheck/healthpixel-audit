# healthpixel-audit

**Check what your health-care website tells advertising platforms — before the visitor ever clicks "accept".**

Try it online: https://check.healthpixelcheck.org

`healthpixel-audit` opens your public website in a clean, headless Chrome browser and records every request the pages send to advertising, analytics, session-replay, call-tracking and chat-widget vendors.
- If you give it a home page, it visits that page and one or two typical inner pages: a service/condition page, and an insurance, admissions or contact page.
- If you give it a specific page, such as an ad landing page, it visits that page first, then the domain's home page and one typical page.

It then tells you, in plain language:

- which **advertising platforms** (Meta, Google Ads, TikTok, LinkedIn, Microsoft/Bing, X, Pinterest, Snap, Reddit, programmatic ad tech) receive data on page load;
- whether they receive the **page address or title naming a condition, procedure or medication** (e.g. `/opioid-addiction-treatment/`, `HIV Testing`, `/dental-implants/`);
- which **events and custom parameters** are sent (e.g. Meta `ev=PageView`, `cd[...]`; GA4 `en=`, `ep.*`);
- whether a **consent banner / consent-management platform** is present, and whether trackers fire **before** the visitor interacts with it;
- what changes **after clicking "Accept"**, **after clicking "Reject"**, and with **Global Privacy Control** turned on (separate runs, each in a fresh browser profile);
- trackers **hidden behind your own subdomains** (CNAME cloaking, e.g. `metrics.example.org → vendor`), found by resolving DNS;
- whether the result is **inconclusive**, e.g. a bot check or 403/429/5xx errors; a consent tool that loaded but showed no banner is reported as a caveat.
- with `--direct-entry`, a separate fresh visit that **lands directly on a service page**, as a patient arriving from an ad or search would — tools such as call tracking often record only the landing page;
- signals of **server-side tagging** or a privacy relay (first-party collection endpoints, known CDPs), and Google Consent Mode flags.

It never fills in or submits forms, never logs in, never types personal data, and never clicks anything except the cookie banner's accept or reject button in the separately labelled runs.

The browser identifies itself honestly in the user agent but does not advertise automation (`navigator.webdriver`). Some consent tools hide their banner from automated browsers, and the measurement has to see what a real visitor sees.

> This is a measurement tool, not legal advice. A browser cannot see server-to-server transfers (for example Meta Conversions API), logged-in patient portals, or what happens after a form is submitted.

## Why

U.S. regulators have repeatedly pointed to tracking pixels on health websites as a channel through which sensitive health information reaches advertising platforms — see HHS OCR's guidance on online tracking technologies and the FTC's Health Breach Notification Rule and enforcement actions. Most providers did not install these tools to share health data; they installed them to measure marketing. This tool makes the data flow visible so that a provider (or its agency, counsel or compliance team) can fix it while keeping the measurement it needs.

## Install

```bash
git clone https://github.com/healthpixelcheck/healthpixel-audit.git
cd healthpixel-audit
python -m pip install .
python -m playwright install chromium
```

Requires Python 3.10+.

## Use

```bash
healthpixel-audit scan https://www.example.org
healthpixel-audit scan example.org --pages 2 --json report.json --raw raw.json
healthpixel-audit scan example.org --no-accept     # skip the "after accept" run
healthpixel-audit scan example.org --direct-entry  # add the direct-entry visit
```

Exit code: `0` no advertising-platform traffic, `1` advertising platforms contacted, `2` advertising platforms received condition-naming URLs or titles, `3` inconclusive (no advertising traffic seen, but the result cannot be trusted, e.g. a bot check or 403/429/5xx errors) — handy for CI checks on your own site.

Example output (abridged):

```
## BEFORE any consent interaction (visitor only moved the mouse and scrolled)
   page [home] https://www.example.org/  (200)
   page [service] https://www.example.org/opioid-addiction-treatment/  (200)
   page [intent] https://www.example.org/verify-insurance/  (200)
   Consent tool detected: none; banner visible: no
[!] Data sent to advertising platforms: Google Ads, Meta Pixel
[!!] Meta Pixel received URLs/titles naming a condition, substance or medication:
       url: https://www.example.org/opioid-addiction-treatment/
   Events observed: Meta Pixel: PageView, SubscribedButtonClick
[!] Session-replay / heatmap tools active: Microsoft Clarity
```

## How it decides

| Finding | Rule |
|---|---|
| Advertising platform contacted | A *beacon* (not just a script download) to a host in the `ads` category of `vendors.py` |
| Page URL sent | Any query/body parameter whose value is a URL on the scanned site's registered domain |
| Condition-naming URL/title | URL path/query or page title (never the hostname) contains a term from `terms.py` that names a condition, substance, procedure or medication. Setting words such as *treatment*, *outpatient*, *therapy* count as "care-related" but not "condition-naming" |
| Consent tool | DuckDuckGo autoconsent rules (846 autoconsent rules); scripts or JS globals of known CMP vendors, including first-party-hosted ones; or a visible fixed overlay or modal with consent wording and accept/decline buttons (open shadow DOM and iframes included) |
| Reject / GPC | Reject via autoconsent's opt-out rule, or our decline-button fallback. GPC via the `Sec-GPC: 1` header plus `navigator.globalPrivacyControl = true` |
| CNAME cloaking | CNAME chain of every first-party host the page contacted, matched against the AdGuard cname-trackers list and our relay list (Ours Privacy, Stape, Segment, Tealium, …) |
| Server-side signal | GA/GTM collection on a first-party subdomain, or a known server-side relay/CDP |

Vendor and vocabulary lists are plain Python and easy to extend; pull requests welcome.

## Third-party data

Bundled unmodified in `healthpixel_audit/thirdparty/` (details and versions in its README):
- DuckDuckGo **autoconsent** 16.44.0, MPL-2.0;
- AdGuard **cname-trackers**, MIT.

DuckDuckGo Tracker Radar is not bundled: its licence is non-commercial.

## Responsible use

- Scan sites you own or public pages, at a polite rate. The default user agent identifies the tool and links to this repository; add your own contact address with `--user-agent`.
- Do not use the tool to submit forms or to access non-public areas.
- Raw request logs can contain your own browser's cookie IDs; keep them private.

## Tests

```bash
python -m pip install ".[test]"
python -m pytest tests
```

The tests check the rules and do not need a browser.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md). Please report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

## License

MIT © 2026 Denis Alekseev. Part of [HealthPixel Check](https://healthpixelcheck.org), a free tool for health-care marketing teams. Contact: research@healthpixelcheck.org.
