"""Fine-gold arithmetic.

Weights are integers (milligrams). No float ever touches a weight, so two parties
running the same inputs always reach the same answer to the milligram.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

# BIS hallmark fineness: parts per thousand of pure gold.
FINENESS = {"24K": 999, "22K": 916, "20K": 833, "18K": 750, "14K": 585}


def to_mg(grams) -> int:
    """'10.250' -> 10250. Rejects anything finer than 1 mg instead of rounding it away."""
    try:
        d = Decimal(str(grams).strip())
    except InvalidOperation as e:
        raise ValueError(f"not a weight: {grams!r}") from e
    mg = d * 1000
    if mg != mg.to_integral_value():
        raise ValueError("weights are recorded to the milligram (3 decimals of a gram)")
    if mg < 0:
        raise ValueError("weight cannot be negative")
    return int(mg)


def fineness_of(value) -> int:
    """'22K' / '916' / 916 -> 916."""
    if isinstance(value, str):
        s = value.strip().upper()
        if s in FINENESS:
            return FINENESS[s]
        if not s.isdigit():
            raise ValueError(f"unknown purity: {value!r}")
        value = int(s)
    f = int(value)
    if not 1 <= f <= 999:
        raise ValueError("fineness must be between 1 and 999")
    return f


def fine_mg(gross_mg: int, fineness: int) -> int:
    """Pure-gold content in mg, rounded half-to-even. Both parties use this same function."""
    q, r = divmod(gross_mg * fineness, 1000)
    if r > 500 or (r == 500 and q % 2 == 1):
        q += 1
    return q


def fmt_mg(mg: int) -> str:
    sign = "-" if mg < 0 else ""
    a = abs(mg)
    return f"{sign}{a // 1000}.{a % 1000:03d} g"
