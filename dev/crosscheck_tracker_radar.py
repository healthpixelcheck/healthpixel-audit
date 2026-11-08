"""Development-only cross-check of our vendor rules against DuckDuckGo Tracker Radar.

Tracker Radar is CC BY-NC-SA 4.0: it is NOT bundled or redistributed. Clone it
locally and point this script at domains/US to list frequent advertising,
session-replay and pixel domains that our rules in vendors.py do not cover.

usage: python dev/crosscheck_tracker_radar.py /path/to/tracker-radar/domains/US [min_prevalence]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from healthpixel_audit import vendors, cname  # noqa: E402

WATCH = {"Advertising", "Ad Motivated Tracking", "Session Replay", "Action Pixels", "Ad Fraud",
         "Audience Measurement", "Third-Party Analytics Marketing"}


def main():
    root = Path(sys.argv[1])
    min_prev = float(sys.argv[2]) if len(sys.argv) > 2 else 0.002
    covered, missing = 0, []
    for f in root.glob("*.json"):
        d = json.loads(f.read_text())
        cats = set(d.get("categories") or [])
        prev = d.get("prevalence") or 0
        if not (cats & WATCH) or prev < min_prev:
            continue
        host = d["domain"]
        # Host-level comparison: does any of our rules' host patterns cover this domain?
        hit = any(h.search(host) or h.search("www." + host) or h.search("x." + host)
                  for _, _, h, _, _ in vendors._compiled) or cname.match(host)
        if hit:
            covered += 1
        else:
            missing.append((prev, host, (d.get("owner") or {}).get("displayName", ""), sorted(cats & WATCH)))
    missing.sort(reverse=True)
    print(f"Tracker Radar domains in watched categories with prevalence >= {min_prev}: "
          f"{covered + len(missing)}; covered by our rules: {covered}; not covered: {len(missing)}")
    for prev, host, owner, cats in missing[:60]:
        print(f"{prev:.4f}  {host:35s} {owner[:30]:30s} {', '.join(cats)}")


if __name__ == "__main__":
    main()
