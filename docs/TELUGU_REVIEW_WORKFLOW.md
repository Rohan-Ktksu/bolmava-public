# Telugu UI review workflow

Owner: Rohan-Ktksu. Added 1 November 2026. Use this for changed Telugu copy in frontend branches. It is an **AI-assisted review**, not a claim that a fluent human has approved the language.

## Purpose and boundaries

The English and Telugu strings in `frontend/src/i18n.tsx` are the primary review input. Keep keys and placeholders such as `{n}` together. Include the UI action and a short description of the screen; a translation can be grammatically sound yet describe a control that no longer exists. Review stock, order confirmation, simulated money, permissions and errors with extra care. Never allow a translation tool to change application behavior or business rules.

Google AI Pro provides expanded access to Gemini and AI Studio. Do not assume that it pays for Gemini API calls. Before any API automation, check the selected model's current free/paid tier and project billing. Keep the local demo and CI independent of paid translation services. Do not submit real customer data or secrets; review only fictional strings and screenshots.

## Fast review for each changed screen

1. Extract the changed English/Telugu key pairs from `frontend/src/i18n.tsx`. Preserve placeholders, currency symbols and status distinctions. List the action each string describes.
2. Run the repository's advisory Gemini review on changed pairs. Ask for **findings only** with key, current Telugu, suggested Telugu, reason, severity and confidence. Do not accept a rewrite merely because it sounds different. AI Studio is a manual fallback when the automated job is unavailable.
3. For disputed terminology, optionally translate the English text with AI4Bharat IndicTrans2 English-to-Indic (Telugu) or its documented successor. Record the model name/revision if used. This is a comparison signal, not an automatic replacement. Its model files may require accepting Hugging Face access conditions. No fork is needed merely to run a model.
4. Compare Gemini's findings and the app copy, using the optional independent translation when available. Investigate disagreements against the UI action and the English contract. Retain domain terms consistently, especially quote, order, stock, reversal and simulated payment. Apply only reviewed corrections.
5. Use screenshots for changed or high-risk screens at 360 px and desktop. They check context, legibility, wrapping and whether the text describes the visible control. The direct strings remain the main, repeatable input; screenshots are targeted context checks, not a substitute for source strings.
6. Run frontend lint, build, unit tests and the relevant browser checks. Verify placeholders, the exact visible Telugu label and no horizontal overflow. Record model names, findings accepted/rejected, screenshots and actual test results in the pull request.

## Human release gate

Label routine results **AI-assisted Telugu review**. Neither Gemini nor IndicTrans2, nor two models agreeing, constitutes fluent-human approval. Before real users rely on Telugu, a fluent Telugu speaker should review complete buyer, seller, support and finance flows on a device, including confirmation and error language. Record their corrections and approval evidence in the F03 language/accessibility branch. Until then, keep the Telugu copy marked draft and do not claim natural-language validation is complete.

## Review prompt for Gemini

> Review these English/Telugu UI string pairs as a Telugu app localization editor for a fictional B2B commerce prototype. Use the supplied action descriptions and screenshots. Flag wrong meaning, unnatural wording, stale instructions, ambiguity in stock/order/simulated-money actions, inconsistent terms and phone-width problems. Preserve every key, placeholder and amount. Return only findings in a table: key, current Telugu, proposed Telugu, reason, severity, confidence. Do not rewrite clear strings. Do not claim human review.

## Sources and setup references

- [Google AI Pro benefits](https://one.google.com/about/google-ai-plans/) and [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) for current access and billing.
- [AI4Bharat IndicTrans2](https://github.com/AI4Bharat/IndicTrans2) and the [English-to-Indic model card](https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M) for licensing, access requirements and usage instructions. Verify the chosen model's current documentation before installing it.
