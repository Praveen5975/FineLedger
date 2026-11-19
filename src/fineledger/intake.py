"""Intake: turns a short WhatsApp-style message into a structured entry.

Hard rule: NEVER guess a weight. If anything is missing or ambiguous it asks the sender
to resend. (A voice/photo front end would feed text into this same parser; the OCR and
speech layers are roadmap, see README.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .gold import fineness_of, to_mg

KINDS = {"issue": "ISSUE", "issued": "ISSUE", "return": "RETURN", "returned": "RETURN", "scrap": "SCRAP",
         "recovery": "RECOVERY", "recovered": "RECOVERY", "paid": "PAYMENT", "payment": "PAYMENT"}


class ParseError(ValueError):
    pass


@dataclass
class ParsedEntry:
    kind: str
    order_id: str
    gross_mg: int | None = None
    fineness: int | None = None
    amount_paise: int | None = None
    wastage_bp: int | None = None
    final: bool = False


def parse(text: str) -> ParsedEntry:
    t = text.strip()
    low = t.lower()
    first = re.match(r"\s*([a-z]+)", low)
    kind = KINDS.get(first.group(1)) if first else None
    if not kind:
        raise ParseError("Start with issue / return / scrap / recovery / paid, e.g. 'issue 10.250g 22K order O-101 wastage 2.5%'.")
    om = re.search(r"order\s+([A-Za-z0-9\-]+)", t, re.I)
    if not om:
        raise ParseError("Which order? Add 'order O-101'.")
    p = ParsedEntry(kind=kind, order_id=om.group(1))
    if kind == "PAYMENT":
        rest = re.sub(r"order\s+[A-Za-z0-9\-]+", "", t, flags=re.I)
        rest = re.sub(r"^\s*[A-Za-z]+", "", rest, count=1)
        am = re.search(r"(\d[\d,]*)", rest)
        if not am:
            raise ParseError("How much was paid? e.g. 'paid 4500 order O-101'.")
        p.amount_paise = int(am.group(1).replace(",", "")) * 100
        return p
    wm = re.search(r"(\d+(?:\.\d+)?)\s*g\b", low)
    if not wm:
        raise ParseError("What weight? Add it in grams, e.g. '10.250g'. Weights are never guessed.")
    try:
        p.gross_mg = to_mg(wm.group(1))
    except ValueError as e:
        raise ParseError(str(e)) from e
    pm = re.search(r"\b(\d{2}k)\b|\b(999|916|833|750|585)\b", low)
    if not pm:
        raise ParseError("What purity? e.g. '22K' or '916'.")
    p.fineness = fineness_of((pm.group(1) or pm.group(2)))
    if kind == "ISSUE":
        wp = re.search(r"wastage\s+(\d+(?:\.\d+)?)\s*%", low)
        if not wp:
            raise ParseError("Issue must state the agreed wastage, e.g. 'wastage 2.5%'.")
        p.wastage_bp = int(Decimal(wp.group(1)) * 100)
    if kind == "RETURN":
        p.final = bool(re.search(r"\bfinal\b", low))
    return p


def scale_check(typed_mg: int, ocr_mg: int, tolerance_mg: int = 0) -> tuple[bool, str]:
    """Cross-check the typed weight against the scale-display photo reading."""
    if abs(typed_mg - ocr_mg) <= tolerance_mg:
        return True, "typed weight matches the scale display"
    return False, f"typed {typed_mg} mg but scale display reads {ocr_mg} mg - re-weigh before recording"
