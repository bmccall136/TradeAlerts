import re,shutil,datetime,pathlib,sys,os,json
p=pathlib.Path(r"C:\TradeAlerts\sell_guard.py")
assert p.exists(), f"missing {p}"
ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak=p.with_suffix(f".py.bak_regime_exit_overlay_from_settings_v1_{ts}")
shutil.copy2(p,bak); print("Backup ->",bak)
txt=p.read_text(encoding="utf-8",errors="strict")
MARK="MM_REGIME_EXIT_OVERLAY_FROM_SETTINGS_V1"
if MARK in txt: print("Already patched:",MARK); sys.exit(0)
helper=("""\n# {MARK}\ndef _mm_load_regime_exit_overlay(mode, legacy_map):\n    \"\"\"Load regime_exit_overlay from settings JSON (DAY/SWING aware) with legacy fallback.\n    Scope: ONLY target_mult/stop_mult/time_mult for TREND/CHOP/DEAD.\n    \"\"\"\n    try:\n        root=os.path.dirname(__file__)\n        mu=(mode or \"\").upper()\n        primary=os.path.join(root,\"live_settings_swing.json\") if (\"SWING\" in mu) else os.path.join(root,\"live_settings_day.json\")\n        fallback=os.path.join(root,\"live_settings.json\")\n        for fp in (primary,fallback):\n            try:\n                raw=open(fp,\"r\",encoding=\"utf-8\").read()\n            except Exception:\n                continue\n            try:\n                cfg=json.loads(raw)\n            except Exception:\n                continue\n            ov=cfg.get(\"regime_exit_overlay\")\n            if not isinstance(ov,dict):\n                continue\n            out={}\n            for k in (\"TREND\",\"CHOP\",\"DEAD\"):\n                v=ov.get(k)\n                if not isinstance(v,dict):\n                    continue\n                lk=(legacy_map.get(k,{}) if isinstance(legacy_map,dict) else {})\n                def _f(key, default):\n                    try:\n                        return float(v.get(key, lk.get(key, default)))\n                    except Exception:\n                        try:\n                            return float(lk.get(key, default))\n                        except Exception:\n                            return float(default)\n                out[k]={\n                    \"target_mult\": _f(\"target_mult\", 1.0),\n                    \"stop_mult\":   _f(\"stop_mult\",   1.0),\n                    \"time_mult\":   _f(\"time_mult\",   1.0),\n                }\n            # ensure all regimes exist; preserve legacy defaults exactly if missing\n            if isinstance(legacy_map,dict):\n                legacy_map=dict(legacy_map)\n                legacy_map.setdefault(\"UNKNOWN\", {\"target_mult\":1.0,\"stop_mult\":1.0,\"time_mult\":1.0})\n            for k in (\"TREND\",\"CHOP\",\"DEAD\",\"UNKNOWN\"):\n                if k not in out:\n                    out[k]=(legacy_map.get(k) if isinstance(legacy_map,dict) else None) or {\"target_mult\":1.0,\"stop_mult\":1.0,\"time_mult\":1.0}\n            return out\n        return legacy_map\n    except Exception:\n        return legacy_map\n""").replace("{MARK}",MARK)
lines=txt.splitlines(True); i=0
import_re=re.compile(r"^\\s*(from\\s+\\S+\\s+import\\s+\\S+|import\\s+\\S+)\\s*$")
while i<len(lines) and import_re.match(lines[i]): i+=1
ins=sum(len(x) for x in lines[:i])
txt=txt[:ins]+helper+txt[ins:]
m=re.search(r"(?ms)^def\\s+_mm_regime_overlay\\s*\\([^)]*\\)\\s*:\\s*$",txt)
if not m: print("ERROR: could not find def _mm_regime_overlay(...)"); sys.exit(2)
fnstart=m.start()
after_def=txt.find("\\n",m.end())
search_from=after_def+1
mnext=re.search(r"(?m)^(def|class)\\s+\\w+",txt[search_from:])
fnend=(search_from+mnext.start()) if mnext else len(txt)
fn=txt[fnstart:fnend]
sig=fn.splitlines(True)[0]
if "mode" not in sig:
    sig2=re.sub(r"^def\\s+_mm_regime_overlay\\s*\\((?P<inner>[^)]*)\\)\\s*:", lambda mm: "def _mm_regime_overlay(" + mm.group("inner").rstrip() + (", " if mm.group("inner").strip() else "") + "mode=\\"\\"):", sig)
    fn=sig2+"".join(fn.splitlines(True)[1:])
legacy={"CHOP":{"target_mult":0.60,"stop_mult":0.80,"time_mult":0.80},"TREND":{"target_mult":1.60,"stop_mult":1.25,"time_mult":1.30},"DEAD":{"target_mult":0.50,"stop_mult":0.70,"time_mult":0.60},"UNKNOWN":{"target_mult":1.00,"stop_mult":1.00,"time_mult":1.00}}
body=("    lab=(label or \\"UNKNOWN\\").upper()\\n" +
      "    legacy_map="+json.dumps(legacy,separators=(",",":"))+"\\n" +
      "    ov_map=_mm_load_regime_exit_overlay(mode, legacy_map)\\n" +
      "    try:\\n" +
      "        return ov_map.get(lab) or ov_map.get(\\"UNKNOWN\\") or {\\"target_mult\\":1.0,\\"stop_mult\\":1.0,\\"time_mult\\":1.0}\\n" +
      "    except Exception:\\n" +
      "        return {\\"target_mult\\":1.0,\\"stop_mult\\":1.0,\\"time_mult\\":1.0}\\n")
fn_lines=fn.splitlines(True)
fn_new=fn_lines[0].rstrip("\\r\\n")+"\\n"+body
txt=txt[:fnstart]+fn_new+txt[fnend:]
txt=re.sub(r"(?m)^(?P<ind>\\s*)ov\\s*=\\s*_mm_regime_overlay\\(\\s*lab\\s*\\)\\s*$", r"\\g<ind>ov = _mm_regime_overlay(lab, mode=mode)", txt)
p.write_text(txt,encoding="utf-8")
print("PATCHED ->",p,"[",MARK,"]")