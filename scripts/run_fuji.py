#!/usr/bin/env python3
"""
run_fuji.py  —  score a published Zenodo DOI with F-UJI and save the result.

F-UJI (https://www.f-uji.net) is an automated FAIR assessor. It reads the *metadata*
of a PUBLISHED record at a resolvable identifier (your Zenodo DOI) and scores
Findable / Accessible / Interoperable / Reusable. It never touches your database.

Two ways to use it:
  (1) Easiest — no script: open https://www.f-uji.net/index.php?action=test , paste the
      DOI, click "Evaluate FAIRness", read the score. Done.
  (2) Scripted — run a local F-UJI via Docker, then this script:
        docker run -p 1071:1071 ghcr.io/pangaea-data-publisher/fuji:latest
        python scripts/run_fuji.py 10.5281/zenodo.XXXXXXX
      (default creds marvel:wonderwoman are the F-UJI Docker defaults.)

Stdlib only (urllib) — run it on a NETWORKED machine (the project venv has no net).

Usage:
    python scripts/run_fuji.py <DOI or URL> [--base URL] [--user U --password P] [--out FILE]
"""
from __future__ import annotations
import argparse, base64, json, sys, urllib.request, urllib.error
from pathlib import Path

DEFAULT_BASE = "http://localhost:1071/fuji/api/v1"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("identifier", help="the Zenodo DOI (e.g. 10.5281/zenodo.123456) or landing-page URL")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"F-UJI API base (default {DEFAULT_BASE})")
    ap.add_argument("--user", default="marvel")
    ap.add_argument("--password", default="wonderwoman")
    ap.add_argument("--metric-version", default="metrics_v0.8")  # F-UJI v3.5.1 default; v0.5 is deprecated
    ap.add_argument("--out", default="outputs/metrics/fuji_result.json")
    args = ap.parse_args()

    payload = json.dumps({
        "object_identifier": args.identifier,
        "test_debug": False,
        "use_datacite": True,
        "metric_version": args.metric_version,
    }).encode("utf-8")

    auth = base64.b64encode(f"{args.user}:{args.password}".encode()).decode()
    req = urllib.request.Request(
        f"{args.base.rstrip('/')}/evaluate", data=payload, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            result = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        sys.exit(f"ERROR contacting F-UJI at {args.base}: {e}\n"
                 f"Is the F-UJI service running? See option (1)/(2) in this script's header.")

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    summary = result.get("summary", {})
    pct = summary.get("score_percent", {})
    print(f"F-UJI result for {args.identifier}")
    print(f"  saved: {out}")
    if pct:
        for k in ("FAIR", "F", "A", "I", "R"):
            if k in pct:
                print(f"  {k:<4} {pct[k]}%")
    else:
        print("  (no 'summary.score_percent' in response — inspect the saved JSON.)")
    print("\nReport the overall FAIR% next to the existing 90-identifier external-resolution "
          "check (0.9444) in the FAIR/limitations text of the paper.")


if __name__ == "__main__":
    main()
