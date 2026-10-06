"""Generate the CloudFlow knowledge base from the world bible (app/world.py).

Owner: C

Spec-first generation: every article is written by the LLM from a fixed list of facts,
then checked for those facts. Failing articles are regenerated (max 2 retries) and,
as a last resort, rendered deterministically from the spec, so the KB is always complete
and always consistent with SQLite and the policy registry.

Usage:
  python scripts/gen_kb.py                 # uses LLM_ORDER providers (Groq -> Gemini -> Ollama)
  GEN_MOCK=true python scripts/gen_kb.py   # no API calls, deterministic content
Outputs:
  data/kb/articles/*.md, data/kb/tickets/*.json, data/source_register.csv, data/article_plan.json,
  data/generation_log.jsonl (every attempt, provider, failures - feeds the data card)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import world as W                      # noqa: E402
from scripts.gen_llm import chat, is_mock, LLMUnavailable    # noqa: E402
from scripts import build_register          # noqa: E402

ART_DIR = ROOT / "data/kb/articles"
TKT_DIR = ROOT / "data/kb/tickets"
LOG = ROOT / "data/generation_log.jsonl"
DEFAULT_AUTHORITY = {"article": 1, "policy": 1, "release_note": 2, "ticket": 4, "community": 5}


def load_prompt(name: str) -> tuple[str, str]:
    text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    system, user = text.split("USER:", 1)
    return system.replace("SYSTEM:", "").strip(), user.strip()


def fill(template: str, **values) -> str:
    for k, v in values.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def md_table(kind: str) -> str:
    if kind == "PLANS":
        rows = ["| Plan | API requests/min | Workflow runs/month | Seats | Support | Price/month (USD) |",
                "|---|---|---|---|---|---|"]
        for plan, p in W.PLANS.items():
            rows.append(f"| {plan} | {p['api_rate_limit_per_min']:,} | {p['monthly_workflow_runs']:,} | {p['seats']} | "
                        f"{p['support_tier']} | {p['monthly_price']:.0f} |")
        return "\n".join(rows)
    if kind == "ERRORS":
        rows = ["| Code | Meaning | What to do |", "|---|---|---|"]
        rows += [f"| {c} | {m} | {f} |" for c, m, f in W.ERROR_CODES]
        return "\n".join(rows)
    raise ValueError(kind)


def expand(fact: str) -> str:
    return md_table(fact.split(":", 1)[1]) if fact.startswith("TABLE:") else fact


def render_mock(spec: dict) -> str:
    """Deterministic article: used in mock mode and as the last-resort fallback."""
    out = [f"# {spec['title']}", "",
           f"This article is for CloudFlow customers on version {spec['product_versions'].replace(';', ' and ')}.", ""]
    for heading, facts in spec["sections"]:
        out += [f"## {heading}", ""]
        for f in facts:
            out += ([expand(f), ""] if f.startswith("TABLE:") else [f"- {f}."])
        out.append("")
    return "\n".join(out).strip() + "\n"


def check_article(text: str, spec: dict) -> list[str]:
    problems = [f"missing fact: {m!r}" for m in spec.get("must_include", []) if m not in text]
    for heading, _ in spec["sections"]:
        if not re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.M):
            problems.append(f"missing section: {heading!r}")
    return problems


def front_matter(meta: dict) -> str:
    lines = ["---"] + [f"{k}: {json.dumps(v) if isinstance(v, str) else v}" for k, v in meta.items()] + ["---", ""]
    return "\n".join(lines)


def article_meta(spec: dict, provenance: str) -> dict:
    return {
        "source_id": spec["source_id"], "doc_type": spec["doc_type"], "title": spec["title"],
        "authority_level": spec.get("authority_level", DEFAULT_AUTHORITY[spec["doc_type"]]),
        "product_versions": spec["product_versions"], "last_updated": spec["last_updated"],
        "effective_from": spec.get("effective_from", ""), "deprecated_on": spec.get("deprecated_on", ""),
        "supersedes": spec.get("supersedes", ""), "provenance": provenance, "synthetic": "Y",
    }


def log(entry: dict):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def gen_article(spec: dict, prompts: dict) -> dict:
    prompt_name = "kb_gen_policy" if spec["doc_type"] == "policy" else "kb_gen_article"
    system, user_t = prompts[prompt_name]
    if is_mock():
        text, prov = render_mock(spec), "template:mock"
        log({"id": spec["source_id"], "attempt": 0, "provider": prov, "problems": []})
    else:
        section_list = "\n".join(f"- {h}" for h, _ in spec["sections"])
        facts = "\n".join(f"[{h}] {expand(f)}" for h, fs in spec["sections"] for f in fs)
        user = fill(user_t, source_id=spec["source_id"], title=spec["title"], category=spec["category"],
                    product_versions=spec["product_versions"], section_list=section_list, facts=facts)
        text, prov = None, None
        for attempt in range(3):
            try:
                out, provider = chat(system, user, temperature=0.4)
            except LLMUnavailable as e:
                log({"id": spec["source_id"], "attempt": attempt, "provider": None, "problems": [str(e)]})
                break
            out = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", out.strip())
            problems = check_article(out, spec)
            log({"id": spec["source_id"], "attempt": attempt, "provider": provider, "problems": problems})
            if not problems:
                text, prov = out + "\n", f"LLM:{provider},prompt:" + prompt_name
                break
            user += "\n\nYour previous draft had these problems, fix them:\n" + "\n".join(problems)
        if text is None:
            text, prov = render_mock(spec), "template:fallback_after_llm_failure"
    meta = article_meta(spec, prov)
    (ART_DIR / f"{spec['source_id']}.md").write_text(front_matter(meta) + text, encoding="utf-8")
    return meta


def gen_ticket(spec: dict, system: str, user_t: str) -> dict:
    angry = spec.get("needs_human")
    body = None
    prov = "template:mock"
    if not is_mock():
        extra = "- This customer was angry and the case needed a human agent." if angry else ""
        user = fill(user_t, source_id=spec["source_id"], product_version=spec["product_version"],
                    gist_q=spec["gist_q"], gist_r=spec["gist_r"], extra=extra,
                    tone=", clearly frustrated and mentioning repeated contact" if angry else "")
        for attempt in range(3):
            try:
                out, provider = chat(system, user, json_mode=True, temperature=0.6)
                body = json.loads(out)
                missing = [k for k in ("subject", "customer_question", "resolution", "tags") if k not in body]
                log({"id": spec["source_id"], "attempt": attempt, "provider": provider, "problems": missing})
                if not missing:
                    prov = f"LLM:{provider},prompt:kb_gen_ticket"
                    break
                body = None
            except (json.JSONDecodeError, LLMUnavailable) as e:
                log({"id": spec["source_id"], "attempt": attempt, "provider": None, "problems": [str(e)[:200]]})
                if isinstance(e, LLMUnavailable):
                    break
    if body is None:
        body = {"subject": spec["gist_q"][:70], "customer_question": spec["gist_q"] + ".",
                "resolution": spec["gist_r"] + ".", "tags": [spec["intent"]]}
    ticket = {
        "id": spec["source_id"], "intent": spec["intent"], "product_version": spec["product_version"],
        "resolved_at": spec["resolved_at"], **body,
        "needs_human": bool(angry), "outdated": bool(spec.get("outdated")), "provenance": prov,
    }
    (TKT_DIR / f"{spec['source_id']}.json").write_text(json.dumps(ticket, indent=2), encoding="utf-8")
    return {
        "source_id": spec["source_id"], "doc_type": "ticket", "title": ticket["subject"],
        "authority_level": 4, "product_versions": spec["product_version"], "last_updated": spec["resolved_at"],
        "effective_from": "", "deprecated_on": "", "supersedes": "", "provenance": prov, "synthetic": "Y",
    }


def write_article_plan():
    """data/article_plan.json: every planned document with its versions and designed conflicts (deliverable)."""
    plan = {
        "as_of_date": W.AS_OF_DATE,
        "articles": [{k: spec.get(k, "") for k in ("source_id", "doc_type", "category", "title", "product_versions",
                                                   "last_updated", "effective_from", "deprecated_on", "supersedes")}
                     | {"sections": [h for h, _ in spec["sections"]], "must_include": spec.get("must_include", [])}
                     for spec in W.ARTICLES],
        "tickets": [{k: spec.get(k) for k in ("source_id", "intent", "product_version", "resolved_at")}
                    | {"outdated": bool(spec.get("outdated")), "contradicts": spec.get("contradicts", ""),
                       "needs_human": bool(spec.get("needs_human"))}
                    for spec in W.TICKETS],
        "intended_conflicts": [
            {"type": "outdated_ticket", "ticket": t["source_id"], "current_source": t["contradicts"]}
            for t in W.TICKETS if t.get("outdated")
        ] + [
            {"type": "version_variant", "sources": ["KB-ADV-001", "KB-ADV-001-3X"], "topic": "run history export"},
            {"type": "version_variant", "sources": ["KB-API-001", "KB-API-002"], "topic": "API authentication"},
            {"type": "version_variant", "sources": ["KB-API-004", "KB-API-004-3X"], "topic": "webhook signing"},
            {"type": "future_deprecation", "sources": ["RN-DEP-001", "KB-API-002"], "effective_from": "2026-12-01"},
        ],
    }
    (ROOT / "data/article_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")


def main():
    for d in (ART_DIR, TKT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    LOG.unlink(missing_ok=True)
    prompts = {n: load_prompt(f"{n}.txt") for n in ("kb_gen_article", "kb_gen_policy")}
    t_sys, t_user = load_prompt("kb_gen_ticket.txt")
    rows = []
    for spec in W.ARTICLES:
        rows.append(gen_article(spec, prompts))
        print("article", spec["source_id"], rows[-1]["provenance"])
    for spec in W.TICKETS:
        rows.append(gen_ticket(spec, t_sys, t_user))
        print("ticket ", spec["source_id"], rows[-1]["provenance"])
    write_article_plan()
    print(f"\n{len(W.ARTICLES)} articles, {len(W.TICKETS)} tickets")
    build_register.main()


if __name__ == "__main__":
    main()
