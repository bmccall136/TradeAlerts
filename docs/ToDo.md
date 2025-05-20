# TradeAlerts To‑Do

## ✅ Done

- **Fix “possibly delisted” false‑positives by catching and handling errors properly**  
  Market‑service crashes used to cascade into “delisted” errors. Now we catch those upstream, so only real missing‑data cases get logged.

- **Decide on or remove _Sharpshooter_ filter entirely**  
  Sharpshooter has been removed—alerts are now only “Prime” or “Sell.”

- **Publish project docs in `/docs` (README, Project Description, Conventions)**  
  All three docs are in place and up‑to‑date.

## 🚧 In Progress

- **Only fetch NewsAPI when a Prime alert triggers**  
  News calls now gated behind `if alert_type == 'Prime'`, but double‑check that no stray calls slip through.

- **Turn News trigger into a clickable link**  
  Instead of a 🔍 icon, the “News” trigger should hyperlink out to the source article.

- **Automatically execute simulation buys/sells**  
  Next step: wire up your simulation engine so that “BUY”/“SELL” buttons become scheduled or auto‑triggered based on alert logic.

- **Style tweaks**  
  - “ALL” filter button should match the others when inactive (gray outline + text).  
  - Alerts table must span 100% width on all viewports.  
  - Title should reflect the current filter (“All”, “Prime”, or “Sell”).

- **Error‐handling & logging**  
  - Surface only meaningful errors—don’t let one symbol’s failure take the whole scan down.  
  - Add per‑symbol try/catch in `build_triggers()` so MACD/RSI/Bollinger failures don’t bubble up.

## 📦 Future

- **Add backtest performance reports**  
  Generate equity‐curve plots after each simulation run.

- **Dockerize the whole stack**  
  One‑click deploy with an `.env` and `docker-compose.yml`.

- **User auth & multi‑user support**  
  So you can share dashboards with your trading buddies.

