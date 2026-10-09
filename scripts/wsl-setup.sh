#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive
# Release versions and SHA-256 values are immutable in tool-lock.json.
WS_DIR="${ASM_WS:-$HOME/asm-ws}"
GH_MIRROR="${GH_MIRROR:-}"
case "$WS_DIR" in /mnt/*|*'..'*|*' '*) echo "Use a native, space-free WSL path" >&2; exit 2;; esac
if [ "$(uname -m)" != x86_64 ]; then echo "This lock supports amd64 only" >&2; exit 2; fi
mkdir -p "$WS_DIR"/{bin,tools,wordlists,results,tmp,manifests}
repo_git() {
  local repo="$1"
  shift
  # Root apt/bootstrap can inspect user-owned clones without a global Git exception.
  git -c "safe.directory=$repo" -C "$repo" "$@"
}
APT_ARGS=(-o DPkg::Lock::Timeout=600)
if [ "${ASM_APT_HTTPS:-1}" = 1 ]; then
  . /etc/os-release
  printf 'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu %s main universe restricted multiverse\n' \
    "$VERSION_CODENAME" "${VERSION_CODENAME}-updates" > "$WS_DIR/tmp/apt-sources.list"
  printf 'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://security.ubuntu.com/ubuntu %s-security main universe restricted multiverse\n' \
    "$VERSION_CODENAME" >> "$WS_DIR/tmp/apt-sources.list"
  APT_ARGS+=(-o "Dir::Etc::sourcelist=$WS_DIR/tmp/apt-sources.list" -o Dir::Etc::sourceparts=-)
fi
if [ "${ASM_SKIP_APT:-0}" != 1 ]; then
  [ "$(id -u)" = 0 ] || { echo "Run apt phase via wsl -u root" >&2; exit 2; }
  apt-get "${APT_ARGS[@]}" update
  apt-get "${APT_ARGS[@]}" install -y nmap masscan dnsutils jq curl unzip git build-essential libpcap-dev \
    python3 python3-pip python3-venv ca-certificates
fi
LOCK="$WS_DIR/tool-lock.json"
jq -c '.binaries[]' "$LOCK" | while read -r entry; do
  name=$(jq -r '.name' <<< "$entry")
  version=$(jq -r '.version' <<< "$entry")
  url=$(jq -r '.url' <<< "$entry")
  sha=$(jq -r '.sha256' <<< "$entry")
  archive="$WS_DIR/tmp/$(basename "$url")"
  stamp="$WS_DIR/manifests/$name.json"
  if [ -x "$WS_DIR/bin/$name" ] && [ -f "$stamp" ] && \
     [ "$(jq -r '.sha256' "$stamp")" = "$sha" ]; then echo "[keep] $name $version"; continue; fi
  echo "[install] $name $version"
  if [ ! -f "$archive" ] || ! echo "$sha  $archive" | sha256sum -c - >/dev/null 2>&1; then
    curl -fsSL --retry 3 --connect-timeout 30 --max-time 1800 "${GH_MIRROR}${url}" -o "$archive.part"
    echo "$sha  $archive.part" | sha256sum -c -
    mv "$archive.part" "$archive"
  fi
  extract_dir=$(mktemp -d "$WS_DIR/tmp/install.XXXXXX")
  case "$url" in
    *.zip) unzip -q "$archive" -d "$extract_dir"; install -m 755 "$extract_dir/$name" "$WS_DIR/bin/$name";;
    *.tar.gz) tar xzf "$archive" -C "$extract_dir"; install -m 755 "$extract_dir/$name" "$WS_DIR/bin/$name";;
    *) install -m 755 "$archive" "$WS_DIR/bin/$name";;
  esac
  printf '%s\n' "$entry" > "$stamp"
done
if ! command -v google-chrome-stable >/dev/null; then
  [ "$(id -u)" = 0 ] || { echo "Chrome install requires root" >&2; exit 2; }
  if [ ! -f "$WS_DIR/tmp/google-chrome.deb" ]; then
    curl -fsSL --retry 3 https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
      -o "$WS_DIR/tmp/google-chrome.deb"
  fi
  apt-get "${APT_ARGS[@]}" install -y "$WS_DIR/tmp/google-chrome.deb"
fi
# Ubuntu 24.04 uses externally managed Python: all Python tools get their own venv.
if [ ! -x "$WS_DIR/tools/wafw00f/.venv/bin/wafw00f" ]; then
  python3 -m venv "$WS_DIR/tools/wafw00f/.venv"
  "$WS_DIR/tools/wafw00f/.venv/bin/pip" install 'wafw00f==2.4.2'
fi
if [ ! -d "$WS_DIR/tools/OneForAll/.git" ]; then
  git clone --depth 1 --branch v0.4.5 https://github.com/shmilylty/OneForAll.git "$WS_DIR/tools/OneForAll"
fi
[ "$(repo_git "$WS_DIR/tools/OneForAll" rev-parse HEAD)" = "$(jq -r '.source_repositories.OneForAll.commit' "$LOCK")" ] || \
  { echo "OneForAll commit differs from lock; preserve local changes and inspect" >&2; exit 2; }
if [ ! -x "$WS_DIR/tools/OneForAll/.venv/bin/python" ]; then
  python3 -m venv "$WS_DIR/tools/OneForAll/.venv"
fi
# Python 3.12 removed stdlib distutils; setuptools supplies its compatible shim.
# The upstream exrex pin imports re.sre_parse, unavailable on Python 3.11+.
sed 's/^exrex==0.10.5$/exrex==0.12.0/' "$WS_DIR/tools/OneForAll/requirements.txt" \
  > "$WS_DIR/tmp/oneforall-requirements.txt"
"$WS_DIR/tools/OneForAll/.venv/bin/pip" install 'setuptools==75.8.0' -r "$WS_DIR/tmp/oneforall-requirements.txt"
if [ ! -d "$WS_DIR/wordlists/SecLists/.git" ]; then
  git clone --depth 1 --filter=blob:none --no-checkout --branch 2026.1 \
    https://github.com/danielmiessler/SecLists.git "$WS_DIR/wordlists/SecLists"
fi
[ "$(repo_git "$WS_DIR/wordlists/SecLists" rev-parse HEAD)" = "$(jq -r '.source_repositories.SecLists.commit' "$LOCK")" ] || \
  { echo "SecLists commit differs from lock; preserve local changes and inspect" >&2; exit 2; }
if [ "${ASM_SECLISTS_FULL:-0}" = 1 ]; then
  repo_git "$WS_DIR/wordlists/SecLists" sparse-checkout disable
elif [ ! -f "$WS_DIR/wordlists/SecLists/Discovery/Web-Content/raft-medium-words.txt" ] || \
     [ "$(repo_git "$WS_DIR/wordlists/SecLists" config --get core.sparseCheckout || true)" = true ]; then
  # Seed exact blobs through raw.githubusercontent.com: some WSL proxy setups
  # can clone Git metadata but cannot open Git's second lazy-fetch connection.
  while IFS= read -r wordlist; do
    blob=$(repo_git "$WS_DIR/wordlists/SecLists" ls-tree HEAD -- "$wordlist" | awk '{print $3}')
    [[ "$blob" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid pinned dictionary: $wordlist" >&2; exit 2; }
    cache="$WS_DIR/tmp/seclists-$blob"
    if [ ! -f "$cache" ] || [ "$(repo_git "$WS_DIR/wordlists/SecLists" hash-object "$cache")" != "$blob" ]; then
      commit=$(jq -r '.source_repositories.SecLists.commit' "$LOCK")
      curl -fsSL --retry 3 --retry-all-errors --connect-timeout 15 --max-time 180 \
        "https://raw.githubusercontent.com/danielmiessler/SecLists/$commit/$wordlist" -o "$cache"
    fi
    [ "$(repo_git "$WS_DIR/wordlists/SecLists" hash-object -w "$cache")" = "$blob" ] || \
      { echo "Dictionary hash mismatch: $wordlist" >&2; exit 2; }
    echo "[verified] SecLists $wordlist"
  done < <(jq -r '.source_repositories.SecLists.sparse_paths[]' "$LOCK")
  jq -r '.source_repositories.SecLists.sparse_paths[] | "/" + .' "$LOCK" | \
    repo_git "$WS_DIR/wordlists/SecLists" sparse-checkout set --no-cone --stdin
fi
if [ ! -f "$WS_DIR/wordlists/SecLists/Discovery/Web-Content/raft-medium-words.txt" ]; then
  repo_git "$WS_DIR/wordlists/SecLists" checkout --detach "$(jq -r '.source_repositories.SecLists.commit' "$LOCK")"
fi
export PATH="$WS_DIR/bin:$WS_DIR/tools/wafw00f/.venv/bin:$PATH"
{
  date -u +'%Y-%m-%dT%H:%M:%SZ'
  nmap --version | head -2
  # Masscan 1.3.2 prints its version with exit status 1.
  masscan --version || [ "$?" -eq 1 ]
  google-chrome-stable --version
  wafw00f --version
  for tool in subfinder dnsx httpx naabu nuclei katana; do "$tool" -version; done
  ffuf -V
  gowitness version
  repo_git "$WS_DIR/tools/OneForAll" rev-parse HEAD
  repo_git "$WS_DIR/wordlists/SecLists" rev-parse HEAD
} 2>&1 | tee "$WS_DIR/manifests/installed.txt"
echo "WSL tools installed: $WS_DIR"
