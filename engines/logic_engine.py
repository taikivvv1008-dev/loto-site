from __future__ import annotations
from pathlib import Path
import json
import random
from typing import List, Dict, Any, Tuple

# verify_rules.py から「判定関数」を流用する
from engines.scripts.verify_rules import (
    load_loto_csv,
    loto6_sum_in_range,
    loto6_balance_1_10_11_30_31_43,
    loto6_lastdigit_diverse,
    loto7_sum_in_range,
    loto7_odd_even_4_3,
    loto7_lastdigit_dispersion_one_dup,
)

ROOT = Path(__file__).resolve().parents[1]

FIXED2_CACHE = ROOT / "fixed2_cache.json"

PRED_CACHE = ROOT / "pred_cache.json"

MAX_TICKETS = 100  # 例：まずは50口まで対応（必要なら変更）

def load_pred_cache() -> Dict[str, Any]:
    if not PRED_CACHE.exists():
        PRED_CACHE.write_text("{}", encoding="utf-8")
    return json.loads(PRED_CACHE.read_text(encoding="utf-8"))

def save_pred_cache(cache: Dict[str, Any]) -> None:
    PRED_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def load_fixed2_cache() -> Dict[str, Any]:
    if not FIXED2_CACHE.exists():
        FIXED2_CACHE.write_text("{}", encoding="utf-8")
    return json.loads(FIXED2_CACHE.read_text(encoding="utf-8"))

def save_fixed2_cache(cache: Dict[str, Any]) -> None:
    FIXED2_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def make_rng(*parts: str) -> random.Random:
    seed = "|".join(parts)
    # 安定したseed（Pythonのhashは実行ごとに変わるので使わない）
    h = 2166136261
    for ch in seed.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return random.Random(h)


def load_config() -> Dict[str, Any]:
    cfg_path = ROOT / "logic_config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def loto_range(loto_type: str) -> range:
    return range(1, 44) if loto_type == "loto6" else range(1, 38)


def need_k(loto_type: str) -> int:
    return 6 if loto_type == "loto6" else 7


def score_pool_by_hot(past_draws: List[List[int]], loto_type: str, window: int = 10) -> Dict[int, float]:
    recent = past_draws[-window:] if len(past_draws) >= window else past_draws
    freq = {n: 0 for n in loto_range(loto_type)}
    for d in recent:
        for n in d:
            freq[n] += 1
    # 重み：最低1.0 + 出現回数×0.25
    return {n: 1.0 + freq[n] * 0.25 for n in freq}

def choose_fixed2(loto_type: str, round_str: str, date_str: str, past_draws: List[List[int]]) -> List[int]:
    cache = load_fixed2_cache()
    key = f"{loto_type}|{round_str}|v1"
    if key in cache:
        return sorted([int(cache[key][0]), int(cache[key][1])])

    rng = make_rng("fixed2", loto_type, round_str, "v1")
    weights_map = score_pool_by_hot(past_draws, loto_type, window=10)

    pool = list(loto_range(loto_type))
    weights = [weights_map[n] for n in pool]

    # ★重み付きで2個をユニーク抽選
    picked = weighted_sample_unique(rng, pool, weights, 2)
    fixed = sorted(picked)

    cache[key] = fixed
    save_fixed2_cache(cache)
    return fixed

def passes_filters_loto6(nums: List[int], cfg: Dict[str, Any]) -> bool:
    if not loto6_sum_in_range(nums, cfg["sum_lo"], cfg["sum_hi"]):
        return False
    if cfg.get("need_balance_bands", True) and not loto6_balance_1_10_11_30_31_43(nums):
        return False
    if not loto6_lastdigit_diverse(nums, cfg.get("need_lastdigit_kinds", 5)):
        return False
    return True


def passes_filters_loto7(nums: List[int], cfg: Dict[str, Any]) -> bool:
    if not loto7_sum_in_range(nums, cfg["sum_lo"], cfg["sum_hi"]):
        return False

    # ここをONにする
    if not loto7_odd_even_4_3(nums):
        return False
    if not loto7_lastdigit_dispersion_one_dup(nums):
        return False

    return True


def weighted_sample_unique(rng: random.Random, items: List[int], weights: List[float], k: int) -> List[int]:
    pool = items[:]
    w = weights[:]
    out = []
    for _ in range(k):
        total = sum(w)
        r = rng.random() * total
        acc = 0.0
        idx = 0
        for i, wi in enumerate(w):
            acc += wi
            if acc >= r:
                idx = i
                break
        out.append(pool.pop(idx))
        w.pop(idx)
    return out


def generate_tickets(
    loto_type: str,
    round_str: str,
    date_str: str,
    user_id: str,
    count: int,
    fixed2: List[int],
    past_draws: List[List[int]],
    cfg: Dict[str, Any],
) -> List[List[int]]:
    rng = make_rng("tickets", loto_type, round_str, user_id, "v1")

    pool = [n for n in loto_range(loto_type) if n not in set(fixed2)]
    weight_map = score_pool_by_hot(past_draws, loto_type, window=10)
    weights = [weight_map[n] for n in pool]

    k = need_k(loto_type) - 2
    max_tries = int(cfg.get("max_tries_per_ticket", 300))

    tickets = []
    used = set()

    for t in range(count):
        ok = False
        for _ in range(max_tries):
            picked = weighted_sample_unique(rng, pool, weights, k)
            nums = sorted(fixed2 + picked)
            if loto_type == "loto6":
                if not passes_filters_loto6(nums, cfg):
                    continue
            else:
                if not passes_filters_loto7(nums, cfg):
                    continue

            key = tuple(nums)
            if key in used:
                continue
            used.add(key)
            tickets.append(nums)
            ok = True
            break

        # どうしても通らない時は緩めて埋める（必ずcountを返す）
        if not ok:
            while True:
                picked = rng.sample(pool, k)
                nums = sorted(fixed2 + picked)
                key = tuple(nums)
                if key in used:
                    continue
                used.add(key)
                tickets.append(nums)
                break

    return tickets

def generate(loto_type: str, round_str: str, date_str: str, user_id: str, count: int, model: str = "logic") -> Dict[str, Any]:
    # ★予想キャッシュ：同じ開催回×ユーザー×モデルなら固定で返す（countは表示でslice）
    pred_cache = load_pred_cache()

    new_key = f"{loto_type}|{round_str}|{model}|{user_id}|v1"
    old_key = f"{loto_type}|{round_str}|{user_id}|v1"  # 後方互換

    if new_key in pred_cache:
        out = pred_cache[new_key]
        out["draw"] = {"round": round_str, "date": date_str}
        return out

    if old_key in pred_cache:
        # 旧キーがあれば移行して返す
        out = pred_cache[old_key]
        pred_cache[new_key] = out
        save_pred_cache(pred_cache)
        out["draw"] = {"round": round_str, "date": date_str}
        return out

    cfg_all = load_config()
    cfg = cfg_all[loto_type]
    cfg6 = cfg_all["loto6"]
    cfg7 = cfg_all["loto7"]

    csv_path = ROOT / "data" / "past_results" / f"{loto_type}.csv"
    df = load_loto_csv(str(csv_path), loto_type)
    past_draws = df["numbers"].tolist()

    fixed2 = choose_fixed2(loto_type, round_str, date_str, past_draws)
    gen_count = max(int(count), MAX_TICKETS)  # いつでも包含される
    tickets = generate_tickets(loto_type, round_str, date_str, user_id, gen_count, fixed2, past_draws, cfg)


    out = {
        "meta": {"model": "logic", "loto_type": loto_type, "version": cfg_all.get("version", "v1")},
        "draw": {"round": round_str, "date": date_str},
        "fixed2": fixed2,
        "tickets": tickets,
        "count_generated": gen_count,
        "rules": {
            "loto6": {
                "sum": [cfg6["sum_lo"], cfg6["sum_hi"]],
                "balance": cfg6.get("need_balance_bands", True),
                "lastdigit_kinds": cfg6.get("need_lastdigit_kinds", 5),
            },
            "loto7": {
                "sum": [cfg7["sum_lo"], cfg7["sum_hi"]],
                "odd_even_4_3": True,
                "lastdigit_one_dup": True,
            }
        }
    }

    pred_cache[new_key] = out
    save_pred_cache(pred_cache)
    return out

def get_cached_prediction(loto_type: str, round_str: str, user_id: str, count: int, model: str = "logic") -> Dict[str, Any] | None:
    cache = load_pred_cache()
    new_key = f"{loto_type}|{round_str}|{model}|{user_id}|v1"
    if new_key in cache:
        return cache[new_key]

    old_key = f"{loto_type}|{round_str}|{user_id}|v1"
    v = cache.get(old_key)
    if v is not None:
        cache[new_key] = v  # 移行
        save_pred_cache(cache)
    return v
