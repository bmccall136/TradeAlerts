
# Small Account Playbook (Day vs Swing)

**Goal:** Grow a sub-$25k account while avoiding PDT traps and keeping risk tight.

---

## 1) Allocation & Modes
- **Primary:** Swing trades (hold 2–5 trading days). Target +5–10%, stop −3%.
- **Secondary:** Intraday scalps only for A+ setups. Save **1–2 day trades per week**.

## 2) PDT Basics (U.S., Margin Accounts)
- If equity < **$25k**, you get **max 3 day trades in any rolling 5 business days**.
- A *day trade* = open and close the **same** security on the **same** day.
- Brokers will restrict NEW day trades if you exceed the limit, but you can **always sell to reduce risk** (closing trades is allowed; forced liquidations can also occur).
- To bypass PDT: use a **cash account** (only with settled cash), or maintain equity >$25k.

## 3) Position Sizing
- Default: **5–15%** of account per swing; avoid >25% per single name.
- Favor **liquid, large-cap** tickers to keep spreads low and exits clean.

## 4) Scanner Guidance (Swing Mode)
Turn on a swing profile so signals favor multi-day continuation instead of only intraday pops:

**Signal Filters**
- Price > SMA20 and SMA20 rising
- RSI rising 45→60 zone (not overbought blowoffs)
- MACD histogram turning up (bullish momentum)
- Volume ≥ 2× 10-day average on breakout day

**Exit**
- Target: +5–10%
- Stop: −3%
- Timeout: **3 trading days** (sell on day 4 open if no target hit)

## 5) Scalp Guard (Intraday Protection)
- Target: **+0.20%** (20 bps)
- Stop: **−1.00%** (100 bps)
- Timeout: **60 minutes**

> Keep this ON during the day even for swing entries to trim obvious failures early.

## 6) PDT Guard (Pre-Buy Check)
Before placing **any** BUY in a margin account:
1. Count completed day trades in the last **5 business days**.
2. If count ≥ 3 → **block buy** unless account equity ≥ $25k.
3. Else allow buy, but tag the position with `opened_today=true` so same-day exit is counted if it happens.

**Minimal Pseudocode**
```python
def can_day_trade(today_count, equity):
    if equity >= 25000:
        return True
    return today_count < 3

# pre-buy gate:
if acct.type == "MARGIN":
    if not can_day_trade(day_trades_last_5d, acct.equity):
        return {"ok": False, "reason": "PDT limit reached"}
```

## 7) Daily Routine
- **Pre-market:** Confirm mode (LIVE), swing or scalp thresholds, and PDT count.
- **During market:** Only use day trades on top-tier setups. Otherwise, let swings work.
- **End of day:** Close weak positions; journal entries, exits, and reasons.

---

## Config Snippets

### `live_settings.json` (swing profile section)
```json
{
  "swing_mode": true,
  "swing": {
    "timeout_days": 3,
    "take_profit_pct": 7.0,
    "stop_loss_pct": 3.0,
    "require_sma20": true,
    "min_signals": 5,
    "required_filters": ["adx","macd","vwap","vol"],
    "vwap_threshold": 2.0,
    "vol_multiplier": 2.5
  }
}
```

### `scalp_config.json` (intraday guard)
```json
{
  "mode": "live",
  "target_bps": 20,
  "stop_bps": 100,
  "max_hold_mins": 60,
  "throttle_ms": 30000,
  "limit_from": "last",
  "limit_offset_bps": 0,
  "blocklist": ["GEVO"]
}
```

### PDT Guard hook (pre-buy)
Place in your **buy** path (e.g., before `buy_live(...)`). Cache the count for the session.
```python
def day_trades_last_5b(trades, today_et):
    # returns completed day trades count over last 5 business days
    # (match open+close same day; exclude partials still open)
    ...

if account.type == "MARGIN":
    count = day_trades_last_5b(load_trades(), today_et())
    if account.equity < 25000 and count >= 3:
        log.warning("PDT block: %d day trades in last 5d", count)
        return  # block buy
```

---

**Bottom line for small accounts:**
- Favor **swings (2–5 days)** to avoid PDT choke.
- Use **scalp guard** intraday for safety.
- Reserve **day trades** for only your best setups.
