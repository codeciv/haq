"""One conversation turn: model proposes, code checks. Used by the web app and the test runner."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from .checker import check, valid_citation_ids, referral_triggers, LAWS, RESOURCES
from .llm import LLM
from . import prompts

EMPTY_CASE = {"type": "unknown", "amount": "", "other_party": "", "state_city": "", "facts": [], "timeline": [],
              "evidence_have": [], "evidence_missing": [], "open_questions": []}


@dataclass
class Session:
    history: list = field(default_factory=list)       # [{"role": "user"|"assistant", "content": str}]
    case: dict = field(default_factory=lambda: dict(EMPTY_CASE))
    mode: str = "assist"                                # assist | roleplay
    last_draft: str = ""


def _messages(s: Session, user_text: str, action: str | None) -> list[dict]:
    if s.mode == "roleplay":
        who = s.case.get("other_party") or ("the landlord" if s.case.get("type") == "deposit" else "the seller")
        sys = prompts.ROLEPLAY_SYSTEM.format(who=who)
        sys += "\n\nCASE CARD:\n" + json.dumps(s.case, ensure_ascii=False)
    else:
        sys = prompts.ASSISTANT_SYSTEM + "\n\n" + prompts.kb_block() + \
            "\n\nCURRENT CASE CARD:\n" + json.dumps(s.case, ensure_ascii=False)
    msgs = [{"role": "system", "content": sys}] + s.history[-16:]
    content = user_text
    if action == "draft":
        content = (user_text + "\n\n" if user_text else "") + \
            "[ACTION: Draft the legal notice now from the case card. Use placeholders for anything unknown.]"
    msgs.append({"role": "user", "content": content})
    return msgs


def turn(s: Session, llm: LLM, user_text: str, action: str | None = None, name: str = "turn") -> dict:
    if action == "roleplay_start":
        s.mode = "roleplay"
    if action == "roleplay_stop" or (s.mode == "roleplay" and user_text.strip().lower() == "stop"):
        s.mode = "assist"
        msg = "Practice ended. Want me to summarise what to say, or draft a notice?"
        s.history += [{"role": "user", "content": user_text or "stop"}, {"role": "assistant", "content": msg}]
        return {"reply": msg, "mode": "assist", "raw": "", "audit": {}}
    if action == "roleplay_start" and not user_text:
        user_text = "(The user starts the practice. Open with your first line as the other party.)"

    data, raw = llm.chat(_messages(s, user_text, action), name)
    reply = str(data.get("reply", ""))
    out = {"raw": raw, "mode": data.get("mode", s.mode)}

    if s.mode == "roleplay":
        r, c = check(reply), check(str(data.get("coach", "")))
        out.update(reply=r.text, coach=c.text,
                   audit={"removed": r.removed + c.removed, "unknown_citation_ids": [], "referrals": []})
    else:
        rc = check(reply)
        draft = str(data.get("draft", "") or "")
        dc = check(draft)
        good_ids, bad_ids = valid_citation_ids(data.get("citations"))
        model_refer = bool(data.get("refer_to_lawyer"))
        rules = referral_triggers(user_text)
        if model_refer and data.get("refer_reason"):
            rules.insert(0, {"reason": str(data.get("refer_reason")), "resources": ["NALSA"]})
        if isinstance(data.get("case"), dict):
            s.case = {**EMPTY_CASE, **data["case"]}
        if dc.text:
            s.last_draft = dc.text
        out.update(reply=rc.text, draft=dc.text, case=s.case,
                   citations=[LAWS[i] for i in good_ids],
                   referral={"needed": bool(rules), "reasons": [r["reason"] for r in rules],
                             "resources": [RESOURCES[x] for x in dict.fromkeys(y for r in rules for y in r["resources"])],
                             "by_model": model_refer, "by_rules": bool(referral_triggers(user_text))},
                   audit={"removed": rc.removed + dc.removed, "unknown_citation_ids": bad_ids})
    s.history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": out["reply"]}]
    return out
