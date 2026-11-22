"""Advisory Gemini review of changed English/Telugu UI strings."""

import ast
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = Path("frontend/src/i18n.tsx")
PAIR = re.compile(r"^\s*('(?:\\.|[^'])*'):\s*('(?:\\.|[^'])*'),?\s*$")
# Free-tier text models (Gemini pricing page, 21 Nov 2026), strongest first; lite models only after every full model.
# When a model has used its daily free requests or is not open to this key, the next one is asked.
# Gemini 4 models are left out for now (owner's choice, 21 Nov 2026).
MODELS = (
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)


def pairs(text):
    en, te = text.split("const te:", 1)

    def read(block):
        result = {}
        for line in block.splitlines():
            match = PAIR.match(line)
            if match:
                result[ast.literal_eval(match[1])] = ast.literal_eval(match[2])
        return result

    return read(en), read(te)


def changed_keys(base):
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", f"{base}...HEAD", "--", str(SOURCE)], text=True, encoding="utf-8"
    )
    return {ast.literal_eval(m[1]) for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++") if (m := PAIR.match(line[1:]))}


FULL = tuple(m for m in MODELS if "lite" not in m)
LITE = tuple(m for m in MODELS if "lite" in m)
# Money, stock and order wording must be right, so it goes to full models only; other labels start on lite models.
SENSITIVE = re.compile(
    r"₹|\b(money|rupee|pay|paid|receiv|refund|stock|order|deliver|dispatch|cancel|confirm|accept|quot|price|amount|total|balance|approv|revers|sale|purchas|delay|complain)",
    re.IGNORECASE,
)
BATCH = 30  # shortcut: fixed size; bigger batches spend fewer daily requests, smaller ones finish more reliably


def sensitive(row):
    return bool(SENSITIVE.search(f"{row['key']} {row['english']}"))


def plan(rows):
    """(title, models, batch) jobs, sensitive pairs first: full models only for them, lite models first for the rest."""
    jobs = []
    for title, group, models in (
        ("Money, stock and order wording", [r for r in rows if sensitive(r)], FULL),
        ("Other wording", [r for r in rows if not sensitive(r)], LITE + FULL),
    ):
        jobs += [(title, models, group[i : i + BATCH]) for i in range(0, len(group), BATCH)]
    return jobs


def text_unchanged_since(previous):
    """True when the last push did not touch the UI strings, so the run for that push already sent them."""
    if not previous or set(previous) == {"0"}:  # a newly opened PR has no previous push
        return False
    # Exit 0 = no change; 1 = changed; 128 = previous commit unknown (force push), so review.
    return subprocess.run(["git", "diff", "--quiet", previous, "HEAD", "--", str(SOURCE)], capture_output=True).returncode == 0


def previous_run_passed(previous):
    """True when this workflow's run for the previous push finished green. A green run either reviewed the strings or
    skipped after an earlier green run, so a skip never hides a failed or unfinished review."""
    try:
        out = subprocess.run(
            ["gh", "run", "list", "--workflow", "telugu-review.yml", "--commit", previous, "--json", "conclusion", "--jq", ".[].conclusion"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and "success" in out.stdout.split()


def review_text(result):
    """The first candidate's answer. Thinking parts are dropped; a cut-off answer is refused, not saved as a review."""
    candidates = result.get("candidates") or []
    if not candidates:
        raise ValueError("no review text")
    first = candidates[0]
    # Thinking tokens count toward maxOutputTokens; a MAX_TOKENS stop leaves a partial table that reads as complete.
    if first.get("finishReason") != "STOP":
        raise ValueError(f"incomplete answer (finishReason {first.get('finishReason')})")
    # Parts are pieces of one answer: joining them with newlines broke words and table rows.
    answer = "".join(part.get("text", "") for part in first.get("content", {}).get("parts", []) if not part.get("thought"))
    if not answer.strip():
        raise ValueError("no review text")
    return answer


def daily_quota(error_body):
    """A 429 for a per-day quota: retries cannot succeed before the reset and only spend more requests."""
    return "PerDay" in error_body


def ask(model, body, key):
    """The review text, or None when this model is spent for the day, not open to this key, not answering or cut off."""
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    for attempt in range(3):
        try:
            # Thinking models can take minutes on a long table.
            with urllib.request.urlopen(request, timeout=300) as response:
                return review_text(json.load(response))
        except ValueError as e:
            print(f"{model}: {e}.")
            return None  # a half answer: the next model reviews this batch again
        except (urllib.error.URLError, TimeoutError) as e:  # HTTPError is a URLError
            if not isinstance(e, urllib.error.HTTPError):
                print(f"{model}: no answer ({e!r}).")
                return None  # no answer in time or a dropped connection: a retry rarely helps, the next model might
            detail = " ".join(e.read().decode("utf-8", "replace").split())[:300]
            if e.code in (403, 404) or e.code == 429 and daily_quota(detail):
                print(f"{model}: HTTP {e.code} {detail}")
                return None  # 403/404: retired, renamed or limited-access model
            # Overload and per-minute limits pass; a bad key or request fails at once.
            if e.code not in (429, 500, 503):
                raise
            if attempt == 2:
                print(f"{model}: still HTTP {e.code} after three tries.")
                return None
            time.sleep(10 * 2**attempt)


def main():
    en, te = pairs(SOURCE.read_text(encoding="utf-8"))
    keys = changed_keys(os.environ.get("BASE_REF", "origin/main"))
    missing = sorted(k for k in keys if k not in en or k not in te or not te[k].strip())
    if missing:
        raise SystemExit(f"Missing English/Telugu pairs: {', '.join(missing)}")
    placeholders = re.compile(r"\{[A-Za-z_][A-Za-z_0-9]*\}")
    mismatch = sorted(k for k in keys if sorted(placeholders.findall(en[k])) != sorted(placeholders.findall(te[k])))
    if mismatch:
        raise SystemExit(f"Placeholder mismatch: {', '.join(mismatch)}")
    rows = [{"key": k, "english": en[k], "telugu": te[k]} for k in sorted(keys)]
    Path("telugu-review-input.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if not rows:
        print("No changed paired UI strings.")
        return
    if os.environ.get("DRY_RUN") == "1":
        print(f"Prepared {len(rows)} pairs; no API call.")
        for title, models, batch in plan(rows):
            print(f"  {title}: {len(batch)} pairs -> {', '.join(models)}")
        return
    previous = os.environ.get("PREVIOUS_SHA")
    if os.environ.get("RUN_ATTEMPT", "1") == "1" and text_unchanged_since(previous) and previous_run_passed(previous):
        print("UI strings unchanged since the last push, whose review passed; no Gemini requests used. Re-run this job to force a review.")
        return
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY secret is unavailable; no API call made.")
    def body(batch):
        prompt = (
            "Review these English/Telugu UI pairs for a fictional B2B commerce app. "
            "Flag only wrong meaning, unnatural or inconsistent Telugu, stale instructions, and ambiguity in stock, "
            "order, delivery or simulated-money actions. Preserve placeholders exactly. Return a concise Markdown "
            "table: key | issue | proposed Telugu | reason | severity. Do not rewrite clear strings or claim human approval. "
            "Dispatch is distinct from delivery and buyer acceptance. Cancellation restores stock but never moves real money.\n\n"
            + json.dumps(batch, ensure_ascii=False)
        )
        return json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 32768}}).encode()

    skipped = set()  # a model that failed once is not asked again in this run
    sections, unreviewed = [], []
    for title, models, batch in plan(rows):
        for model in models:
            if model in skipped:
                continue
            answer = ask(model, body(batch), key)
            if answer is not None:
                weaker = " Lite model: a weaker check of Telugu nuance." if model in LITE else ""
                sections.append(f"## {title}: {len(batch)} pairs, `{model}`.{weaker}\n\n{answer}")
                break
            skipped.add(model)
            print("Trying the next model.")
        else:
            unreviewed += [row["key"] for row in batch]
    if unreviewed:
        sections.append(f"## Not reviewed\n\nNo allowed free model answered for: {', '.join(unreviewed)}. Re-run after the daily reset (midnight Pacific time).")
    report = f"# AI-assisted Telugu review\n\nChanged pairs: {len(rows)}. Advisory only; no human approval.\n\n" + "\n\n".join(sections) + "\n"
    Path("telugu-review.md").write_text(report, encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as output:
            output.write(report)
    if unreviewed:
        raise SystemExit(f"{len(unreviewed)} of {len(rows)} pairs were not reviewed; the report keeps the reviewed ones.")
    print(f"Saved advisory review for {len(rows)} pairs.")


if __name__ == "__main__":
    main()
