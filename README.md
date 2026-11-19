# FineLedger

**Every gram, agreed by both hands.**

A countersigned fine-gold ledger, run by agents, for jewellers and the karigars who work for them.
Built by **Team Fineworks** for the GVAS hackathon, Jeweltech theme, problem statement 2.2
*"Gold given to karigars for job-work is tracked on trust, and disputes follow."*

![tests](https://img.shields.io/badge/tests-35%20passing-brightgreen) ![python](https://img.shields.io/badge/python-3.11%2B-blue) ![deps](https://img.shields.io/badge/core%20dependencies-0-lightgrey) ![license](https://img.shields.io/badge/license-MIT-black)

## The idea in 30 seconds
Disputes about gold are not a tracking problem, they are a trust problem: the record sits in one party's
notebook. FineLedger makes every issue, return, scrap and payment an entry that **both** the jeweller and the
karigar confirm (by replying `1` on WhatsApp), chained so nothing can be edited silently. Agents then do what
busy people skip: propose fair wastage from history, warn before a wedding date is missed, show how long a
karigar has waited to be paid, and turn "our numbers differ" into a line-by-line diff.
**The AI proposes. The two people decide.**

## See it
```bash
pip install -e ".[dev]"
python -m fineledger demo      # a full story in your terminal
pytest -q                      # 35 tests
python -m fineledger serve     # API on a demo ledger (demo keys)
```
Excerpts from a real run (full output: [`docs/DEMO_OUTPUT.txt`](docs/DEMO_OUTPUT.txt)):

```
AGENT LOOP: what the agents do right now
  -> K1 [ta] (confirm_request) Lakshmi Jewellers O-201-க்கு தங்கம் வழங்கல் பதிவு செய்தார்: 40.000 g (தூய தங்கம் 36.640 g). சரியென்றால் 1, தவறு என்றால் 2 அனுப்பவும்.
  -> J1 [en] (risk_alert) Order O-201 (chain) due 2026-11-22: 3 days left, about 4.6 days of work expected (median 6 days, 1 other open order(s)). Risk: RED.
  -> K1 [ta] (payment_due) O-202 டெலிவரி ஆகி 11 நாட்கள் ஆகின்றன; ₹6,000 இன்னும் நிலுவையில் உள்ளது.
  reassignment options for O-201 (needs jeweller approval): [{'karigar': 'K2', 'expected_days': 3.0}]

"THE JEWELLER'S NUMBER DIFFERS FROM MINE": diff two notebooks
  2 agree, 1 differ in weight, 1 only in A, 1 only in B
  differs : 2026-10-09 RETURN  jeweller 24.100 g vs karigar 24.400 g  (delta 0.300 g)

TAMPER TEST: change one weight in the ledger file
  original ledger verifies: True
  tampered ledger verifies: False  ->  record 102: contents do not match their hash (tampered)
```

## How the brief maps to the code
| The brief says | Where it lives | Proved by |
|----------------|----------------|-----------|
| Accuracy has to hold at the level of weight | Integer milligrams of fine gold; sub-mg input rejected, not rounded ([`gold.py`](src/fineledger/gold.py)) | `test_milligram_precision_and_fine_gold`, `test_rounding_is_half_even_and_deterministic` |
| An audit trail both parties accept | Countersigned, hash-chained, append-only ([`ledger.py`](src/fineledger/ledger.py)) | `test_entry_needs_both_parties_before_it_counts`, tamper and deletion tests |
| Settlements go to both parties for approval | Settlement is a proposal; final only when both approve; the agent cannot approve | `test_settlement_needs_both_parties_and_agent_cannot_approve` |
| Each karigar has full access to his own account | `GET /karigars/{id}/account`; a jeweller sees only shared orders | `test_karigar_sees_everything_of_his_own_but_not_others` |
| Fairness matters most to the artisan | Gold in the workshop is not a loss; jeweller-caused delays excused; payer record for jewellers; consent-gated passport | `test_open_order_gold_is_not_counted_as_loss`, `test_passport_excuses_jeweller_caused_delay`, `test_passport_needs_consent_and_can_be_withdrawn` |
| Missed delivery dates | Occasion agent works back from the customer's date | `test_occasion_red_then_green` |
| Artisans waiting to be paid | Payment agent starts a clock at delivery, visible to both | `test_payment_alert_after_grace_period` |
| Numbers differ | `diff_statements`, line by line | `test_diff_statements_finds_each_kind_of_difference` |
| A clean record looks different to anyone deciding whether to trust him | Trust Passport, owned by the karigar | passport tests |

## Design decisions worth reading
1. **Karigar first.** WhatsApp text, voice and photo; no app install; free for karigars.
2. **Agents never do the arithmetic of who owes what.** That is deterministic and auditable; a language model belongs at the edges (understanding a voice note, phrasing a message).
3. **Never guess a weight.** Ambiguous input gets a "please resend", not a best guess.
4. **No invented defaults.** With too little history the wastage agent says so instead of quoting an industry number.
5. **Every agent message cites the ledger entries behind it.**

More in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), including the honest threat model.

## What is built, and what is not
| Built and tested | Not built yet (roadmap) |
|------------------|--------------------------|
| Hash-chained, countersigned ledger with disputes and reversals | WhatsApp Cloud API gateway (messages are produced; sending is not wired) |
| Fine-gold arithmetic in integer mg | Voice-to-text and scale-photo OCR (text parser and the cross-check function exist) |
| Intake parser, wastage, occasion, payment, reconciliation, trust passport | An LLM layer for free-form and regional-language intake |
| Agent loop producing localised messages (English, Tamil, Hindi for key prompts) | Native review of Tamil and Hindi text |
| HTTP API with party authentication and access rules | Real identity (WhatsApp-verified, OTP) and on-device signing keys |
| 35 tests, CI, a one-command demo | Jeweller dashboard UI; Postgres storage; refiner and lender integrations |

The assumptions behind the numbers, and our plan to validate them with karigars and jewellers (not yet done), are in
[`docs/FIELD_VALIDATION.md`](docs/FIELD_VALIDATION.md). The scenario data in the demo is synthetic.

## Layout
```
src/fineledger/
  gold.py            integer-mg fine-gold maths
  ledger.py          append-only countersigned hash chain
  accounts.py        per-order accounts and the karigar's statement
  intake.py          message -> entry (never guesses)
  messages.py        localised outgoing messages
  agents/            wastage, occasion, payments, reconcile, trust, runner
  api.py             FastAPI layer          cli.py / demo.py   the story
tests/               35 tests               docs/              architecture, validation, demo output
```

## Team
Fineworks: 
  1.Praveen Balaji G
  2.Nitish M
  3.Sakthi Saran G
  4.Saranesh S
