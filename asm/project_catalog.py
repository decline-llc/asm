"""Business purpose is independent of live/replay execution and authorization."""
import re
from pathlib import Path


PURPOSE_DIRECTORIES = {"investigation": "investigations", "validation": "validation", "demo": "demo"}
LEGACY_VALIDATION = re.compile(
    r"^(?:ui_fixture_\d{8}_\d{6}|lab_native_\d{8}_\d{6}|"
    r"replay_saved_\d{8}_\d{6}_\d+|"
    r"m5_(?:auth_audit|takeover_probe|vulnerability_check|js_analysis|web_crawl)_\d{8}_\d{6})$"
)


def project_purpose(config, project_id="", path=None):
    explicit = config.get("project_purpose")
    if explicit is not None:
        if not isinstance(explicit, str) or explicit not in PURPOSE_DIRECTORIES:
            raise ValueError("project_purpose must be investigation, validation or demo")
        return explicit
    if path:
        # Folder membership persists classification without rewriting historic configuration hashes.
        parent = Path(path).parent.name
        for purpose, directory in PURPOSE_DIRECTORIES.items():
            if parent == directory:
                return purpose
    identifier = project_id or config.get("profile", "")
    if identifier in {"test", "lab_full"} or LEGACY_VALIDATION.fullmatch(identifier):
        return "validation"
    if identifier == "demo":
        return "demo"
    return "investigation"


def profile_directory(root, purpose):
    if purpose not in PURPOSE_DIRECTORIES:
        raise ValueError("Unknown project purpose")
    return Path(root) / "profiles" / PURPOSE_DIRECTORIES[purpose]
