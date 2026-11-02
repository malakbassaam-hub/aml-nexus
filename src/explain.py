"""Grounded case summaries. The model may only restate the evidence it is given; a checker rejects anything else.
The model never decides: the recommendation comes from the screening system and the decision stays with a human.
No account identifiers and no synthetic ground-truth labels are ever sent. In a real deployment, check your data policy first."""
import json
import re
from dataclasses import dataclass

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-5-5"  # verify the current model name in your Anthropic console
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_GEMINI = "gemini-flash-latest"  # model names are retired often; on a 404 the app asks Google which text models your key can use
GEMINI_LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
_MODEL_CACHE = {}
NAMES = {"claude": "Claude", "gemini": "Gemini"}
PATTERNS = {"fan_in": "many senders paying one account", "cycle": "funds returning to their origin through a loop of accounts",
            "slow_accumulation": "dispersed payments accumulating in a recently opened account"}
FORBIDDEN = ("guilty", "criminal", "fraudster", "terrorist", "freeze", "frozen")
SYSTEM = (
    "You assist a bank compliance reviewer. You receive a JSON object of FACTS about one case produced by an automated "
    "screening system. Write a neutral summary of 4 to 6 sentences using ONLY these facts.\n"
    "Rules: (1) Do not add any fact, number, date, name or inference that is not in the JSON; copy numbers exactly as written. "
    "(2) Present the evidence for suspicion AND the evidence against it; if there is none against, say none was found. "
    "(3) Do not accuse anyone or describe intent; use wording like 'the pattern resembles'. "
    "(4) Attribute any recommendation to the screening system, and end by saying that a human reviewer makes the decision. "
    "(5) Plain English, no bullet points, no markdown.")


@dataclass
class AIConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    provider: str = "claude"  # "claude" or "gemini"


def facts_from_case(row):
    return dict(pattern=PATTERNS.get(row.kind, row.kind), system_recommendation=row.tier,
                suspicion=round(float(row.suspicion), 2), counter_evidence_score=round(float(row.counter), 2),
                evidence_for=list(row.supporting), evidence_against=list(row.counter_evidence))


def facts_from_packet(p, days_observed):
    return dict(watch_status=p["status"], days_observed=int(days_observed),
                recommendation_at_start=p["start"]["tier"], recommendation_now=p["now"]["tier"],
                suspicion_at_start=round(p["start"]["suspicion"], 2), suspicion_now=round(p["now"]["suspicion"], 2),
                counter_evidence_score_now=round(p["now"]["counter"], 2),
                evidence_for=list(p["now"]["supporting"]), evidence_against=list(p["now"]["counter_evidence"]))


def template_summary(f):
    rec = f.get("system_recommendation") or f.get("recommendation_now")
    parts = [f"The screening system recommends {rec} for this account."]
    if "pattern" in f:
        parts.append(f"The pattern resembles {f['pattern']}.")
    if "recommendation_at_start" in f:
        n, a, b = f["days_observed"], f["recommendation_at_start"], f["recommendation_now"]
        if n == 0:
            parts.append("The watch has only just started, so there is no trend yet.")
        elif a == b:
            parts.append(f"Over {n} days of observation the recommendation stayed {b}.")
        else:
            parts.append(f"Over {n} days of observation the recommendation moved from {a} to {b}.")
    parts.append("Evidence for suspicion: " + "; ".join(f["evidence_for"]) + ".")
    parts.append("Evidence against: " + ("; ".join(f["evidence_against"]) if f["evidence_against"] else "none was found") + ".")
    parts.append("This is a recommendation only; a human reviewer makes the decision.")
    return " ".join(parts)


def _numbers(text):
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def check_grounding(text, facts):
    """Returns (ok, reason). Every number must appear in the facts; no accusations; must defer to a human."""
    allowed = _numbers(json.dumps(facts))
    extra = _numbers(text) - allowed
    if extra:
        return False, f"numbers not in the evidence: {sorted(extra)}"
    low = text.lower()
    bad = [w for w in FORBIDDEN if w in low]
    if bad:
        return False, f"forbidden wording: {bad}"
    if "human" not in low and "reviewer" not in low:
        return False, "does not defer to a human reviewer"
    if not 40 <= len(text) <= 1500:
        return False, "unexpected length"
    return True, ""


def _default_list(url, headers):
    import requests
    r = requests.get(url, headers=headers, timeout=30)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def pick_gemini_model(models):
    """Cheapest current text model from a ListModels answer: stable flash-lite, then stable flash, then previews, newest first."""
    banned = ("image", "tts", "embedding", "live", "audio", "robotics", "computer", "imagen", "veo", "learnlm", "gemma", "aqa")
    best = None
    for m in models:
        name = str(m.get("name", "")).replace("models/", "")
        if not name.startswith("gemini-") or "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if any(b in name for b in banned):
            continue
        pre = "preview" in name or "exp" in name
        rank = (0 if "flash-lite" in name else 1 if "flash" in name else 4) + (2 if pre and "flash" in name else 0)
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
        key = (rank, -(float(v.group(1)) if v else 0), name)
        if best is None or key < best[0]:
            best = (key, name)
    return best[1] if best else None


def _default_http(url, headers, body):
    import requests
    r = requests.post(url, headers=headers, json=body, timeout=40)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def summarize(facts, cfg=None, http=_default_http, lister=_default_list):
    """Always returns something usable: the model's checked summary, or the fixed template with the reason."""
    fallback = lambda note: dict(text=template_summary(facts), source="template", note=note, facts=facts)
    if cfg is None or not cfg.api_key:
        return fallback("No API key is configured.")
    try:
        if cfg.provider == "gemini":
            def ask(model):
                return http(GEMINI_URL.format(model=model), {"x-goog-api-key": cfg.api_key, "content-type": "application/json"},
                            {"systemInstruction": {"parts": [{"text": SYSTEM}]},
                             "contents": [{"role": "user", "parts": [{"text": json.dumps(facts)}]}],
                             "generationConfig": {"maxOutputTokens": 700}})
            model = _MODEL_CACHE.get(cfg.model, cfg.model)
            status, body = ask(model)
            if status == 404:  # retired or unavailable model name: let Google tell us what this key can use
                ls, lb = lister(GEMINI_LIST_URL, {"x-goog-api-key": cfg.api_key})
                found = pick_gemini_model(lb.get("models", [])) if ls == 200 and isinstance(lb, dict) else None
                if found and found != model:
                    _MODEL_CACHE[cfg.model] = found
                    status, body = ask(found)
        else:
            status, body = http(API_URL, {"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                                {"model": cfg.model, "max_tokens": 450, "system": SYSTEM,
                                 "messages": [{"role": "user", "content": json.dumps(facts)}]})
    except Exception as e:  # network problems must never break the dashboard
        return fallback(f"The AI service was unreachable ({type(e).__name__}); template shown.")
    if status != 200:
        msg = (body.get("error", {}) or {}).get("message", "") if isinstance(body, dict) else ""
        return fallback(f"The AI service returned HTTP {status}{': ' + str(msg)[:300] if msg else ''}; template shown.")
    try:
        if cfg.provider == "gemini":
            text = "".join(p.get("text", "") for p in body["candidates"][0]["content"]["parts"]).strip()
        else:
            text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text").strip()
    except (KeyError, IndexError, TypeError):
        return fallback("The AI service answered in an unexpected format; template shown.")
    ok, why = check_grounding(text, facts)
    if not ok:
        return fallback(f"The AI summary failed the grounding check ({why}); template shown.")
    return dict(text=text, source=cfg.provider, note="Every number was verified against the evidence.", facts=facts)
