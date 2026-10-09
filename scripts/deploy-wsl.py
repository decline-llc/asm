"""Bootstrap transfer, pure stdlib; invoked from Windows Python, never /mnt I/O."""
import argparse
import os
import shlex
import subprocess
from pathlib import Path


def deploy(distro, user="", install=True):
    prefix = ["wsl.exe", "-d", distro] + (["-u", user] if user else [])
    home = subprocess.check_output(prefix + ["--", "bash", "-lc", 'printf "%s" "$HOME"']).decode().strip()
    if not home.startswith("/home/") and home != "/root":
        raise RuntimeError("Unexpected WSL home")
    workspace = home + "/asm-ws"
    subprocess.run(prefix + ["--", "mkdir", "-p", workspace + "/tools"], check=True)
    project = Path(__file__).resolve().parents[1]
    files = {"scripts/wsl-setup.sh": "wsl-setup.sh", "tools/tool-lock.json": "tool-lock.json",
             "tools/scanners/a_scan.py": "tools/a_scan.py"}
    for source, dest in files.items():
        data = (project / source).read_bytes().replace(b"\r\n", b"\n")
        subprocess.run(prefix + ["--", "bash", "-lc", "cat > " + shlex.quote(workspace + "/" + dest)],
                       input=data, check=True)
    if install:
        script = f"export ASM_WS={shlex.quote(workspace)}; bash {shlex.quote(workspace + '/wsl-setup.sh')}"
        try:
            subprocess.run(["wsl.exe", "-d", distro, "-u", "root", "--", "bash", "-lc", script], check=True)
        finally:
            if home.startswith("/home/"):
                owner = subprocess.check_output(prefix + ["--", "id", "-un"]).decode().strip()
                subprocess.run(["wsl.exe", "-d", distro, "-u", "root", "--", "chown", "-R",
                                owner + ":" + owner, workspace], check=True)
    return workspace


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--distro", default=os.getenv("WSL_DISTRO", "Ubuntu-22.04"))
    parser.add_argument("--user", default=os.getenv("WSL_USER", ""))
    parser.add_argument("--transfer-only", action="store_true")
    args = parser.parse_args()
    print(deploy(args.distro, args.user, not args.transfer_only))
