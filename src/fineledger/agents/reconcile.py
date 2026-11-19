"""Reconciliation Agent.

1. diff_statements: when the jeweller's notebook and the karigar's notebook disagree,
   show EXACTLY where, instead of arguing about totals.
2. propose_settlement: drafts a settlement from confirmed entries only. It is a proposal;
   it becomes final only when BOTH parties approve. The agent cannot approve anything.
"""
from __future__ import annotations

from datetime import date

from ..accounts import karigar_accounts
from ..gold import fmt_mg, to_mg


def diff_statements(a_rows: list[dict], b_rows: list[dict], date_tol_days: int = 1,
                    pair_within: float = 0.2) -> dict:
    """Rows look like {'date': '2026-11-01', 'kind': 'ISSUE', 'grams': '10.000'}."""
    def norm(rows):
        return [{"date": date.fromisoformat(r["date"]), "kind": r["kind"].upper(), "mg": to_mg(r["grams"]), "raw": r}
                for r in rows]
    A, B = norm(a_rows), norm(b_rows)
    used_b: set[int] = set()
    matched, mismatched, only_a = [], [], []
    for x in A:
        best, best_gap = None, None
        for j, y in enumerate(B):
            if j in used_b or y["kind"] != x["kind"] or abs((y["date"] - x["date"]).days) > date_tol_days:
                continue
            gap = abs(y["mg"] - x["mg"])
            if best is None or gap < best_gap:
                best, best_gap = j, gap
        if best is None:
            only_a.append(x["raw"])
            continue
        y = B[best]
        if best_gap == 0:
            used_b.add(best)
            matched.append(x["raw"])
        elif best_gap <= pair_within * max(x["mg"], 1):
            used_b.add(best)
            mismatched.append({"a": x["raw"], "b": y["raw"], "delta_mg": y["mg"] - x["mg"]})
        else:
            only_a.append(x["raw"])
    only_b = [y["raw"] for j, y in enumerate(B) if j not in used_b]
    return {"matched": matched, "weight_mismatch": mismatched, "only_in_a": only_a, "only_in_b": only_b,
            "summary": f"{len(matched)} agree, {len(mismatched)} differ in weight, "
                       f"{len(only_a)} only in A, {len(only_b)} only in B"}


def propose_settlement(ledger, jeweller: str, karigar: str, ts=None):
    ready, blocked, cites = [], [], []
    fine_owed = labour_owed = 0
    lines = []
    for a in karigar_accounts(ledger, karigar, jeweller):
        final_recorded = any(r.data.get("final") for r in ledger.entries(order_id=a.order_id, kind="RETURN"))
        if not (a.closed or final_recorded):
            continue  # still in the workshop: nothing to settle yet
        if a.pending or a.disputed or not a.closed:
            # something on this order is unconfirmed or disputed: list it, never silently drop it
            blocked.append({"order": a.order_id, "pending": a.pending, "disputed": a.disputed})
            continue
        ready.append(a.order_id)
        cites += a.cites
        fine_owed += a.excess_mg
        labour_owed += a.outstanding_paise
        if a.excess_mg or a.outstanding_paise:
            lines.append(f"{a.order_id}: karigar owes {fmt_mg(a.excess_mg)} fine gold beyond agreed wastage; "
                         f"jeweller owes Rs {a.outstanding_paise / 100:,.0f} labour")
    data = {"jeweller": jeweller, "karigar": karigar, "orders": ready,
            "fine_owed_by_karigar_mg": fine_owed, "labour_owed_by_jeweller_paise": labour_owed,
            "blocked_orders": blocked, "explanation": lines, "cites": sorted(set(cites)),
            "proposed_by": "agent:reconcile",
            "note": "Proposal only. Final when BOTH parties approve. Gold and rupees are shown separately; "
                    "how to net them (e.g. at an agreed rate) is the parties' decision."}
    return ledger.add_settlement(data, ts)
