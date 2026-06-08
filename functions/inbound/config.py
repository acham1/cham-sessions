from pathlib import Path

import yaml

_config = None


def load_config() -> dict:
    global _config
    if _config is not None:
        return _config

    # Cloud Functions: source deployed to /workspace
    candidates = [
        Path("/workspace/config.yaml"),
    ]
    # Local dev: walk up from this file
    p = Path(__file__).resolve().parent
    while p != p.parent:
        candidates.append(p / "config.yaml")
        p = p.parent

    for path in candidates:
        if path.exists():
            _config = yaml.safe_load(path.read_text())
            return _config

    raise FileNotFoundError("config.yaml not found")
