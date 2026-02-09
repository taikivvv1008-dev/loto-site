from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # Loto_site
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# 既存のロジックエンジン
from engines.logic_engine import generate, get_cached_prediction
from engines.fortune_engine import generate as fortune_generate, get_cached_prediction as fortune_get_cached


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _weekday_from_date(draw_date: str) -> str:
    # draw_date: "YYYY-MM-DD"
    dt = datetime.strptime(draw_date, "%Y-%m-%d")
    return dt.strftime("%a")  # Sun, Mon, ...


def _engine_version(engine_out: Dict[str, Any]) -> str:
    # engine_out["meta"]["version"] = "v1" など
    v = (engine_out.get("meta") or {}).get("version", "v1")
    return f"engine-{v}"


def _prediction_id(loto_type: str, round_int: int, model: str) -> str:
    return f"{loto_type}_{round_int}_{model}"


def format_from_logic_engine(
    loto_type: str,
    round_str: str,
    draw_date: str,
    user_id: str,
    count: int,
    public: bool = True,
) -> Dict[str, Any]:
    """
    仕様書(決定版)JSONに整形して返す。
    - 予想の中身は logic_engine.generate() が担当（キャッシュ有）
    - ここではキー名/階層/不足メタを埋める
    """
    # まずはキャッシュがあればそれを利用（＝再生成扱いにならない）
    # countをキーに含めない仕様なので、count無しのキャッシュ取得を優先
    try:
        cached = get_cached_prediction(loto_type, round_str, user_id, model="logic")
    except TypeError:
        # 旧シグネチャ互換（万一count必須なら最後の手段で渡す）
        cached = get_cached_prediction(loto_type, round_str, user_id, count, model="logic")
    regenerated = False

    if cached is None:
        engine_out = generate(loto_type, round_str, draw_date, user_id, count, model="logic")
        regenerated = True
    else:
        engine_out = cached
        engine_out["draw"] = {"round": round_str, "date": draw_date}
        regenerated = False

    # engine_out の想定構造：meta, draw, fixed2, tickets, count ... :contentReference[oaicite:1]{index=1}
    fixed_numbers = engine_out.get("fixed2", [])
    all_tickets = engine_out.get("tickets", [])
    tickets = all_tickets[:count]
    numbers = tickets[0] if tickets else []

    round_int = int(round_str)
    weekday = _weekday_from_date(draw_date)

    model = "logic"  # 今回のformatterは logic 用。fortune は別実装予定でOK

    spec = {
        "meta": {
            "loto_type": loto_type,
            "model": model,
            "prediction_id": _prediction_id(loto_type, round_int, model),
            "engine_version": _engine_version(engine_out),
        },
        "draw": {
            "round": round_int,
            "draw_date": draw_date,
            "weekday": weekday,
        },
        "prediction": {
            "numbers": numbers,
            "fixed_numbers": fixed_numbers,
            "tickets": tickets,
            "count": int(count),  # 表示上のcountはユーザー要求で固定
            "number_source": {
                "fixed": "global_fixed_v1",
                "random": "weighted_hot_v1",
            },
        },
        "description": { "headline": "", "main": "", "one_word": "" },
        "system": {
            "generated_at": _utc_now_iso(),
            "regenerated": bool(regenerated),
            "data_source": "engine",
            "public": bool(public),
        },
    }
    return spec

def format_from_fortune_engine(
    loto_type: str,
    round_str: str,
    draw_date: str,
    user_id: str,
    birthdate: str,
    count: int,
    public: bool = True,
) -> Dict[str, Any]:
    """
    仕様書(決定版)JSONに整形して返す（fortune / 方針B-1）。
    - 数字は決定論的ランダム
    - description は数字に触れない（運気 + 選び方ヒント）
    - countは包含ルール（slice）
    """
    cached = fortune_get_cached(loto_type, round_str, user_id, birthdate, model="fortune")
    regenerated = False

    if cached is None:
        engine_out = fortune_generate(
            loto_type=loto_type,
            round_str=round_str,
            draw_date=draw_date,
            weekday=_weekday_from_date(draw_date),
            user_id=user_id,
            birthdate=birthdate,
            count=count,
            model="fortune",
        )
        regenerated = True
    else:
        engine_out = cached
        engine_out["draw"] = {"round": round_str, "date": draw_date, "weekday": _weekday_from_date(draw_date)}
        regenerated = False

    all_tickets = engine_out.get("tickets", [])
    tickets = all_tickets[:count]
    numbers = tickets[0] if tickets else []
    description = engine_out.get("description", {"headline": "", "main": "", "one_word": ""})

    round_int = int(round_str)
    weekday = _weekday_from_date(draw_date)

    model = "fortune"

    spec = {
        "meta": {
            "loto_type": loto_type,
            "model": model,
            "prediction_id": _prediction_id(loto_type, round_int, model),
            "engine_version": _engine_version(engine_out),
        },
        "draw": {
            "round": round_int,
            "draw_date": draw_date,
            "weekday": weekday,
        },
        "prediction": {
            "numbers": numbers,
            "fixed_numbers": [],  # fortuneは固定数字なし
            "tickets": tickets,
            "count": int(count),
            "number_source": {
                "fixed": "none",
                "random": "uniform_v1",
            },
        },
        "description": description,
        "system": {
            "generated_at": _utc_now_iso(),
            "regenerated": bool(regenerated),
            "data_source": "engine",
            "public": bool(public),
        },
    }
    return spec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loto_type", required=True, choices=["loto6", "loto7"])
    ap.add_argument("--round", required=True, dest="round_str")
    ap.add_argument("--draw_date", required=True)
    ap.add_argument("--user_id", required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--out", default="", help="出力先ファイル（未指定なら標準出力）")
    ap.add_argument("--model", default="logic", choices=["logic", "fortune"])
    ap.add_argument("--birthdate", default="", help="fortune用: YYYY-MM-DD（未指定なら空）")
    args = ap.parse_args()

    if args.model == "logic":
        out = format_from_logic_engine(
            loto_type=args.loto_type,
            round_str=args.round_str,
            draw_date=args.draw_date,
            user_id=args.user_id,
            count=args.count,
            public=True,
        )
    else:
        out = format_from_fortune_engine(
            loto_type=args.loto_type,
            round_str=args.round_str,
            draw_date=args.draw_date,
            user_id=args.user_id,
            birthdate=args.birthdate,
            count=args.count,
            public=True,
        )


    s = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(s)
    else:
        print(s)


if __name__ == "__main__":
    main()
