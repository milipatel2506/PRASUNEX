"""AI action layer: action plan + parent message generation with guardrails.

Two providers behind one interface:
  * "llm"      - Anthropic API, used only if ANTHROPIC_API_KEY is set. Receives anonymised input only.
  * "template" - deterministic content library (always available, also the fallback).

Every result passes guardrails (schema, banned words, script check). If the LLM output fails them,
we fall back to the template engine and record why.
"""
from __future__ import annotations
import json
import os
import re

from . import content
from .content import LANGS, SUBJECT_NAME, TOPICS, ACTIONS, REASON_GROUP, subject_label, subject_topics

LLM_MODEL = os.environ.get("SAARTHI_LLM_MODEL", "claude-haiku-5-5")
BANNED = ["stupid", "lazy", "dumb", "hopeless", "punish", "worthless", "will fail", "failure"]
SCRIPT_RANGE = {"gu": (0x0A80, 0x0AFF), "hi": (0x0900, 0x097F)}
KINDS = ["parent_contact", "remedial_session", "practice_test", "homework_checklist",
         "counselling", "peer_support", "progress_check", "goal_setting"]


def provider_info() -> dict:
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"provider": "llm" if has_key else "template", "model": LLM_MODEL if has_key else None,
            "note": "LLM with guardrails and template fallback" if has_key else
                    "Built-in template engine (set ANTHROPIC_API_KEY to enable the LLM)"}


# ---------- template engine ----------------------------------------------------------
def _template_actions(reasons: list[dict], subject_key: str) -> tuple[list[dict], list[str]]:
    topics = subject_topics(subject_key)
    subj = subject_label(subject_key, "en")
    groups: list[str] = []
    for r in reasons:
        g = REASON_GROUP[r["key"]]
        if g not in groups:
            groups.append(g)
    if not groups:
        groups = ["marks"]
    pools = [list(ACTIONS[g]) for g in groups]
    out, i = [], 0
    while len(out) < 3 and any(pools):
        pool = pools[i % len(pools)]
        if pool:
            kind, text = pool.pop(0)
            out.append({"kind": kind, "text": text.format(subject=subj, t0=topics[0], t1=topics[1])})
        i += 1
    show_topics = topics[:2] if any(g in ("marks", "volatile") for g in groups) else []
    return out, [f"{subj}: {t}" for t in show_topics]


def _template_message(ctx: dict, lang: str, name: str) -> str:
    reasons = [r["key"] for r in ctx["reasons"]][:2] or ["marks_falling"]
    clauses = [content.REASON_CLAUSE[k][lang] for k in reasons]
    joined = content.AND[lang].join(clauses)
    primary = REASON_GROUP[reasons[0]]
    subj = subject_label(ctx["weak_subject"], lang)
    fmt = dict(name=name, subject=subj)
    return content.BODY[lang].format(
        greeting=content.GREETING[lang], name=name, reasons=joined, cls=ctx["class"],
        school_action=content.SCHOOL_ACTION[primary][lang].format(**fmt),
        home_action=content.HOME_ACTION[primary][lang].format(**fmt))


# ---------- guardrails -------------------------------------------------------------
def check_message(text: str, lang: str) -> list[str]:
    flags = []
    low = text.lower()
    for w in BANNED:
        if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
            flags.append(f"banned_phrase:{w}")
    if re.search(r"(?:\d[\s-]?){8,}", text) or re.search(r"@|https?://|www\.", low):
        flags.append("contains_contact_details")
    if len(text) > 1200:
        flags.append("too_long")
    if lang in SCRIPT_RANGE:
        lo, hi = SCRIPT_RANGE[lang]
        letters = [c for c in text if c.isalpha()]
        share = sum(lo <= ord(c) <= hi for c in letters) / max(1, len(letters))
        if share < 0.6:
            flags.append("wrong_script")
    return flags


def validate_plan(plan: dict, lang: str) -> list[str]:
    flags = []
    acts = plan.get("actions")
    if (not isinstance(acts, list) or len(acts) != 3 or
            not all(isinstance(a, dict) and isinstance(a.get("text"), str) and 0 < len(a["text"]) <= 300 for a in acts)):
        flags.append("bad_actions_schema")
    msg = plan.get("parent_message")
    if not isinstance(msg, str) or "{student_name}" not in msg:
        flags.append("missing_name_placeholder")
    else:
        flags += check_message(msg, lang)
    return flags


# ---------- LLM provider -----------------------------------------------------------
def _llm_plan(ctx: dict, lang: str) -> dict:
    import anthropic  # imported lazily so the app runs without the package/key
    client = anthropic.Anthropic(timeout=15, max_retries=1)
    system = (
        "You help a school teacher support a struggling student. You will receive anonymised data. "
        "Reply with ONLY a JSON object: {\"actions\":[{\"kind\":<one of " + json.dumps(KINDS) + ">,\"text\":<one short, "
        "practical teacher action>} x3],\"topics\":[<up to 3 short topics to revisit>],\"parent_message\":<message>}. "
        f"The parent_message must be written in {LANGS[lang]}, in simple, warm, respectful language, under 120 words, "
        "never blame the child or parent, avoid gendered wording, mention one thing the school will do and one thing "
        "the family can do, and use the literal placeholder {student_name} for the child's name.")
    resp = client.messages.create(model=LLM_MODEL, max_tokens=2500, system=system,
                                  messages=[{"role": "user", "content": json.dumps(ctx["llm_input"])}])
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    data = json.loads(raw)
    for a in data.get("actions", []):
        if a.get("kind") not in KINDS:
            a["kind"] = "progress_check"
    return data


# ---------- public API -------------------------------------------------------------
def build_context(student: dict, risk: dict) -> dict:
    """Context for generation. `llm_input` is the ONLY part ever sent to an external model."""
    reasons = risk["reasons"]
    subject_key = risk["weakest_subject"]
    llm_input = {
        "student_ref": f"S-{student['id']:04d}",
        "grade": re.sub(r"\D", "", student["cls"]),
        "risk_tier": risk["tier"],
        "reasons": [{"key": r["key"], "evidence": r["evidence"]} for r in reasons],
        "weakest_subject": subject_label(subject_key, "en"),
        "suggested_topics": subject_topics(subject_key),
    }
    return {"reasons": reasons, "weak_subject": subject_key, "class": student["cls"], "llm_input": llm_input}


def student_name_for(student: dict, lang: str) -> str:
    return {"en": student["first_en"], "gu": student["first_gu"], "hi": student["first_hi"]}[lang]


def generate_plan(student: dict, risk: dict, lang: str) -> dict:
    ctx = build_context(student, risk)
    name = student_name_for(student, lang)
    provider, fallback_reason, plan = "template", None, None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            cand = _llm_plan(ctx, lang)
            bad = validate_plan(cand, lang)
            if bad:
                fallback_reason = "guardrail: " + ",".join(bad)
            else:
                plan, provider = cand, "llm"
        except Exception as e:  # network, auth, JSON parse...
            fallback_reason = f"llm_error: {type(e).__name__}"
    if plan is None:
        acts, topics = _template_actions(ctx["reasons"], ctx["weak_subject"])
        plan = {"actions": acts, "topics": topics,
                "parent_message": _template_message(ctx, lang, "{student_name}")}
    plan["parent_message"] = plan["parent_message"].replace("{student_name}", name)
    plan["topics"] = [t for t in (plan.get("topics") or []) if isinstance(t, str)][:3]
    flags = check_message(plan["parent_message"], lang)
    if fallback_reason:
        flags.append(fallback_reason)
    return {"actions": plan["actions"], "topics": plan["topics"], "message": plan["parent_message"],
            "provider": provider, "flags": flags, "llm_input": ctx["llm_input"], "language": lang}


def translate_message(student: dict, risk: dict, lang: str) -> dict:
    """Re-render only the parent message in another language."""
    res = generate_plan(student, risk, lang)
    return {"message": res["message"], "provider": res["provider"], "flags": res["flags"],
            "language": lang, "llm_input": res["llm_input"]}
