"""
ADNI Knowledge Graph — Environment & Config Loader

Loads secrets from .env, non-secret settings from config.yaml, merges them.
Zero external dependencies (no python-dotenv needed).

Usage:
    from utils.env_loader import load_config, validate_secrets

    config = load_config()                          # auto-finds config.yaml + .env
    config = load_config("path/to/config.yaml")     # explicit config path

    # Secrets are merged into the config dict:
    config["neo4j_password"]              # from .env → NEO4J_PASSWORD
    config["bioportal"]["api_key"]        # from .env → BIOPORTAL_API_KEY
    config["who_icd"]["client_id"]        # from .env → WHO_ICD_CLIENT_ID

    # Non-secret settings stay from config.yaml:
    config["max_workers"]                 # 16
    config["bioportal"]["base_url"]       # https://data.bioontology.org

    # Validate before running:
    warnings = validate_secrets(config, phase="semantic")
    for w in warnings:
        print(f"⚠️  {w}")
"""

import os
import logging
from pathlib import Path
from typing import Optional, Union

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Locate project root
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk up from this file's directory to find config.yaml or .git."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "config.yaml").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()


# ---------------------------------------------------------------------------
# .env parser (no dependency on python-dotenv)
# ---------------------------------------------------------------------------

def _parse_dotenv(env_path: Path) -> dict:
    """
    Minimal .env parser. Handles:
      KEY=value
      KEY="quoted value"
      KEY='quoted value'
      # comments and empty lines
    """
    env_vars = {}
    if not env_path.exists():
        return env_vars

    with open(env_path, "r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                logger.warning(f".env line {line_num}: no '=' found, skipping")
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]

            env_vars[key] = value

    return env_vars


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load_config(
    config_path: Optional[Union[str, Path]] = None,
    env_path: Optional[Union[str, Path]] = None,
) -> dict:
    """
    Load config.yaml and merge secrets from .env.

    Priority (highest → lowest):
      1. Real environment variables (os.environ)
      2. .env file
      3. config.yaml values

    Returns a merged dict ready for pipeline use.
    """

    # --- Resolve paths ---
    if config_path is None:
        config_path = PROJECT_ROOT / "config.yaml"
    config_path = Path(config_path)

    if env_path is None:
        env_path = PROJECT_ROOT / ".env"
    env_path = Path(env_path)

    # --- Load config.yaml ---
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    logger.info(f"Loaded config from {config_path}")

    # --- Load .env ---
    dotenv_vars = _parse_dotenv(env_path)
    if dotenv_vars:
        logger.info(f"Loaded {len(dotenv_vars)} vars from {env_path}")
    else:
        logger.warning(
            f"No .env file found at {env_path}. "
            "Secrets must come from environment variables or config.yaml."
        )

    def _env(key: str, fallback: Optional[str] = None) -> Optional[str]:
        """Get value: os.environ > .env > fallback."""
        val = os.environ.get(key) or dotenv_vars.get(key) or fallback
        # Treat placeholder values as unset
        placeholders = {
            "your_neo4j_password",
            "your_password",
            "your_bioportal_api_key_here",
            "your_who_icd_client_id_here",
            "your_who_icd_client_secret_here",
        }
        if val and val.strip() in placeholders:
            return None
        return val if val and val.strip() else None

    # --- Merge secrets into config ---

    # Database credentials
    neo4j_pw = _env("NEO4J_PASSWORD")
    if neo4j_pw:
        config["neo4j_password"] = neo4j_pw

    es_user = _env("ELASTICSEARCH_USERNAME")
    es_pass = _env("ELASTICSEARCH_PASSWORD")
    if es_user:
        config.setdefault("elasticsearch", {})["username"] = es_user
    if es_pass:
        config.setdefault("elasticsearch", {})["password"] = es_pass

    # BioPortal API — merge key from .env into config section
    bp_key = _env("BIOPORTAL_API_KEY")
    bp_section = config.setdefault("bioportal", {})
    if bp_key:
        bp_section["api_key"] = bp_key
    # Also check legacy location: updated_config had bio_portal.key
    elif config.get("bio_portal", {}).get("key"):
        bp_section["api_key"] = config["bio_portal"]["key"]
        logger.warning(
            "Found API key in config.yaml [bio_portal.key]. "
            "Move it to .env as BIOPORTAL_API_KEY and remove from config.yaml."
        )
    bp_section.setdefault("base_url", "https://data.bioontology.org")
    bp_section.setdefault("rate_limit_per_minute", 15)
    bp_section.setdefault("cache_ttl_seconds", 86400)

    # WHO ICD API — merge client_id/secret from .env
    icd_id = _env("WHO_ICD_CLIENT_ID")
    icd_secret = _env("WHO_ICD_CLIENT_SECRET")
    icd_section = config.setdefault("who_icd", {})
    if icd_id:
        icd_section["client_id"] = icd_id
    if icd_secret:
        icd_section["client_secret"] = icd_secret
    icd_section.setdefault("token_url", "https://icdaccessmanagement.who.int/connect/token")
    icd_section.setdefault("api_url", "https://id.who.int/icd")
    icd_section.setdefault("release", "2019")
    icd_section.setdefault("api_version", "v2")
    icd_section.setdefault("rate_limit_per_minute", 30)
    icd_section.setdefault("cache_ttl_seconds", 604800)

    # AlzKB — no secrets needed, just defaults
    alzkb_section = config.setdefault("alzkb", {})
    alzkb_section.setdefault("github_url", "https://github.com/EpistasisLab/AlzKB")
    alzkb_section.setdefault("max_concepts", 200)
    alzkb_section.setdefault("cache_dir", "ontology/alzkb_cache")

    # Causal discovery defaults
    config.setdefault("causal", {
        "alpha": 0.05,
        "algorithms": ["PC", "FCI", "GES"],
        "consensus_threshold": 2,
        "independence_test": "kci",
        "max_missing_pct": 0.5,
        "imputation_method": "mice",
        "feature_selection": True,
        "output_dir": "causal",
    })

    # New step flags (Steps 17–28) — default False (opt-in)
    new_step_defaults = {
        "run_apply_constraints": False,
        "run_ontology_properties": False,
        "run_icd10_integration": False,
        "run_ontology_layer": False,
        "run_causal_feature_extraction": False,
        "run_causal_discovery": False,
        "run_embed_causal_edges": False,
        "run_alzkb_bridge": False,
        "run_evaluate_causality": False,
        "run_dowhy_inference": False,
        "run_final_stats": False,
        "run_thesis_figures": False,
    }
    for key, default in new_step_defaults.items():
        config.setdefault(key, default)

    return config


# ---------------------------------------------------------------------------
# Validate that required secrets are present
# ---------------------------------------------------------------------------

def validate_secrets(config: dict, phase: str = "all") -> list:
    """
    Check that required API keys are present for the given phase.
    Returns a list of warning messages (empty = all good).

    phase: "all" | "semantic" | "phase1" | "causal" | "phase2" | "validate" | "phase3"
    """
    warnings = []

    if phase in ("all", "semantic", "phase1"):
        bp_key = config.get("bioportal", {}).get("api_key")
        if not bp_key:
            warnings.append(
                "BIOPORTAL_API_KEY not set → Steps 18/20 will use hardcoded mappings only."
            )

        icd_id = config.get("who_icd", {}).get("client_id")
        if not icd_id:
            warnings.append(
                "WHO_ICD_CLIENT_ID not set → Step 19 will use static icd10_mappings.json only."
            )

    neo4j_pw = config.get("neo4j_password")
    if not neo4j_pw or neo4j_pw in ("your_password", "your_neo4j_password"):
        warnings.append(
            "NEO4J_PASSWORD still has placeholder value. Set it in .env."
        )

    return warnings


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = load_config()

    print("\n╔══════════════════════════════════════════╗")
    print("║   ADNI KG — Config & Secrets Summary     ║")
    print("╚══════════════════════════════════════════╝")

    def _status(val, placeholders=None):
        if placeholders is None:
            placeholders = set()
        if val and val not in placeholders:
            return "✅ SET"
        return "❌ NOT SET"

    pw_placeholders = {"your_password", "your_neo4j_password"}

    print(f"  Neo4j URI:        {cfg.get('neo4j_uri')}")
    print(f"  Neo4j password:   {_status(cfg.get('neo4j_password'), pw_placeholders)}")
    print(f"  BioPortal key:    {_status(cfg.get('bioportal', {}).get('api_key'))}")
    print(f"  WHO ICD ID:       {_status(cfg.get('who_icd', {}).get('client_id'))}")
    print(f"  WHO ICD secret:   {_status(cfg.get('who_icd', {}).get('client_secret'))}")
    print(f"  Base path:        {cfg.get('base_path')}")
    print(f"  Incremental:      {cfg.get('incremental')}")

    issues = validate_secrets(cfg)
    if issues:
        print(f"\n⚠️  {len(issues)} warning(s):")
        for w in issues:
            print(f"    → {w}")
    else:
        print("\n✅ All secrets configured — ready to run.")