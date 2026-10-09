from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    independent_sources: tuple[str, ...] = ()
    ip_owner: bool = False
    icp_owner: bool = False
    page_owner: bool = False
    small_company: bool = False
    distinct_ips: int = 0
    all_titles_match: bool = False


def classify(query: str, *, exact=False, short_name=False):
    if "body" in query.lower():
        return "D"
    if exact:
        return "A"
    if short_name:
        return "B"
    return "D"


def destination(confidence: str, evidence: Evidence | None = None):
    evidence = evidence or Evidence()
    if confidence in {"A", "B"}:
        return "assets", confidence, ""
    if confidence == "C" and (
        len(set(evidence.independent_sources)) >= 2
        or (evidence.ip_owner and evidence.icp_owner and evidence.page_owner)
    ):
        return "assets", "A", "corroborated"
    if confidence == "D+" and (evidence.small_company and 1 <= evidence.distinct_ips <= 10
                               and evidence.all_titles_match):
        return "assets", "D+", "small-company verified exception"
    # D never promotes implicitly, even if new records share the same host.
    return "assets_quarantine", confidence, "unverified or fuzzy attribution"
