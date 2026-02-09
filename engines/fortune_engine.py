from __future__ import annotations

"""fortune_engine.py

Fortune model (方針B-1):

- numbers/tickets are deterministic-random (seeded) per (loto_type, round, user_id, birthdate).
- description is also deterministic and **does not reference numbers** (運気 + 選び方ヒントのみ).
- MAX_TICKETS are generated and cached; `count` is NOT part of the cache key (包含ルール).

This module intentionally does NOT call any external LLM API yet.
You can later replace `build_description_b1()` with an OpenAI call and keep caching the result.
"""

from pathlib import Path
import json
import random
from typing import Any, Dict, List, Optional, Tuple

import os
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]  # Loto_site/
PRED_CACHE = ROOT / "pred_cache.json"  # shared cache file (消えてもOK)

MAX_TICKETS = 100


# ---------------------------
# Cache helpers
# ---------------------------
def load_pred_cache() -> Dict[str, Any]:
    if not PRED_CACHE.exists():
        PRED_CACHE.write_text("{}", encoding="utf-8")
    return json.loads(PRED_CACHE.read_text(encoding="utf-8"))


def save_pred_cache(cache: Dict[str, Any]) -> None:
    PRED_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------
# Deterministic RNG
# ---------------------------
def make_rng(*parts: str) -> random.Random:
    """Create deterministic RNG from stable hash (NOT Python's built-in hash)."""
    seed = "|".join(parts)
    # FNV-1a 32-bit
    h = 2166136261
    for ch in seed.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return random.Random(h)


def loto_range(loto_type: str) -> range:
    return range(1, 44) if loto_type == "loto6" else range(1, 38)


def need_k(loto_type: str) -> int:
    return 6 if loto_type == "loto6" else 7


# ---------------------------
# Fortune tickets (random)
# ---------------------------
def _sample_ticket(rng: random.Random, loto_type: str) -> List[int]:
    k = need_k(loto_type)
    nums = rng.sample(list(loto_range(loto_type)), k)
    nums.sort()
    return nums


def generate_fortune_tickets(
    loto_type: str,
    round_str: str,
    user_id: str,
    birthdate: str = "",
    max_tickets: int = MAX_TICKETS,
) -> List[List[int]]:
    """Generate deterministic-random tickets.

    - duplicates across tickets are allowed by spec.
    - within a ticket, numbers are unique (rng.sample).
    """
    rng = make_rng("fortune_tickets", loto_type, round_str, user_id, birthdate, "v1")

    tickets: List[List[int]] = []
    # Try to avoid identical whole tickets *a bit* for UX, but allow if it happens.
    seen: set[Tuple[int, ...]] = set()
    soft_max_retry = 50

    for _ in range(int(max_tickets)):
        for _try in range(soft_max_retry):
            t = _sample_ticket(rng, loto_type)
            key = tuple(t)
            if key not in seen:
                seen.add(key)
                tickets.append(t)
                break
        else:
            # give up uniqueness, just append
            tickets.append(_sample_ticket(rng, loto_type))

    return tickets


# ---------------------------
# Fortune description (B-1)
# ---------------------------
_HEADLINES = [
    "迷いを削る流れ",
    "静かに整える週",
    "直感より段取り",
    "選択を絞る好機",
    "焦らず決める日",
    "小さく確かめる",
]

_MAIN_OPENERS = [
    "今週は情報が増えるほど判断が散りやすい運気です。",
    "今回は気持ちが先走りやすい流れなので、いったん落ち着くのが吉です。",
    "周りに引っ張られやすい時期なので、自分の基準を先に決めると良いでしょう。",
    "細部に目が行きやすい運気なので、全体像を先に見ると判断が安定します。",
]

_MAIN_ADVICE = [
    "候補を増やしたら、最後は“迷わない1口”だけを選ぶ意識が鍵になります。",
    "数を広げるほど迷いが出るので、先にルール（削る基準）を作って選びましょう。",
    "まずは1口を本線に決め、追加は“近い感覚の口”だけに寄せるとぶれにくいです。",
    "悩むほど良い時期ではないので、決めたら引きずらずに切り替えるのがコツです。",
]

_ONE_WORD = [
    "絞って決める",
    "迷いは削る",
    "基準を先に",
    "本線を固定",
    "落ち着き重視",
    "決めたら切替",
]


def build_description_b1(
    loto_type: str,
    round_str: str,
    user_id: str,
    birthdate: str,
    draw_date: str,
    weekday: str,
) -> Dict[str, str]:
    """Deterministic description generator for fortune (B-1).

    IMPORTANT: Does not reference numbers/tickets.
    """
    rng = make_rng("fortune_txt", loto_type, round_str, user_id, birthdate, "b1", "v1")

    headline = rng.choice(_HEADLINES)
    opener = rng.choice(_MAIN_OPENERS)
    advice = rng.choice(_MAIN_ADVICE)
    one_word = rng.choice(_ONE_WORD)

    # 2 sentences max by design
    main = f"{opener}{advice}"

    return {
        "headline": headline,
        "main": main,
        "one_word": one_word,
    }

def _call_openai_description_b1(
    loto_type: str,
    round_str: str,
    user_id: str,
    birthdate: str,
    draw_date: str,
    weekday: str,
) -> Dict[str, str]:
    """
    OpenAIで fortune(B-1) 文章を生成して返す。
    失敗したら例外を投げる（呼び出し側でフォールバックする）。
    """
    # 念のため：キーが無いならここで分かりやすく落とす
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI()

    # 方針B-1：数字に一切触れない
    prompt = f"""
あなたは日本向けの「ロト占い」文章ライターです。以下の条件に基づき、短い占い文を作ってください。

【条件】
- loto_type: {loto_type}
- round: {round_str}
- draw_date: {draw_date}
- weekday: {weekday}
- birthdate: {birthdate}

【絶対ルール】
- 数字・番号・当選確率・特定の数の提案には一切触れない
- 断定や煽りは禁止（「必ず当たる」等NG）
- 出力は JSON のみ（前後に文章を付けない）
- 日本語、読みやすい口調（広告臭くしない）

【追加ルール（品質）】
- 「焦らず」「自然体」「落ち着いて」「直感を信じて」「大切です」だけで終えるのは禁止
- 本文に曜日・日付は入れない
- line2 は “具体行動” を1つだけ。書式は「動詞＋対象＋条件」で書く（例は書かない）
- line2 に同じ名詞（例：メモ/候補/基準/軸）を毎回使い回さない。できるだけ言い換える
- 抽象語（運気/波動/エネルギー等）だけで終えない

【やること】
1) 今回の運勢を ★1〜★5 で評価し、rating(1〜5) と stars(例: ★★★★☆) を出す
2) その評価に合わせて、本文を2行だけ作る
   - line1: 「今の運気の流れ」を具体的に（抽象語だけ禁止）
   - line2: 「選び方/心構え」の行動指針を1つだけ（具体的に）
3) 2行はそれぞれ 30〜45文字程度。句点は各行1回まで。

【評価の目安】
- 5: 追い風。決めた基準を通しやすい
- 4: 安定。無理せず整えると良い
- 3: 普通。迷いが出やすいので軸が必要
- 2: 注意。外部要因に振られやすい
- 1: 低調。休息・見直しを優先

【出力JSON仕様（厳守）】
{{
  "rating": 4,
  "stars": "★★★★☆",
  "line1": "...",
  "line2": "..."
}}
""".strip()

    # Responses API
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    text = (resp.output_text or "").strip()

    # JSONとしてパース
    try:
        data = json.loads(text)
    except Exception as e:
        raise RuntimeError(f"OpenAI output is not valid JSON: {text[:200]}") from e

    # 最低限の検証（rating版）
    for k in ("rating", "stars", "line1", "line2"):
        if k not in data:
            raise RuntimeError(f"OpenAI JSON missing key: {k}")

    if not isinstance(data["rating"], int) or not (1 <= data["rating"] <= 5):
        raise RuntimeError(f"OpenAI rating invalid: {data.get('rating')}")

    if not isinstance(data["stars"], str) or not data["stars"].strip():
        raise RuntimeError("OpenAI stars invalid")

    for k in ("line1", "line2"):
        if not isinstance(data[k], str) or not data[k].strip():
            raise RuntimeError(f"OpenAI {k} invalid")

    # formatter互換のため headline/main/one_word も埋める（←重要）
    rating = data["rating"]
    stars = data["stars"].strip()
    line1 = data["line1"].strip()
    line2 = data["line2"].strip()

    headline = f"今回の運勢 {stars}"
    main = f"{line1}\n{line2}"
    one_word = f"★{rating}"

    return {
        "headline": headline,
        "main": main,
        "one_word": one_word,
        # 将来UIで使えるように内部的に残す（外に出してもOKなら formatter 側で表示対応）
        "rating": rating,
        "stars": stars,
        "line1": line1,
        "line2": line2,
    }

# ---------------------------
# Public API
# ---------------------------
def _cache_key(
    loto_type: str,
    round_str: str,
    user_id: str,
    birthdate: str,
    model: str = "fortune",
    version: str = "v1",
) -> str:
    # NOTE: count is intentionally excluded.
    return f"{loto_type}|{round_str}|{model}|{user_id}|{birthdate}|{version}"


def generate(
    loto_type: str,
    round_str: str,
    draw_date: str,
    weekday: str,
    user_id: str,
    birthdate: str,
    count: int,
    model: str = "fortune",
) -> Dict[str, Any]:
    """Generate fortune engine output (internal structure).

    - Always generates MAX_TICKETS and caches.
    - Returns cached output if present.
    - descriptionは初回のみOpenAI生成し、以後キャッシュ固定（方針B-1）
    """
    cache = load_pred_cache()
    key = _cache_key(loto_type, round_str, user_id, birthdate, model=model, version="v4")

    # 既にキャッシュがある場合：原則そのまま返す
    if key in cache:
        out = cache[key]
        # drawは表示用なので更新OK
        out["draw"] = {"round": round_str, "date": draw_date, "weekday": weekday}

        # もし古いキャッシュ等で description が無い場合だけ生成して埋める
        desc = out.get("description")
        if not (isinstance(desc, dict) and desc.get("headline") and desc.get("main") and desc.get("one_word")):
            try:
                out["description"] = _call_openai_description_b1(
                    loto_type=loto_type,
                    round_str=round_str,
                    user_id=user_id,
                    birthdate=birthdate,
                    draw_date=draw_date,
                    weekday=weekday,
                )
            except Exception:
                # フォールバック：決定論文（数字に触れない）
                out["description"] = build_description_b1(
                    loto_type=loto_type,
                    round_str=round_str,
                    user_id=user_id,
                    birthdate=birthdate,
                    draw_date=draw_date,
                    weekday=weekday,
                )

            cache[key] = out
            save_pred_cache(cache)

        return out

    # キャッシュ無し：tickets は決定論で生成して保存
    tickets = generate_fortune_tickets(
        loto_type=loto_type,
        round_str=round_str,
        user_id=user_id,
        birthdate=birthdate,
        max_tickets=MAX_TICKETS,
    )

    # description は「初回だけ」OpenAI（失敗時は決定論にフォールバック）
    try:
        description = _call_openai_description_b1(
            loto_type=loto_type,
            round_str=round_str,
            user_id=user_id,
            birthdate=birthdate,
            draw_date=draw_date,
            weekday=weekday,
        )
    except Exception as e:
        print("[fortune][openai] failed:", repr(e))
        description = build_description_b1(
            loto_type=loto_type,
            round_str=round_str,
            user_id=user_id,
            birthdate=birthdate,
            draw_date=draw_date,
            weekday=weekday,
        )

    out: Dict[str, Any] = {
        "meta": {"model": model, "loto_type": loto_type, "version": "v4"},
        "draw": {"round": round_str, "date": draw_date, "weekday": weekday},
        "fixed2": [],
        "tickets": tickets,
        "count_generated": int(MAX_TICKETS),
        "description": description,
        "number_source": {
            "fixed": "none",
            "random": "uniform_v1",
        },
    }

    cache[key] = out
    save_pred_cache(cache)
    return out

def get_cached_prediction(
    loto_type: str,
    round_str: str,
    user_id: str,
    birthdate: str,
    model: str = "fortune",
) -> Optional[Dict[str, Any]]:
    cache = load_pred_cache()
    key = _cache_key(loto_type, round_str, user_id, birthdate, model=model, version="v4")
    return cache.get(key)
