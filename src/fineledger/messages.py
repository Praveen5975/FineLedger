"""Outgoing messages (what a WhatsApp gateway would send), in the recipient's language.

English, Hindi and Tamil are provided for the two most important prompts (confirm, payment due).
Those translations were machine-written and need native-speaker review before real use.
Other message kinds fall back to English.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .gold import fmt_mg


@dataclass
class Message:
    to: str
    lang: str
    kind: str
    text: str
    cites: list[int] = field(default_factory=list)


KIND_LABEL = {
    "en": {"ISSUE": "gold issued", "RETURN": "return", "SCRAP": "scrap return", "RECOVERY": "refiner recovery"},
    "hi": {"ISSUE": "सोना जारी", "RETURN": "वापसी", "SCRAP": "कतरन वापसी", "RECOVERY": "रिफाइनर से वसूली"},
    "ta": {"ISSUE": "தங்கம் வழங்கல்", "RETURN": "திருப்பம்", "SCRAP": "கழிவு திருப்பம்", "RECOVERY": "ரிஃபைனர் மீட்பு"},
}

T = {
    "confirm_gold": {
        "en": "{who} recorded {what} for order {order}: {gross} gross ({fine} fine gold). Reply 1 to confirm, 2 if it is wrong.",
        "hi": "{who} ने {order} के लिए {what} दर्ज किया: {gross} (शुद्ध सोना {fine})। सही है तो 1 भेजें, गलत है तो 2 भेजें।",
        "ta": "{who} {order}-க்கு {what} பதிவு செய்தார்: {gross} (தூய தங்கம் {fine}). சரியென்றால் 1, தவறு என்றால் 2 அனுப்பவும்.",
    },
    "confirm_payment": {
        "en": "{who} recorded a payment of Rs {amount} for order {order}. Reply 1 to confirm, 2 if it is wrong.",
        "hi": "{who} ने {order} के लिए ₹{amount} का भुगतान दर्ज किया। सही है तो 1, गलत है तो 2 भेजें।",
        "ta": "{who} {order}-க்கு ₹{amount} பணம் செலுத்தியதாகப் பதிவு செய்தார். சரியென்றால் 1, தவறு என்றால் 2 அனுப்பவும்.",
    },
    "payment_due": {
        "en": "Order {order} was delivered {days} days ago and Rs {amount} is still unpaid.",
        "hi": "{order} की डिलीवरी को {days} दिन हो गए हैं और ₹{amount} अभी बाकी है।",
        "ta": "{order} டெலிவரி ஆகி {days} நாட்கள் ஆகின்றன; ₹{amount} இன்னும் நிலுவையில் உள்ளது.",
    },
}


def render(kind: str, lang: str, **kw) -> str:
    variants = T[kind]
    return (variants.get(lang) or variants["en"]).format(**kw)


def confirm_request(ledger, entry, to: str) -> Message:
    d = entry.data
    lang = ledger.party(to)["lang"]
    who = ledger.party(d["by"])["name"]
    if d["kind"] == "PAYMENT":
        text = render("confirm_payment", lang, who=who, order=d["order_id"], amount=f"{d['amount_paise'] / 100:,.0f}")
    else:
        what = KIND_LABEL.get(lang, KIND_LABEL["en"])[d["kind"]]
        text = render("confirm_gold", lang, who=who, what=what, order=d["order_id"],
                      gross=fmt_mg(d["gross_mg"]), fine=fmt_mg(d["fine_mg"]))
    return Message(to, lang, "confirm_request", text, [entry.seq])
