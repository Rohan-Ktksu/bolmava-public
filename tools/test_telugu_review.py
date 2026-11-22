"""Offline checks for tools/telugu_review.py; run with `python tools/test_telugu_review.py`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from telugu_review import BATCH, FULL, LITE, MODELS, daily_quota, plan, review_text, sensitive, text_unchanged_since  # noqa: E402


def refused(result):
    try:
        review_text(result)
    except ValueError:
        return True
    return False


part = lambda text, thought=False: {"text": text, **({"thought": True} if thought else {})}  # noqa: E731
done = {"candidates": [{"finishReason": "STOP", "content": {"parts": [part("plan", True), part("| key |"), part(" row |")]}}]}
assert review_text(done) == "| key | row |"  # thinking dropped, answer parts joined without inserted breaks
assert refused({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [part("| key | half")]}}]})
assert refused({"candidates": []}) and refused({})
assert refused({"candidates": [{"finishReason": "STOP", "content": {"parts": [part("   ")]}}]})
quota = '{"error": {"code": 429, "details": [{"violations": [{"quotaId": "GenerateRequestsPer%sPerProjectPerModel-FreeTier"}]}]}}'
assert daily_quota(quota % "Day") and not daily_quota(quota % "Minute")  # only the daily limit moves on to the next model
lite = ["lite" in m for m in MODELS]
assert lite == sorted(lite) and not lite[0] and lite[-1]  # every full model is tried before any lite model
row = lambda key, english: {"key": key, "english": english, "telugu": "-"}  # noqa: E731
assert sensitive(row("rep.sales.received", "Received (recorded, simulated)")) and sensitive(row("x", "Total ₹{amount}"))
assert not sensitive(row("nav.help", "Help")) and not sensitive(row("x", "Display settings"))
rows = [row(f"o.{i}", "Order placed") for i in range(BATCH + 1)] + [row("nav.help", "Help")]
jobs = plan(rows)
assert [(t[:5], m, len(b)) for t, m, b in jobs] == [("Money", FULL, BATCH), ("Money", FULL, 1), ("Other", LITE + FULL, 1)]
assert not set(FULL) & set(LITE)  # sensitive batches never reach a lite model
assert text_unchanged_since("HEAD")  # same commit: nothing new to review
assert not text_unchanged_since("") and not text_unchanged_since("0" * 40) and not text_unchanged_since("f" * 40)  # new PR, unknown commit
print("telugu_review checks passed")
