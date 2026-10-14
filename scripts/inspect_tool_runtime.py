"""Inspect an existing WSL tool workspace without installing or scanning."""
import argparse
import os
import subprocess

from asm.bridge import decode


INSPECT = r'''
import hashlib, json, os, pathlib, shutil, subprocess
home = pathlib.Path.home()
workspace = home / "asm-ws"
paths = [workspace / "bin", workspace / "tools/wafw00f/.venv/bin"]
os.environ["PATH"] = ":".join(map(str, paths)) + ":" + os.environ["PATH"]
result = {"user": subprocess.check_output(["id", "-un"], text=True).strip(),
          "home": str(home), "workspace": str(workspace), "exists": workspace.is_dir(),
          "tools": {}, "resources": {}}
versions = {"subfinder": ["-version", "-duc"], "dnsx": ["-version", "-duc"],
            "httpx": ["-version", "-duc"], "naabu": ["-version", "-duc"],
            "nuclei": ["-version", "-duc"], "katana": ["-version", "-duc"],
            "ffuf": ["-V"], "gowitness": ["version"], "nmap": ["--version"],
            "masscan": ["--version"], "dig": ["-v"], "wafw00f": ["-V"],
            "google-chrome": ["--version"], "python3": ["--version"],
            "unshare": ["--version"], "ip": ["-V"], "openssl": ["version"]}
for tool, args in versions.items():
    executable = shutil.which(tool)
    item = {"path": executable}
    if executable:
        try:
            p = subprocess.run([executable, *args], capture_output=True, text=True, timeout=8)
            item.update(rc=p.returncode, version=(p.stdout + p.stderr).strip()[:1200])
        except subprocess.TimeoutExpired:
            item["error"] = "version query timed out"
    result["tools"][tool] = item
for relative in ["tools/a_scan.py", "tools/OneForAll", "tools/oneforall", "vendor/OneForAll",
                 "tools/SecLists", "wordlists/SecLists", "vendor/SecLists", "tool-lock.json"]:
    path = workspace / relative
    item = {"exists": path.exists()}
    if path.is_file():
        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir() and (path / ".git").exists():
        p = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=8)
        item["commit"] = p.stdout.strip()
    result["resources"][relative] = item
print(json.dumps(result, ensure_ascii=True))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distro", default=os.getenv("WSL_DISTRO", "Ubuntu"))
    args = parser.parse_args()
    registered = subprocess.run(["wsl.exe", "--list", "--verbose"], capture_output=True, check=True)
    print(decode(registered.stdout), flush=True)
    result = subprocess.run(["wsl.exe", "-d", args.distro, "--", "python3", "-"],
                            input=INSPECT.encode(), capture_output=True)
    print(decode(result.stdout), flush=True)
    if result.stderr:
        print(decode(result.stderr), flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
