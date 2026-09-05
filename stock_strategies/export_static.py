"""產生靜態網頁用的 latest.json（給 Cloudflare Pages 免後端模式）

讀本地 watchlist_40.csv（或 Google Sheet），對每檔跑 evaluate，
寫到 web/public/data/latest.json，Dashboard 開啟即顯示，無需後端。

執行：uv run python -m stock_strategies.export_static
需 FINMIND_TOKEN（TWSE 大盤已免 token）
"""
import json
import time
from pathlib import Path
from datetime import datetime

from stock_strategies.sheet import read_watchlist
from stock_strategies.evaluate import evaluate
from stock_strategies.market import get_market_state, apply_market_filter
from stock_strategies.night_session import get_night_session, night_filter_note
from stock_strategies import loader


def main():
    watchlist = read_watchlist()
    print(f"[export] watchlist {len(watchlist)} 檔")
    # 過濾 P0W00 這種指數（evaluate 會 ERROR）
    watchlist = [r for r in watchlist if str(r.get("stock_id")) != "P0W00"]
    print(f"[export] 過濾後 {len(watchlist)} 檔")

    strategy = loader.get_strategy("default") or {"id": "default", "name": "default", "params": {}}
    market = get_market_state()
    print(f"[export] market: {market['note']}")

    try:
        night = get_night_session()
        night_note = night_filter_note(night)
    except Exception as e:
        night = None
        night_note = f"夜盤取得失敗: {e}"
    print(f"[export] night: {night_note}")

    results = []
    for i, row in enumerate(watchlist, 1):
        sid = str(row["stock_id"])
        name = row.get("name", "")
        print(f"[{i}/{len(watchlist)}] {sid} {name}")
        r = evaluate(sid, name, strategy=strategy)
        if r:
            results.append(r)
        time.sleep(0.4)

    # 套大盤濾鏡（與 main.py 一致）
    downgraded = apply_market_filter(results, market)
    if downgraded:
        print(f"[export] 大盤濾鏡降級 {downgraded} 檔")

    order = {"BUY": 0, "WATCH": 1, "SKIP": 2, "ERROR": 3}
    results.sort(key=lambda x: (order.get(x.get("action"), 4), -x.get("signal_score", 0)))

    summary = {
        "total": len(results),
        "buy": sum(1 for r in results if r.get("action") == "BUY"),
        "watch": sum(1 for r in results if r.get("action") == "WATCH"),
        "skip": sum(1 for r in results if r.get("action") == "SKIP"),
        "error": sum(1 for r in results if r.get("action") == "ERROR"),
    }

    payload = {
        "generated_at": datetime.now().isoformat(),
        "strategy": {"id": strategy.get("id"), "name": strategy.get("name")},
        "market": market,
        "night": night,
        "night_note": night_note,
        "downgraded": downgraded,
        "summary": summary,
        "results": results,
        "watchlist": watchlist,
    }

    out = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] 已寫 {out} ({summary})")


if __name__ == "__main__":
    main()
