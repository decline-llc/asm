import pytest

from asm.browser.aiqicha import parse_seven_fields, search_keys
from asm.browser.xiaolanben import Xiaolanben
from asm.parallel.p1_osint import parse_sse, parse_tender, validate_keyword
from asm.stages.s2b_icp import branch, enumerate_subnumbers, parse_icp
from asm.stages.s4_subdomain import enumerate_dns
from asm.stages.s5_dns_cdn import cdn_fingerprint, corrected_answers, scan_ports, takeover_provider
from asm.stages.s7_web import catch_all, differential
from asm.utils.http import Response


def test_equity_replay(project):
    browser = Xiaolanben()
    companies = browser.replay(project / "tests/fixtures/equity.json")
    assert len(companies) == 3 and len(browser.trace) == 6
    assert companies[-1]["parent_cid"] == "fixture-child"
    assert companies[1]["website"] is None
    assert search_keys({"company": "Long", "brands": ["Brand"], "extra_persons": ["[PERSON]"]})[0] == "Brand"
    text = "公司名称：示例公司\n注册资本：占位\n法人：[PERSON]\n成立时间：2000-01-01\n电话：[PHONE]\n邮箱：p@example.invalid\n地址：[ADDRESS]"
    assert all(parse_seven_fields(text).values())


def test_icp_branches():
    assert branch(200, "示ICP备00000000号-1") == "footer"
    assert branch(200, "nothing") == "snapshot"
    assert branch(302) == "redirect"
    assert branch(403) == branch(503) == "snapshot"
    assert branch(None) == "expired_or_unreachable"
    values = parse_icp("示ICP备00000000号-1 示ICP备00000000号-2")
    assert len(values) == 2 and len(enumerate_subnumbers(values)) == 1


def test_wildcard_skips_brute():
    calls = []
    def resolver(domain):
        calls.append(domain)
        return ["192.0.2.1"]
    wild, domains = enumerate_dns("example.invalid", resolver=resolver)
    assert wild and domains == [] and len(calls) == 2


def test_cdn_and_takeover():
    assert cdn_fingerprint(["a.gccdn.net"])
    assert scan_ports(True) == "3000-9200" and scan_ports(False) == "1-65535"
    assert corrected_answers({"1.1.1.1": ["0.0.0.0"], "114.114.114.114": ["192.0.2.1"]}) == ["192.0.2.1"]
    assert takeover_provider("fixture.s3.amazonaws.com", 404, "<Code>NoSuchBucket</Code>") == "Amazon S3"
    assert takeover_provider("fixture.s3.amazonaws.com", 403, "NoSuchBucket") is None
    assert takeover_provider("fixture.s3.amazonaws.com", 404, "Not found") is None
    assert differential(502) == "backend_filtered_candidate"
    assert differential(404) == "not_found" and differential(403) == "route_denied"
    assert catch_all([Response("http://localhost", 200, {}, b"same") for _ in range(3)])
    assert not catch_all([Response("http://localhost", 404, {}, b"same") for _ in range(3)])


def test_osint_parsers(project):
    events = list(parse_sse((project / "tests/fixtures/sourcegraph.sse").read_text().splitlines()))
    assert events[0][0] == "matches" and events[1][1]["done"]
    tender = parse_tender((project / "tests/fixtures/tender.txt").read_text(encoding="utf-8"))
    assert tender["system_name"] and tender["vendor"] and tender["deployment"] and tender["person"]
    assert validate_keyword("example.invalid") == "example.invalid"
    for keyword in ["password", "admin", "api", "", 'x" OR type:repo']:
        with pytest.raises(ValueError):
            validate_keyword(keyword)
