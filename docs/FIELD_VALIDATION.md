# Field validation

**Status: not yet validated with karigars or jewellers.** This design was built from the problem brief
and desk reasoning only. The table below is our validation plan, not a record of findings.

FineLedger encodes assumptions about how job-work really runs. Each one below is a
**hypothesis until a karigar or jeweller confirms it**. Fill in the findings column from real
interviews (target: karigars from several workshops and jewellers of different sizes). Do not
leave invented answers here.

## The six questions from the problem brief

| # | Question | What the code assumes today | Where it matters | Finding (to fill) |
|---|----------|-----------------------------|------------------|-------------------|
| 1 | How is gold issued and recorded today, and who holds the record? | A slip/notebook held by the jeweller; the karigar often keeps none | `intake.py`, `ledger.py` | Not yet validated (planned) |
| 2 | How is wastage agreed, and how often is it disputed? | Agreed verbally per piece, as a percentage of issued gold | `ISSUE.wastage_bp`, `agents/wastage.py` | Not yet validated (planned) |
| 3 | What happens when a piece is late for a wedding? | Delay causes are contested; a note both sides confirm settles whose it was | `DELAY_NOTE`, `agents/occasion.py`, `agents/trust.py` | Not yet validated (planned) |
| 4 | How long does a karigar wait to be paid after delivery? | Labour is due on delivery; waits beyond a grace period are shown to both sides | `agents/payments.py` | Not yet validated (planned) |
| 5 | What does a karigar do when the jeweller's number differs from his own? | Argument over totals, no line-by-line comparison | `agents/reconcile.py: diff_statements` | Not yet validated (planned) |
| 6 | How many karigars and open orders does a typical shop handle at once? | Tens of karigars, several open orders each | load penalty in `agents/occasion.py` | Not yet validated (planned) |

## Assumptions to confirm or correct

| Assumption | Current value | Why it might be wrong |
|------------|---------------|-----------------------|
| Wastage convention: loss up to the agreed wastage is the jeweller's; loss beyond it is owed by the karigar | `accounts.py` | Practice varies by region and trade; some shops charge wastage to the karigar up front |
| Purity uses BIS hallmark fineness (22K = 916, not 22/24) | `gold.py` | Some workshops quote touch or karat informally; may need conversion rules |
| Weights recorded to 1 mg | `gold.to_mg` | Many shop scales read to 10 mg; the precision is a ceiling, not a requirement |
| Grace period 3 days, escalation 10 days for payment | `payments.assess` | Illustrative only |
| Occasion risk: +15% time per extra open order, 2-day buffer | `occasion.assess` | Heuristic; calibrate from question 6 |
| Minimum 3 past orders before proposing wastage; passport needs 5 delivered orders | `wastage.py`, `trust.py` | Illustrative only |
| Passport bands ("strong record" at 80% on time and within wastage) | `trust.py` | Illustrative; lenders will have their own criteria |
| Tamil and Hindi message text | `messages.py` | Machine-written; needs native-speaker review |

## Interview log

| Date | Who (role, workshop type, area) | Key quotes | What changed in the design |
|------|---------------------------------|------------|----------------------------|
| [INSERT] | [INSERT] | [INSERT] | Not yet validated (planned) |
