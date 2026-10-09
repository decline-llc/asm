import io
import tarfile

import pytest

from asm.bridge import Bridge, BridgeError, WsFs, native_path
from asm.models import Asset, Domain
from asm.precision import Evidence, classify, destination
from asm.scope import Scope, ScopeError, normalize_host, registrable
from asm.stages.s6_port import clusters, honeypot


def test_scope():
    scope = Scope({"authorization": True, "targets": {"roots": ["example.com"], "ip_cidrs": ["192.0.2.0/24"]},
                   "scope": {"exclude_saas": ["saas.example.com"]}})
    assert scope.contains("a.example.com") and scope.contains("192.0.2.100")
    assert not scope.contains("badexample.com") and not scope.contains("example.com.evil.test")
    assert not scope.contains("a.saas.example.com")
    for host in ["example.net", "192.0.3.1"]:
        with pytest.raises(ScopeError):
            scope.assert_in_scope(host)
    with pytest.raises(ScopeError):
        Scope({"targets": {"roots": ["com"]}})
    with pytest.raises(ScopeError):
        Scope({"targets": {"roots": ["example.com"]}}).assert_in_scope("example.com")
    with pytest.raises(ScopeError):
        Scope({"authorization": True, "targets": {"roots": ["example.com"]}}, passive_only=True).assert_in_scope("example.com")


def test_normalize():
    assert normalize_host("https://WWW.Example.com:443/x") == "www.example.com"
    assert normalize_host("[::1]") == "::1"
    assert normalize_host("::ffff:127.0.0.1") == "127.0.0.1"
    assert registrable("test.example.co.uk") == "example.co.uk"
    with pytest.raises(ScopeError):
        normalize_host("https://user:pass@example.com")


def test_precision_and_dedup(db):
    db.asset(Asset(host="EXAMPLE.COM", title="First", source="fofa"))
    db.asset(Asset(host="example.com", title="Other", tech="Java", source="quake"))
    trusted = db.rows("SELECT * FROM assets")
    assert len(trusted) == 1 and trusted[0]["title"] == "First" and trusted[0]["tech"] == "Java"
    assert trusted[0]["source"] == "fofa,quake"
    db.asset(Asset(host="example.com", title="Fuzzy", confidence="D", source="body"))
    db.asset(Asset(host="other.example.com", confidence="D+"))
    assert len(db.rows("SELECT * FROM assets")) == 1
    assert len(db.rows("SELECT * FROM assets_quarantine")) == 2
    assert db.asset({"title": "invalid"}) is None
    assert db.rows("SELECT kind FROM findings") == [{"kind": "invalid"}]
    assert classify('body:"domain.example"', exact=True) == "D"
    assert destination("C", Evidence(independent_sources=("one", "two")))[0] == "assets"
    assert destination("C", Evidence(independent_sources=("one", "one")))[0] == "assets_quarantine"
    assert destination("D+", Evidence(small_company=True, distinct_ips=10, all_titles_match=True))[0] == "assets"
    assert destination("D+", Evidence(small_company=True, distinct_ips=11, all_titles_match=True))[0] == "assets_quarantine"
    assert destination("D", Evidence(ip_owner=True, icp_owner=True, page_owner=True))[0] == "assets_quarantine"
    db.domain(Domain("WWW.Example.com", sources="seed"))
    db.domain(Domain("www.example.com", sources="dns"))
    assert db.rows("SELECT sources FROM domains")[0]["sources"] == "dns,seed"


def test_native_paths_and_commands():
    bridge = Bridge("Ubuntu", "fixture")
    bridge._home = "/home/fixture"
    assert "root" in bridge.argv("id", root=True)
    cmd = bridge.command("nmap", ["--", "quote'; touch /tmp/bad"], timeout=12)
    assert "timeout --signal=TERM --kill-after=5s 12s" in cmd
    assert "'quote'" in cmd
    for value in ["/mnt/c/a", "C:\\project", "/home/fixture/../etc", "\\\\wsl$\\a"]:
        with pytest.raises(BridgeError):
            native_path(value)


def archive(name, *, link=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        entry = tarfile.TarInfo(name)
        if link:
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/etc/passwd"
            tar.addfile(entry)
        else:
            entry.size = 3
            tar.addfile(entry, io.BytesIO(b"ABC"))
    stream.seek(0)
    return stream


def test_tar_integrity_and_traversal(tmp_path):
    WsFs.extract_archive(archive("sub/abc.bin"), tmp_path)
    assert (tmp_path / "sub/abc.bin").read_bytes() == b"ABC"
    for name in ("../escape", "/absolute", "C:evil", "a\\..\\escape"):
        with pytest.raises(BridgeError):
            WsFs.extract_archive(archive(name), tmp_path)
    with pytest.raises(BridgeError):
        WsFs.extract_archive(archive("link", link=True), tmp_path)
    with pytest.raises(BridgeError):
        WsFs.extract_archive(archive("large"), tmp_path, byte_limit=1)


def test_clusters_and_honeypot():
    rows = [{"ip": f"192.0.2.{i}", "host": f"{i}.example.invalid"} for i in range(1, 6)]
    rows += [{"ip": "198.51.100.10", "host": "single.example.invalid"}]
    assert clusters(rows) == {"192.0.2.0/24": "核心集群", "198.51.100.0/24": "独立弱防护"}
    assert honeypot(range(1, 1001), range(1, 1001))
    assert not honeypot([80, 443], [80, 443])
    assert not honeypot(range(1, 999), range(1, 1001))
