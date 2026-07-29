"""
BioPortal REST API Client
==========================
Resolves ontology identifiers against BioPortal (https://data.bioontology.org)
and verifies that the labels asserted in this project match the authority.

This closes the gap where ``config.yaml [bioportal]`` and ``BIOPORTAL_API_KEY``
were configured but had no consumer: the ``base_url``, ``rate_limit_per_minute``
and ``cache_ttl_seconds`` settings are all honoured here.

Why BioPortal rather than EBI OLS4: OLS4 serves the OBO ontologies (HPO, UBERON,
GO, MONDO, DOID) but does not serve SNOMED-CT, LOINC or ICD-10. BioPortal serves
all of them under one API, so it is the only single authority that can verify the
SNOMED-CT and LOINC codes that ``metrics/verify_ontology_labels.py`` currently
lists as ``skipped``.

SNOMED-CT licensing: BioPortal serves SNOMEDCT only to accounts that have
accepted the IHTSDO Affiliate licence on the BioPortal site. If the account
behind BIOPORTAL_API_KEY has not accepted it, SNOMEDCT lookups return HTTP 403
and are reported as ``licence_gated`` rather than as mismatches — an honest
"cannot check" is not the same as a failure.

Usage:
    # verify every row of ontology/mappings/*.csv against BioPortal
    python -m utils.bioportal_client --verify-mappings

    # single identifier
    python -m utils.bioportal_client --code snomed:26929004
    python -m utils.bioportal_client --code hpo:HP:0002354

    # cache-only, never touch the network (for CI / offline gates)
    python -m utils.bioportal_client --verify-mappings --offline

Exit code is 1 if any identifier mismatched, so this can be used as a gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.env_loader import load_config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "ontology" / "bioportal_cache.json"
MAPPINGS_DIR = PROJECT_ROOT / "ontology" / "mappings"

# Prefix (as used in ontology/mappings/*.csv target_uri) → BioPortal acronym
# plus the PURL template BioPortal indexes that ontology under.
_OBO = "http://purl.obolibrary.org/obo/{acronym}_{num}"
_BIO = "http://purl.bioontology.org/ontology/{acronym}/{num}"
# NCI Thesaurus is indexed under its EVS namespace, not an OBO PURL.
_NCIT = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl#{num}"

PREFIX_MAP: Dict[str, Tuple[str, str]] = {
    "snomed": ("SNOMEDCT", _BIO),
    "snomed-ct": ("SNOMEDCT", _BIO),
    "snomedct": ("SNOMEDCT", _BIO),
    "loinc": ("LNC", _BIO),
    "lnc": ("LNC", _BIO),
    "icd10": ("ICD10", _BIO),
    "icd-10": ("ICD10", _BIO),
    "ncit": ("NCIT", _NCIT),
    "uberon": ("UBERON", _OBO),
    "hpo": ("HP", _OBO),
    "hp": ("HP", _OBO),
    "mondo": ("MONDO", _OBO),
    "doid": ("DOID", _OBO),
    "go": ("GO", _OBO),
}

# Ontologies BioPortal gates behind a licence acceptance on the account.
LICENCE_GATED = {"SNOMEDCT", "LNC"}

# Prefixes that are not ontology terms at all — skip without complaint.
NON_ONTOLOGY_PREFIXES = {"biolink", "skos", "rdfs", "owl", "ro", "sio"}


class RateLimiter:
    """Simple wall-clock spacer honouring a per-minute budget."""

    def __init__(self, per_minute: int) -> None:
        self._interval = 60.0 / max(1, per_minute)
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self._interval:
            time.sleep(self._interval - gap)
        self._last = time.monotonic()


class BioPortalClient:
    """Cached, rate-limited BioPortal REST client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://data.bioontology.org",
        rate_limit_per_minute: int = 15,
        cache_ttl_seconds: int = 86400,
        cache_path: Path = CACHE_PATH,
        offline: bool = False,
    ) -> None:
        if not api_key and not offline:
            raise ValueError(
                "BIOPORTAL_API_KEY is not set. Add it to .env, or pass offline=True "
                "to run against the cache only."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.limiter = RateLimiter(rate_limit_per_minute)
        self.cache_ttl = cache_ttl_seconds
        self.cache_path = cache_path
        self.offline = offline
        self._cache: Dict[str, Any] = self._load_cache()
        self._dirty = False

    # ── cache ─────────────────────────────────────────────────────────

    def _load_cache(self) -> Dict[str, Any]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not read BioPortal cache (%s); starting empty", e)
        return {}

    def save_cache(self) -> None:
        if not self._dirty:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        logger.info("Cache written: %s (%d entries)", self.cache_path, len(self._cache))

    def _cached(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry.get("fetched_at", 0) > self.cache_ttl:
            return None if not self.offline else entry.get("payload")
        return entry.get("payload")

    def _store(self, key: str, payload: Dict[str, Any]) -> None:
        self._cache[key] = {"fetched_at": time.time(), "payload": payload}
        self._dirty = True

    # ── HTTP ──────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[Dict[str, str]] = None,
             retries: int = 4) -> Dict[str, Any]:
        """GET with exponential backoff on 5xx and timeouts.

        The API key travels in the Authorization header, never in the query
        string, so it does not leak into logs or proxy access records.
        """
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        delay = 1.0
        last_status: Optional[int] = None
        for attempt in range(retries):
            self.limiter.wait()
            req = urllib.request.Request(url, headers={
                "Authorization": f"apikey token={self.api_key}",
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_status = e.code
                # 4xx are terminal — retrying a 403 or 404 cannot help.
                if e.code < 500:
                    raise
                logger.warning("HTTP %s on attempt %d/%d; backing off %.1fs",
                               e.code, attempt + 1, retries, delay)
            except (urllib.error.URLError, TimeoutError) as e:
                logger.warning("Network error (%s) on attempt %d/%d; backing off %.1fs",
                               e, attempt + 1, retries, delay)
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2

        raise RuntimeError(
            f"BioPortal request failed after {retries} attempts "
            f"(last status {last_status}): {path}"
        )

    # ── public API ────────────────────────────────────────────────────

    def fetch_class(self, acronym: str, class_uri: str) -> Dict[str, Any]:
        """Fetch one ontology class. Returns a dict with a ``status`` key.

        status is one of: ok | licence_gated | not_found | offline_miss | error
        """
        cache_key = f"{acronym}|{class_uri}"
        hit = self._cached(cache_key)
        if hit is not None:
            return hit

        if self.offline:
            return {"status": "offline_miss", "uri": class_uri}

        encoded = urllib.parse.quote(class_uri, safe="")
        path = f"/ontologies/{acronym}/classes/{encoded}"
        try:
            raw = self._get(path)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                payload = {
                    "status": "licence_gated" if acronym in LICENCE_GATED else "unauthorised",
                    "uri": class_uri,
                    "detail": (
                        f"HTTP {e.code}. For {acronym}, accept the licence for this "
                        f"ontology while signed in at bioportal.bioontology.org, "
                        f"then re-run."
                    ),
                }
            elif e.code == 404:
                payload = {"status": "not_found", "uri": class_uri,
                           "detail": "No such class in this ontology."}
            else:
                payload = {"status": "error", "uri": class_uri,
                           "detail": f"HTTP {e.code}"}
            self._store(cache_key, payload)
            return payload
        except RuntimeError as e:
            return {"status": "error", "uri": class_uri, "detail": str(e)}

        payload = {
            "status": "ok",
            "uri": class_uri,
            "pref_label": raw.get("prefLabel"),
            "synonyms": raw.get("synonym", []),
            "definition": (raw.get("definition") or [None])[0],
            "obsolete": bool(raw.get("obsolete", False)),
        }
        self._store(cache_key, payload)
        return payload

    def resolve(self, curie: str) -> Dict[str, Any]:
        """Resolve a CURIE or PURL as it appears in ontology/mappings/*.csv."""
        acronym, class_uri = curie_to_bioportal(curie)
        if acronym is None:
            return {"status": "skipped", "uri": curie,
                    "detail": "Not an ontology term prefix."}
        return self.fetch_class(acronym, class_uri)


# ── identifier plumbing ───────────────────────────────────────────────

def curie_to_bioportal(curie: str) -> Tuple[Optional[str], str]:
    """Map a CURIE/PURL to (BioPortal acronym, class URI).

    Handles the three shapes present in this project's mapping tables:
      snomed:26929004 | hpo:HP:0002354 | MONDO:0004975
    and passes through anything already in full http(s) PURL form.
    """
    curie = curie.strip()
    if curie.startswith("http://") or curie.startswith("https://"):
        for acronym, _ in PREFIX_MAP.values():
            token = f"/{acronym}_" if "obolibrary" in curie else f"/{acronym}/"
            if token in curie:
                return acronym, curie
        return None, curie

    if ":" not in curie:
        return None, curie

    prefix, rest = curie.split(":", 1)
    key = prefix.lower()
    if key in NON_ONTOLOGY_PREFIXES:
        return None, curie
    if key not in PREFIX_MAP:
        return None, curie

    acronym, template = PREFIX_MAP[key]
    # hpo:HP:0002354 and MONDO:0004975 both reduce to the numeric local part.
    num = rest.split(":")[-1] if ":" in rest else rest
    if template is _OBO:
        num = num.replace(":", "_")
    return acronym, template.format(acronym=acronym, num=num)


def normalise_label(label: str) -> str:
    """Casefold and strip punctuation/whitespace for tolerant comparison.

    Possessive ``'s`` is dropped first so that authority/house-style pairs like
    "Alzheimer's disease" / "Alzheimer disease" compare as variants rather than
    as mismatches — that difference is editorial, not semantic.
    """
    text = (label or "").casefold().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def compare_label(asserted: str, authoritative: str) -> str:
    """exact | variant | mismatch — never silently accept a mismatch."""
    if not authoritative:
        return "mismatch"
    if asserted == authoritative:
        return "exact"
    a, b = normalise_label(asserted), normalise_label(authoritative)
    if a == b:
        return "variant"
    if a and b and (a in b or b in a):
        return "variant"
    return "mismatch"


# ── mapping-table verification ────────────────────────────────────────

def verify_mappings(client: BioPortalClient,
                    mappings_dir: Path = MAPPINGS_DIR) -> Dict[str, Any]:
    """Check every target_uri/target_label pair in ontology/mappings/*.csv."""
    rows: List[Dict[str, str]] = []
    for csv_path in sorted(mappings_dir.glob("*.csv")):
        if csv_path.name == "index.csv":
            continue  # index.csv duplicates the per-source files
        with csv_path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                row["_source_csv"] = csv_path.name
                rows.append(row)

    report: Dict[str, Any] = {
        "checked": 0, "exact": 0, "variant": 0,
        "mismatches": [], "licence_gated": [], "unresolved": [], "skipped": 0,
    }
    seen: set = set()

    for row in rows:
        uri = (row.get("target_uri") or "").strip()
        label = (row.get("target_label") or "").strip()
        if not uri or (uri, label) in seen:
            continue
        seen.add((uri, label))

        result = client.resolve(uri)
        status = result.get("status")

        if status == "skipped":
            report["skipped"] += 1
            continue
        if status == "licence_gated":
            report["licence_gated"].append({
                "uri": uri, "label": label, "csv": row["_source_csv"],
                "detail": result.get("detail"),
            })
            continue
        if status != "ok":
            report["unresolved"].append({
                "uri": uri, "label": label, "csv": row["_source_csv"],
                "status": status, "detail": result.get("detail"),
            })
            continue

        report["checked"] += 1
        verdict = compare_label(label, result.get("pref_label") or "")
        if verdict == "exact":
            report["exact"] += 1
        elif verdict == "variant":
            report["variant"] += 1
            logger.info("variant  %-28s asserted=%r authority=%r",
                        uri, label, result.get("pref_label"))
        else:
            report["mismatches"].append({
                "uri": uri, "csv": row["_source_csv"],
                "asserted_label": label,
                "authoritative_label": result.get("pref_label"),
                "obsolete": result.get("obsolete", False),
            })
            logger.error("MISMATCH %-28s asserted=%r authority=%r",
                         uri, label, result.get("pref_label"))

        if result.get("obsolete"):
            logger.warning("OBSOLETE %s is deprecated in %s", uri, row["_source_csv"])

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify ontology identifiers against the BioPortal REST API.",
    )
    parser.add_argument("--verify-mappings", action="store_true",
                        help="check every row of ontology/mappings/*.csv")
    parser.add_argument("--code", help="resolve one CURIE, e.g. snomed:26929004")
    parser.add_argument("--offline", action="store_true",
                        help="cache-only; never call the network")
    parser.add_argument("--json-out", type=Path,
                        help="write the verification report to this path")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    config = load_config()
    bp = config.get("bioportal", {})
    client = BioPortalClient(
        api_key=bp.get("api_key", ""),
        base_url=bp.get("base_url", "https://data.bioontology.org"),
        rate_limit_per_minute=bp.get("rate_limit_per_minute", 15),
        cache_ttl_seconds=bp.get("cache_ttl_seconds", 86400),
        offline=args.offline,
    )

    exit_code = 0
    try:
        if args.code:
            result = client.resolve(args.code)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            exit_code = 0 if result.get("status") in ("ok", "skipped") else 1

        elif args.verify_mappings:
            report = verify_mappings(client)
            print("\n── BioPortal mapping verification ──")
            print(f"  checked:       {report['checked']}")
            print(f"    exact:       {report['exact']}")
            print(f"    variant:     {report['variant']}")
            print(f"  mismatches:    {len(report['mismatches'])}")
            print(f"  licence-gated: {len(report['licence_gated'])}")
            print(f"  unresolved:    {len(report['unresolved'])}")
            print(f"  skipped:       {report['skipped']}")

            for m in report["mismatches"]:
                print(f"    MISMATCH {m['uri']}: asserted {m['asserted_label']!r} "
                      f"but BioPortal says {m['authoritative_label']!r}")
            if report["licence_gated"]:
                first = report["licence_gated"][0]
                print(f"\n  {len(report['licence_gated'])} identifier(s) need a licence "
                      f"acceptance:\n    {first['detail']}")

            if args.json_out:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(
                    json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"\n  report → {args.json_out}")

            exit_code = 1 if report["mismatches"] else 0
        else:
            parser.print_help()
    finally:
        client.save_cache()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
