Max, please.

# TradeAlerts Project Rules

## Database
- Always use `alerts.db`, never `alerts_clean.db`.

## Routes
- `/alerts` must accept POST for scanner ingestion.
- Do NOT delete or change route logic without explicit instruction.

## File Integrity
- `dashboard.py` must NEVER be fully rebuilt — only surgically modified.
- All major updates must go through a Git checkpoint first.

## UI Theme
- Use a black background theme with yellow highlights (preferred style).
- Do not change theme colors without approval.

## Sparkline
- Sparkline must render clearly on a black background using real scanner values.

## Price Source
- **Last price must always come from E*TRADE API.**
- Absolutely no fallback to Yahoo Finance.
- Never use E*TRADE sandbox environment.

## Simulation
- Simulation must remain decoupled from core alert ingestion logic.
- Starting cash: $10,000

## Deployment
- Do not switch environments without explicit approval.
