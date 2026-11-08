"""Layer 3 of hallucination control: code, not the model, decides which legal references reach the user.

Every reply and draft is scanned for anything that looks like a legal reference:
  - section / article / rule / order numbers
  - names of Acts, Codes, Sanhitas, Rules
  - abbreviations of criminal and procedure codes (IPC, BNS, CrPC, ...)
  - case-law patterns ("X v. Y", AIR 2019 SC ..., (2020) 5 SCC ...)
A reference survives only if it matches an entry in laws.json. Everything else is removed and replaced with a
visible warning, and counted, so we can measure how often the model tried to invent law.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

KB = json.loads((Path(__file__).parent / "laws.json").read_text(encoding="utf-8"))
LAWS = {l["id"]: l for l in KB["laws"]}
ACTS = KB["acts"]
RESOURCES = {r["id"]: r for r in KB["resources"]}
ALLOWED = {(l["act"], l["number"].lower().replace(" ", "")) for l in KB["laws"] if l["number"]}
# Section 34 is used together with the Jurisdiction Rules, 2021
ALLOWED_ACTS = set(ACTS)

REDACT = "[unverified legal reference removed]"

SEC_RE = re.compile(
    r"\b(?:Section|Sections|Sec\.?|S\.|Article|Art\.?|Rule|Rules|Order|Regulation|Clause)\s*"
    r"(\d+[A-Z]?(?:\s*\(\s*[0-9a-z]+\s*\))*|[IVXL]{2,}\b(?:\s*Rule\s*\d+)?)", re.I)
ACT_RE = re.compile(
    r"\b((?:the\s+)?(?:[A-Z][A-Za-z.'-]*\s+|\(\s*|of\s+|and\s+|the\s+|[A-Z][A-Za-z-]*\)\s*)*?"
    r"(?:Act|Code|Sanhita|Adhiniyam|Rules|Regulations))\b(?:,?\s*(\d{4}))?")
ABBR_RE = re.compile(r"\b(IPC|BNS|BNSS|BSA|CrPC|Cr\.P\.C\.?|CPC|C\.P\.C\.?|NI Act|RERA|IT Act)\b")
CASE_RE = re.compile(
    r"(\b[A-Z][\w.&'-]*(?:\s+(?:[A-Z][\w.&'-]*|of|and|&))*\s+(?:v\.|vs\.?|versus)\s+[A-Z][\w.&'-]*(?:\s+(?:[A-Z][\w.&'-]*|of|and|&))*"
    r"|\bAIR\s+\d{4}\s+\w+(?:\s+\d+)?|\(\d{4}\)\s*\d+\s*SCC\s*\d*|\b\d{4}\s+SCC\s+OnLine\b|\bSCR\b|\bSupreme Court (?:held|ruled|said|judgment in)\b)")


def _act_key(text: str, nearest: str = "first") -> str | None:
    """Return the Act whose alias appears in text; 'first' = earliest occurrence, 'last' = latest."""
    t = text.lower()
    best = None
    for key, a in ACTS.items():
        for alias in a["aliases"]:
            i = t.find(alias) if nearest == "first" else t.rfind(alias)
            if i >= 0 and (best is None or (i < best[0] if nearest == "first" else i > best[0])):
                best = (i, key)
    return best[1] if best else None


def _act_for_reference(text: str, start: int, end: int) -> str | None:
    """'Section 69 of the X Act' -> look right after the number first; otherwise the nearest Act before it."""
    after = text[end:end + 90]
    m = re.match(r"\s*(?:,|of|of the|under|under the|the|\s)*", after)
    head = after[m.end() if m else 0:][:80]
    k = _act_key(head, "first") if re.match(r"\s*[A-Z(]", head or "") else None
    if k and _act_key(head[:60], "first") == k:
        return k
    return _act_key(text[max(0, start - 90):start], "last")


@dataclass
class CheckResult:
    text: str
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.removed


def check(text: str) -> CheckResult:
    if not text:
        return CheckResult(text or "")
    spans: list[tuple[int, int, str]] = []   # (start, end, reason)
    kept = []

    for m in CASE_RE.finditer(text):
        spans.append((m.start(), m.end(), "case law is never cited"))
    for m in ABBR_RE.finditer(text):
        spans.append((m.start(), m.end(), "code not in verified list"))

    for m in ACT_RE.finditer(text):
        phrase = m.group(0)
        words = phrase.split()[:-1] if not m.group(2) else phrase.split()
        named = [w for w in phrase.split()[:-1] if w[:1].isupper() and w.lower() not in ("the", "of", "and")]
        if not named and not m.group(2):
            continue                                   # "the Rules", "an Act" etc. are not legal references
        key = _act_key(phrase)
        if key is None:
            spans.append((m.start(), m.end(), "Act/Rules not in verified list"))
        else:
            kept.append(phrase.strip())

    for m in SEC_RE.finditer(text):
        num = re.sub(r"\s+", "", m.group(1)).lower()
        key = _act_for_reference(text, m.start(), m.end())
        base = num.split("(")[0]
        if key:
            ok = (key, num) in ALLOWED or (key, base) in ALLOWED or any(
                k == key and n.split("(")[0] == base for k, n in ALLOWED)
        else:
            ok = any(n == num or n.split("(")[0] == base for _, n in ALLOWED)
        if ok:
            kept.append(m.group(0))
        else:
            spans.append((m.start(), m.end(), "section not in verified list"))

    if not spans:
        return CheckResult(text, [], kept)
    # merge overlapping spans and redact from the end
    spans.sort()
    merged = []
    for s, e, r in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]), merged[-1][2])
        else:
            merged.append((s, e, r))
    out, removed = text, []
    for s, e, r in reversed(merged):
        removed.append(f"{text[s:e]}  ({r})")
        out = out[:s] + REDACT + out[e:]
    return CheckResult(out, list(reversed(removed)), kept)


def valid_citation_ids(ids) -> tuple[list[str], list[str]]:
    ids = [i for i in (ids or []) if isinstance(i, str)]
    return [i for i in ids if i in LAWS], [i for i in ids if i not in LAWS]


# ---------------------------------------------------------------- referral rules (code, not model)

REFERRAL_RULES = [
    (r"\b(police|fir|arrest\w*|jail|criminal|cheat(?:ed|ing)? case|chargesheet)\b", "Police or criminal matters need a lawyer.", ["NALSA"]),
    (r"\b(summons|court notice|legal notice (?:from|sent to me|received)|received a (?:legal )?notice|hearing (?:is )?(?:tomorrow|next week|on))\b",
     "You have received formal legal papers or have a hearing; a lawyer should read them.", ["NALSA"]),
    (r"\b(beat|hit me|assault\w*|threat\w*|violence|goons?|attack\w*|lock(?:ed)? me out|thrown out|evict\w*)\b",
     "Threats, force or eviction can be urgent. If you are in danger call 112.", ["EMERGENCY", "NALSA"]),
    (r"\b(suicid\w*|kill myself|end my life|self[- ]harm)\b", "You don't have to deal with this alone.", ["TELEMANAS"]),
    (r"\b(divorce|custody|dowry|domestic violence|maintenance|property title|land dispute|will and inheritance|inheritance|partition)\b",
     "This is outside what I can help with (deposit and refund disputes only).", ["NALSA"]),
    (r"\b(cheque (?:bounced|bounce|dishonou?red)|bounced cheque)\b", "A bounced cheque has strict deadlines; see a lawyer quickly.", ["NALSA"]),
]
CRORE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(crore|cr)\b", re.I)
LAKH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(lakh|lac|lakhs)\b", re.I)


def referral_triggers(user_text: str) -> list[dict]:
    t = user_text.lower()
    hits = []
    for pat, why, res in REFERRAL_RULES:
        if re.search(pat, t):
            hits.append({"reason": why, "resources": res})
    amt = 0.0
    for m in CRORE_RE.finditer(user_text):
        amt = max(amt, float(m.group(1)) * 100)
    for m in LAKH_RE.finditer(user_text):
        amt = max(amt, float(m.group(1)))
    if amt > 50:
        hits.append({"reason": "Amounts above Rs 50 lakh go beyond the District Commission; get a lawyer.", "resources": ["NALSA"]})
    return hits
