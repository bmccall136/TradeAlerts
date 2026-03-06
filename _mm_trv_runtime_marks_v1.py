import pathlib, shutil, datetime

targets = [
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review_single.html"),
    pathlib.Path(r"C:\TradeAlerts\templates\trade_review.html"),
]

needle = """  function firstTimestampUnderHeader(headerText){
    const headers = qq("h1,h2,h3,h4,div,span,strong");
    const hdr = headers.find(el => ((el.textContent||"").trim() === headerText));
    if(!hdr) return "";
    let n = hdr.nextElementSibling;
    while(n){
      const txt = (n.textContent || "").trim();
      const m = txt.match(/\\b(20\\d{2}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2})\\b/);
      if(m) return m[1];
      if(/^(Buy Triggers|Sell Triggers|Signal Fires)$/i.test(txt)) break;
      n = n.nextElementSibling;
    }
    return "";
  }"""

insert = """  function firstTimestampUnderHeader(headerText){
    const headers = qq("h1,h2,h3,h4,div,span,strong");
    const hdr = headers.find(el => ((el.textContent||"").trim() === headerText));
    if(!hdr) return "";
    let n = hdr.nextElementSibling;
    while(n){
      const txt = (n.textContent || "").trim();
      const m = txt.match(/\\b(20\\d{2}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2})\\b/);
      if(m) return m[1];
      if(/^(Buy Triggers|Sell Triggers|Signal Fires)$/i.test(txt)) break;
      n = n.nextElementSibling;
    }
    return "";
  }

  function allTimestampsUnderHeader(headerText){
    const out = [];
    const headers = qq("h1,h2,h3,h4,div,span,strong");
    const hdr = headers.find(el => ((el.textContent||"").trim() === headerText));
    if(!hdr) return out;
    let n = hdr.nextElementSibling;
    while(n){
      const txt = (n.textContent || "").trim();
      const matches = txt.match(/\\b20\\d{2}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}\\b/g);
      if(matches){ matches.forEach(x => out.push(x)); }
      if(/^(Buy Triggers|Sell Triggers|Signal Fires)$/i.test(txt)) break;
      n = n.nextElementSibling;
    }
    return Array.from(new Set(out));
  }"""

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
patched = 0

for p in targets:
    if not p.exists():
        continue
    txt = p.read_text(encoding="utf-8", errors="replace")
    bak = p.with_name(p.name + f".bak_runtime_marks_v1_{ts}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")

    if needle in txt and "allTimestampsUnderHeader" not in txt:
        txt = txt.replace(needle, insert, 1)
        txt = txt.replace(
            '    const buyTs = firstTimestampUnderHeader("Buy Triggers");\n    const sellTs = firstTimestampUnderHeader("Sell Triggers");',
            '    const buyTs = firstTimestampUnderHeader("Buy Triggers");\n    const sellTs = firstTimestampUnderHeader("Sell Triggers");\n    const buyMarks = allTimestampsUnderHeader("Buy Triggers");\n    const sellMarks = allTimestampsUnderHeader("Sell Triggers");'
        )
        txt = txt.replace(
            '    if(sellTs) src += "&sell_ts=" + enc(sellTs);',
            '    if(sellTs) src += "&sell_ts=" + enc(sellTs);\n    if(buyMarks.length) src += "&buy_marks=" + buyMarks.map(enc).join("|");\n    if(sellMarks.length) src += "&sell_marks=" + sellMarks.map(enc).join("|");'
        )
        p.write_text(txt, encoding="utf-8", newline="\n")
        print(f"PATCHED -> {p}")
        patched += 1
    else:
        print(f"UNCHANGED -> {p}")

print(f"PATCH_COUNT={patched}")
