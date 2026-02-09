"""Update LOTO6/LOTO7 historical result CSVs from KYO's sites.

This project keeps historical draw results under:
  data/past_results/loto6.csv
  data/past_results/loto7.csv

KYO's download pages state the CSV is updated around 20:00 on draw days.
So this script is designed to be run on draw days (or forced), and it will
only overwrite your local file when it can prove the remote file is newer.

URLs (as of 2026-01):
  - https://loto6.thekyo.jp/data/loto6.csv
  - https://loto7.thekyo.jp/data/loto7.csv

Usage examples
--------------
  # Update both (recommended to run after ~20:00 JST)
  python scripts/update_kyo_csv.py --all

  # Update only LOTO6
  python scripts/update_kyo_csv.py --loto loto6

  # Dry-run (no file changes)
  python scripts/update_kyo_csv.py --all --dry-run

  # If you want to test anytime
  python scripts/update_kyo_csv.py --all --force
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shutil
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple


KYO_CSV_URL = {
    "loto6": "https://loto6.thekyo.jp/data/loto6.csv",
    "loto7": "https://loto7.thekyo.jp/data/loto7.csv",
}

LOCAL_CSV_PATH = {
    "loto6": Path("data/past_results/loto6.csv"),
    "loto7": Path("data/past_results/loto7.csv"),
}


# KYO CSVs are typically Shift-JIS (Windows-31J / CP932).
CSV_ENCODING_CANDIDATES = ("cp932", "shift_jis", "utf-8")


@dataclass(frozen=True)
class CsvTailInfo:
    round_no: int
    draw_date: dt.date


def _parse_draw_date(s: str) -> dt.date:
    """Parse a date like '2026/1/12' or '2026/01/12'."""
    s = s.strip()
    # allow YYYY/M/D
    parts = s.split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid draw_date: {s!r}")
    y, m, d = (int(p) for p in parts)
    return dt.date(y, m, d)


def _read_csv_tail_info(path: Path) -> CsvTailInfo:
    """Read the last non-empty row and extract (round, draw_date)."""
    if not path.exists():
        raise FileNotFoundError(path)

    last_row: Optional[list[str]] = None
    used_encoding: Optional[str] = None
    last_error: Optional[Exception] = None

    raw = path.read_bytes()
    for enc in CSV_ENCODING_CANDIDATES:
        try:
            text = raw.decode(enc)
            used_encoding = enc
            break
        except Exception as e:  # noqa: BLE001
            last_error = e
    else:
        raise UnicodeDecodeError(
            "unknown",
            b"",
            0,
            1,
            f"Failed to decode {path} with candidates={CSV_ENCODING_CANDIDATES}. last_error={last_error}",
        )

    reader = csv.reader(text.splitlines())
    for row in reader:
        if row and any(c.strip() for c in row):
            last_row = row

    if not last_row:
        raise ValueError(f"CSV has no data rows: {path}")

    # Expected columns: round, date, ...
    try:
        round_no = int(last_row[0].strip())
        draw_date = _parse_draw_date(last_row[1])
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Failed to parse last row in {path} (encoding={used_encoding}): {last_row!r}") from e

    return CsvTailInfo(round_no=round_no, draw_date=draw_date)


def _download_to_temp(url: str, timeout_sec: int = 30) -> Path:
    """Download URL to a temporary file path and return it."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; LotoSiteBot/1.0; +https://example.invalid)",
            "Accept": "text/csv,*/*;q=0.8",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        data = resp.read()

    # Basic sanity: avoid writing tiny error pages.
    if len(data) < 1024:
        raise ValueError(f"Downloaded file looks too small ({len(data)} bytes): {url}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="kyo_csv_"))
    tmp_path = tmp_dir / "download.csv"
    tmp_path.write_bytes(data)
    return tmp_path


def _looks_like_kyo_csv(path: Path) -> Tuple[bool, str]:
    """Check header contains Japanese '開催回' or plausible first two columns."""
    raw = path.read_bytes()
    last_error: Optional[Exception] = None
    for enc in CSV_ENCODING_CANDIDATES:
        try:
            text = raw.decode(enc)
            header_line = text.splitlines()[0]
            # KYO header typically starts with '開催回,日付,...'
            if "開催回" in header_line and "日付" in header_line:
                return True, f"ok (encoding={enc})"
            # If not, still accept if first two columns are parseable names.
            if header_line.count(",") >= 2:
                return True, f"header not standard but CSV-like (encoding={enc})"
        except Exception as e:  # noqa: BLE001
            last_error = e
            continue
    return False, f"failed to decode/validate header. last_error={last_error}"


def _is_draw_day(loto: str, today: dt.date) -> bool:
    """Simple rule-of-thumb schedule.

    - LOTO6: Monday(0) and Thursday(3)
    - LOTO7: Friday(4)
    """
    wd = today.weekday()
    if loto == "loto6":
        return wd in (0, 3)
    if loto == "loto7":
        return wd == 4
    raise ValueError(loto)


def update_one(
    loto: str,
    *,
    dry_run: bool,
    force: bool,
    today: dt.date,
    min_hour_jst: int,
    now_local: Optional[dt.datetime] = None,
) -> int:
    """Return exit code (0=ok, 1=skipped/failed)."""
    url = KYO_CSV_URL[loto]
    local_path = LOCAL_CSV_PATH[loto]

    # Optional time gate (recommended because KYO updates around ~20:00)
    if now_local is None:
        now_local = dt.datetime.now()

    if not force:
        if not _is_draw_day(loto, today):
            print(f"[{loto}] SKIP: today={today} is not a draw day (use --force to override)")
            return 0
        if now_local.hour < min_hour_jst:
            print(
                f"[{loto}] SKIP: now={now_local.strftime('%H:%M')} < {min_hour_jst}:00. "
                "KYO CSV is usually updated around 20:00 (use --force to override)."
            )
            return 0

    print(f"[{loto}] Downloading: {url}")
    tmp = _download_to_temp(url)

    ok, reason = _looks_like_kyo_csv(tmp)
    if not ok:
        print(f"[{loto}] FAIL: downloaded file did not look like expected CSV: {reason}")
        return 1

    remote_tail = _read_csv_tail_info(tmp)
    if local_path.exists():
        local_tail = _read_csv_tail_info(local_path)
        print(f"[{loto}] local : round={local_tail.round_no}, date={local_tail.draw_date}")
    else:
        local_tail = None
        print(f"[{loto}] local : (missing) -> will create")

    print(f"[{loto}] remote: round={remote_tail.round_no}, date={remote_tail.draw_date}")

    # Update condition: remote must be newer.
    is_newer = (
        local_tail is None
        or (remote_tail.round_no > local_tail.round_no)
        or (remote_tail.round_no == local_tail.round_no and remote_tail.draw_date > local_tail.draw_date)
    )

    if not is_newer:
        print(f"[{loto}] NO-UPDATE: remote is not newer than local")
        return 0

    # Extra safety on draw day: ensure remote includes today's row (or later).
    if not force and remote_tail.draw_date < today:
        print(
            f"[{loto}] FAIL: remote seems not updated for today. remote_date={remote_tail.draw_date} < today={today}."
        )
        return 1

    if dry_run:
        print(f"[{loto}] DRY-RUN: would overwrite {local_path}")
        return 0

    local_path.parent.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    if local_path.exists():
        backup = local_path.with_suffix(local_path.suffix + f".bak_{ts}")
        shutil.copy2(local_path, backup)
        print(f"[{loto}] backup created: {backup}")

    shutil.copy2(tmp, local_path)
    print(f"[{loto}] UPDATED: {local_path}")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Update loto6/loto7 CSVs from KYO's sites")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--loto", choices=["loto6", "loto7"], help="Which loto to update")
    g.add_argument("--all", action="store_true", help="Update both loto6 and loto7")
    p.add_argument("--dry-run", action="store_true", help="Do not write files")
    p.add_argument("--force", action="store_true", help="Ignore draw-day and time gate")
    p.add_argument(
        "--min-hour",
        type=int,
        default=20,
        help="Only run after this hour (local time). Default: 20 (recommended)",
    )
    p.add_argument(
        "--date",
        default=None,
        help="Treat this as 'today' (YYYY-MM-DD). Useful for testing.",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    if args.date:
        try:
            today = dt.date.fromisoformat(args.date)
        except ValueError as e:
            raise SystemExit(f"Invalid --date: {args.date!r} (expected YYYY-MM-DD)") from e
    else:
        today = dt.date.today()

    exit_codes = []
    if args.all:
        for loto in ("loto6", "loto7"):
            exit_codes.append(
                update_one(
                    loto,
                    dry_run=args.dry_run,
                    force=args.force,
                    today=today,
                    min_hour_jst=args.min_hour,
                )
            )
    else:
        exit_codes.append(
            update_one(
                args.loto,
                dry_run=args.dry_run,
                force=args.force,
                today=today,
                min_hour_jst=args.min_hour,
            )
        )

    # return non-zero if any failed
    return 1 if any(code != 0 for code in exit_codes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
