import os
import re
import json
import time
import uuid
import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import email as email_lib

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


st.set_page_config(
    page_title="Supplier Negotiation Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


MAX_UPLOAD_BYTES = 2_000_000
MAX_STEPS = 14

FX_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.26,
}

UNIT_ALIASES = {
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "kgs": "kg",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "ton": "ton",
    "tons": "ton",
    "tonne": "ton",
    "tonnes": "ton",
    "mt": "ton",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "pcs": "each",
    "pc": "each",
    "piece": "each",
    "pieces": "each",
    "unit": "each",
    "units": "each",
    "each": "each",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "l": "l",
    "liter": "l",
    "litre": "l",
    "liters": "l",
    "litres": "l",
    "ml": "ml",
    "milliliter": "ml",
    "millilitre": "ml",
}

UNIT_DIMENSIONS = {
    "kg": ("mass", 1.0),
    "lb": ("mass", 0.45359237),
    "g": ("mass", 0.001),
    "ton": ("mass", 1000.0),
    "oz": ("mass", 0.0283495),
    "each": ("count", 1.0),
    "m": ("length", 1.0),
    "l": ("volume", 1.0),
    "ml": ("volume", 0.001),
}

BASE_FOR_DIMENSION = {
    "mass": "kg",
    "count": "each",
    "length": "m",
    "volume": "l",
}

PRESSURE_PHRASES = [
    "final offer",
    "must accept",
    "confirm today",
    "by today",
    "immediately",
    "urgent",
    "expire",
    "another buyer",
    "waiting on",
    "end of day",
    "eod",
    "within 24 hours",
    "allocation will be released",
]

INTERNAL_KEYWORDS = [
    "walk-away",
    "walkaway",
    "internal maximum",
    "budget cap",
    "maximum price",
    "ceiling price",
]

POLICIES = {
    "metals": {
        "category": "metals",
        "currency": "EUR",
        "max_price_per_base": 3.00,
        "target_discount_pct": 9.0,
        "payment_days": 45,
        "min_lead_days": 14,
        "auto_approve_max_savings_pct": 5.0,
        "walkaway_buffer_pct": 2.0,
    },
    "packaging": {
        "category": "packaging",
        "currency": "USD",
        "max_price_per_base": 0.80,
        "target_discount_pct": 8.0,
        "payment_days": 45,
        "min_lead_days": 10,
        "auto_approve_max_savings_pct": 5.0,
        "walkaway_buffer_pct": 2.0,
    },
    "chemicals": {
        "category": "chemicals",
        "currency": "EUR",
        "max_price_per_base": 2.95,
        "target_discount_pct": 7.0,
        "payment_days": 30,
        "min_lead_days": 14,
        "auto_approve_max_savings_pct": 4.0,
        "walkaway_buffer_pct": 2.0,
    },
    "electronics": {
        "category": "electronics",
        "currency": "USD",
        "max_price_per_base": 12.50,
        "target_discount_pct": 6.0,
        "payment_days": 45,
        "min_lead_days": 21,
        "auto_approve_max_savings_pct": 4.0,
        "walkaway_buffer_pct": 2.0,
    },
    "logistics": {
        "category": "logistics",
        "currency": "USD",
        "max_price_per_base": 1.20,
        "target_discount_pct": 5.0,
        "payment_days": 30,
        "min_lead_days": 2,
        "auto_approve_max_savings_pct": 3.0,
        "walkaway_buffer_pct": 1.0,
    },
    "mro": {
        "category": "mro",
        "currency": "USD",
        "max_price_per_base": 5.00,
        "target_discount_pct": 5.0,
        "payment_days": 30,
        "min_lead_days": 7,
        "auto_approve_max_savings_pct": 3.0,
        "walkaway_buffer_pct": 2.0,
    },
}

BENCHMARKS = {
    "AL-5052": {
        "low": 2.35,
        "median": 2.55,
        "high": 2.75,
        "currency": "EUR",
        "unit": "kg",
    },
    "BOX-22": {
        "low": 0.70,
        "median": 0.78,
        "high": 0.86,
        "currency": "USD",
        "unit": "each",
    },
    "RESIN-PA6": {
        "low": 2.45,
        "median": 2.65,
        "high": 2.85,
        "currency": "EUR",
        "unit": "kg",
    },
}

CATEGORY_BENCHMARKS = {
    "metals": {
        "low": 2.10,
        "median": 2.45,
        "high": 2.70,
        "currency": "EUR",
        "unit": "kg",
    },
    "packaging": {
        "low": 0.62,
        "median": 0.75,
        "high": 0.88,
        "currency": "USD",
        "unit": "each",
    },
    "chemicals": {
        "low": 2.20,
        "median": 2.55,
        "high": 2.85,
        "currency": "EUR",
        "unit": "kg",
    },
    "electronics": {
        "low": 8.50,
        "median": 10.80,
        "high": 12.40,
        "currency": "USD",
        "unit": "each",
    },
    "logistics": {
        "low": 0.75,
        "median": 0.95,
        "high": 1.15,
        "currency": "USD",
        "unit": "each",
    },
    "mro": {
        "low": 3.60,
        "median": 4.40,
        "high": 5.10,
        "currency": "USD",
        "unit": "each",
    },
}

SAMPLE_EMAILS = {
    "Gold 1: 18% above band, short lead": """From: procurement@skylinemetals.example
Subject: RFQ AL-5052 sheets - urgent
Supplier: Skyline Metals Ltd
Category: metals
Currency: EUR

Hello,

Please quote for the following:
ITEM: AL-5052 | Aluminum sheet 2mm x 1250 x 2500 | qty 1200 kg | price EUR 3.245 / kg | MOQ 500 kg | lead 7 days | payment net 15 | incoterm DDP Rotterdam

This pricing is final if confirmed today. We have another buyer waiting on the allocation.

Regards,
Anna Berger
""",
    "Gold 2: already below target (accept)": """From: sales@northpack.example
Subject: Corrugated boxes renewal
Supplier: NorthPack Packaging
Category: packaging
Currency: USD

Hello,

Renewal quote:
ITEM: BOX-22 | Double-wall corrugated box 40x30x30 cm | qty 20000 pcs | price USD 0.71 / pcs | MOQ 5000 pcs | lead 14 days | payment net 45 | incoterm FOB Chicago

We value the renewal and can hold this price for 30 days.

Best regards,
Luis Chen
""",
    "Gold 3: mixed units kg/lb and EUR": """From: quotes@euroresin.example
Subject: PA6 resin pellet offer
Supplier: EuroResin GmbH
Category: chemicals
Currency: EUR

Hello,

Offer for polyamide pellets:
ITEM: RESIN-PA6 | Polyamide 6 natural pellets | qty 5000 lb | price EUR 1.35 / lb | MOQ 1000 lb | lead 21 days | payment net 30 | incoterm EXW Duisburg

Please note pricing is quoted per pound due to customer preference.

Kind regards,
Marta Weber
""",
}

TOOL_CONTRACTS = [
    {
        "tool": "parse_quote",
        "side_effect": False,
        "idempotent": True,
        "timeout_s": 5,
        "error_types": "EmptyInput, ParseWarning, LowConfidence",
    },
    {
        "tool": "get_budget_policy",
        "side_effect": False,
        "idempotent": True,
        "timeout_s": 2,
        "error_types": "PolicyUnavailable",
    },
    {
        "tool": "benchmark_price",
        "side_effect": False,
        "idempotent": True,
        "timeout_s": 3,
        "error_types": "BenchmarkMissing",
    },
    {
        "tool": "compute_counter",
        "side_effect": False,
        "idempotent": True,
        "timeout_s": 5,
        "error_types": "InvalidQuote, DivisionByZero",
    },
    {
        "tool": "request_approval",
        "side_effect": True,
        "idempotent": True,
        "timeout_s": 3,
        "error_types": "ApprovalStoreUnavailable",
    },
]


class GracefulGiveUp(Exception):
    pass


class ToolLoopError(GracefulGiveUp):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return "RUN-" + uuid.uuid4().hex[:10].upper()


def hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def sanitize_text(value: Any, limit: int = 220) -> str:
    s = str(value if value is not None else "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"(?i)(ignore previous|system:|assistant:|api key|password|secret)", "[redacted]", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def convert_currency(amount: float, from_curr: str, to_curr: str) -> float:
    if amount is None:
        return 0.0
    from_curr = (from_curr or "USD").upper()
    to_curr = (to_curr or "USD").upper()
    if from_curr == to_curr:
        return float(amount)
    fr = FX_TO_USD.get(from_curr)
    to = FX_TO_USD.get(to_curr)
    if not fr or not to:
        return float(amount)
    return float(amount) * fr / to


def normalize_unit(unit: Optional[str]) -> str:
    if not unit:
        return "each"
    u = str(unit).strip().lower().rstrip(".")
    return UNIT_ALIASES.get(u, u)


def detect_currency(text: str) -> Optional[str]:
    codes = re.findall(r"\b(EUR|USD|GBP)\b", (text or "").upper())
    if codes:
        return codes[0]
    if "€" in text:
        return "EUR"
    if "$" in text:
        return "USD"
    if "£" in text:
        return "GBP"
    return None


def detect_pressure(text: str) -> bool:
    lower = (text or "").lower()
    return any(phrase in lower for phrase in PRESSURE_PHRASES)


def infer_category(text: str, sku: str = "") -> str:
    t = (text or "").lower()
    m = re.search(r"category\s*:\s*([a-z\s-]+)", t, re.I)
    if m:
        return m.group(1).strip().replace(" ", "-")

    sku_u = (sku or "").upper()
    prefix_map = {
        "AL": "metals",
        "ST": "metals",
        "BOX": "packaging",
        "CARTON": "packaging",
        "RESIN": "chemicals",
        "CHEM": "chemicals",
        "PCB": "electronics",
        "CHIP": "electronics",
        "FREIGHT": "logistics",
        "LANE": "logistics",
        "MRO": "mro",
    }
    for prefix, cat in prefix_map.items():
        if sku_u.startswith(prefix):
            return cat

    keyword_map = {
        "aluminum": "metals",
        "steel": "metals",
        "metal": "metals",
        "box": "packaging",
        "packaging": "packaging",
        "corrugated": "packaging",
        "resin": "chemicals",
        "chemical": "chemicals",
        "polyamide": "chemicals",
        "electronic": "electronics",
        "pcb": "electronics",
        "freight": "logistics",
        "logistic": "logistics",
        "transport": "logistics",
    }
    for k, v in keyword_map.items():
        if k in t:
            return v
    return "mro"


def parse_number_unit(raw: str) -> Tuple[Optional[float], Optional[str]]:
    if not raw:
        return None, None
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*([A-Za-z]+)?", raw)
    if not m:
        return None, None
    try:
        num = float(m.group(1).replace(",", ""))
    except Exception:
        return None, None
    unit = normalize_unit(m.group(2))
    return num, unit


def parse_price_part(part: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    cleaned = part.replace("price", " ").replace("Price", " ").replace("@", " ").replace(":", " ")
    currency = detect_currency(cleaned)
    m = re.search(r"([\d,]+(?:\.\d+)?)", cleaned)
    if not m:
        return currency, None, None
    try:
        price = float(m.group(1).replace(",", ""))
    except Exception:
        return currency, None, None

    per_m = re.search(r"(?:/|per\s+)([A-Za-z]+)", cleaned, re.I)
    if per_m:
        price_unit = normalize_unit(per_m.group(1))
    else:
        tail_m = re.search(r"[\d,\.]+\s*([A-Za-z]+)", cleaned)
        price_unit = normalize_unit(tail_m.group(1)) if tail_m else None
    return currency, price, price_unit


def parse_item_block(block: str) -> Optional[Dict[str, Any]]:
    block = (block or "").strip()
    if not block.upper().startswith("ITEM"):
        return None

    first_line = block.split("\n", 1)[0]
    first_line = re.sub(r"^ITEM\s*:\s*", "", first_line, flags=re.I).strip()
    parts = [p.strip() for p in first_line.split("|") if p.strip()]
    if not parts:
        return None

    sku_desc = parts[0]
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9/_-]{2,})\s+(.*)$", sku_desc)
    if m:
        sku, desc = m.group(1), m.group(2)
    else:
        sku, desc = sku_desc, ""

    item = {
        "sku": sku.upper(),
        "description": desc,
        "qty": None,
        "unit": None,
        "price": None,
        "price_currency": None,
        "price_unit": None,
        "moq": None,
        "moq_unit": None,
        "lead_days": None,
        "payment_days": None,
        "incoterm": None,
    }

    for p in parts[1:]:
        lp = p.lower()
        if lp.startswith("qty") or lp.startswith("quantity"):
            suffix = p[8:] if lp.startswith("quantity") else p[3:]
            num, unit = parse_number_unit(suffix)
            item["qty"] = num
            item["unit"] = unit
        elif "price" in lp or lp.startswith("@"):
            cur, val, pu = parse_price_part(p)
            item["price"] = val
            item["price_currency"] = cur
            item["price_unit"] = pu
        elif lp.startswith("moq"):
            num, unit = parse_number_unit(p[3:])
            item["moq"] = num
            item["moq_unit"] = unit
        elif "lead" in lp:
            dm = re.search(r"(\d+)", p)
            item["lead_days"] = int(dm.group(1)) if dm else None
        elif "payment" in lp or "terms" in lp:
            pm = re.search(r"net\s*(\d+)", lp)
            item["payment_days"] = int(pm.group(1)) if pm else None
        elif "incoterm" in lp:
            item["incoterm"] = p.split(":", 1)[-1].strip()

    return item


def parse_quote(email_text: str) -> Dict[str, Any]:
    text = email_text or ""
    warnings: List[str] = []

    supplier_m = re.search(r"Supplier\s*:\s*([^\n]+)", text, re.I)
    if not supplier_m:
        supplier_m = re.search(r"From\s*:\s*([^\n]+)", text, re.I)
    supplier = sanitize_text(supplier_m.group(1), 120) if supplier_m else "Unknown supplier"

    currency = detect_currency(text)
    currency_codes = re.findall(r"\b(EUR|USD|GBP)\b", text.upper())
    if len(set(currency_codes)) > 1:
        warnings.append("Multiple currency codes found; using first detected currency.")
    if not currency:
        currency = "USD"
        warnings.append("Currency not stated; assumed USD.")

    pressure = detect_pressure(text)

    global_moq_num = None
    global_moq_unit = None
    moq_m = re.search(r"MOQ\s*[:\-]?\s*([\d,\.]+)\s*([A-Za-z]+)?", text, re.I)
    if moq_m:
        try:
            global_moq_num = float(moq_m.group(1).replace(",", ""))
            global_moq_unit = normalize_unit(moq_m.group(2))
        except Exception:
            pass

    global_lead = None
    lead_m = re.search(r"lead(?:\s+time)?\s*[:\-]?\s*(\d+)\s*days?", text, re.I)
    if lead_m:
        global_lead = int(lead_m.group(1))

    global_payment = None
    pay_m = re.search(r"(?:payment|terms)\s*[:\-]?\s*net\s*(\d+)", text, re.I)
    if not pay_m:
        pay_m = re.search(r"net\s*(\d+)", text, re.I)
    if pay_m:
        global_payment = int(pay_m.group(1))

    items_raw: List[Dict[str, Any]] = []
    for m in re.finditer(r"ITEM\s*:\s*([^\n]+)", text, re.I):
        parsed = parse_item_block("ITEM: " + m.group(1))
        if parsed:
            items_raw.append(parsed)

    for raw in items_raw:
        if raw.get("lead_days") is None:
            raw["lead_days"] = global_lead
        if raw.get("payment_days") is None:
            raw["payment_days"] = global_payment
        if raw.get("moq") is None:
            raw["moq"] = global_moq_num
            raw["moq_unit"] = global_moq_unit

    normalized_items: List[Dict[str, Any]] = []
    for raw in items_raw:
        if raw.get("qty") is None or raw.get("price") is None:
            warnings.append(f"Incomplete item {raw.get('sku', 'UNKNOWN')}: missing qty or price.")
            continue

        qty_unit = raw.get("unit") or "each"
        price_unit = raw.get("price_unit") or qty_unit

        if qty_unit not in UNIT_DIMENSIONS:
            warnings.append(f"Unknown quantity unit '{qty_unit}' for {raw['sku']}; assumed each.")
            qty_unit = "each"
        if price_unit not in UNIT_DIMENSIONS:
            price_unit = qty_unit

        dim_q = UNIT_DIMENSIONS[qty_unit][0]
        dim_p = UNIT_DIMENSIONS[price_unit][0]
        if dim_q != dim_p:
            warnings.append(f"Quantity and price units differ for {raw['sku']}; assuming price applies to quantity unit.")
            price_unit = qty_unit
            dim_p = dim_q

        base_unit = BASE_FOR_DIMENSION[dim_q]
        qty_base = float(raw["qty"]) * UNIT_DIMENSIONS[qty_unit][1]
        price_base = float(raw["price"]) / UNIT_DIMENSIONS[price_unit][1]

        item_currency = raw.get("price_currency") or currency
        currency_conversion = False
        if raw.get("price_currency") is None:
            warnings.append(f"Item price currency missing for {raw['sku']}; assumed email currency.")
        elif item_currency != currency:
            price_base = convert_currency(price_base, item_currency, currency)
            currency_conversion = True
            warnings.append(f"Converted {raw['sku']} price from {item_currency} to {currency}.")

        unit_conversion = (qty_unit != base_unit) or (price_unit != base_unit)

        moq_base = None
        if raw.get("moq") is not None:
            moq_unit = raw.get("moq_unit") or qty_unit
            if moq_unit in UNIT_DIMENSIONS and UNIT_DIMENSIONS[moq_unit][0] == dim_q:
                moq_base = float(raw["moq"]) * UNIT_DIMENSIONS[moq_unit][1]
            else:
                moq_base = float(raw["moq"])
                warnings.append(f"MOQ unit for {raw['sku']} is not directly comparable; stored as quoted number.")

        normalized_items.append(
            {
                "sku": raw["sku"],
                "description": sanitize_text(raw.get("description", ""), 180),
                "qty_base": round(qty_base, 6),
                "base_unit": base_unit,
                "price_base": round(price_base, 6),
                "currency": currency,
                "moq_base": round(moq_base, 6) if moq_base is not None else None,
                "lead_days": raw.get("lead_days"),
                "payment_days": raw.get("payment_days"),
                "incoterm": raw.get("incoterm"),
                "unit_conversion": unit_conversion,
                "currency_conversion": currency_conversion,
            }
        )

    category = infer_category(text, normalized_items[0]["sku"] if normalized_items else "")

    leads = [i["lead_days"] for i in normalized_items if i.get("lead_days") is not None]
    payments = [i["payment_days"] for i in normalized_items if i.get("payment_days") is not None]
    moqs = [i["moq_base"] for i in normalized_items if i.get("moq_base") is not None]
    incoterms = [i["incoterm"] for i in normalized_items if i.get("incoterm")]

    terms = {
        "moq": max(moqs) if moqs else None,
        "lead_days": max(leads) if leads else global_lead,
        "payment_days": min(payments) if payments else global_payment,
        "incoterm": incoterms[0] if incoterms else None,
    }

    confidence = 0.35
    if supplier != "Unknown supplier":
        confidence += 0.15
    if normalized_items:
        confidence += 0.25 + min(0.10, 0.03 * len(normalized_items))
    if currency_codes:
        confidence += 0.08
    if terms["lead_days"] is not None:
        confidence += 0.04
    if terms["payment_days"] is not None:
        confidence += 0.04
    if terms["moq"] is not None:
        confidence += 0.04
    if pressure:
        confidence -= 0.02
    if any(i["unit_conversion"] for i in normalized_items):
        confidence -= 0.04
    if any(i["currency_conversion"] for i in normalized_items):
        confidence -= 0.04
    if not currency_codes:
        confidence -= 0.08

    confidence = max(0.05, min(0.99, confidence))

    return {
        "supplier": supplier,
        "category": category,
        "currency": currency,
        "items": normalized_items,
        "terms": terms,
        "confidence": round(confidence, 2),
        "warnings": warnings,
        "pressure": pressure,
        "email_hash": hash_text(text),
    }


def get_budget_policy(category: str) -> Dict[str, Any]:
    cat = (category or "mro").lower().strip()
    policy = POLICIES.get(cat, POLICIES["mro"]).copy()
    policy["category"] = cat
    return policy


def benchmark_price(skus: List[str], category: str) -> Dict[str, Dict[str, Any]]:
    bands: Dict[str, Dict[str, Any]] = {}
    cat_band = CATEGORY_BENCHMARKS.get((category or "mro").lower(), CATEGORY_BENCHMARKS["mro"])
    for sku in skus:
        bands[sku] = BENCHMARKS.get(sku, cat_band).copy()
    return bands


def compute_counter(
    quote: Dict[str, Any],
    policy: Dict[str, Any],
    benchmarks: Dict[str, Dict[str, Any]],
    strictness: int,
) -> Dict[str, Any]:
    currency = quote.get("currency", "USD")
    policy_max_q = convert_currency(policy["max_price_per_base"], policy.get("currency", "USD"), currency)

    strict_factor = 0.75 + float(strictness) / 200.0
    target_discount = float(policy["target_discount_pct"]) * strict_factor
    auto_threshold = float(policy["auto_approve_max_savings_pct"]) * (0.5 + float(strictness) / 100.0)

    items_out: List[Dict[str, Any]] = []
    item_details: List[Dict[str, Any]] = []
    risk_flags = set()
    warnings: List[str] = []

    quoted_total = 0.0
    counter_total = 0.0
    benchmark_high_total = 0.0
    walkaway_total = 0.0
    total_qty_base = 0.0

    base_units = [item.get("base_unit", "each") for item in quote.get("items", [])]
    base_unit = max(set(base_units), key=base_units.count) if base_units else "each"
    if len(set(base_units)) > 1:
        risk_flags.add("multi_unit_policy_approximation")
        warnings.append("Multiple base units detected; policy cap is approximated per item.")

    for item in quote.get("items", []):
        sku = item.get("sku", "UNKNOWN")
        qty = safe_float(item.get("qty_base"), 0.0)
        quoted_unit = safe_float(item.get("price_base"), 0.0)
        item_base_unit = item.get("base_unit", base_unit)

        if qty <= 0 or quoted_unit <= 0:
            warnings.append(f"Skipped invalid item {sku}.")
            continue

        band = benchmarks.get(sku, CATEGORY_BENCHMARKS.get(quote.get("category", "mro"), CATEGORY_BENCHMARKS["mro"]))
        low_q = convert_currency(safe_float(band.get("low"), 0.0), band.get("currency", currency), currency)
        med_q = convert_currency(safe_float(band.get("median"), 0.0), band.get("currency", currency), currency)
        high_q = convert_currency(safe_float(band.get("high"), 0.0), band.get("currency", currency), currency)

        cap_unit = policy_max_q
        if high_q > 0:
            market_cap = max(high_q * 1.08, med_q if med_q > 0 else high_q)
            cap_unit = min(policy_max_q, market_cap)

        policy_target_unit = med_q * (1.0 - target_discount / 100.0) if med_q > 0 else quoted_unit * (1.0 - target_discount / 100.0)
        desired_unit = min(quoted_unit * (1.0 - target_discount / 100.0), cap_unit)

        if quoted_unit <= policy_target_unit + 1e-9 and quoted_unit <= cap_unit + 1e-9:
            counter_unit = quoted_unit
            action = "accept"
        else:
            counter_unit = desired_unit
            floor_unit = low_q * 0.98 if low_q > 0 else 0.0
            if counter_unit < floor_unit:
                counter_unit = floor_unit
                warnings.append(f"Target for {sku} raised to near historical low to remain credible.")
            if counter_unit > quoted_unit:
                counter_unit = quoted_unit
            action = "counter"
            if high_q > 0 and quoted_unit > high_q * 1.05:
                risk_flags.add("above_benchmark")

        if counter_unit > policy_max_q + 1e-6:
            counter_unit = policy_max_q
            risk_flags.add("policy_cap_applied")

        item_quoted_total = qty * quoted_unit
        item_counter_total = qty * counter_unit
        item_walkaway = qty * policy_max_q * (1.0 + float(policy.get("walkaway_buffer_pct", 2.0)) / 100.0)
        item_benchmark_high = qty * (high_q if high_q > 0 else policy_max_q)

        quoted_total += item_quoted_total
        counter_total += item_counter_total
        walkaway_total += item_walkaway
        benchmark_high_total += item_benchmark_high
        total_qty_base += qty

        items_out.append(
            {
                "sku": sku,
                "qty": round(qty, 4),
                "quoted_price": round(quoted_unit, 4),
                "target_price": round(counter_unit, 4),
            }
        )
        item_details.append(
            {
                "sku": sku,
                "action": action,
                "qty_base": round(qty, 4),
                "base_unit": item_base_unit,
                "quoted_unit": round(quoted_unit, 4),
                "counter_unit": round(counter_unit, 4),
                "benchmark_low": round(low_q, 4),
                "benchmark_median": round(med_q, 4),
                "benchmark_high": round(high_q, 4),
            }
        )

        if item.get("unit_conversion"):
            risk_flags.add("unit_conversion")
        if item.get("currency_conversion"):
            risk_flags.add("currency_conversion")

    quoted_lead = quote.get("terms", {}).get("lead_days") or 0
    quoted_payment = quote.get("terms", {}).get("payment_days") or policy["payment_days"]
    moq = int(round(safe_float(quote.get("terms", {}).get("moq"), 0.0)))

    min_lead = int(policy.get("min_lead_days", 0))
    counter_lead = int(max(quoted_lead, min_lead)) if quoted_lead else min_lead

    if policy["payment_days"] < 30:
        counter_payment = int(policy["payment_days"])
    else:
        counter_payment = int(min(max(quoted_payment, 30), policy["payment_days"]))

    terms_changed = (quoted_lead > 0 and counter_lead != quoted_lead) or (counter_payment != quoted_payment)

    if quoted_lead and quoted_lead < min_lead:
        risk_flags.add("short_lead")
    if quoted_payment and quoted_payment < 30:
        risk_flags.add("tight_payment")
    if quote.get("pressure"):
        risk_flags.add("pressure_language")

    concessions: List[str] = []
    any_price_counter = any(d.get("action") == "counter" for d in item_details)

    if any_price_counter:
        concessions.append(
            f"Price normalized in {currency} per {base_unit} using historical band and target discount {target_discount:.1f}%."
        )
    if quoted_lead > 0 and counter_lead != quoted_lead:
        concessions.append(f"Move lead time from {quoted_lead} to {counter_lead} days to remove rush premium.")
    if counter_payment != quoted_payment:
        concessions.append(f"Align payment terms to net {counter_payment} days.")
    if "unit_conversion" in risk_flags:
        concessions.append("Convert quoted pounds to kilograms for comparable unit pricing.")
    if "currency_conversion" in risk_flags:
        concessions.append("Restate pricing in the quote currency after FX normalization.")
    if "pressure_language" in risk_flags:
        concessions.append("Keep timeline neutral and require written confirmation before allocation.")

    savings_pct = 0.0
    if quoted_total > 0:
        savings_pct = max(0.0, (1.0 - counter_total / quoted_total) * 100.0)

    accepted = savings_pct <= 0.01 and not terms_changed and not risk_flags

    if accepted:
        tone = "appreciative and concise"
    elif "pressure_language" in risk_flags:
        tone = "firm, neutral, relationship-preserving"
    else:
        tone = "collaborative and evidence-based"

    requires_approval = bool(
        risk_flags
        or savings_pct > auto_threshold
        or terms_changed
        or quote.get("confidence", 0.0) < 0.80
    )

    draft = {
        "supplier": quote.get("supplier", "Unknown supplier"),
        "items": items_out,
        "terms": {
            "moq": moq,
            "lead_days": counter_lead,
            "payment_days": counter_payment,
        },
        "counter": {
            "price": round(counter_total, 2),
            "concessions": concessions,
            "walk_away_price": round(walkaway_total, 2),
        },
        "savings_pct": round(savings_pct, 2),
        "requires_approval": requires_approval,
        "tone": tone,
    }

    meta = {
        "currency": currency,
        "base_unit": base_unit,
        "total_qty_base": round(total_qty_base, 4),
        "quoted_total": round(quoted_total, 2),
        "counter_total": round(counter_total, 2),
        "benchmark_high_total": round(benchmark_high_total, 2),
        "walkaway_total": round(walkaway_total, 2),
        "policy_max_q": round(policy_max_q, 4),
        "target_discount": round(target_discount, 2),
        "auto_threshold": round(auto_threshold, 2),
        "risk_flags": sorted(risk_flags),
        "warnings": warnings,
        "accepted": accepted,
        "item_details": item_details,
        "degraded": False,
    }

    return {"draft": draft, "meta": meta}


def contains_internal_number(text: str, number_str: str) -> bool:
    if not number_str:
        return False
    pattern = r"(?<![\d.,])" + re.escape(number_str) + r"(?![\d,])"
    return bool(re.search(pattern, text))


def redact_number(text: str, number_str: str) -> str:
    if not number_str:
        return text
    pattern = r"(?<![\d.,])" + re.escape(number_str) + r"(?![\d,])"
    return re.sub(pattern, "[internal limit]", text)


def redact_internal(text: str, numbers: List[str]) -> str:
    out = text or ""
    for n in numbers:
        out = redact_number(out, n)
    for kw in INTERNAL_KEYWORDS:
        out = re.sub(r"(?i)\b" + re.escape(kw) + r"\b", "[internal limit]", out)
    return out


def check_leaks(text: str, numbers: List[str]) -> List[str]:
    issues: List[str] = []
    lower = (text or "").lower()
    for kw in INTERNAL_KEYWORDS:
        if kw in lower:
            issues.append(f"keyword:{kw}")
    for n in numbers:
        if contains_internal_number(text, n):
            issues.append(f"number:{n}")
    return issues


def build_outbound_preview(draft: Dict[str, Any], quote: Dict[str, Any], meta: Dict[str, Any]) -> str:
    currency = meta.get("currency", quote.get("currency", "USD"))
    total = safe_float(draft.get("counter", {}).get("price"), 0.0)
    qty = safe_float(meta.get("total_qty_base"), 0.0)
    unit = meta.get("base_unit", "each")
    avg_unit = total / qty if qty > 0 else 0.0
    accepted = bool(meta.get("accepted"))
    supplier = sanitize_text(draft.get("supplier", "supplier"), 100)
    category = sanitize_text(quote.get("category", "procurement"), 60)

    subject = "Acceptance" if accepted else "Counter-offer"
    lines = [
        f"Subject: {subject} for {supplier} - {category} RFQ",
        "",
        "Hello,",
        "",
    ]

    if accepted:
        lines.append(
            f"Thank you for the quote. The commercial terms are within our current parameters, "
            f"so we can accept the quoted total of {total:,.2f} {currency}."
        )
    else:
        lines.append(
            f"Thank you for the quote. To align with current volume and specification, "
            f"we can proceed at {total:,.2f} {currency} total, equivalent to about {avg_unit:,.4f} {currency}/{unit}."
        )
        lines.append(
            f"We propose lead time of {draft.get('terms', {}).get('lead_days', 0)} days "
            f"and payment net {draft.get('terms', {}).get('payment_days', 0)} days."
        )

    concessions = draft.get("counter", {}).get("concessions", [])
    if concessions:
        lines.append("")
        lines.append("Commercial basis:")
        for c in concessions:
            lines.append(f"- {sanitize_text(c, 220)}")

    lines.append("")
    lines.append("Please send a revised proforma for review. This message is a draft and is not an authorization to ship or invoice.")
    return "\n".join(lines)


def apply_guardrails(plan: Dict[str, Any], policy: Dict[str, Any], quote: Dict[str, Any], strictness: int) -> Dict[str, Any]:
    draft = json.loads(json.dumps(plan["draft"]))
    meta = json.loads(json.dumps(plan["meta"]))
    meta.setdefault("degraded", False)

    violations: List[str] = []
    warnings: List[str] = list(meta.get("warnings", []))

    if not draft.get("items"):
        violations.append("No valid line items were parsed.")
        meta["degraded"] = True

    if meta.get("counter_total", 0) > meta.get("walkaway_total", 0) + 0.01 and meta.get("counter_total", 0) > 0:
        factor = meta["walkaway_total"] / meta["counter_total"]
        for item in draft.get("items", []):
            item["target_price"] = round(safe_float(item.get("target_price"), 0.0) * factor, 4)
        draft["counter"]["price"] = round(meta["walkaway_total"], 2)
        meta["counter_total"] = round(meta["walkaway_total"], 2)
        if meta.get("quoted_total", 0) > 0:
            draft["savings_pct"] = round(max(0.0, (1.0 - meta["counter_total"] / meta["quoted_total"]) * 100.0), 2)
        violations.append("Counter price exceeded walk-away ceiling and was capped.")
        meta["degraded"] = True
        draft["requires_approval"] = True

    if safe_float(draft.get("savings_pct"), 0.0) < -0.01:
        draft["savings_pct"] = 0.0
        warnings.append("Savings floored at zero.")

    if int(draft.get("terms", {}).get("payment_days", 0)) > int(policy.get("payment_days", 0)):
        draft["terms"]["payment_days"] = int(policy["payment_days"])
        violations.append("Payment terms capped to policy maximum.")
        draft["requires_approval"] = True

    quoted_lead = quote.get("terms", {}).get("lead_days") or 0
    if quoted_lead and int(draft.get("terms", {}).get("lead_days", 0)) < int(quoted_lead):
        draft["terms"]["lead_days"] = int(quoted_lead)
        warnings.append("Lead time was not shortened below supplier quote.")

    if safe_float(draft.get("savings_pct"), 0.0) > 30.0:
        warnings.append("Savings unusually high; verify units, currency, and quantity normalization.")

    if quote.get("pressure"):
        draft["requires_approval"] = True
    if "unit_conversion" in meta.get("risk_flags", []) or "currency_conversion" in meta.get("risk_flags", []):
        draft["requires_approval"] = True
    if safe_float(quote.get("confidence"), 0.0) < 0.75:
        draft["requires_approval"] = True
        meta["degraded"] = True
        warnings.append("Low parsing confidence; degraded mode enabled.")

    internal_numbers: List[str] = []
    for val in [meta.get("policy_max_q"), meta.get("walkaway_total")]:
        if val is None:
            continue
        fv = safe_float(val, 0.0)
        candidates = [
            f"{fv:.2f}",
            f"{fv:,.2f}",
            f"{fv:.4f}",
        ]
        for c in candidates:
            if c and c not in internal_numbers:
                internal_numbers.append(c)

    outbound = build_outbound_preview(draft, quote, meta)
    outbound = redact_internal(outbound, internal_numbers)
    leaks = check_leaks(outbound, internal_numbers)
    if leaks:
        outbound = redact_internal(outbound, internal_numbers)
        leaks2 = check_leaks(outbound, internal_numbers)
        if leaks2:
            violations.extend([f"Outbound leak check failed: {x}" for x in leaks2])
            draft["requires_approval"] = True
            meta["degraded"] = True

    if violations:
        risk_level = "critical" if any("No valid" in v or "capped" in v or "leak" in v.lower() for v in violations) else "high"
    elif draft.get("requires_approval"):
        risk_level = "high"
    elif warnings:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "draft": draft,
        "meta": meta,
        "violations": violations,
        "warnings": warnings,
        "outbound_preview": outbound,
        "internal_numbers": internal_numbers,
        "risk_level": risk_level,
    }


def validate_output_schema(draft: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if not isinstance(draft.get("supplier"), str) or not draft.get("supplier"):
        errors.append("supplier must be a non-empty string")

    items = draft.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items must be a non-empty list")
    else:
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"items[{idx}] must be an object")
                continue
            if not isinstance(item.get("sku"), str) or not item.get("sku"):
                errors.append(f"items[{idx}].sku must be a non-empty string")
            for field_name in ["qty", "quoted_price", "target_price"]:
                val = item.get(field_name)
                if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
                    errors.append(f"items[{idx}].{field_name} must be a non-negative number")

    terms = draft.get("terms")
    if not isinstance(terms, dict):
        errors.append("terms must be an object")
    else:
        for field_name in ["moq", "lead_days", "payment_days"]:
            val = terms.get(field_name)
            if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
                errors.append(f"terms.{field_name} must be a non-negative number")

    counter = draft.get("counter")
    if not isinstance(counter, dict):
        errors.append("counter must be an object")
    else:
        price = counter.get("price")
        walkaway = counter.get("walk_away_price")
        concessions = counter.get("concessions")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
            errors.append("counter.price must be a non-negative number")
        if not isinstance(walkaway, (int, float)) or isinstance(walkaway, bool) or walkaway < 0:
            errors.append("counter.walk_away_price must be a non-negative number")
        if isinstance(price, (int, float)) and isinstance(walkaway, (int, float)) and walkaway + 0.01 < price:
            errors.append("counter.walk_away_price must be greater than or equal to counter.price")
        if not isinstance(concessions, list):
            errors.append("counter.concessions must be a list")

    savings = draft.get("savings_pct")
    if not isinstance(savings, (int, float)) or isinstance(savings, bool) or savings < 0 or savings > 100:
        errors.append("savings_pct must be a number between 0 and 100")

    if not isinstance(draft.get("requires_approval"), bool):
        errors.append("requires_approval must be boolean")

    if not isinstance(draft.get("tone"), str) or not draft.get("tone"):
        errors.append("tone must be a non-empty string")

    return errors


def request_approval(draft: Dict[str, Any], savings: float, risk: str) -> Dict[str, Any]:
    key_material = json.dumps(draft, sort_keys=True, default=str).encode("utf-8")
    key = hashlib.md5(key_material).hexdigest()
    approval_id = "APR-" + key[:8].upper()
    return {
        "approval_id": approval_id,
        "created_at": now_iso(),
        "risk": risk,
        "savings_pct": round(safe_float(savings, 0.0), 2),
        "requires_human": bool(draft.get("requires_approval")),
        "status": "pending" if draft.get("requires_approval") else "auto_approved",
    }


def make_failure_result(
    run_id: str,
    scenario: str,
    email_text: str,
    error_message: str,
    events: List[Dict[str, Any]],
    started: float,
) -> Dict[str, Any]:
    latency_ms = int((time.time() - started) * 1000)
    draft = {
        "supplier": "Unknown supplier",
        "items": [
            {
                "sku": "UNKNOWN",
                "qty": 1.0,
                "quoted_price": 0.0,
                "target_price": 0.0,
            }
        ],
        "terms": {
            "moq": 0,
            "lead_days": 0,
            "payment_days": 0,
        },
        "counter": {
            "price": 0.0,
            "concessions": [],
            "walk_away_price": 0.0,
        },
        "savings_pct": 0.0,
        "requires_approval": True,
        "tone": "neutral",
    }
    meta = {
        "currency": "USD",
        "base_unit": "each",
        "total_qty_base": 1.0,
        "quoted_total": 0.0,
        "counter_total": 0.0,
        "benchmark_high_total": 0.0,
        "walkaway_total": 0.0,
        "policy_max_q": 0.0,
        "target_discount": 0.0,
        "auto_threshold": 0.0,
        "risk_flags": ["parse_failure"],
        "warnings": [error_message],
        "accepted": False,
        "item_details": [],
        "degraded": True,
    }
    approval = request_approval(draft, 0.0, "critical")
    approval["status"] = "pending"
    return {
        "run_id": run_id,
        "created_at": now_iso(),
        "scenario": scenario,
        "status": "failed",
        "dry_run": True,
        "quote": {
            "supplier": "Unknown supplier",
            "category": "unknown",
            "currency": "USD",
            "items": [],
            "terms": {},
            "confidence": 0.05,
            "warnings": [error_message],
            "pressure": False,
            "email_hash": hash_text(email_text),
        },
        "policy": POLICIES["mro"].copy(),
        "benchmarks": {},
        "draft": draft,
        "meta": meta,
        "totals": {
            "quoted_total": 0.0,
            "counter_total": 0.0,
            "benchmark_high_total": 0.0,
            "walkaway_total": 0.0,
            "currency": "USD",
        },
        "savings_pct": 0.0,
        "risk_level": "critical",
        "confidence": 0.05,
        "degraded": True,
        "warnings": [error_message],
        "violations": [error_message],
        "audit": events,
        "approval": approval,
        "outbound_preview": "Draft unavailable. A buyer must review the original email manually.",
        "internal_numbers": [],
        "schema_errors": ["Run failed before a valid draft could be produced."],
        "metrics": {
            "latency_ms": latency_ms,
            "tokens_in": max(1, len(email_text or "") // 4),
            "tokens_out": max(1, len(json.dumps(draft)) // 4),
            "cost_usd": 0.0,
            "estimated_manual_minutes": 35.0,
            "time_saved_minutes": round(max(0.0, 35.0 - latency_ms / 60000.0), 2),
        },
    }


def run_pipeline(
    email_text: str,
    scenario_label: str,
    strictness: int,
    dry_run: bool,
    progress_cb: Optional[Any] = None,
) -> Dict[str, Any]:
    run_id = new_run_id()
    started = time.time()
    events: List[Dict[str, Any]] = []
    tool_calls: List[str] = []
    steps = 0

    def emit(node: str, event: str, message: str, level: str = "info", data: Optional[Dict[str, Any]] = None) -> None:
        events.append(
            {
                "timestamp": now_iso(),
                "run_id": run_id,
                "node": node,
                "event": event,
                "level": level,
                "message": sanitize_text(message, 500),
                "data": data or {},
            }
        )

    def prog(message: str, node: str = "orchestrator") -> None:
        emit(node, "progress", message)
        if progress_cb:
            progress_cb(message)
        time.sleep(0.12)

    def bump_step(node: str) -> None:
        nonlocal steps
        steps += 1
        if steps > MAX_STEPS:
            raise GracefulGiveUp(f"Maximum step count exceeded at {node}.")

    def record_tool(name: str, args: Dict[str, Any]) -> None:
        sig = name + ":" + hashlib.md5(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()
        repeats = sum(1 for x in tool_calls if x == sig)
        if repeats >= 2:
            raise ToolLoopError(f"Repeated identical tool call detected: {name}")
        tool_calls.append(sig)

    try:
        prog("1/7 Ingesting supplier email", "ingest")
        bump_step("ingest")
        if not (email_text or "").strip():
            raise GracefulGiveUp("Empty email input.")
        emit("ingest", "input_received", "Email received and hashed.", data={"hash": hash_text(email_text), "bytes": len(email_text)})

        prog("2/7 Analyzing: parsing quote", "analyze")
        bump_step("analyze")
        record_tool("parse_quote", {"chars": len(email_text)})
        quote = parse_quote(email_text)
        emit(
            "analyze",
            "parse_complete",
            f"Parsed {len(quote.get('items', []))} item(s); confidence {quote.get('confidence', 0):.2f}.",
            data={"confidence": quote.get("confidence"), "warnings": quote.get("warnings", [])},
        )
        if not quote.get("items"):
            raise GracefulGiveUp("No line items could be parsed from the email.")

        policy = get_budget_policy(quote.get("category", "mro"))
        emit("analyze", "policy_loaded", f"Loaded policy for {policy.get('category')}.", data={"category": policy.get("category")})

        benchmarks = benchmark_price([item.get("sku", "") for item in quote.get("items", [])], quote.get("category", "mro"))
        emit("benchmark", "benchmark_loaded", "Historical price bands loaded.", data={"skus": list(benchmarks.keys())})

        prog("3/7 Planning counter-offer", "plan")
        bump_step("plan")
        record_tool("compute_counter", {"items": len(quote.get("items", [])), "strictness": strictness})
        plan = compute_counter(quote, policy, benchmarks, strictness)
        emit("plan", "counter_planned", f"Planned counter with savings {plan['draft'].get('savings_pct', 0):.2f}%.", data={"risk_flags": plan["meta"].get("risk_flags", [])})

        prog("4/7 Acting: applying budget guardrails", "act")
        bump_step("act")
        guarded = apply_guardrails(plan, policy, quote, strictness)
        draft = guarded["draft"]
        meta = guarded["meta"]
        emit(
            "act",
            "guardrails_applied",
            f"Guardrails complete. Risk level {guarded['risk_level']}.",
            level="warning" if guarded["violations"] else "info",
            data={"violations": guarded["violations"], "warnings": guarded["warnings"]},
        )

        prog("5/7 Verifying schema and outbound leaks", "verify")
        bump_step("verify")
        schema_errors = validate_output_schema(draft)
        if schema_errors:
            raise GracefulGiveUp("Schema validation failed: " + "; ".join(schema_errors[:3]))
        leak_issues = check_leaks(guarded["outbound_preview"], guarded["internal_numbers"])
        if leak_issues:
            raise GracefulGiveUp("Outbound leak check failed: " + ", ".join(leak_issues[:3]))
        emit("verify", "schema_valid", "Final draft satisfies output schema and leak rules.")

        prog("6/7 Human gate", "human-gate")
        bump_step("human-gate")
        record_tool("request_approval", {"draft_hash": hash_text(json.dumps(draft, sort_keys=True, default=str))})
        approval = request_approval(draft, draft.get("savings_pct", 0.0), guarded["risk_level"])
        if draft.get("requires_approval") or guarded["violations"]:
            status = "pending_approval"
            approval["status"] = "pending"
        else:
            status = "approved_auto"
            approval["status"] = "auto_approved"
        emit(
            "human-gate",
            "approval_requested",
            f"Approval gate created: {approval.get('approval_id')} ({approval.get('status')}).",
            data={"approval_id": approval.get("approval_id"), "status": approval.get("status")},
        )

        prog("7/7 Finalizing run", "finalize")
        bump_step("finalize")
        latency_ms = int((time.time() - started) * 1000)
        tokens_in = max(1, len(email_text) // 4)
        tokens_out = max(1, len(json.dumps(draft, default=str)) // 4)

        result = {
            "run_id": run_id,
            "created_at": now_iso(),
            "scenario": scenario_label,
            "status": status,
            "dry_run": bool(dry_run),
            "quote": quote,
            "policy": policy,
            "benchmarks": benchmarks,
            "draft": draft,
            "meta": meta,
            "totals": {
                "quoted_total": meta.get("quoted_total", 0.0),
                "counter_total": meta.get("counter_total", 0.0),
                "benchmark_high_total": meta.get("benchmark_high_total", 0.0),
                "walkaway_total": meta.get("walkaway_total", 0.0),
                "currency": meta.get("currency", quote.get("currency", "USD")),
            },
            "savings_pct": draft.get("savings_pct", 0.0),
            "risk_level": guarded["risk_level"],
            "confidence": quote.get("confidence", 0.0),
            "degraded": bool(meta.get("degraded") or guarded["violations"]),
            "warnings": guarded["warnings"],
            "violations": guarded["violations"],
            "audit": events,
            "approval": approval,
            "outbound_preview": guarded["outbound_preview"],
            "internal_numbers": guarded["internal_numbers"],
            "schema_errors": [],
            "metrics": {
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": 0.0,
                "estimated_manual_minutes": 35.0,
                "time_saved_minutes": round(max(0.0, 35.0 - latency_ms / 60000.0), 2),
            },
        }
        emit("finalize", "run_complete", f"Run completed with status {status}.", data={"latency_ms": latency_ms})
        return result

    except GracefulGiveUp as e:
        emit("give-up-gracefully", "graceful_failure", str(e), level="error")
        return make_failure_result(run_id, scenario_label, email_text, str(e), events, started)
    except Exception as e:
        emit("give-up-gracefully", "unexpected_failure", repr(e), level="error")
        return make_failure_result(run_id, scenario_label, email_text, f"Unexpected error: {e}", events, started)


def apply_decision(run_id: str, decision: str, note: str = "") -> None:
    res = st.session_state.get("results", {}).get(run_id)
    if not res:
        return
    res["status"] = decision
    res["audit"].append(
        {
            "timestamp": now_iso(),
            "run_id": run_id,
            "node": "human-gate",
            "event": "human_decision",
            "level": "info",
            "message": sanitize_text(f"Human decision: {decision}. Note: {note or 'none'}", 500),
            "data": {"decision": decision, "note": sanitize_text(note, 300)},
        }
    )
    if decision == "approved_human" and not res.get("dry_run", True):
        res["simulated_send"] = True
        res["audit"].append(
            {
                "timestamp": now_iso(),
                "run_id": run_id,
                "node": "finalize",
                "event": "simulated_send",
                "level": "info",
                "message": "Simulated outbound send recorded. No real email was sent.",
                "data": {},
            }
        )
    st.session_state.results[run_id] = res


def generate_pdf(result: Dict[str, Any]) -> Optional[bytes]:
    if not REPORTLAB_AVAILABLE:
        return None

    def esc(s: Any) -> str:
        return (
            str(s if s is not None else "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Supplier Negotiation Agent Report",
        author="Supplier Negotiation Agent",
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Supplier Negotiation Agent Report", styles["Title"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Run ID: {esc(result.get('run_id'))}", styles["Normal"]))
    story.append(Paragraph(f"Created: {esc(result.get('created_at'))}", styles["Normal"]))
    story.append(Paragraph(f"Scenario: {esc(result.get('scenario'))}", styles["Normal"]))
    story.append(Paragraph(f"Status: {esc(result.get('status'))}", styles["Normal"]))
    story.append(Paragraph(f"Risk level: {esc(result.get('risk_level'))}", styles["Normal"]))
    story.append(Spacer(1, 10))

    draft = result.get("draft", {})
    story.append(Paragraph("Draft Summary", styles["Heading2"]))
    summary_rows = [
        ["Supplier", esc(draft.get("supplier"))],
        ["Savings %", esc(draft.get("savings_pct"))],
        ["Counter total", esc(draft.get("counter", {}).get("price"))],
        ["Requires approval", esc(draft.get("requires_approval"))],
        ["Tone", esc(draft.get("tone"))],
    ]
    t = Table(summary_rows, colWidths=[130, 330])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Items", styles["Heading2"]))
    item_rows = [["SKU", "Qty", "Quoted price", "Target price"]]
    for item in draft.get("items", []):
        item_rows.append(
            [
                esc(item.get("sku")),
                esc(item.get("qty")),
                esc(item.get("quoted_price")),
                esc(item.get("target_price")),
            ]
        )
    it = Table(item_rows, colWidths=[110, 80, 140, 140])
    it.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(it)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Outbound Preview", styles["Heading2"]))
    story.append(Paragraph(f"<pre>{esc(result.get('outbound_preview', ''))}</pre>", styles["Code"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Audit Trail", styles["Heading2"]))
    audit_rows = [["Time", "Node", "Event", "Message"]]
    for ev in result.get("audit", [])[-30:]:
        audit_rows.append(
            [
                esc(ev.get("timestamp", "")[11:19]),
                esc(ev.get("node")),
                esc(ev.get("event")),
                Paragraph(esc(ev.get("message")), styles["Normal"]),
            ]
        )
    at = Table(audit_rows, colWidths=[55, 80, 100, 325])
    at.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(at)

    doc.build(story)
    return buf.getvalue()


VIDEO_TEMPLATE = """
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
  <canvas id="vm-canvas" width="640" height="400" style="width:100%; max-width:640px; border-radius:14px; background:#0b1220;"></canvas>
  <video id="vm-video" controls autoplay muted playsinline style="width:100%; max-width:640px; margin-top:10px; border-radius:14px; background:#000; display:none;"></video>
  <div id="vm-status" style="font-size:12px; color:#94a3b8; margin-top:6px;">Starting live video capture...</div>
  <a id="vm-download" download="supplier-negotiation-demo.webm" style="display:none; font-size:12px; color:#38bdf8; margin-top:4px;">Download live video file</a>
</div>
<script>
const DATA = __DATA__;
const canvas = document.getElementById('vm-canvas');
const ctx = canvas.getContext('2d');
const W = canvas.width;
const H = canvas.height;
const start = performance.now();
const DURATION = 7000;

const stages = [
  { t: 0.00, label: 'Ingest RFQ email', detail: DATA.supplier + ' • ' + DATA.currency },
  { t: 0.18, label: 'Parse line items', detail: DATA.items_count + ' items • confidence ' + DATA.confidence },
  { t: 0.36, label: 'Budget policy check', detail: 'Target discount ' + DATA.target_discount + '%' },
  { t: 0.54, label: 'Guardrails & redaction', detail: DATA.risk_level + ' risk • ' + (DATA.degraded ? 'degraded' : 'stable') },
  { t: 0.72, label: 'Counter draft', detail: 'Save ' + DATA.savings + '% • ' + DATA.counter_total + ' ' + DATA.currency },
  { t: 0.90, label: 'Human approval gate', detail: DATA.status }
];

function rr(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

let recorder = null;
let chunks = [];
try {
  if (canvas.captureStream && window.MediaRecorder) {
    const stream = canvas.captureStream(30);
    const candidates = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
    let mimeType = '';
    for (const c of candidates) {
      if (MediaRecorder.isTypeSupported(c)) {
        mimeType = c;
        break;
      }
    }
    recorder = new MediaRecorder(stream, mimeType ? { mimeType: mimeType } : undefined);
    recorder.ondataavailable = function(e) {
      if (e.data && e.data.size) chunks.push(e.data);
    };
    recorder.onstop = function() {
      const blob = new Blob(chunks, { type: mimeType || 'video/webm' });
      const url = URL.createObjectURL(blob);
      const vid = document.getElementById('vm-video');
      vid.src = url;
      vid.style.display = 'block';
      const dl = document.getElementById('vm-download');
      dl.href = url;
      dl.style.display = 'inline-block';
      document.getElementById('vm-status').textContent =
        'Live video file generated: ' + Math.round(blob.size / 1024) + ' KB WebM. Playback and download enabled.';
    };
    recorder.start();
    document.getElementById('vm-status').textContent = 'Recording live canvas to WebM video...';
  } else {
    document.getElementById('vm-status').textContent = 'Browser video recording unavailable; live canvas animation running.';
  }
} catch (err) {
  document.getElementById('vm-status').textContent = 'Recorder unavailable: ' + err.message;
}

function draw(now) {
  const p = Math.min((now - start) / DURATION, 1);

  ctx.fillStyle = '#0b1220';
  ctx.fillRect(0, 0, W, H);

  ctx.fillStyle = '#e2e8f0';
  ctx.font = 'bold 22px sans-serif';
  ctx.fillText('Supplier Negotiation Agent — live demo', 24, 42);

  ctx.fillStyle = '#94a3b8';
  ctx.font = '14px sans-serif';
  ctx.fillText(DATA.scenario, 24, 66);

  ctx.fillStyle = '#1e293b';
  rr(24, 86, W - 48, 10, 5);
  ctx.fill();

  ctx.fillStyle = '#38bdf8';
  rr(24, 86, Math.max(1, (W - 48) * p), 10, 5);
  ctx.fill();

  let y = 122;
  stages.forEach(function(s, i) {
    const active = p >= s.t;
    const nextT = (i + 1 < stages.length) ? stages[i + 1].t : 1.0;
    const done = p >= nextT;

    ctx.beginPath();
    ctx.arc(38, y + 8, 8, 0, Math.PI * 2);
    ctx.fillStyle = done ? '#22c55e' : (active ? '#38bdf8' : '#334155');
    ctx.fill();

    ctx.fillStyle = active ? '#e2e8f0' : '#64748b';
    ctx.font = 'bold 16px sans-serif';
    ctx.fillText(s.label, 58, y + 8);

    ctx.fillStyle = active ? '#94a3b8' : '#475569';
    ctx.font = '13px sans-serif';
    ctx.fillText(s.detail, 58, y + 28);

    y += 42;
  });

  ctx.fillStyle = '#0f172a';
  rr(24, H - 84, W - 48, 60, 12);
  ctx.fill();

  ctx.fillStyle = '#e2e8f0';
  ctx.font = 'bold 18px sans-serif';
  ctx.fillText('Draft total: ' + DATA.counter_total + ' ' + DATA.currency, 40, H - 50);

  ctx.fillStyle = '#22c55e';
  ctx.fillText('Savings: ' + DATA.savings + '%', W - 205, H - 50);

  if (p < 1) {
    requestAnimationFrame(draw);
  } else {
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
  }
}

requestAnimationFrame(draw);
</script>
"""


def make_video_data(result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not result:
        return {
            "scenario": "Waiting for run",
            "supplier": "—",
            "currency": "USD",
            "items_count": 0,
            "confidence": "0%",
            "target_discount": "0.0",
            "risk_level": "unknown",
            "degraded": False,
            "savings": "0.0",
            "counter_total": "0.00",
            "status": "idle",
        }

    meta = result.get("meta", {})
    draft = result.get("draft", {})
    return {
        "scenario": sanitize_text(result.get("scenario", "Run"), 80),
        "supplier": sanitize_text(draft.get("supplier", "—"), 60),
        "currency": sanitize_text(meta.get("currency", result.get("quote", {}).get("currency", "USD")), 10),
        "items_count": len(draft.get("items", [])),
        "confidence": f"{safe_float(result.get('confidence'), 0.0) * 100:.0f}%",
        "target_discount": f"{safe_float(meta.get('target_discount'), 0.0):.1f}",
        "risk_level": sanitize_text(result.get("risk_level", "unknown"), 20),
        "degraded": bool(result.get("degraded")),
        "savings": f"{safe_float(draft.get('savings_pct'), 0.0):.1f}",
        "counter_total": f"{safe_float(draft.get('counter', {}).get('price'), 0.0):,.2f}",
        "status": sanitize_text(result.get("status", "unknown"), 40),
    }


def render_live_video(result: Optional[Dict[str, Any]] = None) -> None:
    data = make_video_data(result)
    html = VIDEO_TEMPLATE.replace("__DATA__", json.dumps(data))
    components.html(html, height=620, scrolling=False)


@st.cache_resource(show_spinner=False)
def load_offline_assets() -> Dict[str, int]:
    return {
        "policies": len(POLICIES),
        "benchmarks": len(BENCHMARKS),
        "category_benchmarks": len(CATEGORY_BENCHMARKS),
        "sample_emails": len(SAMPLE_EMAILS),
    }


def read_upload(upload_file: Any) -> Tuple[Optional[str], Optional[str]]:
    if not upload_file:
        return None, None
    try:
        if upload_file.size > MAX_UPLOAD_BYTES:
            return None, "File is too large. Limit is 2 MB."
        raw = upload_file.getvalue()
        if not raw:
            return None, "Uploaded file is empty."

        if upload_file.name.lower().endswith(".eml"):
            try:
                msg = email_lib.message_from_bytes(raw)
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                return payload.decode("utf-8", errors="replace"), None
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace"), None
            except Exception:
                pass

        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            return None, "Uploaded file contains no readable text."
        return text, None
    except Exception as e:
        return None, f"Could not read file: {e}"


def render_kpis(result: Dict[str, Any]) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Risk level", str(result.get("risk_level", "unknown")).upper())
    c2.metric("Extraction confidence", f"{safe_float(result.get('confidence'), 0.0) * 100:.0f}%")
    c3.metric("Savings vs quote", f"{safe_float(result.get('savings_pct'), 0.0):.1f}%")
    c4.metric(
        "Latency",
        f"{int(result.get('metrics', {}).get('latency_ms', 0))} ms",
        delta=f"~{safe_float(result.get('metrics', {}).get('time_saved_minutes'), 0.0):.1f} min saved",
    )


def render_parsed_quote(result: Dict[str, Any]) -> None:
    quote = result.get("quote", {})
    st.markdown(
        f"**Supplier:** {sanitize_text(quote.get('supplier'), 100)} | "
        f"**Category:** {sanitize_text(quote.get('category'), 50)} | "
        f"**Currency:** {sanitize_text(quote.get('currency'), 10)} | "
        f"**Pressure language:** {'yes' if quote.get('pressure') else 'no'}"
    )

    items = quote.get("items", [])
    if items:
        df = pd.DataFrame(items)
        preferred = [
            "sku",
            "description",
            "qty_base",
            "base_unit",
            "price_base",
            "currency",
            "moq_base",
            "lead_days",
            "payment_days",
            "incoterm",
            "unit_conversion",
            "currency_conversion",
        ]
        cols = [c for c in preferred if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.warning("No line items parsed.")

    if quote.get("warnings"):
        with st.expander("Parser warnings", expanded=False):
            for w in quote["warnings"]:
                st.markdown(f"- {sanitize_text(w, 300)}")


def render_policy_panel(result: Dict[str, Any]) -> None:
    policy = result.get("policy", {})
    meta = result.get("meta", {})
    st.markdown("**Budget policy and negotiation envelope**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Effective target discount", f"{safe_float(meta.get('target_discount'), policy.get('target_discount_pct', 0.0)):.1f}%")
    c2.metric("Payment cap", f"net {int(policy.get('payment_days', 0))}")
    c3.metric("Minimum lead time", f"{int(policy.get('min_lead_days', 0))} days")
    c4.metric("Auto-approve savings cap", f"{safe_float(meta.get('auto_threshold'), policy.get('auto_approve_max_savings_pct', 0.0)):.1f}%")
    st.caption("Internal maximum and walk-away values are redacted from outbound text and only shown in internal audit views.")


def render_savings_chart(result: Dict[str, Any]) -> None:
    totals = result.get("totals", {})
    df = pd.DataFrame(
        {
            "Amount": [
                safe_float(totals.get("quoted_total"), 0.0),
                safe_float(totals.get("counter_total"), 0.0),
                safe_float(totals.get("benchmark_high_total"), 0.0),
                safe_float(totals.get("walkaway_total"), 0.0),
            ]
        },
        index=["Quoted total", "Proposed total", "Benchmark high total", "Walk-away cap"],
    )
    st.bar_chart(df)


def render_human_gate(result: Dict[str, Any]) -> None:
    status = result.get("status", "unknown")
    approval = result.get("approval", {})
    st.markdown(f"**Approval status:** `{status}`")
    st.markdown(f"**Approval ID:** `{sanitize_text(approval.get('approval_id'), 40)}`")

    if status == "pending_approval":
        st.warning("Human gate active. Approve, reject, or escalate before any outbound action.")
        note = st.text_input("Decision note", key=f"note_{result.get('run_id')}")
        c1, c2, c3 = st.columns(3)
        if c1.button("Approve", key=f"approve_{result.get('run_id')}"):
            apply_decision(result["run_id"], "approved_human", note)
            st.rerun()
        if c2.button("Reject", key=f"reject_{result.get('run_id')}"):
            apply_decision(result["run_id"], "rejected", note)
            st.rerun()
        if c3.button("Escalate", key=f"escalate_{result.get('run_id')}"):
            apply_decision(result["run_id"], "escalated", note)
            st.rerun()
    elif status in ("approved_auto", "approved_human"):
        st.success("Approved. Dry run means no real email is sent.")
    elif status == "rejected":
        st.error("Rejected by human reviewer.")
    elif status == "escalated":
        st.info("Escalated to category manager.")
    elif status == "failed":
        st.error("Run failed gracefully. No outbound draft was authorized.")


def render_editor(result: Dict[str, Any]) -> None:
    draft = result.get("draft", {})
    totals = result.get("totals", {})
    policy = result.get("policy", {})
    quote = result.get("quote", {})

    with st.form("edit_draft_form"):
        st.subheader("Editable draft")
        new_price = st.number_input(
            "Counter total price",
            min_value=0.0,
            value=float(safe_float(draft.get("counter", {}).get("price"), 0.0)),
            step=1.0,
            format="%.2f",
        )
        c1, c2 = st.columns(2)
        new_lead = c1.number_input(
            "Lead days",
            min_value=0,
            value=int(safe_float(draft.get("terms", {}).get("lead_days"), 0.0)),
            step=1,
        )
        new_payment = c2.number_input(
            "Payment days",
            min_value=0,
            value=int(safe_float(draft.get("terms", {}).get("payment_days"), 0.0)),
            step=1,
        )

        tones = [
            "appreciative and concise",
            "collaborative and evidence-based",
            "firm, neutral, relationship-preserving",
            "custom",
        ]
        current_tone = draft.get("tone", tones[0])
        if current_tone not in tones:
            tones.insert(0, current_tone)
        tone_index = tones.index(current_tone)
        tone = st.selectbox("Tone", tones, index=tone_index)

        concessions_text = st.text_area(
            "Concessions (one per line)",
            value="\n".join(draft.get("counter", {}).get("concessions", [])),
            height=120,
        )
        submitted = st.form_submit_button("Apply edits and revalidate")

    if submitted:
        updated = json.loads(json.dumps(result, default=str))
        quoted_total = safe_float(updated.get("totals", {}).get("quoted_total"), 0.0)
        walkaway_total = safe_float(updated.get("totals", {}).get("walkaway_total"), 0.0)
        quoted_lead = safe_float(updated.get("quote", {}).get("terms", {}).get("lead_days"), 0.0)
        policy_payment = int(policy.get("payment_days", 0))

        critical: List[str] = []
        warn: List[str] = []

        if new_price > walkaway_total + 0.01:
            new_price = walkaway_total
            critical.append("Edited counter price was capped to walk-away ceiling.")
        if new_payment > policy_payment:
            new_payment = policy_payment
            critical.append("Edited payment terms were capped to policy maximum.")
        if quoted_lead and new_lead < quoted_lead:
            new_lead = int(quoted_lead)
            warn.append("Edited lead time was restored to supplier-quoted minimum.")

        updated["draft"]["counter"]["price"] = round(float(new_price), 2)
        updated["draft"]["terms"]["lead_days"] = int(new_lead)
        updated["draft"]["terms"]["payment_days"] = int(new_payment)
        updated["draft"]["tone"] = str(tone)
        updated["draft"]["counter"]["concessions"] = [
            sanitize_text(x, 220) for x in str(concessions_text).split("\n") if x.strip()
        ]

        savings = 0.0
        if quoted_total > 0:
            savings = max(0.0, (1.0 - float(new_price) / quoted_total) * 100.0)
        updated["draft"]["savings_pct"] = round(savings, 2)
        updated["totals"]["counter_total"] = round(float(new_price), 2)
        updated["savings_pct"] = round(savings, 2)

        schema_errors = validate_output_schema(updated["draft"])
        if schema_errors:
            critical.extend(schema_errors)

        updated["violations"] = critical
        updated["warnings"] = list(set(updated.get("warnings", []) + warn))
        updated["draft"]["requires_approval"] = True
        updated["status"] = "pending_approval"
        updated["degraded"] = bool(critical) or bool(updated.get("degraded"))

        internal_numbers = updated.get("internal_numbers", [])
        outbound = build_outbound_preview(updated["draft"], updated["quote"], updated["meta"])
        updated["outbound_preview"] = redact_internal(outbound, internal_numbers)

        updated["audit"].append(
            {
                "timestamp": now_iso(),
                "run_id": updated["run_id"],
                "node": "verify",
                "event": "draft_edited",
                "level": "warning" if critical else "info",
                "message": sanitize_text("Draft edited and revalidated. " + "; ".join(critical[:2]), 500),
                "data": {"critical": critical, "warnings": warn},
            }
        )

        st.session_state.results[result["run_id"]] = updated
        if critical:
            st.error("Edits applied with guardrail interventions: " + "; ".join(critical))
        else:
            st.success("Edits applied. Draft re-entered the human approval gate.")
        st.rerun()


def render_downloads(result: Dict[str, Any]) -> None:
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "Download JSON",
        json.dumps(result, indent=2, default=str).encode("utf-8"),
        file_name=f"{result.get('run_id', 'run')}.json",
        mime="application/json",
        use_container_width=True,
    )

    events_df = pd.DataFrame(result.get("audit", []))
    c2.download_button(
        "Download audit CSV",
        events_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{result.get('run_id', 'run')}_audit.csv",
        mime="text/csv",
        use_container_width=True,
    )

    if REPORTLAB_AVAILABLE:
        pdf_bytes = generate_pdf(result)
        if pdf_bytes:
            c3.download_button(
                "Download PDF report",
                pdf_bytes,
                file_name=f"{result.get('run_id', 'run')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            c3.button("PDF unavailable", disabled=True, use_container_width=True)
    else:
        c3.button("Install reportlab for PDF", disabled=True, use_container_width=True)


def render_results_tab(result: Optional[Dict[str, Any]]) -> None:
    if not result:
        st.info("Run a simulation from the Live Run tab.")
        return

    if result.get("degraded"):
        st.warning("Degraded mode: the draft is usable but requires human review.")

    render_kpis(result)
    st.divider()

    left, right = st.columns([1.15, 0.85])
    with left:
        st.subheader("Draft and outbound preview")
        st.json(result.get("draft", {}))
        st.markdown("#### Outbound preview (redacted)")
        st.code(result.get("outbound_preview", ""), language="markdown")

        if result.get("violations"):
            st.error("Guardrail violations: " + "; ".join(result["violations"]))
        if result.get("warnings"):
            with st.expander("Warnings", expanded=False):
                for w in result["warnings"]:
                    st.markdown(f"- {sanitize_text(w, 300)}")

    with right:
        st.subheader("Control panel")
        render_human_gate(result)
        st.divider()
        render_editor(result)
        st.divider()
        render_downloads(result)


def render_audit_tab(result: Optional[Dict[str, Any]]) -> None:
    if not result:
        st.info("No audit trail yet.")
        return

    df = pd.DataFrame(result.get("audit", []))
    if df.empty:
        st.info("No audit events.")
        return

    level_opts = sorted(df["level"].dropna().unique().tolist())
    node_opts = sorted(df["node"].dropna().unique().tolist())

    c1, c2, c3 = st.columns([1, 1, 2])
    sel_levels = c1.multiselect("Levels", level_opts, default=level_opts)
    sel_nodes = c2.multiselect("Nodes", node_opts, default=node_opts)
    query = c3.text_input("Search messages")

    fd = df[df["level"].isin(sel_levels) & df["node"].isin(sel_nodes)]
    if query:
        fd = fd[fd["message"].astype(str).str.contains(query, case=False, na=False)]

    st.dataframe(fd, use_container_width=True, hide_index=True)


def render_about_tab() -> None:
    assets = load_offline_assets()
    st.markdown(
        """
### What this app is

This is an offline, production-shaped demo of a **Supplier Negotiation Agent**.
It reads supplier quote emails, normalizes units and currencies, applies budget
guardrails, drafts counter-offers, and holds every risky draft behind a human
approval gate.

It does **not** require an API key. The Gemini-style intelligence layer is
represented by a deterministic rule-based surrogate so the workflow, guardrails,
auditability, and UI can be evaluated safely.

### Architecture strip

`Ingestion -> Parsing/Normalization -> Policy + Benchmark -> Counter Planner -> Guardrails -> Human Gate -> Finalize`

### What the AI is not allowed to do

- It cannot send email.
- It cannot reveal internal maximum price or walk-away price in outbound text.
- It cannot agree to payment terms beyond policy.
- It cannot bypass the human approval gate for risky drafts.
- It cannot call unlisted tools.
- It cannot treat supplier pressure language as authorization.

### Current limitations

- Parsing is heuristic and optimized for the bundled RFQ format.
- Historical benchmarks are local fixtures, not live procurement data.
- The offline surrogate is not a substitute for a validated LLM extraction layer.
- PDF export depends on ReportLab being installed.
        """
    )

    st.markdown("### Bundled assets")
    st.json(assets)

    st.markdown("### Tool contracts")
    st.dataframe(pd.DataFrame(TOOL_CONTRACTS), use_container_width=True, hide_index=True)


def main() -> None:
    st.title("🤖 Supplier Negotiation Agent")
    st.caption("Offline live demo: budget guardrails, approval gate, audit trail, and in-browser video generation.")

    with st.sidebar:
        st.header("Inputs and settings")

        scenario_options = list(SAMPLE_EMAILS.keys())
        selected = st.selectbox("Demo scenario", scenario_options, key="selected_scenario")

        upload = st.file_uploader(
            "Upload supplier quote email (.txt, .eml, .html)",
            type=["txt", "eml", "html"],
            key="upload_file",
        )
        upload_text, upload_error = read_upload(upload)
        if upload_error:
            st.error(upload_error)

        use_upload = st.checkbox("Use uploaded email", value=bool(upload and not upload_error))
        if upload_error:
            use_upload = False

        strictness = st.slider("Guardrail strictness", min_value=0, max_value=100, value=50, step=1)
        try:
            dry_run = st.toggle("Dry run", value=True, key="dry_run_toggle")
        except Exception:
            dry_run = st.checkbox("Dry run", value=True, key="dry_run_toggle")

        st.text_input(
            "Gemini API key (optional, offline simulation ignores it)",
            type="password",
            value=os.getenv("GEMINI_API_KEY", ""),
            key="api_key_optional",
            help="Leave blank. This demo runs without an API key.",
        )

        run_btn = st.button("Run simulation", use_container_width=True)

        if use_upload and upload_text:
            email_text = upload_text
            scenario_label = f"Custom upload: {sanitize_text(upload.name if upload else 'file', 60)}"
            source_key = "upload:" + hash_text(upload_text)
        else:
            email_text = SAMPLE_EMAILS[selected]
            scenario_label = selected
            source_key = "sample:" + selected

        if run_btn:
            st.session_state.pending_run = True

        if st.session_state.get("last_source_key") != source_key:
            st.session_state.pending_run = True
            st.session_state.last_source_key = source_key

    st.session_state.setdefault("results", {})
    st.session_state.setdefault("active_run_id", None)

    tabs = st.tabs(["Live Run", "Results", "Audit Log", "About"])

    active_result = None

    with tabs[0]:
        if st.session_state.get("pending_run"):
            st.session_state.pending_run = False
            status = st.status("Running supplier negotiation simulation...", expanded=True)

            def progress_callback(msg: str) -> None:
                status.write(msg)

            active_result = run_pipeline(
                email_text=email_text,
                scenario_label=scenario_label,
                strictness=int(strictness),
                dry_run=bool(dry_run),
                progress_cb=progress_callback,
            )
            st.session_state.results[active_result["run_id"]] = active_result
            st.session_state.active_run_id = active_result["run_id"]

            if active_result.get("status") == "failed":
                status.update(label="Run failed gracefully", state="error")
            else:
                status.update(label="Run complete", state="complete")
        else:
            active_result = st.session_state.results.get(st.session_state.active_run_id)

        render_live_video(active_result)

        if active_result:
            st.divider()
            render_kpis(active_result)
            st.divider()
            c1, c2 = st.columns([1.1, 0.9])
            with c1:
                render_parsed_quote(active_result)
            with c2:
                render_policy_panel(active_result)
                render_savings_chart(active_result)

    with tabs[1]:
        render_results_tab(active_result)

    with tabs[2]:
        render_audit_tab(active_result)

    with tabs[3]:
        render_about_tab()


main()