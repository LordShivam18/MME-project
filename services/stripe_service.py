"""
Stripe Payment Integration Service
===================================
Encapsulates all Stripe API calls and event processing.
Keeps billing logic separate from route handlers.

Required Environment Variables:
    STRIPE_SECRET_KEY       - Stripe API secret key (sk_test_... or sk_live_...)
    STRIPE_WEBHOOK_SECRET   - Webhook endpoint signing secret (whsec_...)
    STRIPE_PRICE_ID_PRO     - Stripe Price ID for the Pro plan
    FRONTEND_URL            - Frontend base URL for redirect after checkout
"""

import os
import logging
from datetime import datetime, timedelta

import stripe

logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

stripe.api_key = STRIPE_SECRET_KEY


def is_stripe_configured() -> bool:
    """Check if Stripe credentials are set. Allows graceful fallback to simulated billing."""
    return bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET and STRIPE_PRICE_ID_PRO)


# ---------------- CUSTOMER MANAGEMENT ----------------
def get_or_create_customer(email: str, org_id: int, existing_customer_id: str = None) -> str:
    """
    Retrieve existing Stripe customer or create a new one.
    Returns the Stripe customer ID.
    """
    if existing_customer_id:
        try:
            customer = stripe.Customer.retrieve(existing_customer_id)
            if not customer.get("deleted"):
                return customer.id
        except stripe.error.InvalidRequestError:
            logger.warning("Stripe customer %s not found, creating new one", existing_customer_id)

    customer = stripe.Customer.create(
        email=email,
        metadata={"org_id": str(org_id)}
    )
    logger.info("Created Stripe customer: %s for org: %s", customer.id, org_id)
    return customer.id


# ---------------- CHECKOUT SESSION ----------------
def create_checkout_session(customer_id: str, org_id: int) -> dict:
    """
    Create a Stripe Checkout Session for Pro plan subscription.
    Returns session ID and URL for frontend redirect.
    """
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{
            "price": STRIPE_PRICE_ID_PRO,
            "quantity": 1,
        }],
        mode="subscription",
        success_url=f"{FRONTEND_URL}/billing?status=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{FRONTEND_URL}/billing?status=cancelled",
        metadata={
            "org_id": str(org_id),
        },
    )
    logger.info("Created Stripe checkout session: %s for org: %s", session.id, org_id)
    return {
        "session_id": session.id,
        "checkout_url": session.url,
    }


# ---------------- WEBHOOK VERIFICATION ----------------
def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """
    Verify Stripe webhook signature and return the parsed event.
    Raises ValueError on invalid signature.
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
    except stripe.error.SignatureVerificationError as e:
        logger.error("Stripe webhook signature verification failed: %s", str(e))
        raise ValueError("Invalid webhook signature")
    except Exception as e:
        logger.error("Stripe webhook parsing failed: %s", str(e))
        raise ValueError(f"Webhook parsing error: {str(e)}")


# ---------------- EVENT PROCESSORS ----------------
def extract_subscription_data(event: dict) -> dict:
    """
    Extract relevant subscription data from a Stripe event object.
    Returns a dict with normalized fields for DB updates.
    """
    event_type = event["type"]
    data_object = event["data"]["object"]

    result = {
        "event_type": event_type,
        "stripe_subscription_id": None,
        "stripe_customer_id": None,
        "org_id": None,
        "plan_status": None,
        "expiry_date": None,
        "payment_intent_id": None,
        "amount": None,
        "currency": None,
    }

    if event_type == "checkout.session.completed":
        result["stripe_subscription_id"] = data_object.get("subscription")
        result["stripe_customer_id"] = data_object.get("customer")
        result["org_id"] = data_object.get("metadata", {}).get("org_id")
        result["plan_status"] = "active"
        result["payment_intent_id"] = data_object.get("payment_intent")
        result["amount"] = data_object.get("amount_total")
        result["currency"] = data_object.get("currency")

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        result["stripe_subscription_id"] = data_object.get("id")
        result["stripe_customer_id"] = data_object.get("customer")
        result["org_id"] = data_object.get("metadata", {}).get("org_id")
        status = data_object.get("status")
        result["plan_status"] = "active" if status == "active" else "expired"
        # current_period_end is a Unix timestamp
        period_end = data_object.get("current_period_end")
        if period_end:
            result["expiry_date"] = datetime.utcfromtimestamp(period_end)

    elif event_type == "customer.subscription.deleted":
        result["stripe_subscription_id"] = data_object.get("id")
        result["stripe_customer_id"] = data_object.get("customer")
        result["org_id"] = data_object.get("metadata", {}).get("org_id")
        result["plan_status"] = "expired"

    elif event_type == "invoice.payment_failed":
        result["stripe_subscription_id"] = data_object.get("subscription")
        result["stripe_customer_id"] = data_object.get("customer")
        result["org_id"] = data_object.get("metadata", {}).get("org_id")
        result["plan_status"] = "expired"
        result["payment_intent_id"] = data_object.get("payment_intent")
        result["amount"] = data_object.get("amount_due")
        result["currency"] = data_object.get("currency")

    elif event_type == "invoice.payment_succeeded":
        result["stripe_subscription_id"] = data_object.get("subscription")
        result["stripe_customer_id"] = data_object.get("customer")
        result["org_id"] = data_object.get("metadata", {}).get("org_id")
        result["plan_status"] = "active"
        result["payment_intent_id"] = data_object.get("payment_intent")
        result["amount"] = data_object.get("amount_paid")
        result["currency"] = data_object.get("currency")
        period_end = data_object.get("lines", {}).get("data", [{}])[0].get("period", {}).get("end")
        if period_end:
            result["expiry_date"] = datetime.utcfromtimestamp(period_end)

    return result
