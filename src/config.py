import os
import sys
import yaml
import copy

def _get_config_path_from_args():
    for i, arg in enumerate(sys.argv):
        if arg in ["--config", "-c"] and i + 1 < len(sys.argv):
            return os.path.abspath(sys.argv[i+1])
    return None

# --- APPLICATION IDENTITY ---
APP_NAME = "deep-research-agent"          # Used for config/log folders
APP_TITLE = "Deep Research Agent"         # Used for UI branding
APP_DESCRIPTION = "Hierarchical research agent: Orchestrator → Searcher → Analyzer, with post-research Reviewer"

_DEFAULT_CONFIG_DIR = os.path.expanduser(f"~/.{APP_NAME}")
_CONFIG_PATH = _get_config_path_from_args() or os.path.join(_DEFAULT_CONFIG_DIR, "config.yaml")

_DEFAULTS = {
    "api": {
        "openai_base_urls": ["http://localhost:8080/v1"],
        "openai_model": "local-model",
    },
    "settings": {
        "enable_thinking": False,
        "concurrency": {
            "per_endpoint_cap": 1
        },
        "quotas": {},
        "workspace": {
            "type": "memory",
            "dir": "~/.{APP_NAME}/workspace"
        }
    }
}

cfg: dict = {}

def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge overlay into base, recursively for nested dicts."""
    result = copy.deepcopy(base)
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def load_config() -> dict:
    """Load config from YAML file, falling back to defaults for missing keys."""
    global cfg
    file_cfg = {}

    if not os.path.exists(_CONFIG_PATH):
        bundled_config = os.path.join(os.path.dirname(__file__), "config_template.yaml")
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        if os.path.exists(bundled_config):
            import shutil
            shutil.copy(bundled_config, _CONFIG_PATH)
        else:
            with open(_CONFIG_PATH, "w") as f:
                yaml.dump(_DEFAULTS, f, default_flow_style=False, sort_keys=False)

    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r") as f:
            file_cfg = yaml.safe_load(f) or {}

    cfg = _deep_merge(_DEFAULTS, file_cfg)

    # Expand APP_NAME placeholder and tilde (~) in workspace directory
    if "settings" in cfg and "workspace" in cfg["settings"]:
        ws = cfg["settings"]["workspace"]
        if "dir" in ws and isinstance(ws["dir"], str):
            dir_str = ws["dir"].replace("{APP_NAME}", APP_NAME)
            ws["dir"] = os.path.abspath(os.path.expanduser(dir_str))

    # Apply fast-test overlay if enabled
    settings = cfg.get("settings", {})
    fast_test = settings.get("fast_test", {})
    if isinstance(fast_test, dict) and fast_test.get("enabled", False):
        overrides = fast_test.get("overrides", {})
        if isinstance(overrides, dict):
            cfg["settings"] = _deep_merge(cfg["settings"], overrides)
            print("[config] FAST-TEST MODE ACTIVE — quotas reduced", file=sys.stderr)

    # Overlay API keys from environment if set.
    # Env vars are used ONLY if the corresponding value in config is still at its default.
    # This makes config.yaml the primary source, with env vars as fallbacks for unset values.
    if os.environ.get("OPENAI_MODEL") and cfg["api"]["openai_model"] == _DEFAULTS["api"]["openai_model"]:
        cfg["api"]["openai_model"] = os.environ["OPENAI_MODEL"]

    # --- Normalise endpoint URL list ---
    # `openai_base_urls` is the single source of truth for endpoints.
    # Accept a bare string as a one-element list (operator convenience),
    # drop blanks, and strip whitespace. Order is preserved.
    api_cfg = cfg.setdefault("api", {})
    raw_urls = api_cfg.get("openai_base_urls")
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    if not isinstance(raw_urls, list):
        raw_urls = []
    urls = []
    for u in raw_urls:
        if isinstance(u, str) and u.strip():
            s = u.strip()
            if s not in urls:
                urls.append(s)
    if not urls:
        raise ValueError(
            "config error: api.openai_base_urls must contain at least one "
            "endpoint URL (e.g. http://192.168.68.69:1234/v1)"
        )
    api_cfg["openai_base_urls"] = urls

    # per_endpoint_cap must be a positive int
    conc = cfg.setdefault("settings", {}).setdefault("concurrency", {})
    cap = conc.get("per_endpoint_cap", 1)
    if not isinstance(cap, int) or cap < 1:
        raise ValueError(
            f"config error: settings.concurrency.per_endpoint_cap must be a "
            f"positive integer, got {cap!r}"
        )
    conc["per_endpoint_cap"] = cap

    return cfg

def save_config() -> None:
    """Persist the current config dict back to config.yaml."""
    save_data = copy.deepcopy(cfg)

    # Strip out sensitive API keys before writing if any are stored in keys
    if "api" in save_data:
        save_data["api"].pop("openai_api_key", None)

    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(save_data, f, default_flow_style=False, sort_keys=False)

# Auto-initialize on import so it's globally available
load_config()
