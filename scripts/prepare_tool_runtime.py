"""Deploy the repository's pinned tools to an explicitly selected existing WSL.

This setup script never loads .env, reads account secrets, or scans a target.
Invoke with explicit approval for OS/package/network installation.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess

from asm.bridge import decode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distro", default=os.getenv("WSL_DISTRO", "Ubuntu"))
    args = parser.parse_args()
    if args.distro not in {"Ubuntu-24.04", "Ubuntu-22.04", "Ubuntu"}:
        parser.error("Choose a supported Ubuntu WSL distribution")
    result = subprocess.run(["wsl.exe", "--list", "--quiet"], capture_output=True, check=True)
    names = {line.strip() for line in decode(result.stdout).splitlines() if line.strip()}
    if args.distro not in names:
        parser.error("Selected WSL is not visible. Verify host permissions and wsl --list --verbose; "
                     "an empty restricted-process inventory does not prove WSL is absent. "
                     "This script never creates or unregisters distributions.")
    # Verify registration before any deployment mutation.
    subprocess.run(["wsl.exe", "--distribution", args.distro, "--", "true"], check=True)
    path = Path(__file__).with_name("deploy-wsl.py")
    spec = importlib.util.spec_from_file_location("asm_runtime_deployment", path)
    deployment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deployment)
    print(deployment.deploy(args.distro), flush=True)
    print("Runtime prepared. Start the backend with WSL_DISTRO=" + args.distro, flush=True)


if __name__ == "__main__":
    main()
