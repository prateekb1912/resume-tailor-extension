import re

# Ported from the n8n workflows so dedup keys stay stable across scrape sources.
_LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co",
    "company", "gmbh", "plc", "pvt", "private", "ag", "sa", "srl", "bv", "holdings",
}


def norm_company(name: str) -> str:
    lowered = (name or "").lower().replace("&", " and ")
    lowered = re.sub(r"[.,/]", "", lowered)
    tokens = [t for t in lowered.split() if t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


def norm_title(title: str) -> str:
    return " ".join((title or "").lower().split())


def dedup_key(company: str, title: str) -> str:
    return f"{norm_company(company)}|{norm_title(title)}"
