# verify_rules.py
from __future__ import annotations
import argparse
from dataclasses import dataclass
from typing import List, Tuple, Dict, Iterable, Optional
import pandas as pd

# -----------------------------
# CSV load / normalize
# -----------------------------
def load_loto_csv(path: str, loto_type: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="cp932")
    # 数字列（BONUSは除外）
    if loto_type == "loto6":
        num_cols = [f"第{i}数字" for i in range(1, 7)]
        max_n = 43
    elif loto_type == "loto7":
        num_cols = [f"第{i}数字" for i in range(1, 8)]
        max_n = 37
    else:
        raise ValueError("loto_type must be loto6 or loto7")

    for c in num_cols:
        if c not in df.columns:
            raise ValueError(f"Missing column: {c}")

    df = df.copy()
    df["round"] = pd.to_numeric(df["開催回"], errors="coerce")
    df["date"] = pd.to_datetime(df["日付"], errors="coerce")

    # numbers as sorted list
    df["numbers"] = df[num_cols].apply(lambda r: sorted([int(x) for x in r.values.tolist()]), axis=1)
    df["sum"] = df["numbers"].apply(sum)
    df["max_n"] = max_n
    df = df.dropna(subset=["round"]).sort_values("round").reset_index(drop=True)
    return df

def last_digits(nums: List[int]) -> List[int]:
    return [n % 10 for n in nums]

def count_consecutive_pairs(nums: List[int]) -> int:
    s = sorted(nums)
    cnt = 0
    for i in range(len(s) - 1):
        if s[i+1] == s[i] + 1:
            cnt += 1
    return cnt

def complement_pairs_lastdigit(d: int) -> int:
    # 末尾ミラー交差: (1,9),(2,8),(3,7),(4,6),(0,5)
    comp = {1:9, 9:1, 2:8, 8:2, 3:7, 7:3, 4:6, 6:4, 0:5, 5:0}
    return comp.get(d, -1)

# -----------------------------
# LOTO6 rules (testable ones)
# -----------------------------
def loto6_gap_pattern_match(prev: List[int], cur: List[int], allow_mismatch: int = 0) -> bool:
    """
    ①スライドギャップ法（あなたの解釈版）
    - 前回の昇順差分（ギャップ列）が次回も続くかを判定
    - allow_mismatch=0 なら完全一致
    """
    prev_s = sorted(prev)
    cur_s = sorted(cur)

    g_prev = [prev_s[i+1] - prev_s[i] for i in range(len(prev_s)-1)]
    g_cur  = [cur_s[i+1]  - cur_s[i]  for i in range(len(cur_s)-1)]

    mism = sum(1 for a,b in zip(g_prev, g_cur) if a != b)
    return mism <= allow_mismatch

def loto6_triangle_zone_ok(nums: List[int]) -> bool:
    # ②三角ゾーン法：低1-14 / 中15-28 / 高29-43 を 2個ずつ
    low = sum(1 for n in nums if 1 <= n <= 14)
    mid = sum(1 for n in nums if 15 <= n <= 28)
    high = sum(1 for n in nums if 29 <= n <= 43)
    return (low, mid, high) == (2, 2, 2)

def loto6_odd_even_3_3(nums: List[int]) -> bool:
    odd = sum(1 for n in nums if n % 2 == 1)
    even = len(nums) - odd
    return odd == 3 and even == 3

def loto6_inner_mountain(nums: List[int], edge_tol: int = 2, mid_max: int = 6) -> bool:
    """
    ⑩対称インナー法（あなたの仮説：5,3,1,2,4,6 並びのペア差）
    s=昇順 [n1,n2,n3,n4,n5,n6]
    並び: [n5,n3,n1,n2,n4,n6]
    ペア差: d1=|n5-n3|, d2=|n2-n1|, d3=|n6-n4|
    判定（仮）:
      - |d1-d3| <= edge_tol
      - d2 <= mid_max
    """
    n1,n2,n3,n4,n5,n6 = sorted(nums)
    d1 = abs(n5 - n3)
    d2 = abs(n2 - n1)
    d3 = abs(n6 - n4)
    return (abs(d1 - d3) <= edge_tol) and (d2 <= mid_max)

def loto6_odd_even_mirrorish(nums: List[int], sum_tolerance: int = 2) -> bool:
    """
    ③奇偶対称ミラー法（あなたの解釈寄り）
    - 奇数3:偶数3 を満たす
    - 昇順の左右ペア和が「ほぼ同じ」なら対称とみなす
      (s0+s5, s1+s4, s2+s3 の最大差 <= sum_tolerance)
    """
    s = sorted(nums)
    odd = sum(1 for n in s if n % 2 == 1)
    if odd != 3:
        return False

    pair_sums = [s[0]+s[5], s[1]+s[4], s[2]+s[3]]
    return (max(pair_sums) - min(pair_sums)) <= sum_tolerance

def loto6_cold_revive(nums: List[int], past: List[List[int]], lookback: int = 30) -> int:
    # ④コールド復活法：直近lookback回で一度も出てない数字（コールド）を何個含むか
    recent = past[-lookback:] if len(past) >= lookback else past[:]
    appeared = set(x for draw in recent for x in draw)
    cold = set(range(1, 44)) - appeared
    return len(set(nums) & cold)

def loto6_sum_in_range(nums: List[int], lo: int = 100, hi: int = 160) -> bool:
    return lo <= sum(nums) <= hi

def loto6_pull_one(prev: List[int], cur: List[int]) -> bool:
    # ⑥ 引っ張り一点軸法：前回と1個以上一致
    return len(set(prev) & set(cur)) >= 1

def loto6_lastdigit_diverse(nums: List[int], min_kinds: int = 5) -> bool:
    # ⑦ 末尾グラデーション法：末尾種類が5以上
    return len(set(last_digits(nums))) >= min_kinds

def loto6_balance_1_10_11_30_31_43(nums: List[int]) -> bool:
    # ⑨ バランスレンジ法：1-10, 11-30, 31-43 から最低1個ずつ
    a = sum(1 for n in nums if 1 <= n <= 10) >= 1
    b = sum(1 for n in nums if 11 <= n <= 30) >= 1
    c = sum(1 for n in nums if 31 <= n <= 43) >= 1
    return a and b and c

def loto6_inversion_overlap(prev: List[int], cur: List[int]) -> int:
    # ⑧ 反転ミラー法：44-n で反転した前回セットと当回の一致数（※法則は作り方寄りなので一致数で参考表示）
    inv = [44 - n for n in prev]
    return len(set(inv) & set(cur))

# -----------------------------
# LOTO7 rules (testable ones)
# -----------------------------
def loto7_hot_mix(nums: List[int], past: List[List[int]], window: int = 10, hot_min_count: int = 2, need_hot_included: int = 2) -> bool:
    # ①ホットミックス法：直近window回で2回以上出た数字＝ホット、当回にホットが2個以上含まれるか
    recent = past[-window:] if len(past) >= window else past[:]
    freq: Dict[int,int] = {}
    for draw in recent:
        for n in draw:
            freq[n] = freq.get(n, 0) + 1
    hot = {n for n,c in freq.items() if c >= hot_min_count}
    return len(set(nums) & hot) >= need_hot_included

def loto7_teens_pivot(nums: List[int]) -> bool:
    # ②十台ピボット法：10-19が2〜3個
    cnt = sum(1 for n in nums if 10 <= n <= 19)
    return 2 <= cnt <= 3

def loto7_odd_even_4_3(nums: List[int]) -> bool:
    # ③奇遇ウィンドウ法：奇数4:偶数3
    odd = sum(1 for n in nums if n % 2 == 1)
    even = len(nums) - odd
    return odd == 4 and even == 3

def loto7_sum_in_range(nums: List[int], lo: int = 100, hi: int = 170) -> bool:
    return lo <= sum(nums) <= hi

def loto7_lastdigit_dispersion_one_dup(nums: List[int]) -> bool:
    # ⑤末尾分散+一点重複法：7個のうち末尾種類が6（＝1つだけ末尾重複）
    return len(set(last_digits(nums))) == 6

def loto7_inversion_overlap(prev: List[int], cur: List[int]) -> int:
    # ⑥左右反転軸法：38-n の反転セットと当回の一致数（参考）
    inv = [38 - n for n in prev]
    return len(set(inv) & set(cur))

def loto7_rhythm_stair(nums: List[int], diffs=(3,4), min_len=4) -> bool:
    # ⑦リズム会談法：+3 or +4 の等差っぽい並びが長さmin_len以上あるか（簡易判定）
    s = sorted(nums)
    # DP: for each i, length of chain ending at i for each diff
    for d in diffs:
        best = 1
        dp = {x:1 for x in s}
        for x in s:
            dp[x] = dp.get(x - d, 0) + 1
            best = max(best, dp[x])
        if best >= min_len:
            return True
    return False

def loto7_double_consecutive(nums: List[int]) -> bool:
    # ⑧連番ダブル法：連番ペアが2組以上
    return count_consecutive_pairs(nums) >= 2

def loto7_lastdigit_mirror_cross(nums: List[int], min_pairs: int = 2) -> bool:
    # ⑨末尾ミラー交差法：末尾の補完ペアが min_pairs 以上あるか
    ds = set(last_digits(nums))
    pairs = set()
    for d in ds:
        cd = complement_pairs_lastdigit(d)
        if cd in ds and cd != -1:
            pairs.add(tuple(sorted((d, cd))))
    return len(pairs) >= min_pairs

def loto7_half_swap_overlap(prev: List[int], cur: List[int]) -> bool:
    # ⑩ハーフ入替法：前回と3個以上一致（※「前半3つを残す」を厳密に定義できないので一致数で近似）
    return len(set(prev) & set(cur)) >= 3

# -----------------------------
# runner
# -----------------------------
def summarize_bool(series: List[bool]) -> Dict[str, float]:
    n = len(series)
    t = sum(1 for x in series if x)
    return {"count": n, "true": t, "rate": (t / n if n else 0.0)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loto_type", required=True, choices=["loto6","loto7"])
    ap.add_argument("--csv", required=True)
    ap.add_argument("--start_round", type=int, default=None)
    ap.add_argument("--end_round", type=int, default=None)
    ap.add_argument("--print_head", type=int, default=0, help="print first N rows of per-round results")
    args = ap.parse_args()

    df = load_loto_csv(args.csv, args.loto_type)

    if args.start_round is not None:
        df = df[df["round"] >= args.start_round].reset_index(drop=True)
    if args.end_round is not None:
        df = df[df["round"] <= args.end_round].reset_index(drop=True)

    nums_all: List[List[int]] = df["numbers"].tolist()
    rounds: List[int] = df["round"].astype(int).tolist()

    # per-round metrics
    out_rows = []

    if args.loto_type == "loto6":
        # ①：ギャップ一致（True/False）
        gap_ok = []

        # ②
        tri_ok = []

        # ③：奇偶3:3 + 左右対称っぽさ（True/False）
        mirror_ok = []

        # ④：コールド数（int）
        cold_hits = []

        # ⑤
        sum_ok = []

        # ⑥（prev必要）
        pull_ok = []

        # ⑦
        lastdig_ok = []

        # ⑨
        bal_ok = []

        # ⑧（prev必要：overlap数）
        inv_hits = []

        # ⑩：あなた仮説のインナー（True/False）
        inner_ok = []

        for i in range(len(nums_all)):
            cur = nums_all[i]
            past = nums_all[:i]
            prev = nums_all[i-1] if i-1 >= 0 else None

            # prev依存（①⑥⑧）
            if prev is not None:
                gap_ok.append(loto6_gap_pattern_match(prev, cur, allow_mismatch=2))
                inv_hits.append(loto6_inversion_overlap(prev, cur))
                pull_ok.append(loto6_pull_one(prev, cur))

            # prev不要（②③④⑤⑦⑨⑩）
            tri_ok.append(loto6_triangle_zone_ok(cur))
            mirror_ok.append(loto6_odd_even_mirrorish(cur, sum_tolerance=6))
            cold_hits.append(loto6_cold_revive(cur, past, lookback=30))
            sum_ok.append(loto6_sum_in_range(cur, 100, 160))
            lastdig_ok.append(loto6_lastdigit_diverse(cur, 5))
            bal_ok.append(loto6_balance_1_10_11_30_31_43(cur))
            inner_ok.append(loto6_inner_mountain(cur, edge_tol=4, mid_max=8))

            if args.print_head and len(out_rows) < args.print_head:
                out_rows.append({
                    "round": rounds[i],
                    "nums": cur,
                    "gap_match": gap_ok[-1] if prev is not None else None,           # ①
                    "triangle_2-2-2": tri_ok[-1],                                    # ②
                    "odd_even_mirrorish": mirror_ok[-1],                             # ③
                    "cold_hits(30)": cold_hits[-1],                                  # ④
                    "sum_100_160": sum_ok[-1],                                       # ⑤
                    "pull>=1": pull_ok[-1] if prev is not None else None,            # ⑥
                    "lastdigit>=5": lastdig_ok[-1],                                  # ⑦
                    "inv_overlap": inv_hits[-1] if prev is not None else None,       # ⑧
                    "balance_bands": bal_ok[-1],                                     # ⑨
                    "inner_mountain": inner_ok[-1],                                  # ⑩
                })

        print("=== LOTO6 verification (updated interpretation) ===")

        # ①
        if gap_ok:
            print(f"[①スライドギャップ法(ギャップ一致)] {summarize_bool(gap_ok)}")

        # ②
        print(f"[②三角ゾーン法(2-2-2)] {summarize_bool(tri_ok)}")

        # ③
        print(f"[③奇偶対称ミラー法(昇順ペア和が近い)] {summarize_bool(mirror_ok)}")

        # ④
        cs = pd.Series(cold_hits)
        print(f"[④コールド復活(直近30未出)] >=1 rate={(cs>=1).mean():.3f}  >=2 rate={(cs>=2).mean():.3f}  mean_hits={cs.mean():.3f}")

        # ⑤
        print(f"[⑤合計100-160] {summarize_bool(sum_ok)}")

        # ⑥
        if pull_ok:
            print(f"[⑥引っ張り(前回と>=1一致)] {summarize_bool(pull_ok)}")

        # ⑦
        print(f"[⑦末尾種類>=5] {summarize_bool(lastdig_ok)}")

        # ⑨
        print(f"[⑨バランス(1-10/11-30/31-43)] {summarize_bool(bal_ok)}")

        # ⑧
        if inv_hits:
            invs = pd.Series(inv_hits)
            print(f"[⑧反転ミラー(44-n) overlap] mean={invs.mean():.3f}  >=1 rate={(invs>=1).mean():.3f}")

        # ⑩
        print(f"[⑩対称インナー法(仮: 5,3,1,2,4,6ペア差)] {summarize_bool(inner_ok)}")

        if out_rows:
            print("\n--- sample rows ---")
            for r in out_rows:
                print(r)

    else:
        hot_ok = []
        teens_ok = []
        oe_ok = []
        sum_ok = []
        lastdig_ok = []
        inv_hits = []
        rhythm_ok = []
        dblcon_ok = []
        ldmirror_ok = []
        halfswap_ok = []

        for i in range(len(nums_all)):
            cur = nums_all[i]
            past = nums_all[:i]
            prev = nums_all[i-1] if i-1 >= 0 else None

            hot_ok.append(loto7_hot_mix(cur, past, window=10, hot_min_count=2, need_hot_included=2))
            teens_ok.append(loto7_teens_pivot(cur))
            oe_ok.append(loto7_odd_even_4_3(cur))
            sum_ok.append(loto7_sum_in_range(cur, 100, 170))
            lastdig_ok.append(loto7_lastdigit_dispersion_one_dup(cur))
            rhythm_ok.append(loto7_rhythm_stair(cur, diffs=(3,4), min_len=4))
            dblcon_ok.append(loto7_double_consecutive(cur))
            ldmirror_ok.append(loto7_lastdigit_mirror_cross(cur, min_pairs=2))

            if prev is not None:
                inv_hits.append(loto7_inversion_overlap(prev, cur))
                halfswap_ok.append(loto7_half_swap_overlap(prev, cur))

            if args.print_head and len(out_rows) < args.print_head:
                out_rows.append({
                    "round": rounds[i],
                    "nums": cur,
                    "hot_mix": hot_ok[-1],
                    "teens_2-3": teens_ok[-1],
                    "odd4_even3": oe_ok[-1],
                    "sum_100_170": sum_ok[-1],
                    "lastdigit_unique=6": lastdig_ok[-1],
                    "mirror_overlap(38-n)": inv_hits[-1] if prev is not None else None,
                    "rhythm(+3/+4 len>=4)": rhythm_ok[-1],
                    "double_consecutive>=2": dblcon_ok[-1],
                    "lastdigit_mirror_pairs>=2": ldmirror_ok[-1],
                    "half_swap(overlap>=3)": halfswap_ok[-1] if prev is not None else None,
                })

        print("=== LOTO7 verification (testable rules) ===")
        print(f"[①ホットミックス] {summarize_bool(hot_ok)}")
        print(f"[②十台2-3個] {summarize_bool(teens_ok)}")
        print(f"[③奇偶4:3] {summarize_bool(oe_ok)}")
        print(f"[④合計100-170] {summarize_bool(sum_ok)}")
        print(f"[⑤末尾分散(種類=6)] {summarize_bool(lastdig_ok)}")

        if inv_hits:
            invs = pd.Series(inv_hits)
            print(f"[⑥左右反転(38-n) overlap] mean={invs.mean():.3f}  >=1 rate={(invs>=1).mean():.3f}")

        print(f"[⑦リズム会談(+3/+4, len>=4)] {summarize_bool(rhythm_ok)}")
        print(f"[⑧連番ダブル(連番>=2組)] {summarize_bool(dblcon_ok)}")
        print(f"[⑨末尾ミラー交差(ペア>=2)] {summarize_bool(ldmirror_ok)}")

        if halfswap_ok:
            print(f"[⑩ハーフ入替(前回と>=3一致)] {summarize_bool(halfswap_ok)}")

        if out_rows:
            print("\n--- sample rows ---")
            for r in out_rows:
                print(r)

if __name__ == "__main__":
    main()
