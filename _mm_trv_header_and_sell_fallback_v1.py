import pathlib, shutil, datetime, re

P = pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html")
txt = P.read_text(encoding="utf-8", errors="replace")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_name(P.name + f".bak_header_and_sell_fallback_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

old = """        mountIntoBlocks(j.buy_triggers || [], j.sell_triggers || []);
        setMeta(j.meta || {});"""

new = """        const _meta = j.meta || {};
        const _tradeId = String((_meta.anchor_trade_id != null ? _meta.anchor_trade_id : "")).trim();
        const _symbol  = String((_meta.symbol || "")).trim().toUpperCase();

        let _sellRows = Array.isArray(j.sell_triggers) ? j.sell_triggers.slice() : [];
        if(!_sellRows.length){
          const _sells = Array.isArray(j.sells) ? j.sells : [];
          let _match = null;

          if(_tradeId){
            _match = _sells.find(function(r){
              return String((r && r.trade_id != null ? r.trade_id : "")).trim() === _tradeId;
            }) || null;
          }
          if(!_match && _symbol){
            _match = _sells.find(function(r){
              return String((r && r.symbol || "")).trim().toUpperCase() === _symbol;
            }) || null;
          }

          if(_match){
            _sellRows = [{
              time_et: _match.time_et || "",
              price: _match.price,
              signals_pretty: (_match.reason || _match.source || "SELL from DB")
            }];

            if(!_meta.anchor_sell_time_et && _match.time_et){
              _meta.anchor_sell_time_et = _match.time_et;
            }
            if((_meta.anchor_sell_price == null || Number(_meta.anchor_sell_price || 0) === 0) && _match.price != null){
              _meta.anchor_sell_price = _match.price;
            }
          }
        }

        mountIntoBlocks(j.buy_triggers || [], _sellRows);
        setMeta(_meta);"""

if old not in txt:
    raise SystemExit("Target hydrate block not found")

txt = txt.replace(old, new, 1)

# also make setMeta compute pnl when sell fallback exists
old2 = """      var buyPx  = meta.anchor_buy_price;
      var sellPx = meta.anchor_sell_price;
      var qty    = meta.anchor_qty;"""

new2 = """      var buyPx  = meta.anchor_buy_price;
      var sellPx = meta.anchor_sell_price;
      var qty    = meta.anchor_qty;

      try{
        if((sellPx == null || Number(sellPx||0) === 0) && meta.anchor_sell_price != null){
          sellPx = meta.anchor_sell_price;
        }
      }catch(e){}"""

if old2 in txt:
    txt = txt.replace(old2, new2, 1)

P.write_text(txt, encoding="utf-8", newline="\n")
print(f"PATCHED -> {P}")
print("MM_TRV_HEADER_AND_SELL_FALLBACK_V1")
