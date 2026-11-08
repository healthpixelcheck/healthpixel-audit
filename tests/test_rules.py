from healthpixel_audit import terms, vendors
from healthpixel_audit.scanner import analyze_request


def test_condition_terms():
    assert terms.condition_terms("/services/cancer-care") == ["cancer"]
    assert terms.condition_terms("/dental-implants/") == ["implant"]
    assert terms.condition_terms("/about-us") == []
    # setting words are care-related but do not name a condition
    assert terms.health_terms("/treatment/") == ["treatment"]
    assert terms.condition_terms("/treatment/") == []


def test_vendor_classification():
    assert vendors.classify("www.facebook.com", "/tr/") == ("Meta Pixel", "ads", True)
    assert vendors.classify("connect.facebook.net", "/en_US/fbevents.js")[2] is False
    assert vendors.classify("region1.google-analytics.com", "/g/collect")[0] == "Google Analytics 4"
    assert vendors.classify("bat.bing.com", "/action/0")[0].startswith("Microsoft UET")
    assert vendors.classify("example.org", "/") is None


def test_meta_pixel_url_leak():
    url = ("https://www.facebook.com/tr/?id=123&ev=PageView"
           "&dl=https%3A%2F%2Fwww.example.org%2Fopioid-addiction-treatment%2F&rl=&cd[content_name]=Suboxone")
    hit, _ = analyze_request("https://www.example.org/opioid-addiction-treatment/", "example.org", url, "GET", None)
    assert hit.vendor == "Meta Pixel"
    assert "PageView" in hit.events
    assert "opioid" in hit.condition_terms and "suboxone" in hit.condition_terms
    assert any(e.startswith("url:") for e in hit.evidence)


def test_ga4_batch_body():
    body = "en=page_view&dl=https%3A%2F%2Fexample.org%2Fhiv-testing&dt=HIV%20Testing\nen=scroll"
    hit, _ = analyze_request("https://example.org/hiv-testing", "example.org",
                             "https://region1.google-analytics.com/g/collect?v=2&tid=G-X", "POST", body)
    assert "hiv" in hit.condition_terms
    assert {"page_view", "scroll"} <= set(hit.events)


def test_first_party_server_side():
    hit, ss = analyze_request("https://example.org/", "example.org",
                              "https://metrics.example.org/g/collect?v=2", "POST", "")
    # now recognized by signature as a first-party server-side GTM endpoint
    assert hit.vendor == "Server-side GTM" and hit.first_party_relay


def test_title_brand_is_ignored():
    # Brand words describe the organization, not the page (false positives seen in review).
    assert terms.title_condition_terms("Get Started | Examplecare Orthodontics", "examplecareortho.example") == []
    assert terms.title_condition_terms("Treatments | Examplecare Orthodontics", "examplecareortho.example") == []
    assert terms.title_condition_terms("Our Services | Sample Dental", "sampledental.example") == []
    assert terms.title_condition_terms("Opioid Treatment | Example Recovery Center",
                                       "examplerecovery.example") == ["opioid"]
    assert terms.title_condition_terms("Braces, Invisalign - Demo Orthodontics",
                                       "demosmiles.example") == ["braces", "invisalign"]


def test_generic_words_alone_do_not_count():
    for t in ["Treatments", "Services", "Get Started", "Our Treatment Programs", "Therapy & Counseling"]:
        assert terms.condition_terms(t) == [], t


def test_home_page_title_not_counted():
    url = "https://www.google-analytics.com/g/collect?v=2&dt=Welcome%20to%20Examplecare%20Orthodontics%20%7C%20Invisalign%20%26%20Braces"
    hit, _ = analyze_request("https://www.examplecareortho.example/", "examplecareortho.example", url, "GET", None)
    assert hit.condition_terms == []
    hit, _ = analyze_request("https://www.examplecareortho.example/invisalign", "examplecareortho.example", url, "GET", None)
    assert hit.condition_terms == ["braces", "invisalign"]


def test_first_party_cname_relay_detection():
    known = {}
    h, _ = analyze_request("https://www.example.org/", "example.org", "https://op.example.org/cmp-init?token=abc", "GET", None, known)
    assert h.vendor == "Ours Privacy" and h.cmp_name == "Ours Privacy CMP" and h.first_party_relay
    h, _ = analyze_request("https://www.example.org/hiv", "example.org", "https://op.example.org/ingest", "POST",
                           '{"url":"https://www.example.org/hiv-testing"}', known)
    assert h.is_hit and h.category == "cdp" and h.first_party_relay
    # same path on an unknown host is not attributed
    h, _ = analyze_request("https://www.example.net/", "example.net", "https://cdn.example.net/ingest", "POST", "", {})
    assert h is None
    h, _ = analyze_request("https://www.example.net/", "example.net", "https://sgtm.example.net/g/collect?v=2&tid=G-1", "POST", "", {})
    assert h.vendor == "Server-side GTM" and h.is_hit


def test_relay_not_counted_as_third_party_exposure():
    from healthpixel_audit.report import summarize_condition
    known = {}
    a, _ = analyze_request("https://www.example.org/", "example.org", "https://op.example.org/tag-manager-init?token=t", "GET", None, known)
    b, _ = analyze_request("https://www.example.org/hiv", "example.org", "https://op.example.org/ingest?u=https%3A%2F%2Fwww.example.org%2Fhiv-testing", "GET", None, known)
    c = {"condition": "no_interaction", "pages": [], "hits": [a.__dict__, b.__dict__], "cmp": [],
         "server_side": [], "banner_detected": False, "accept_clicked": ""}
    s = summarize_condition(c)
    assert s["condition_url"] == {} and s["cdp"] == ["Ours Privacy"]


def test_cname_targets():
    from healthpixel_audit import cname
    assert cname.classify(["clinic-domain.oursprivacy.com", "d3x.cloudfront.net"])[:3] == \
        ("Ours Privacy", "cdp", True)
    assert cname.classify(["abc.stape.io"])[0].startswith("Stape")
    assert cname.classify(["sc.omtrdc.net"])[1] == "analytics"          # from the AdGuard list
    assert cname.classify(["wp.wpenginepowered.com"]) is None


def test_signature_on_vendor_host_is_not_first_party():
    h, _ = analyze_request("https://www.telehealth.example/", "telehealth.example",
                           "https://cdp.customer.io/v1/projects/abc/settings", "GET", None, {})
    assert h.vendor == "Segment (proxied)" and not h.first_party_relay


def test_inconclusive_reasons():
    from healthpixel_audit.report import inconclusive_reasons, NOT_SHOWN
    a = {"condition": "no_interaction", "cmp": ["Osano"], "banner_detected": False, "pages_ok": 1,
         "pages": [{"status": 200, "title": "Home", "error": ""}, {"status": 429, "title": "", "error": ""}],
         "action_result": "", "accept_clicked": "", "action": ""}
    r = inconclusive_reasons([a])
    assert any("429" in x for x in r) and NOT_SHOWN not in r
    from healthpixel_audit.report import caveats
    assert NOT_SHOWN in caveats([a])
    a2 = dict(a, cmp=[], pages=[{"status": 200, "title": "Clinic", "error": ""}] * 3, pages_ok=3)
    assert inconclusive_reasons([a2]) == []


def test_exit_codes():
    from healthpixel_audit.cli import exit_code
    clean = {"conditions": [{"ads": [], "ads_condition": []}], "inconclusive_reasons": [], "error": ""}
    assert exit_code(clean) == 0
    assert exit_code(dict(clean, inconclusive_reasons=["The site showed a bot-check page."])) == 3
    assert exit_code({"conditions": [], "inconclusive_reasons": ["The site could not be loaded."]}) == 3
    ads = {"conditions": [{"ads": ["Meta Pixel"], "ads_condition": []}], "inconclusive_reasons": ["x"]}
    assert exit_code(ads) == 1                      # a finding outranks "inconclusive"
    leak = {"conditions": [{"ads": ["Meta Pixel"], "ads_condition": ["Meta Pixel"]}], "inconclusive_reasons": []}
    assert exit_code(leak) == 2
