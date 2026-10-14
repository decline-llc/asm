"""Read-only dependency hints: no credentials, network, browser or tool launch."""
import importlib.util
import os
from pathlib import Path
import shutil


def _result(status, reason):
    return {"status": status, "reason": reason}


def _wsl_distribution(distro):
    if not shutil.which("wsl.exe"):
        return _result("blocked", "wsl_launcher_missing")
    if os.name != "nt":
        return _result("unverified", "wsl_distribution_and_binary_checked_at_execution")
    import winreg
    names = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Lxss") as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                with winreg.OpenKey(root, winreg.EnumKey(root, index)) as entry:
                    names.append(winreg.QueryValueEx(entry, "DistributionName")[0])
    except FileNotFoundError:
        return _result("unverified", "wsl_distribution_inventory_not_visible")
    except OSError:
        return _result("unverified", "wsl_distribution_inventory_unavailable")
    if not names:
        return _result("unverified", "wsl_distribution_inventory_not_visible")
    if distro not in names:
        return _result("blocked", "configured_wsl_distribution_missing")
    return _result("unverified", "wsl_distribution_present_binary_checked_at_execution")


def dependency_status(config, capability, tool):
    if config["execution"]["source"] == "replay":
        return _result("ready", "saved_evidence_only_no_live_dependencies")
    if capability == "service_probe" and config["plan"]["params"].get(capability, {}).get("approved_script_categories"):
        return _result("blocked", "service_scripts_require_separate_deep_service_probe_and_approved_probes")
    if not tool or tool.startswith("planned_"):
        return _result("blocked", "selected_tool_adapter_not_integrated")
    params = dict(config["plan"]["params"].get(capability, {}))
    params.update(params.get("tool_options", {}).get(tool, {}))
    if tool == "oneforall_passive" and params.get("oneforall_report") and params.get("oneforall_observations"):
        return _result("unverified", "configured_saved_collector_inputs_checked_at_execution")
    if tool == "nuclei" and not params.get("approved_templates"):
        return _result("blocked", "approved_http_templates_required")
    if tool == "wafw00f" and "waf_fingerprint" not in params.get("approved_checks", []):
        return _result("blocked", "waf_fingerprint_check_not_selected")
    if tool in {"nmap", "masscan", "subfinder", "naabu", "a_scan", "dig_probe", "dnsx", "oneforall_passive", "httpx", "ffuf", "katana", "gowitness", "nuclei", "wafw00f"}:
        return _wsl_distribution(os.getenv("WSL_DISTRO", "Ubuntu"))
    if tool == "playwright":
        if importlib.util.find_spec("playwright") is None:
            return _result("blocked", "playwright_package_missing")
        configured = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        if configured == "0":
            import playwright
            directory = Path(playwright.__file__).parent / "driver/package/.local-browsers"
        else:
            directory = Path(configured) if configured else (
                Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright" if os.name == "nt"
                else Path.home() / ".cache/ms-playwright")
        binaries = ("chromium-*/chrome-win/chrome.exe", "chromium-*/chrome-win64/chrome.exe",
                    "chromium_headless_shell-*/chrome-win/headless_shell.exe",
                    "chromium_headless_shell-*/chrome-win64/headless_shell.exe",
                    "chromium_headless_shell-*/chrome-linux/headless_shell",
                    "chromium-*/chrome-linux/chrome")
        if not any(path.is_file() for pattern in binaries for path in directory.glob(pattern)):
            return _result("blocked", "playwright_chromium_binary_missing")
        return _result("ready", "playwright_package_and_chromium_present_launch_checked_at_execution")
    if tool in {"dnspython", "dnspython_dictionary"}:
        return _result("ready", "dnspython_present") if importlib.util.find_spec("dns") else _result("blocked", "dnspython_missing")
    if capability == "search":
        return _result("unverified", "backend_credentials_and_shared_quota_checked_at_execution")
    if capability in {"company_lookup", "osint", "passive_supply_chain"} or tool == "oneforall_passive":
        return _result("unverified", "configured_source_inputs_checked_at_execution")
    return _result("ready", "native_adapter_dependencies_present")
