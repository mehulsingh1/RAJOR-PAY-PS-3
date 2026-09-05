"""
Recovery message templates — English and Hinglish, one per failure code.

Placeholders: {name} {amount} {link} {days}
The same body is used across channels (email adds the subject line).
Track 3's problem statement explicitly lists "Hinglish voice recovery" — these
are the text equivalents.
"""

RECOVERY_LINK = "https://rzp.io/i/recover/{token}"

TEMPLATES = {
    "insufficient_funds": {
        "subject": "Your payment of ₹{amount} didn't go through",
        "en": "Hi {name}, your payment of ₹{amount} failed due to insufficient balance. "
              "Please top up and retry here: {link}",
        "hinglish": "Hi {name}, aapka ₹{amount} ka payment insufficient balance ki wajah se "
                    "fail ho gaya. Balance add karke yahan retry karein: {link}",
    },
    "bank_decline": {
        "subject": "Payment of ₹{amount} was declined by your bank",
        "en": "Hi {name}, your bank declined the ₹{amount} payment. Try another method "
              "or retry here: {link}",
        "hinglish": "Hi {name}, aapke bank ne ₹{amount} ka payment decline kar diya. "
                    "Doosra method try karein ya yahan retry karein: {link}",
    },
    "card_expired": {
        "subject": "Update your card to complete ₹{amount}",
        "en": "Hi {name}, the card on file has expired. Update your card details to "
              "complete the ₹{amount} payment: {link}",
        "hinglish": "Hi {name}, aapka saved card expire ho gaya hai. ₹{amount} ka payment "
                    "complete karne ke liye card update karein: {link}",
    },
    "issuer_timeout": {
        "subject": "We couldn't confirm your ₹{amount} payment",
        "en": "Hi {name}, a temporary bank issue interrupted your ₹{amount} payment. "
              "Please retry: {link}",
        "hinglish": "Hi {name}, temporary bank issue ki wajah se ₹{amount} ka payment "
                    "complete nahi hua. Please retry karein: {link}",
    },
    "gateway_timeout": {
        "subject": "Resume your ₹{amount} checkout",
        "en": "Hi {name}, a technical timeout stopped your ₹{amount} checkout. Resume "
              "where you left off: {link}",
        "hinglish": "Hi {name}, technical timeout ki wajah se ₹{amount} ka checkout ruk "
                    "gaya. Yahan se resume karein: {link}",
    },
    "otp_timeout": {
        "subject": "Complete your ₹{amount} payment — OTP expired",
        "en": "Hi {name}, your OTP expired before the ₹{amount} payment went through. "
              "Tap to finish now: {link}",
        "hinglish": "Hi {name}, OTP expire hone se ₹{amount} ka payment complete nahi hua. "
                    "Abhi finish karein: {link}",
    },
    "user_dropped": {
        "subject": "Still thinking it over? ₹{amount} is waiting",
        "en": "Hi {name}, you left ₹{amount} in your cart. Here's a little something to "
              "help you decide: {link}",
        "hinglish": "Hi {name}, aapne ₹{amount} ka cart chhod diya tha. Decide karne mein "
                    "help ke liye ek chhota offer: {link}",
    },
    "mandate_lapsed": {
        "subject": "Re-authorize your subscription mandate",
        "en": "Hi {name}, your auto-pay mandate has expired, so the ₹{amount} charge "
              "failed. Re-authorize in 30 seconds: {link}",
        "hinglish": "Hi {name}, aapka auto-pay mandate expire ho gaya, isliye ₹{amount} "
                    "ka charge fail hua. 30 second mein re-authorize karein: {link}",
    },
    "invoice_unpaid": {
        "subject": "Invoice for ₹{amount} is {days} days overdue",
        "en": "Hi {name}, invoice for ₹{amount} is {days} days past due. Pay now to avoid "
              "escalation: {link}",
        "hinglish": "Hi {name}, ₹{amount} ka invoice {days} din se overdue hai. Escalation "
                    "se bachne ke liye abhi pay karein: {link}",
    },
}

DEFAULT = {
    "subject": "Action needed on your ₹{amount} payment",
    "en": "Hi {name}, your ₹{amount} payment needs attention: {link}",
    "hinglish": "Hi {name}, aapke ₹{amount} payment par action chahiye: {link}",
}


def render(failure_code: str, txn: dict, lang: str = "en") -> dict:
    """Return {subject, body, lang} for this transaction."""
    tpl = TEMPLATES.get(failure_code, DEFAULT)
    lang = "hinglish" if str(lang).lower() in ("hinglish", "hi", "hindi") else "en"
    fields = {
        "name": _display_name(txn),
        "amount": f"{float(txn.get('amount', 0) or 0):,.0f}",
        "link": RECOVERY_LINK.format(token=str(txn.get("txn_id", ""))[-8:]),
        "days": _fmt_days(txn.get("days_overdue")),
    }
    return {
        "subject": tpl["subject"].format(**fields),
        "body": tpl[lang].format(**fields),
        "lang": lang,
    }


def _display_name(txn: dict) -> str:
    uid = str(txn.get("user_id", ""))
    return "Customer" if not uid else uid.replace("user_", "Customer ")[:16]


def _fmt_days(v) -> str:
    try:
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return "a few"
