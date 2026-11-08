"""Command-line interface: `healthpixel-audit scan https://example.org`."""
import argparse
import json
import sys
from pathlib import Path

from .scanner import Scanner, DEFAULT_UA, to_dict
from .report import summarize, text_report


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="healthpixel-audit",
        description="Check what a health-care website sends to advertising and analytics "
                    "platforms before and after cookie consent.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="scan one website")
    sc.add_argument("url")
    sc.add_argument("--pages", type=int, default=2, help="inner pages to visit (default 2)")
    sc.add_argument("--no-accept", action="store_true",
                    help="skip the second run that clicks 'accept' on the cookie banner")
    sc.add_argument("--json", metavar="FILE", help="write the summary as JSON")
    sc.add_argument("--raw", metavar="FILE", help="write raw tracker requests as JSON")
    sc.add_argument("--direct-entry", action="store_true",
                    help="extra fresh visit that lands directly on a service page, as from an ad or search "
                         "(shows tools that record the landing page, e.g. call tracking)")
    sc.add_argument("--user-agent", default=DEFAULT_UA)
    sc.add_argument("--headful", action="store_true", help="show the browser window")
    args = ap.parse_args(argv)

    scanner = Scanner(user_agent=args.user_agent, headless=not args.headful,
                      inner_pages=args.pages, keep_raw=bool(args.raw),
                      inner_landing_run=args.direct_entry)
    res = scanner.scan(args.url, accept_condition=not args.no_accept)
    summary = summarize(res)
    print(text_report(summary))
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=2))
    if args.raw:
        Path(args.raw).write_text(json.dumps(to_dict(res), indent=1))
    return exit_code(summary)


def exit_code(summary):
    """0 no advertising-platform traffic, 1 advertising platforms contacted,
    2 they received condition-naming URLs or titles, 3 inconclusive (a clean-looking
    result that cannot be trusted, e.g. a bot check or 403/429/5xx errors)."""
    first = summary["conditions"][0] if summary["conditions"] else {}
    if first.get("ads_condition"):
        return 2
    if first.get("ads"):
        return 1
    if summary.get("inconclusive_reasons") or summary.get("error"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
