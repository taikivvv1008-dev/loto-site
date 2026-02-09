from __future__ import annotations

import os
import subprocess
import json
from fastapi import FastAPI, Query, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from pathlib import Path
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import sys

load_dotenv()

from backend.database import engine, get_db, Base
from backend.models import User
from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_optional,
)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

ROOT = Path(__file__).resolve().parents[1]  # Loto_site
FORMATTER = ROOT / "engines" / "formatter.py"

# --- CORS ---
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Helpers (既存)
# ============================================================

def _weekday_3(draw_date: str) -> str:
    # draw_date: "YYYY-MM-DD"
    dt = datetime.strptime(draw_date, "%Y-%m-%d")
    return dt.strftime("%a")  # "Mon" etc.

def _read_latest_from_csv(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # ✅ 日本CSV（cp932）を優先して読む。ダメならutf-8も試す
    text = None
    for enc in ("cp932", "shift_jis", "utf-8-sig", "utf-8"):
        try:
            text = csv_path.read_text(encoding=enc)
            break
        except Exception:
            continue
    if text is None:
        # 最後の手段
        text = csv_path.read_text(encoding="utf-8", errors="ignore")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError(f"CSV has no data rows: {csv_path}")

    header = [h.strip() for h in lines[0].split(",")]
    last = [v.strip() for v in lines[-1].split(",")]

    def get_any(*names):
        for name in names:
            if name in header:
                idx = header.index(name)
                if idx < len(last):
                    return last[idx]
        return None

    # ✅ あなたのCSVは「開催回」「日付」になってる可能性が高いので候補に入れる
    round_str = get_any("開催回", "round", "Round", "回", "開催回数")
    date_str  = get_any("日付", "draw_date", "DrawDate", "抽せん日", "抽選日", "date")

    if not round_str or not date_str:
        raise ValueError(f"CSV header mismatch. header={header}")

    # 日付を YYYY-MM-DD に正規化（例: 2026/1/15 → 2026-01-15）
    date_str = date_str.replace("/", "-")
    y, m, d = date_str.split("-")
    draw_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    return int(round_str), draw_date

# ============================================================
# Auth schemas
# ============================================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# ============================================================
# Auth endpoints
# ============================================================

@app.post("/auth/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="このメールアドレスは既に登録されています")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "is_premium": user.is_premium,
        },
    }


@app.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが正しくありません")

    token = create_access_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "is_premium": user.is_premium,
        },
    }


@app.get("/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_premium": current_user.is_premium,
        "stripe_customer_id": current_user.stripe_customer_id,
        "created_at": str(current_user.created_at) if current_user.created_at else None,
    }


# ============================================================
# 既存エンドポイント（変更なし）
# ============================================================

@app.get("/draw/latest")
def draw_latest(loto_type: str = Query(...)):
    # regex は環境差で落ちることがあるので手動チェックにする
    if loto_type not in ("loto6", "loto7"):
        raise HTTPException(status_code=400, detail="loto_type must be loto6 or loto7")

    try:
        # Loto_site/backend/app.py から見て Loto_site/ を指す
        base = Path(__file__).resolve().parents[1]  # ←ここも確実な書き方に
        csv_path = base / "data" / "past_results" / f"{loto_type}.csv"

        round_int, draw_date = _read_latest_from_csv(csv_path)

        return {
            "loto_type": loto_type,
            "round": round_int,
            "draw_date": draw_date,
            "weekday": _weekday_3(draw_date),
        }
    except Exception as e:
        # 500で真っ白になるのを防いで、原因を画面に出す
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/predict")
def predict(
    loto_type: str = Query(..., pattern="^(loto6|loto7)$"),
    round: int = Query(..., ge=1),
    draw_date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user_id: str = Query(..., min_length=1),
    count: int = Query(..., ge=1, le=100),
    model: str = Query("logic", pattern="^(logic|fortune)$"),
    birthdate: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_premium:
        raise HTTPException(status_code=403, detail="有料プランへの登録が必要です")

    print("SUBPROCESS PY =", sys.executable)
    cmd = [
        sys.executable,   # ←ここが重要
        str(FORMATTER),
        "--loto_type", loto_type,
        "--round", str(round),
        "--draw_date", draw_date,
        "--user_id", user_id,
        "--count", str(count),
        "--model", model,
    ]
    if model == "fortune":
        if not birthdate:
            raise HTTPException(status_code=400, detail="fortune requires birthdate=YYYY-MM-DD")
        cmd += ["--birthdate", birthdate]

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(p.stdout)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"formatter error: {e.stderr}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="formatter returned non-json output")

@app.get("/engine/prediction")
def engine_prediction(
    loto_type: str,
    round: int,
    draw_date: str,
    user_id: str,
    count: int = 5,
    model: str = "logic",
    birthdate: str | None = None,
    current_user: User = Depends(get_current_user),
):
    return predict(
        loto_type=loto_type,
        round=round,
        draw_date=draw_date,
        user_id=user_id,
        count=count,
        model=model,
        birthdate=birthdate,
        current_user=current_user,
    )

# ============================================================
# Billing endpoints (imported from billing.py)
# ============================================================
from backend.billing import router as billing_router
app.include_router(billing_router)

# ============================================================
# Static files (本番用: frontend/ を配信)
# ============================================================
from fastapi.staticfiles import StaticFiles

_frontend_dir = ROOT / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
