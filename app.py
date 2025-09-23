import os, json, logging, requests
from typing import Dict, Any
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from dotenv import load_dotenv
import stripe
from discord_notification_system import send_discord_notification
from products_config import PRODUCTS, ATTACHMENT_SIZE_LIMIT
from token_links import make_signed_link, verify_token
from notifier import send_fulfillment_card
import os, logging

load_dotenv()

# --- Config ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_API_KEY", "")                 # safe
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")   # safe
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

DELIVERY_FROM_NAME = os.environ.get("DELIVERY_FROM_NAME", "Your Store")
BRAND_FOOTER = os.environ.get("BRAND_FOOTER", "Thanks for your purchase!")

stripe.api_key = STRIPE_SECRET_KEY or None  # ok if None at boot


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stripe-fulfillment")

app = FastAPI(title="Stripe Digital Delivery")

# Simple in-memory idempotency (replace with Redis/DB in prod)
SEEN_EVENTS = set()

@app.get("/")
def health():
    return {"ok": True, "service": "Stripe Digital Delivery"}

@app.get("/_debug/discord/env")
def debug_env():
    def L(s): return len(s) if s else 0
    return {
        "WEBHOOK_CUSTOMER_set": bool(os.getenv("WEBHOOK_CUSTOMER")),
        "WEBHOOK_URL_set": bool(os.getenv("WEBHOOK_URL")),
        "chosen": "WEBHOOK_CUSTOMER" if os.getenv("WEBHOOK_CUSTOMER") else ("WEBHOOK_URL" if os.getenv("WEBHOOK_URL") else "none"),
        "lengths": {"customer": L(os.getenv("WEBHOOK_CUSTOMER")), "url": L(os.getenv("WEBHOOK_URL"))},
    }

@app.get("/_debug/discord")  # sends a real test card via your notifier
def debug_discord():
    ok = send_fulfillment_card(
        customer_email="test@example.com",
        deliverables=[{"name":"Test Pack","direct_link":"https://example.com"}],
        order_id="debug",
        mode="customer",
    )
    log.info("DEBUG notifier sent=%s", ok)
    return {"notifier_ok": ok}

@app.get("/_debug/inspect/{cs_id}")
def inspect_session(cs_id: str):
    cs = stripe.checkout.Session.retrieve(
        cs_id, expand=["line_items.data.price.product"]
    )
    items = []
    for li in cs.get("line_items", {}).get("data", []):
        p = li.get("price")
        price_id = p if isinstance(p, str) else (p.get("id") if p else None)
        prod = (p.get("product") if isinstance(p, dict) else None)
        product_id = prod if isinstance(prod, str) else (prod.get("id") if isinstance(prod, dict) else None)
        items.append({"price_id": price_id, "product_id": product_id, "qty": li.get("quantity", 1)})
    return {"session": cs.get("id"), "items": items}

# optional: raw POST ping straight to the webhook URL in case the notifier is the issue
@app.get("/_debug/discord/ping")
def debug_discord_ping():
    url = os.getenv("WEBHOOK_CUSTOMER") or os.getenv("WEBHOOK_URL")
    if not url: return {"ok": False, "error": "no webhook env set"}
    r = requests.post(url, json={"content": "hello from app (_debug/discord/ping) 🔔"}, timeout=10)
    log.info("DEBUG direct POST status=%s body=%s", r.status_code, r.text[:120])
    return {"ok": r.ok, "status": r.status_code}
    
@app.get("/_debug/stripe")
def debug_stripe():
    try:
        stripe.Price.list(limit=1)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    
@app.get("/_debug/test-fulfillment/{price_id}")
def debug_test_fulfillment(price_id: str):
    """Test fulfillment for a specific price ID"""
    
    # Test product lookup
    deliverable = PRODUCTS.get(price_id)
    log.info("=== FULFILLMENT DEBUG ===")
    log.info("Testing price_id: %s", price_id)
    log.info("Found deliverable: %s", deliverable)
    log.info("All PRODUCTS keys: %s", list(PRODUCTS.keys()))
    
    if not deliverable:
        return {
            "error": "Price ID not found",
            "price_id": price_id,
            "available_ids": list(PRODUCTS.keys())
        }
    
    # Test Discord notification
    test_email = "debug@test.com"
    enriched = [{
        "name": deliverable.get("name", "Test Item"),
        "direct_link": deliverable.get("direct_link") or deliverable.get("url"),  # Check both fields
    }]
    
    log.info("Sending test notification with: %s", enriched)
    
    try:
        ok = send_fulfillment_card(
            customer_email=test_email,
            deliverables=enriched,
            order_id="debug-test",
            mode="customer"
        )
        
        return {
            "success": ok,
            "price_id": price_id,
            "deliverable": deliverable,
            "enriched": enriched,
            "discord_sent": ok
        }
    except Exception as e:
        log.exception("Debug fulfillment failed")
        return {
            "error": str(e),
            "price_id": price_id,
            "deliverable": deliverable
        }


def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return None

def notify_admin_unmapped(event, product_ids, customer_email):
    try:
        fields = [
            {"name": "Customer", "value": customer_email or "(unknown)", "inline": True},
            {"name": "IDs from event", "value": ", ".join(product_ids) or "(none)", "inline": False},
            {"name": "Event type", "value": event.get("type",""), "inline": True},
            {"name": "Event id",   "value": event.get("id",""), "inline": True},
        ]
        send_discord_notification(
            webhook_type="admin",   # uses WEBHOOK_ADMIN; falls back if your helper supports it
            title="Stripe IDs not mapped",
            description="Add these IDs to PRODUCTS in products_config.py",
            fields=fields,
            color=15158332  # red-ish
        )
    except Exception:
        log.exception("Failed to notify admin of unmapped IDs")


def extract_product_ids(event) -> list[str]:
    try:
        obj = event.get("data", {}).get("object", {}) if isinstance(event, dict) else {}
        cs_id = obj.get("id")
        if not cs_id:
            return []
        cs = stripe.checkout.Session.retrieve(
            cs_id, expand=["line_items.data.price.product"]
        )
        ids = []
        for li in cs.get("line_items", {}).get("data", []):
            price = li.get("price")
            # price can be a string id OR an object
            if isinstance(price, str):
                ids.append(price)
            elif isinstance(price, dict):
                if price.get("id"):
                    ids.append(price["id"])
                prod = price.get("product")
                if isinstance(prod, str):
                    ids.append(prod)
                elif isinstance(prod, dict) and prod.get("id"):
                    ids.append(prod["id"])
        return list({i for i in ids if i})  # unique, non-empty
    except Exception as e:
        log.exception("Unable to expand line_items: %s", e)
        return []

def pick_deliverables(product_ids):
    """
    From incoming Stripe IDs, pick configured deliverables.
    Returns a list of dicts {name, path?, url?}
    """
    out = []
    for pid in product_ids:
        conf = PRODUCTS.get(pid)
        if conf:
            out.append(conf)
    return out

def format_email_body(customer_email: str, deliverables):
    items_html = []
    for d in deliverables:
        label = d.get("name", "Your Download")
        if d.get("direct_link"):
            items_html.append(f"<li><strong>{label}</strong>: <a href='{d['direct_link']}'>Download link (1 hour)</a></li>")
        else:
            items_html.append(f"<li><strong>{label}</strong>: attached to this email</li>")
    items = "\n".join(items_html)
    return f"""
    <div style="font-family:system-ui, -apple-system, Segoe UI, Roboto, Arial;">
      <h2>{DELIVERY_FROM_NAME} — Your Downloads</h2>
      <p>Hi {customer_email}, thanks for your purchase. Your downloads are below:</p>
      <ul>{items}</ul>
      <p style="margin-top:24px;color:#666">{BRAND_FOOTER}</p>
    </div>
    """

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_id = event.get("id")
    if event_id in SEEN_EVENTS:
        return JSONResponse({"ok": True, "idempotent": True})
    SEEN_EVENTS.add(event_id)

    event_type = event.get("type")
    log.info(f"▶️ Stripe event: {event_type}")

    # Handle after successful checkout
    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        obj = event["data"]["object"]
        
        # DEBUG: Log the full object
        log.info("=== DEBUG: Full event object ===")
        log.info("Event ID: %s", event_id)
        log.info("Event type: %s", event_type)
        log.info("Object keys: %s", list(obj.keys()))

        customer_email = _first_nonempty(
            obj.get("customer_details", {}).get("email"),
            obj.get("receipt_email"),
            obj.get("charges", {}).get("data", [{}])[0].get("billing_details", {}).get("email") if obj.get("charges") else None,
            obj.get("customer_email"),
        )
        
        # DEBUG: Log email extraction
        log.info("=== DEBUG: Customer email extraction ===")
        log.info("customer_details.email: %s", obj.get("customer_details", {}).get("email"))
        log.info("receipt_email: %s", obj.get("receipt_email"))
        log.info("customer_email: %s", obj.get("customer_email"))
        log.info("Final customer_email: %s", customer_email)
        
        if not customer_email:
            log.warning("No customer email found; skipping.")
            return JSONResponse({"ok": True, "note": "no customer email"})

        # DEBUG: Product ID extraction
        log.info("=== DEBUG: Product ID extraction ===")
        product_ids = extract_product_ids(event)
        log.info("Extracted product IDs: %s", product_ids)
        
        deliverables = pick_deliverables(product_ids)
        log.info("=== DEBUG: Deliverables mapping ===")
        log.info("Mapped deliverables: %s", deliverables)
        log.info("Available PRODUCTS keys: %s", list(PRODUCTS.keys()))
        
        if not deliverables:
            log.warning(f"No configured deliverables for IDs: {product_ids}")
            # Send admin notification for unmapped IDs
            notify_admin_unmapped(event, product_ids, customer_email)
            return JSONResponse({"ok": True, "note": "no deliverables matched"})

        # Build email plan: attach small files, generate links for big or remote URLs
        enriched = []
        for d in deliverables:
            name = d.get("name", "Your Download")
            path = d.get("path")
            url  = d.get("url")
            item = {"name": name}

            if url:
                # Never attach; send signed redirect link to this URL
                link = make_signed_link(APP_BASE_URL, customer_email, name, None, url, ttl_seconds=3600)
                item["direct_link"] = link
            elif path:
                p = Path(path)
                if not p.exists():
                    log.error(f"File missing: {p}")
                    item["error"] = f"missing file: {p}"
                else:
                    if p.stat().st_size <= ATTACHMENT_SIZE_LIMIT:
                        item["attach_path"] = str(p)
                    else:
                        link = make_signed_link(APP_BASE_URL, customer_email, name, str(p), None, ttl_seconds=3600)
                        item["direct_link"] = link
            enriched.append(item)

        # DEBUG: Log enriched deliverables
        log.info("=== DEBUG: Enriched deliverables ===")
        log.info("Enriched items: %s", enriched)

        # Send Discord notification
        try:
            log.info("=== DEBUG: Sending Discord notification ===")
            ok = send_fulfillment_card(
                customer_email=customer_email,
                deliverables=enriched,
                order_id=obj.get("id") or obj.get("payment_intent"),
                mode="customer"
            )
            log.info("Discord fulfillment sent=%s items=%d", ok, len(deliverables))
            
            if not ok:
                log.error("❌ Discord notification failed")
                # Try sending a simple test message to verify webhook works
                log.info("Attempting fallback Discord test...")
                try:
                    import requests
                    webhook_url = os.getenv("WEBHOOK_CUSTOMER") or os.getenv("WEBHOOK_URL")
                    if webhook_url:
                        test_payload = {
                            "content": f"🚨 Fulfillment failed for {customer_email} - order {obj.get('id')}"
                        }
                        r = requests.post(webhook_url, json=test_payload, timeout=10)
                        log.info("Fallback message status: %s", r.status_code)
                except Exception as e:
                    log.error("Fallback message also failed: %s", e)
            else:
                log.info("✅ Discord notification sent successfully")
                
        except Exception as e:
            log.exception("Discord notification failed with exception")
            raise HTTPException(status_code=500, detail=f"Notification error: {e}")

    else:
        log.info("Event type %s not handled", event_type)

    return JSONResponse({"ok": True})

@app.get("/download/{token}")
async def download_with_token(token: str):
    try:
        data = verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired link")

    # Prefer file_url (remote) else serve local file
    file_url = data.get("u")
    file_path = data.get("p")
    label = data.get("f", "Your Download")

    if file_url:
        # Simple HTML redirect so the user sees a branded page
        return HTMLResponse(f"""
        <html><head><meta http-equiv="refresh" content="0; url={file_url}"></head>
        <body><p>Redirecting to download <strong>{label}</strong>...</p></body></html>
        """)
    elif file_path:
        p = Path(file_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path=str(p), filename=p.name, media_type="application/octet-stream")
    else:
        raise HTTPException(status_code=400, detail="No file configured")

@app.get("/")
async def root():
    return {"ok": True, "service": "Stripe Digital Delivery"}
