# F01c Telugu review packet

Owner: Rohan-Ktksu. Review branch: `localization/f01c-telugu-review`, based on F01c implementation commit `b72534b` (PR #18). This branch is for language evidence and copy corrections only. It does not certify fluent-human review.

## Review input

- Source of truth: the 29 `ful.*` English/Telugu pairs in `frontend/src/i18n.tsx`. PR #18's description provides a side-by-side table with each string's screen action.
- Screen context: `frontend/src/pages/Orders.tsx` (`Fulfilment`, the order delivery section) and `docs/f01/10-delivery-confirm-phone-telugu.png`. The direct strings are the primary input; screenshots check what the user actually sees and whether text fits.
- Meaning to protect: dispatched is not delivered; delivered is not buyer acceptance; cancellation is allowed before dispatch; cancellation restores stock once and changes *simulated* payment requests but does not move real money.
- Preserve keys, placeholders, the `₹` symbol, and explicit simulated-money wording. Do not copy private or real customer data into external tools.

## Review methods

Owner update, 1 November 2026: for quick prototype PRs, Gemini plus deterministic string checks and targeted screenshots is the routine AI-assisted path. AI4Bharat remains an optional independent comparison for disputed terminology; it is not required to finish this branch. The fluent-human F03 gate remains unchanged. The GitHub workflow `.github/workflows/telugu-review.yml` reviews changed pairs with `gemini-3.5-flash` using the free-tier project secret; its output is advisory and never edits copy.

1. **Gemini in Google AI Studio:** paste the 29 pairs and action descriptions from PR #18, plus the phone screenshot. Use the prompt below. Save the model name, date and findings in this packet. Google AI Pro offers expanded AI Studio access, but do not assume an API call is covered by the subscription or connect a paid project for this task.
2. **AI4Bharat comparison:** run a pinned revision of the English-to-Indic IndicTrans2 model in a local notebook or Colab, targeting Telugu. Record the exact model ID/revision and access terms accepted. Translate the English strings independently and compare meaning with the app copy. Do not replace strings automatically or fork the model just to run it. A translation model cannot judge screen context by itself.
3. Triage disagreements against the English action and the live UI. Mark each proposal accepted or rejected with a short reason. Apply accepted copy changes in this branch, then rerun frontend lint, build, unit tests and the F01c browser tests. Check 360 px and desktop screenshots for changed high-risk text.

Gemini prompt:

> Review these English/Telugu UI pairs as a Telugu app localization editor for a fictional B2B commerce prototype. Use each key's action description and the attached screen. Flag wrong meaning, unnatural Telugu, stale instructions, ambiguous dispatch/delivery/acceptance/cancellation or simulated-money language, and phone-width problems. Preserve all keys, placeholders and amounts. Return only findings: key, current Telugu, suggested Telugu, reason, severity, confidence. Do not rewrite clear strings. Do not claim human review.

## Review record

Automated check on 1 November 2026: GitHub run 41275600466 succeeded with `gemini-3.5-flash` on 11 changed pairs. Its seven-day `telugu-review` artifact lists three advisory findings: `ful.ask.cancel` (suggests “pending” for open requests and refund terminology), `ful.waitBuyer`, and `ful.waitSeller` (suggests status phrasing instead of imperative phrasing). All three were triaged and applied; see "Decisions on the automated run" below. Checked against the API: the payment requests cancelled with an order are those in `pending_approval` or `approved` (`backend/app/payments.py` `OPEN`), i.e. requested but not yet recorded, which పెండింగ్‌లో ఉన్న describes. The waiting messages now use the status voice of the English and of the existing `status.quote.sent` / `status.rfq.open` strings. The earlier owner's AI Studio model name remains unknown.

| Check | Status | Evidence |
| --- | --- | --- |
| Source pairs and screen context collected | Ready | PR #18 table; `frontend/src/i18n.tsx`; F01c phone screenshot |
| Gemini editorial review | Run 1 November 2026 by the owner in AI Studio | 14 findings; triage below (model name not recorded) |
| AI4Bharat independent comparison | Optional, not run | Use for disputed app-wide terminology when model access/runtime are available |
| Accepted copy changes and browser recheck | Done for Gemini findings | 11 Telugu strings changed (3 accepted, 6 partly accepted, 2 adapted), 3 deferred. Lint 0 errors; build passes; unit 13/13 + 4/4; browser 25/25 (F01c 5/5); screenshots `docs/f01/11-cancel-confirm-{phone,desktop}-telugu.png` |
| Fluent human Telugu review | Not run | Separate F03 gate before real-user reliance |

## Gemini findings and triage (1 November 2026)

Gemini review run by the owner in Google AI Studio on 1 November 2026 with the packet prompt, the 29 pairs and the 360 px screenshot; 14 findings returned (the model name was not recorded with the findings). Triage by the developer against the English meaning, the live screen and the terms the rest of the app already uses (`frontend/src/i18n.tsx` Telugu has నిల్వ for stock 21 times and స్టాక్ 0 times; అనుకరణ for simulated money 13 times; పంపబడింది for the dispatched status label; డిస్పాచ్ 0 times). The workflow requires domain terms to stay consistent, so single-string term swaps are deferred rather than applied piecemeal.

| Key | Gemini proposal (summary) | Decision | Applied Telugu / reason |
| --- | --- | --- | --- |
| `ful.cancelled` | డిస్పాచ్; స్టాక్ ... వద్దకు తిరిగి చేరింది | Partly accepted | నిల్వ అమ్మకందారు వద్దకు తిరిగి చేరింది (more natural phrasing kept with the app's term నిల్వ); డిస్పాచ్ and స్టాక్ deferred |
| `ful.event.dispatched` | అమ్మకందారు డిస్పాచ్ చేశారు | Deferred | Term change; the status label elsewhere says పంపబడింది. Decide app-wide after the AI4Bharat comparison and human review |
| `ful.action.dispatch` | డిస్పాచ్ చేసినట్లు గుర్తించండి | Deferred | Same term decision; పంపు (send) and అందజేయు (hand over) are already different verbs |
| `ful.ask.dispatch` | డిస్పాచ్ ...; adds ఇది | Partly accepted | Added ఇది ("it appears on the way to the buyer"); term deferred |
| `ful.confirm.dispatch` | డిస్పాచ్‌ని నిర్ధారించండి | Deferred | Gemini also calls the current wording unnatural; fix together with the term decision |
| `ful.ask.cancel` | ఆర్డర్‌ను; స్టాక్ ... తిరిగి చేరుతుంది; పెండింగ్ డెమో పేమెంట్ రిక్వెస్ట్‌లు; రీఫండ్ కోసం మార్క్ | Partly accepted | Accusative ఆర్డర్‌ను and నిల్వ ... వద్దకు తిరిగి చేరుతుంది applied; the simulated-payment wording is deferred because అనుకరణ is the app-wide term for simulated money and "డెమో పేమెంట్" would change it in one place only |
| `ful.confirm.cancel` | అవును, ఆర్డర్‌ను రద్దు చేయండి | Accepted | Accusative marker |
| `ful.reasonRequired` | దయచేసి కారణాన్ని పేర్కొనండి. | Accepted | Standard form-validation phrasing |
| `ful.done.dispatch` | డిస్పాచ్ చేసినట్లు గుర్తించబడింది. | Partly accepted | పంపినట్లు గుర్తించబడింది. (system voice consistent with the timeline); term deferred |
| `ful.done.deliver` | డెలివరీ చేసినట్లు గుర్తించబడింది. | Partly accepted | అందజేసినట్లు గుర్తించబడింది. (voice); keeps the verb used by the timeline entry |
| `ful.done.cancel` | స్టాక్ ... వద్దకు తిరిగి చేరింది | Partly accepted | నిల్వ అమ్మకందారు వద్దకు తిరిగి చేరింది. |
| `ful.waitSeller` | డిస్పాచ్ లేదా డెలివరీ చేసేంత వరకు వేచి ఉండండి | Adapted | అమ్మకందారు పంపేంత వరకు లేదా అందజేసేంత వరకు వేచి ఉండండి. (fixes the impersonal syntax Gemini flagged; keeps the app's verbs; wording composed by the developer, needs the comparison/human check) |
| `ful.waitBuyer` | కొనుగోలుదారు స్పందించేంత వరకు వేచి ఉండండి. | Accepted | Fixes the literal "waiting for the buyer" |
| `ful.paymentSeparate` | ఎటువంటి నగదు లావాదేవీలు నమోదు కావు; డెమో మాత్రమే | Adapted | డెలివరీ ప్రక్రియలో ఎటువంటి డబ్బు లావాదేవీలు నమోదు కావు. చెల్లింపులు పూర్తిగా వేరు, ఇవి అనుకరణ మాత్రమే. (నగదు means cash only, so డబ్బు; అనుకరణ kept as the app-wide term) |

Open terminology questions for the AI4Bharat comparison and the fluent-human review (apply app-wide, not per string): డిస్పాచ్ vs పంపు/పంపబడింది for dispatch; స్టాక్ vs నిల్వ for stock; డెమో vs అనుకరణ for simulated payments; పెండింగ్ vs తెరిచి ఉన్న for open requests.

### Decisions on the automated run (GitHub run 41275600466, `gemini-3.5-flash`)

| Key | Finding | Decision | Applied Telugu / reason |
| --- | --- | --- | --- |
| `ful.ask.cancel` | "తెరిచి ఉన్న" is a literal "open"; use పెండింగ్‌లో ఉన్న and రీఫండ్ కోసం | Accepted | పెండింగ్‌లో ఉన్న అనుకరణ చెల్లింపు అభ్యర్థనలు రద్దవుతాయి; నమోదైన అనుకరణ చెల్లింపు రీఫండ్ కోసం గుర్తించబడుతుంది. Both Gemini reviews (AI Studio and this run) flagged the same phrase; the change keeps అనుకరణ and నిల్వ, and neither replaced phrase is used elsewhere in the app |
| `ful.waitBuyer` | Status text was turned into an instruction | Accepted | కొనుగోలుదారు కోసం వేచి ఉంది. The English is a status, and the app already uses this exact status wording in `status.quote.sent`; this reverses the earlier imperative change, which the first review had suggested |
| `ful.waitSeller` | Status text was turned into an instruction | Accepted | అమ్మకందారు పంపడానికి లేదా అందజేయడానికి వేచి ఉంది. Status form like `status.rfq.open`, and avoids the impersonal construction the first review flagged |

Follow-up automated run (GitHub run 41276367938, `gemini-3.5-flash`, 10 changed pairs) found one high-severity meaning error in the applied `ful.waitSeller`: అమ్మకందారు పంపడానికి లేదా అందజేయడానికి వేచి ఉంది can read as "the seller is waiting to send", reversing who waits. **Accepted:** అమ్మకందారు పంపడం లేదా అందజేయడం కోసం వేచి ఉంది. — the same "… కోసం వేచి ఉంది" pattern as `ful.waitBuyer` and `status.rfq.open`. It is close to the original draft that the first review called stiff; correct meaning takes precedence, and the style question stays with the F03 fluent-human review.

After that fix, GitHub run 41276551863 (`gemini-3.5-flash`, 9 changed pairs at `33174b6`) returned no findings; backend, frontend and browser checks passed on the same commit.

The two Gemini reviews disagreed on the waiting messages (instruction vs status). The decision follows the English contract and the existing status strings; a fluent speaker should confirm in F03.

## Completion rule

This branch can report **AI-assisted Telugu review** after Gemini findings are triaged, corrections are applied, deterministic string checks and relevant UI checks pass. The optional AI4Bharat comparison remains useful for disputed terms. It must not report fluent-human approval. Keep that release gate in F03. The automated Gemini report is advisory; accepted copy decisions remain documented above.
