"""Telugu review sheet for a fluent reader: every UI string with its English, grouped by screen (F03).

    python tools/telugu_sheet.py   # writes docs/telugu-review/telugu_strings.csv (opens in Excel or Google Sheets)

Columns the reviewer fills: ok (yes/no), corrected_telugu, comment. AI notes are advisory suggestions that were not applied.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from telugu_review import SOURCE, pairs  # noqa: E402

OUT = Path("docs/telugu-review/telugu_strings.csv")

# Key prefix -> screen, first match wins (longest prefixes first where they overlap).
SCREENS = [
    ("status.order", "Orders and delivery"), ("status.fulfil", "Orders and delivery"), ("order.", "Orders and delivery"), ("ful.", "Orders and delivery"),
    ("status.payment", "Simulated payments"), ("pay.", "Simulated payments"), ("fin.", "Simulated payments"),
    ("status.case", "Support"), ("status.handoff", "Support"), ("case.cat", "Support and complaints"), ("urgency.", "Support and complaints"), ("sup.", "Support"),
    ("cmp.", "Complaints"), ("rep.", "Reports"), ("chat.", "Assistant chat"), ("voice.", "Voice input"), ("wa.", "WhatsApp simulator"),
    ("reg.", "Register a business"), ("sp.", "Seller products and stock"), ("products.", "Find products"), ("product.", "Find products"),
    ("rfq.", "Requests and quotes"), ("quote.", "Requests and quotes"), ("confirm.", "Requests and quotes"), ("terms.", "Requests and quotes"),
    ("status.rfq", "Requests and quotes"), ("status.quote", "Requests and quotes"), ("unit.", "Requests and quotes"),
    ("error.", "Messages and errors"), ("state.", "Messages and errors"), ("signin.", "Sign in"), ("help.", "Help"),
    ("nav.", "Navigation"), ("home.", "Home"), ("role.", "Navigation"),
]

# Advisory AI suggestions left for a fluent reader (F01e to F06), not applied.
NOTES = {
    "rep.delayedRule": "AI suggested a passive phrasing for 'not yet delivered'; two runs disagreed.",
    "rep.lead": "AI suggested ఒక వ్యవధిలో for 'over a period' (now ఒక కాలంలో).",
    "rep.show": "AI suggested నివేదికను చూపించు.",
    "status.case.open": "Follows the English label 'Waiting'; AI suggested తెరిచి ఉంది (open).",
    "status.case.assigned": "Follows the English label 'Taken'; AI suggested కేటాయించబడింది (assigned).",
    "status.handoff.queued": "Follows 'Waiting'; AI suggested క్యూలో ఉంది.",
    "nav.support": "App-wide term సహాయ వరుస; AI preferred సపోర్ట్ క్యూ. Decide once for all screens.",
    "sup.back": "Uses సహాయ వరుస; see nav.support.",
    "sup.notYoursText": "Uses సహాయ వరుస; see nav.support.",
    "case.cat.wrong_product": "AI suggested వేరే ఉత్పత్తి (a different product, not a faulty one).",
    "sup.take": "AI suggested స్వీకరించండి instead of తీసుకోండి for taking a task (three runs).",
    "sup.case.reopened": "AI suggested తిరిగి తెరిచిన సార్లు.",
    "sup.emptyMine": "AI found 'taken any yet' vague in Telugu.",
    "sup.case.noMoney": "AI preferred నిధులు over the app-wide ఏ డబ్బూ బదిలీ కాదు.",
    "pay.tooMuch": "AI suggested అభ్యర్థించవచ్చు for 'can be requested'.",
    "fin.approved": "Queue heading in the plural (ఆమోదించినవి); AI read it as a sentence.",
    "fin.err.open_request_exists": "AI suggested the English loanword ఓపెన్ రిక్వెస్ట్; not applied.",
    "reg.doneLead": "AI suggested సిమ్యులేటెడ్; the app says అనుకరణ for simulated everywhere.",
    "reg.fictional": "AI suggested డెమో కోసం మాత్రమే.",
    "cmp.talk": "AI suggested సపోర్ట్ ప్రతినిధి (representative); the app says సపోర్ట్ వ్యక్తి everywhere.",
    "cmp.talkLead": "AI suggested a phrasing for 'takes over' (బాధ్యత తీసుకునే).",
    "cmp.shareNew": "AI found పంచుకోబడవు formal; suggested షేర్ చేయబడవు.",
    "cmp.close": "AI suggested మూసివేయండి for closing a complaint (now ముగించండి, matching status.case.closed).",
    "chat.role.agent": "App-wide term సపోర్ట్ వ్యక్తి; see cmp.talk.",
    "chat.pa.validUntil": "An earlier AI run suggested adding గడువు.",
    "status.fulfil.dispatched": "The app says పంపబడింది / పంపడం for dispatch; on the front page AI suggested the loanword డిస్పాచ్. Decide once for all screens.",
}


def screen(key: str) -> str:
    return next((name for prefix, name in SCREENS if key.startswith(prefix)), "General")


def main():
    en, te = pairs(SOURCE.read_text(encoding="utf-8"))
    assert en.keys() == te.keys(), sorted(en.keys() ^ te.keys())
    assert not set(NOTES) - set(en), sorted(set(NOTES) - set(en))  # every note points at a real string
    rows = sorted(en, key=lambda k: (screen(k), k))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8 with BOM, so Excel shows Telugu correctly
        w = csv.writer(f)
        w.writerow(["screen", "key", "english", "telugu", "ai_note", "ok (yes/no)", "corrected_telugu", "comment"])
        for k in rows:
            w.writerow([screen(k), k, en[k], te[k], NOTES.get(k, ""), "", "", ""])
    print(f"Wrote {len(rows)} strings ({len(NOTES)} with AI notes) to {OUT}")


if __name__ == "__main__":
    main()
