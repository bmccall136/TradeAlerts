# TradeAlerts Project Description

## Overview
TradeAlerts is a Flask-based web application for live and simulated stock trading signals. The system now includes **real-time dashboard alerts**, an advanced **backtesting engine with full parameter control and performance visualization**, and seamless workflow for deploying backtested strategies to production.

## Major Features

- **Dashboard**  
  - Real-time alerts (Prime/Sell) with filter, sparklines, triggers, and news links.
  - Table with confidence, price, timestamp, trigger badges, and buy/sell actions.
  - Persistent nav bar for one-click access to all app sections.

- **Scanner**  
  - Loops through S&P500, computes all indicators and triggers.
  - Posts new Prime alerts to the dashboard API if *all* required signals align (configurable).

- **Backtest Engine**  
  - Run historical simulations using your exact “Prime” logic and tweakable parameters.
  - Simulate auto-buy/sell with customizable profit/stop/hold/exits.
  - See summary stats (win %, avg win/loss, max drawdown), full trade log, and interactive equity/P&L charts.
  - Download results as CSV.
  - “Promote to Live” button applies backtest settings to your live scanner instantly.

- **Parameter Controls**  
  - All key strategy variables (targets, stops, hold time, required triggers) are adjustable from the UI—both for backtest and (optionally) live trading.
  - Config is stored in `config.json` and read by both modules.

## Core Components

- **dashboard.py**: Main Flask entrypoint
- **api.py**: API blueprint (alerts, promote settings, sparkline SVG)
- **backtest_service.py**: Historical engine (simulates signals, returns stats/results)
- **scanner.py**: Real-time signal generator
- **services/**: All indicator, DB, and news logic
- **templates/**: UI for alerts, simulation, and backtest results

## Usage

- Use backtest page to optimize parameters/logic (UI controls and charts)
- When ready, click "Promote to Live" to push config to production scanner
- All config changes are live instantly—no code edit required

## Docs
- Project conventions, ToDo roadmap, and architecture notes are in `/docs`
