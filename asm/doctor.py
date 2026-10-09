import importlib.util
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

from .bridge import Bridge, decode


def doctor(root=None):
    root = Path(root or Path.cwd()).resolve()
    bridge = Bridge()
    checks = []
    def check(number, name, callback, repair):
        try:
            detail = callback()
            ok = bool(detail)
            detail = str(detail)
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        checks.append({"id": number, "name": name, "ok": ok, "detail": detail, "repair": "" if ok else repair})

    def wsl(script, root_user=False):
        return decode(bridge.control(script, root=root_user, timeout=30).stdout).strip()

    check(1, "WSL2", lambda: shutil.which("wsl.exe") and re.search(r"\b2\b", decode(
        subprocess.run(["wsl.exe", "-l", "-v"], capture_output=True, timeout=15).stdout)), "Install WSL2 and reboot")
    check(2, "Distribution", lambda: wsl("uname -s"), "Set WSL_DISTRO to a distro from wsl --list --verbose")
    check(3, "Root", lambda: wsl("id -u", True) == "0", "Check wsl -d <distro> -u root -- id")
    check(4, "Locale", lambda: wsl("LC_ALL=C.UTF-8 locale charmap") == "UTF-8", "Install locales with C.UTF-8")
    check(5, "Nmap >=7.90", lambda: version_at_least(wsl("nmap --version"), (7, 90)), "Run asm init-wsl")
    check(6, "Masscan", lambda: wsl("command -v masscan"), "Run asm init-wsl")
    check(7, "DNS network", lambda: wsl("dig +short +time=3 +tries=1 example.com A"), "Check WSL DNS/proxy connectivity")
    check(8, "Eight pinned binaries", lambda: binary_versions(bridge), "Run asm init-wsl; inspect manifests and checksums")
    check(9, "OneForAll", lambda: wsl(f"cd {bridge.workspace}/tools/OneForAll && .venv/bin/python -c 'import oneforall; print(1)'"),
          "Repair OneForAll's isolated venv")
    check(10, "SecLists", lambda: wsl(f"test -f {bridge.workspace}/wordlists/SecLists/Discovery/Web-Content/raft-medium-words.txt && echo yes"),
          "Run asm init-wsl to install the pinned SecLists release")
    check(11, "Fallback scanner", lambda: wsl(f"python3 {bridge.workspace}/tools/a_scan.py --help"), "Run asm init-wsl")
    check(12, "wafw00f", lambda: wsl(f"{bridge.workspace}/tools/wafw00f/.venv/bin/wafw00f --version"), "Run asm init-wsl")
    check(13, "Windows Python >=3.11", lambda: sys.version_info >= (3, 11) and sys.platform == "win32",
          "Create .venv with native Windows Python 3.11+")
    check(14, "Python dependencies", lambda: all(importlib.util.find_spec(v) for v in
          ("click", "httpx", "dns", "openpyxl", "playwright", "dotenv", "yaml", "pytest", "tldextract")),
          "pip install -e .[dev,browser]")
    check(15, "Playwright Chromium", chromium_installed, "python -m playwright install chromium")
    check(16, ".env template", lambda: env_valid(root), "Copy .env.example to .env; fill paired FOFA_EMAIL/FOFA_KEY")
    check(17, "Path and LF", lambda: " " not in str(root) and "onedrive" not in str(root).lower()
          and all(b"\r\n" not in p.read_bytes() for p in (root / "scripts").glob("*.sh")),
          "Use a space-free path outside OneDrive; normalize .sh line endings to LF")
    check(18, "Disk and bridge latency", lambda: disk_latency(bridge, root), "Keep >2GB Windows and >5GB WSL free; check WSL load")
    return checks


def version_at_least(text, expected):
    match = re.search(r"(?:version\s+)?(\d+)\.(\d+)", text, re.I)
    return bool(match and tuple(map(int, match.groups())) >= expected)


def binary_versions(bridge):
    results = []
    for tool in ("subfinder", "dnsx", "httpx", "naabu", "nuclei", "katana", "ffuf", "gowitness"):
        args = ["-V"] if tool == "ffuf" else ["version"] if tool == "gowitness" else ["-version"]
        reply = bridge.control(bridge.command(tool, args, timeout=10), timeout=20)
        results.append(decode(reply.stdout + reply.stderr).strip())
    return " | ".join(results)


def chromium_installed():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        return Path(playwright.chromium.executable_path).is_file()


def env_valid(root):
    path = root / ".env"
    if not path.is_file():
        return False
    keys = dotenv_values(path)
    required = set(dotenv_values(root / ".env.example"))
    return required <= set(keys) and bool(keys.get("FOFA_EMAIL")) == bool(keys.get("FOFA_KEY"))


def disk_latency(bridge, root):
    win_free = shutil.disk_usage(root.anchor).free
    wsl_free = int(decode(bridge.control('df -B1 --output=avail "$HOME" | tail -1').stdout).strip())
    times = []
    for _ in range(10):
        start = time.perf_counter()
        bridge.control("true")
        times.append(time.perf_counter() - start)
    average = sum(times) / len(times)
    if win_free < 2 * 1024**3 or wsl_free < 5 * 1024**3 or average >= 1:
        return False
    return f"Windows free={win_free//1024**3}GB, WSL free={wsl_free//1024**3}GB, mean={average:.3f}s"
