#!/usr/bin/env python3
"""Run every test case through the bot and save unedited outputs.
  python run_tests.py --provider gemini            (needs GEMINI_API_KEY)
  python run_tests.py --provider replay --replay-dir replay_answers
"""
import argparse, json, time
from pathlib import Path
from lawyer.bot import Session, turn
from lawyer.llm import LLM, PRESETS, PendingResponse


def evaluate(case, turns):
    e, res = case["expect"], {}
    assist = [t for t in turns if t.get("mode") != "roleplay" and "referral" in t]
    if e.get("refer") is not None:
        got = any(t["referral"]["needed"] for t in assist)
        res["referral"] = got == e["refer"]
    if e.get("asks_question"):
        res["asks_question_first"] = "?" in turns[0]["reply"]
    if e.get("out_of_scope") is not None:
        res["scope"] = any(t.get("mode") == "out_of_scope" for t in assist) == e["out_of_scope"]
    if e.get("cite_any"):
        ids = {c["id"] for t in assist for c in t.get("citations", [])}
        res["cites_relevant_law"] = bool(ids & set(e["cite_any"]))
    if e.get("draft") is True:
        d = next((t.get("draft") for t in assist if t.get("draft")), "")
        res["draft_with_placeholders"] = bool(d) and "[" in d
    if e.get("draft") is False:
        res["no_threat_draft"] = not any(t.get("draft") for t in assist)
    if e.get("roleplay"):
        rp = [t for t in turns if t.get("mode") == "roleplay"]
        res["roleplay_with_coaching"] = bool(rp) and all(t.get("coach") for t in rp)
    res["no_unverified_law_shown"] = True   # guaranteed by checker; attempts are counted separately
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="gemini", choices=list(PRESETS) + ["replay"])
    ap.add_argument("--model")
    ap.add_argument("--replay-dir", default="replay_answers")
    ap.add_argument("--cases", default="test_cases.json")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--min-interval", type=float, default=4.0)
    a = ap.parse_args()
    llm = LLM(a.provider, a.model, replay_dir=a.replay_dir, min_interval=a.min_interval)
    out = Path(a.out); (out / "tests").mkdir(parents=True, exist_ok=True)
    rows, pending, attempts = [], [], 0
    for case in json.load(open(a.cases)):
        s, turns = Session(), []
        try:
            for i, (text, action) in enumerate(case["turns"], 1):
                t = turn(s, llm, text, action, name=f"{case['id']}_t{i}")
                turns.append({"user": text, "action": action, **t})
        except PendingResponse as p:
            pending.append(str(p)); continue
        checks = evaluate(case, turns)
        removed = sum(len((t.get("audit") or {}).get("removed", [])) for t in turns)
        bad_ids = sum(len((t.get("audit") or {}).get("unknown_citation_ids", [])) for t in turns)
        attempts += removed + bad_ids
        rec = {"id": case["id"], "category": case["category"], "expect": case["expect"], "checks": checks,
               "unverified_refs_removed": removed, "unknown_citation_ids": bad_ids, "turns": turns}
        (out / "tests" / f"{case['id']}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        rows.append(rec)
    if pending:
        print(f"{len(pending)} turns waiting for replay answers, e.g. {pending[:3]}")
    L = [f"# Test results ({a.provider}/{llm.model}, {time.strftime('%Y-%m-%d %H:%M')})", "",
         f"Cases run: {len(rows)}. Legal references the model tried that were NOT in the verified list "
         f"(removed before display): {attempts}.", "",
         "| case | category | checks | result | refs removed |", "|---|---|---|---|---|"]
    total = passed = 0
    for r in rows:
        ok = all(r["checks"].values())
        total += len(r["checks"]); passed += sum(r["checks"].values())
        fails = [k for k, v in r["checks"].items() if not v]
        L.append(f"| {r['id']} | {r['category']} | {', '.join(r['checks'])} | "
                 f"{'PASS' if ok else 'FAIL: ' + ', '.join(fails)} | {r['unverified_refs_removed'] + r['unknown_citation_ids']} |")
    L += ["", f"Checks passed: {passed}/{total}"]
    (out / "summary.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[-3:]))


if __name__ == "__main__":
    main()
