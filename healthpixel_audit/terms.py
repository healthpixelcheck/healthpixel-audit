"""Health-context vocabulary used to decide whether data sent to a third party
reveals a health condition or care-seeking intent.

Matching is done on lowercase word tokens of URL paths, query strings and page
titles (never on the site's hostname, which is reported separately).
"""
import re

# Condition / treatment terms (prefix match on tokens).
HEALTH_PREFIXES = [
    "addict", "rehab", "detox", "alcohol", "opioid", "opiate", "heroin", "fentanyl",
    "methadone", "suboxone", "buprenorph", "sublocade", "vivitrol", "naltrexon",
    "subutex", "brixadi", "narcan", "naloxon", "substance", "drug", "meth", "cocain",
    "crack", "benzo", "xanax", "kratom", "marijuana", "cannabis", "overdos", "sober",
    "sobriety", "relapse", "withdraw", "dualdiag", "dual-diag", "mentalhealth",
    "depress", "anxiety", "bipolar", "ptsd", "trauma", "schizo", "psychos",
    "eating-disorder", "anorex", "bulimi", "suicid", "selfharm", "psychiatr",
    "gambling", "behavioral", "behavioural", "mat", "moud", "iop", "php", "otp",
    "intensive-outpatient", "partial-hospital", "residential", "inpatient",
    "outpatient", "recovery", "treatment", "therapy", "counsel", "hiv", "hepatitis",
    # general medicine
    "cancer", "oncolog", "tumor", "chemo", "radiation", "mammogra", "biopsy", "cardio",
    "cardiac", "stroke", "diabet", "insulin", "obstetric", "pregnan", "prenatal",
    "abortion", "contracept", "fertility", "infertil", "ivf", "gynec", "urolog", "erectile",
    "vasectom", "prostat", "std", "sexually", "covid", "vaccin", "dermatolog", "acne",
    "psoria", "eczema", "weight-loss", "weightloss", "bariatric", "obesity", "semaglut",
    "ozempic", "wegovy", "tirzepat", "glp", "transgender", "gender-affirm", "hormone",
    "testosteron", "menopaus", "dementia", "alzheim", "autism", "adhd", "kidney", "renal",
    "dialysis", "transplant", "asthma", "copd", "allerg", "arthrit", "rheumat", "migraine",
    "epilep", "seizure", "neurolog", "parkinson", "sleep-apnea", "apnea", "hearing-loss",
    "cataract", "glaucoma", "lasik", "colonoscop", "gastro", "crohn", "colitis", "hernia",
    "orthoped", "spine", "joint-replace", "knee", "hip-replace", "pain-manage", "chronic-pain",
    "wound", "hospice", "palliative", "lupus", "thyroid", "endocrin", "pulmon", "lung",
    "hiv-prep", "pediatric", "geriatric", "lactation", "nicu", "maternity", "labor",
    # dental
    "implant", "root-canal", "rootcanal", "periodont", "gum-disease", "orthodont", "invisalign",
    "braces", "denture", "extraction", "wisdom-teeth", "tmj", "endodont", "oral-surg",
    "sedation", "cosmetic-dent", "veneer", "whitening", "crown", "cavity", "fluoride",
]
# Exact tokens that are too short for prefix matching.
HEALTH_EXACT = {"mat", "moud", "iop", "php", "otp", "aud", "sud", "oud", "dui", "dwi", "mh",
                "hiv", "std", "sti", "ivf", "ed", "ent", "ob", "obgyn", "ob-gyn", "gyn", "ptsd",
                "ocd", "adhd", "copd", "prep", "tmj", "glp-1", "trt", "hrt", "ivf",
                "heart", "hearts"}

# Care-seeking intent terms.
INTENT_PREFIXES = [
    "insurance", "verify", "verification", "admission", "admit", "intake",
    "appointment", "schedule", "get-help", "gethelp", "get-started", "contact",
    "assessment", "referral", "payment", "cost", "medicaid", "medicare", "aetna",
    "cigna", "bcbs", "bluecross", "humana", "unitedhealth", "tricare",
]

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _tokens(text):
    text = (text or "").lower()
    toks = set(_TOKEN.findall(text))
    # Also split hyphenated tokens.
    for t in list(toks):
        if "-" in t:
            toks.update(t.split("-"))
    return toks


def health_terms(text):
    found = set()
    for t in _tokens(text):
        if t in HEALTH_EXACT:
            found.add(t)
            continue
        if len(t) < 4:
            continue
        for p in HEALTH_PREFIXES:
            if len(p) >= 4 and t.startswith(p) or (len(p) < 4 and t == p):
                found.add(p)
    return sorted(found)


def intent_terms(text):
    found = set()
    for t in _tokens(text):
        for p in INTENT_PREFIXES:
            if t.startswith(p):
                found.add(p)
    return sorted(found)


# Link-text / href patterns used to pick inner pages for the scan.
SERVICE_LINK = re.compile(
    r"addict|rehab|detox|alcohol|opioid|methadone|suboxone|buprenorph|substance|drug|"
    r"\bmat\b|medication-assisted|outpatient|inpatient|residential|iop|php|"
    r"treatment|program|service|mental-health|dual-diagnosis|condition|specialt|"
    r"department|cancer|cardio|heart|orthop|women|maternity|obstetric|pediatric|dental|"
    r"implant|orthodont|periodont|dermatolog|weight|bariatric|urolog|behavioral|therapy", re.I)
INTENT_LINK = re.compile(
    r"insurance|verify|admission|intake|get-help|get-started|appointment|contact", re.I)


# Terms that describe a setting of care rather than a condition. A URL that
# only contains these is "care-related"; one that contains any other health
# term names a condition, substance or medication ("condition-specific").
SETTING_TERMS = {"behavioral", "behavioural", "residential", "inpatient", "outpatient",
                 "recovery", "treatment", "therapy", "counsel", "iop", "php", "otp",
                 "intensive-outpatient", "partial-hospital", "mh", "pediatric", "geriatric",
                 "labor", "lung", "knee", "crown", "whitening", "fluoride", "sedation",
                 "maternity", "hormone"}


def condition_terms(text):
    return [t for t in health_terms(text) if t not in SETTING_TERMS]


# ---------------------------------------------------------------- page titles
# Titles usually look like "Page name | Brand". Words in the brand ("Examplecare
# Orthodontics", "Sample Recovery") describe the organization, not the page,
# so they are removed before looking for condition terms.
_TITLE_SEP = re.compile(r"\s+[|\-–—:•·»]\s+|\s*\|\s*")


def _compact(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _is_brand(segment, site_label):
    from difflib import SequenceMatcher
    a, b = _compact(segment), _compact(site_label)
    if not a or not b:
        return False
    m = SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
    return m.size >= 4 and (m.size >= 0.6 * len(b) or m.size >= 0.7 * len(a))


def title_page_part(title, site_domain):
    """Return the part of a page title that describes the page, not the brand."""
    label = (site_domain or "").split(".")[0]
    segs = [s.strip() for s in _TITLE_SEP.split(title or "") if s and s.strip()]
    if not segs:
        return ""
    brand = [i for i, s in enumerate(segs) if _is_brand(s, label)]
    if not brand:
        # Brand not recognized: by convention ("Page | Brand | City") the page
        # name is the first segment.
        return segs[0] if len(segs) > 1 else segs[0]
    if brand[0] > 0:
        return " ".join(segs[:brand[0]])
    rest = [s for i, s in enumerate(segs) if i not in brand]
    return " ".join(rest)


def title_condition_terms(title, site_domain):
    return condition_terms(title_page_part(title, site_domain))
