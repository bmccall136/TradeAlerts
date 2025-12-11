# C:\TradeAlerts\ai_advisor.py

from __future__ import annotations

import json
import os
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

# NEW: simple budget + throttle helper
from ai_budget import allow_ai_call, note_ai_call, budget_summary

# Load .env if present
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_client: OpenAI | None = None
_ai_enabled: bool = True  # flipped to False if we detect a hard failure


def _get_client() -> OpenAI | None:
    """
    Lazy-init OpenAI client.
    If no key is set, disable AI and return None.
    """
    global _client, _ai_enabled

    if not _ai_enabled:
        return None

    if _client is not None:
        return _client

    if not OPENAI_API_KEY:
        # No key, permanently disable AI until restart
        _ai_enabled = False
        return None

    _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _neutral_recommendation(reason: str) -> Dict[str, Any]:
    """
    Safe fallback when AI is unavailable or errors out.
    """
    return {
        "action": "SKIP",
        "confidence": 0,
        "sizing_hint": "AVOID_ADDING",
        "reason_tags": ["ai_unavailable", reason],
        "comment": "AI advisor unavailable; defaulting to SKIP.",
        "raw": {"error": reason},
    }


def _budget_block_recommendation() -> Dict[str, Any]:
    """
    Special neutral rec used when the budget/throttle blocks an AI call.
    Behaves like _neutral_recommendation, but with a distinct tag so we
    can see it in logs if needed.
    """
    try:
        summary = budget_summary()
    except Exception:
        summary = "AI budget/throttle limit reached."

    return {
        "action": "SKIP",
        "confidence": 0,
        "sizing_hint": "AVOID_ADDING",
        "reason_tags": ["ai_budget_block"],
        "comment": f"AI call blocked by budget/throttle. {summary}",
        "raw": {"error": "ai_budget_block"},
    }


def get_ai_recommendation(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given a snapshot describing a potential trade (symbol, price, indicators, news),
    ask the LLM for a conservative recommendation.

    This function is designed to NEVER raise on AI errors. It will always return a
    dict, falling back to a neutral SKIP recommendation if the AI is unavailable.
    """
    # Make sure snapshot is JSON-serializable
    try:
        snapshot_json = json.dumps(snapshot)
    except TypeError as exc:
        return _neutral_recommendation(f"snapshot_not_serializable: {exc}")

    # --- Budget / throttle gate (hard stop) ---
    # If this says "no", we *do not* call OpenAI at all.
    try:
        if not allow_ai_call("generic"):
            return _budget_block_recommendation()
    except Exception:
        # If the budget module itself fails, fail open rather than
        # breaking trading logic; we'll just proceed without throttling.
        pass

    client = _get_client()
    if client is None:
        return _neutral_recommendation("no_api_key_or_disabled")

    prompt = f"""
You are a cautious trading assistant helping a human swing/day trader.

You receive a JSON snapshot describing:
- A stock (symbol, name, price, vwap, vwap_diff)
- Technical indicators (RSI, MACD, trend, ATR, etc.)
- The trader's portfolio context (buying power, open positions, exposure)
- Recent news headlines for the symbol.

Your job:
- Evaluate whether opening or adding to a position RIGHT NOW looks attractive
  for a short-term trade (1-3 days), based on risk vs reward.
- You DO NOT place trades yourself, you only recommend.

Rules:
- Be conservative. If risk/reward is not clearly favorable, prefer SKIP.
- If news looks dangerous (lawsuits, regulatory issues, big guidance cuts,
  clear fundamental bad news), use RED_FLAG even if technicals look good.
- If the setup is strong (trend up, supports nearby, healthy volume, positive/
  neutral news), you may say BUY or, rarely, STRONG_BUY.
- Confidence should be 0-100. Use >80 only for very clear situations.
- Sizing hint:
    - "SMALL" if setup is okay but volatility/risk is high.
    - "NORMAL" if setup is strong and risk seems reasonable.
    - "AVOID_ADDING" if trader already seems very exposed or risk is high.
- Respond with ONLY valid JSON, no extra text.

Output JSON schema:
{{
  "action": "BUY | SELL | HOLD | SKIP | RED_FLAG",
  "confidence": 0-100,
  "sizing_hint": "SMALL | NORMAL | AVOID_ADDING",
  "reason_tags": ["short", "machine-readable", "tags"],
  "comment": "Short, human-friendly explanation (1-2 sentences)."
}}

Here is the snapshot to evaluate:
{snapshot_json}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": prompt.strip()}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:
        # Any API problem → safe neutral rec, don't crash your loop
        global _ai_enabled
        return _neutral_recommendation(f"openai_error: {exc}")

    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _neutral_recommendation("json_parse_error")

    # --- Record this call in the budget tracker ---
    try:
        # For now we just use the estimated per-call cost.
        # If you want to use token-precise pricing later, you can
        # compute it from resp.usage and pass a float to note_ai_call().
        note_ai_call()
    except Exception:
        # Never let budget logging break trading
        pass

    # Normalize and enforce keys
    action = str(data.get("action", "SKIP")).upper()
    if action not in {"BUY", "SELL", "HOLD", "SKIP", "RED_FLAG"}:
        action = "SKIP"

    try:
        confidence = int(float(data.get("confidence", 0)))
    except (TypeError, ValueError):
        confidence = 0

    sizing_hint = str(data.get("sizing_hint", "AVOID_ADDING")).upper()
    if sizing_hint not in {"SMALL", "NORMAL", "AVOID_ADDING"}:
        sizing_hint = "AVOID_ADDING"

    reason_tags = data.get("reason_tags") or []
    if not isinstance(reason_tags, list):
        reason_tags = [str(reason_tags)]

    comment = str(data.get("comment", "")).strip()

    return {
        "action": action,
        "confidence": confidence,
        "sizing_hint": sizing_hint,
        "reason_tags": reason_tags,
        "comment": comment,
        "raw": data,
    }


if __name__ == "__main__":
    # Tiny demo you can run: python ai_advisor.py
    test_snapshot = {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "price": 500.12,
        "vwap": 498.90,
        "vwap_diff": 1.22,
        "indicators": {
            "rsi": 58.3,
            "macd": 0.85,
            "trend": "up",
            "atr": 3.5,
        },
        "position": None,
        "portfolio": {
            "buying_power": 400.0,
            "open_positions": 2,
            "total_exposure_pct": 35.0,
        },
        "news_headlines": [
            "S&P 500 edges higher as tech stocks lead gains",
            "No major negative macro news in last 24h",
        ],
        "timeframe": "short-term swing (1-3 days)",
    }

    rec = get_ai_recommendation(test_snapshot)
    print("AI recommendation:")
    print(json.dumps(rec, indent=2))
