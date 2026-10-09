import re

FIELDS = {
    "company": r"(?:公司名称|企业名称)[:：\s]+([^\n]+)",
    "capital": r"注册资本[:：\s]+([^\n]+)",
    "legal_person": r"(?:法人|法定代表人)[:：\s]+([^\n]+)",
    "founded": r"(?:成立时间|成立日期)[:：\s]+([^\n]+)",
    "phone": r"(?:电话|联系电话)[:：\s]+([^\n]+)",
    "email": r"(?:邮箱|电子邮箱)[:：\s]+([^\n]+)",
    "address": r"(?:地址|注册地址)[:：\s]+([^\n]+)",
}


def search_keys(targets):
    return list(dict.fromkeys(targets.get("brands", []) + targets.get("extra_persons", [])
                              + ([targets["company"]] if targets.get("company") else [])))


def parse_seven_fields(text):
    return {key: (m[1].strip() if (m := re.search(pattern, text)) else None)
            for key, pattern in FIELDS.items()}
