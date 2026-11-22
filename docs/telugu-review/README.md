# Telugu review sheet (F03)

For a fluent Telugu reader. Bolmava is a fictional trading demo for electrical switches; no real money moves. Every Telugu line you see in the app is in [`telugu_strings.csv`](telugu_strings.csv), next to its English, grouped by screen. Open it in Excel or Google Sheets (File → Import; the file is UTF-8).

## What to do

For each row:

1. Read the English (`english`) and the Telugu (`telugu`).
2. In **`ok (yes/no)`**, write `yes` if the Telugu is natural and means the same, `no` otherwise.
3. If `no`, write your version in **`corrected_telugu`**. Keep anything in braces exactly as it is, for example `{name}`, `{date}`, `{amount}`: the app fills those in.
4. Use **`comment`** for anything else, such as "too formal" or "this word is confusing".

Rows with an **`ai_note`** have an open suggestion from the automated (AI) review that was not applied. Please decide those first. Some are about one word used across many screens, so one decision settles all of them:

| Decide once | Now | Alternative suggested |
| --- | --- | --- |
| Support queue | సహాయ వరుస | సపోర్ట్ క్యూ |
| Support person | సపోర్ట్ వ్యక్తి | సపోర్ట్ ప్రతినిధి |
| Simulated (no real money) | అనుకరణ | సిమ్యులేటెడ్ (not recommended) |
| "Take" a waiting task | తీసుకోండి | స్వీకరించండి |

## Words the app should keep consistent

- **Simulated money:** అనుకరణ. Money is never real in this demo, and the wording must never suggest a real payment.
- **Quote:** కొటేషన్. **Order:** ఆర్డర్. **Complaint:** ఫిర్యాదు. **Delivery:** డెలివరీ.
- **Dispatch** (sent out by the seller) is different from **delivery** (arrived) and from **acceptance** (the buyer agrees it arrived as ordered).

## Not in this sheet

The **assistant's chat replies** are written in the backend (`backend/app/conversation.py`, the `TEXT["te"]` block), not in the screens. Two points there need a fluent decision too:

- The assistant's report says **నమూనా డబ్బు** for simulated money, while the screens say **అనుకరణ**.
- Spoken Telugu was tested on 22 November: Chrome writes six as ఆరు, ఆర్ or ఆరే, and amp as ఆంప్, ఆమ్ or ఆంపియర్. The assistant accepts all of these.

## After the review

Send the filled sheet back. The development side applies the changes, re-runs the checks and the automated Telugu review, and records who reviewed it and what changed. Only then does the app count as human-reviewed Telugu.

To refresh the sheet after text changes: `python tools/telugu_sheet.py`.
