from __future__ import annotations

import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from backend.database import get_db
from backend.models import User
from backend.auth import get_current_user

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

router = APIRouter()


@router.post("/billing/create-checkout-session")
def create_checkout_session(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Already premium?
    if current_user.is_premium:
        raise HTTPException(status_code=400, detail="既にプレミアム会員です")

    # Create or reuse Stripe customer
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        current_user.stripe_customer_id = customer.id
        db.commit()

    base_url = str(request.base_url).rstrip("/")

    session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        mode="subscription",
        success_url=f"{base_url}/login.html?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/login.html?status=cancelled",
        metadata={"user_id": str(current_user.id)},
    )

    return {"checkout_url": session.url}


@router.get("/billing/verify-session")
def verify_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stripe Checkout Session を検証し、支払い済みなら is_premium=true に更新"""
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.InvalidRequestError:
        raise HTTPException(status_code=400, detail="無効なセッションIDです")

    if checkout_session.payment_status != "paid":
        raise HTTPException(
            status_code=400,
            detail="決済が完了していません (status: {})".format(checkout_session.payment_status),
        )

    # metadata の user_id が現在のユーザーと一致するか確認
    meta_user_id = checkout_session.metadata.get("user_id")
    if meta_user_id and str(current_user.id) != meta_user_id:
        raise HTTPException(status_code=403, detail="このセッションは別のユーザーのものです")

    # DB 更新
    current_user.is_premium = True
    if checkout_session.customer:
        current_user.stripe_customer_id = checkout_session.customer
    if checkout_session.subscription:
        current_user.stripe_subscription_id = checkout_session.subscription
    db.commit()

    return {
        "status": "ok",
        "is_premium": True,
        "email": current_user.email,
    }


@router.post("/billing/create-portal-session")
def create_portal_session(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Stripe顧客情報がありません")

    base_url = str(request.base_url).rstrip("/")

    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=f"{base_url}/mypage.html",
    )

    return {"portal_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # If webhook secret is configured, verify signature
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # Development: parse without verification
        import json
        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data_object, db)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data_object, db)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data_object, db)

    return JSONResponse({"status": "ok"})


def _handle_checkout_completed(session: dict, db: Session):
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    user_id = session.get("metadata", {}).get("user_id")

    user = None
    if user_id:
        user = db.query(User).filter(User.id == int(user_id)).first()
    if not user and customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

    if user:
        user.is_premium = True
        user.stripe_customer_id = customer_id
        user.stripe_subscription_id = subscription_id
        db.commit()


def _handle_subscription_updated(subscription: dict, db: Session):
    customer_id = subscription.get("customer")
    sub_status = subscription.get("status")

    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user:
        user.is_premium = sub_status in ("active", "trialing")
        user.stripe_subscription_id = subscription.get("id")
        db.commit()


def _handle_subscription_deleted(subscription: dict, db: Session):
    customer_id = subscription.get("customer")

    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user:
        user.is_premium = False
        user.stripe_subscription_id = None
        db.commit()
