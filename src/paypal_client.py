"""PayPal Sandbox integration (READ-ONLY): OAuth2 client-credentials + Transaction Search API.
Sandbox only: this module refuses any other base URL. No real money, no real customers.

Docs used: GET /v1/reporting/transactions (start_date and end_date required, RFC 3339, at most 31 days apart;
page_size up to 500; transactions can take up to 3 hours to appear; the app needs the 'Transaction Search' option).
Assumption to verify on your first real response: direction is inferred from the SIGN of transaction_amount
(positive = money in for the account holder, negative = money out)."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from .detectors import WARMUP
from .risk import build_cases

SANDBOX = "https://api-m.sandbox.paypal.com"
SEARCH_SCOPE = "reporting/search/read"


class PayPalError(Exception):
    pass


@dataclass
class PayPalConfig:
    client_id: str
    client_secret: str
    base_url: str = SANDBOX

    def __post_init__(self):
        if self.base_url != SANDBOX:
            raise ValueError("Sandbox only: refusing to use a non-sandbox URL.")
        if not self.client_id or not self.client_secret:
            raise ValueError("Missing PayPal sandbox credentials.")


def _default_http(method, url, headers=None, data=None, params=None, auth=None):
    import requests
    r = requests.request(method, url, headers=headers, data=data, params=params, auth=auth, timeout=30)
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:300]}
    return r.status_code, body


def _err(status, body):
    if not isinstance(body, dict):
        return f"HTTP {status}"
    bits = [str(body.get(k)) for k in ("name", "error", "message", "error_description") if body.get(k)]
    dbg = f" (debug_id {body['debug_id']})" if body.get("debug_id") else ""
    return f"HTTP {status}: {' - '.join(bits) or 'unexpected response'}{dbg}"


def get_token(cfg, http=_default_http):
    status, body = http("POST", f"{cfg.base_url}/v1/oauth2/token",
                        headers={"Accept": "application/json", "Accept-Language": "en_US"},
                        data={"grant_type": "client_credentials"}, auth=(cfg.client_id, cfg.client_secret))
    if status != 200 or "access_token" not in body:
        raise PayPalError("Authentication failed. " + _err(status, body))
    scope = body.get("scope", "")
    return dict(token=body["access_token"], expires_in=int(body.get("expires_in", 0)), scope=scope,
                has_search_scope=SEARCH_SCOPE in scope)


def _rfc3339(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_transactions(cfg, token, start, end, http=_default_http, page_size=100, max_pages=50):
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if not start < end or end - start > timedelta(days=31):
        raise ValueError("The range must be positive and at most 31 days.")
    details, holder, page = [], None, 1
    while page <= max_pages:
        status, body = http("GET", f"{cfg.base_url}/v1/reporting/transactions",
                            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                            params={"start_date": _rfc3339(start), "end_date": _rfc3339(end), "fields": "all",
                                    "page_size": page_size, "page": page})
        if status in (401, 403):
            raise PayPalError("Not authorised to read transactions. Enable 'Transaction Search' for the sandbox app "
                              "(it can take hours to activate if the app was already used). " + _err(status, body))
        if status != 200:
            raise PayPalError("Transaction Search failed. " + _err(status, body))
        details += body.get("transaction_details", [])
        holder = holder or body.get("account_number")
        if page >= int(body.get("total_pages", 1) or 1):
            break
        page += 1
    return details, holder


def fetch_last_days(cfg, token, days=30, now=None, http=_default_http):
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=min(days, 31))
    details, holder = list_transactions(cfg, token, start, end, http=http)
    return details, holder, start


def _parse_dt(s):
    s = re.sub(r"Z$", "+00:00", s.strip())
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    return datetime.fromisoformat(s)


EDGE_COLS = ["src", "dst", "amount", "day", "tx_id", "event"]


def to_edges(details, holder, origin):
    """Normalise Transaction Search records into the (src, dst, amount, day) schema the detectors use."""
    holder = holder or "ACCOUNT_HOLDER"
    rows, skipped = [], {"not_completed": 0, "non_usd": 0, "unparsable": 0}
    for d in details:
        ti, pi = d.get("transaction_info", {}) or {}, d.get("payer_info", {}) or {}
        if ti.get("transaction_status") != "S":
            skipped["not_completed"] += 1
            continue
        money = ti.get("transaction_amount", {}) or {}
        if money.get("currency_code") != "USD":
            skipped["non_usd"] += 1
            continue
        try:
            value, when = float(money["value"]), _parse_dt(ti["transaction_initiation_date"])
        except (KeyError, ValueError, TypeError):
            skipped["unparsable"] += 1
            continue
        cp = pi.get("account_id") or pi.get("email_address") or ti.get("paypal_account_id") or f"OUTSIDE:{ti.get('transaction_event_code', '?')}"
        src, dst = (cp, holder) if value > 0 else (holder, cp)
        rows.append(dict(src=src, dst=dst, amount=abs(value), day=(when.astimezone(timezone.utc).date() - origin.date()).days,
                         tx_id=ti.get("transaction_id"), event=ti.get("transaction_event_code")))
    return pd.DataFrame(rows, columns=EDGE_COLS), skipped


def analyze(edges):
    """Run AML-Nexus on live edges. PayPal does not expose account age, so age-based signals are neutral here."""
    names = sorted(set(edges.src) | set(edges.dst))
    acc = pd.DataFrame({"account": names, "opened_day": -1000,
                        "label": ["external" if n.startswith("OUTSIDE:") else "live" for n in names], "role": "live"})
    if edges.empty:
        return build_cases(edges.assign(day=pd.Series(dtype=int)), acc, now=0)
    return build_cases(edges, acc, now=int(edges.day.max()))


def default_origin(start):
    return start - timedelta(days=WARMUP)  # the first WARMUP days are history only for the detectors


# Illustrative sample in the documented Transaction Search format. NOT a live call.
def _s(i, payer, value, day, event="T0006"):
    return {"transaction_info": {"paypal_account_id": f"PAYER{payer:03d}", "transaction_id": f"SAMPLE{i:012d}",
                                 "transaction_event_code": event, "transaction_status": "S",
                                 "transaction_initiation_date": f"2026-10-{day:02d}T10:00:00+0000",
                                 "transaction_amount": {"currency_code": "USD", "value": value}},
            "payer_info": {"account_id": f"PAYER{payer:03d}", "email_address": f"payer{payer}@example.com"} if value[0] != "-" else {}}


SAMPLE_RESPONSE = {"account_number": "SAMPLEMERCHANT", "total_pages": 1,
                   "transaction_details": [_s(i, i, f"{9500 - 40 * i}.00", 3 + i // 3) for i in range(1, 10)]
                   + [_s(20, 0, "-7800.00", 9, "T0400")]}
