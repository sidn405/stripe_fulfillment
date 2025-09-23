from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os, json, logging, requests
from typing import Dict, Any
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from dotenv import load_dotenv
import stripe
from products_config import PRODUCTS, ATTACHMENT_SIZE_LIMIT
from token_links import make_signed_link, verify_token
from email_sender import send_customer_email  # Only email, no Discord

load_dotenv()

# --- Config ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

stripe.api_key = STRIPE_SECRET_KEY or None

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("stripe-fulfillment")

app = FastAPI(title="Stripe Digital Delivery")

# Create static directory if it doesn't exist
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
# Simple in-memory idempotency (replace with Redis/DB in prod)
SEEN_EVENTS = set()

@app.get("/")
def health():
    return {"ok": True, "service": "Stripe Digital Delivery"}

@app.get("/_debug/email")
def debug_email():
    """Test email functionality"""
    try:
        ok = send_customer_email(
            customer_email="test@example.com",
            deliverables=[{
                "name": "Test Download",
                "direct_link": "https://example.com/download"
            }],
            order_id="debug-test"
        )
        return {"email_sent": ok, "message": "Check logs for details"}
    except Exception as e:
        log.exception("Debug email failed")
        return {"email_sent": False, "error": str(e)}

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

def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return None

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
    """From incoming Stripe IDs, pick configured deliverables."""
    out = []
    for pid in product_ids:
        conf = PRODUCTS.get(pid)
        if conf:
            out.append(conf)
    return out

def deduplicate_deliverables(deliverables):
    """Remove duplicate deliverables based on name and URL"""
    seen = set()
    unique_deliverables = []
    
    for d in deliverables:
        # Create a unique key based on name and URL
        key = (d.get("name", ""), d.get("url", ""))
        if key not in seen:
            seen.add(key)
            unique_deliverables.append(d)
    
    return unique_deliverables

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

    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        obj = event["data"]["object"]

        customer_email = _first_nonempty(
            obj.get("customer_details", {}).get("email"),
            obj.get("receipt_email"),
            obj.get("charges", {}).get("data", [{}])[0].get("billing_details", {}).get("email") if obj.get("charges") else None,
            obj.get("customer_email"),
        )
        
        if not customer_email:
            log.warning("No customer email found; skipping.")
            return JSONResponse({"ok": True, "note": "no customer email"})

        product_ids = extract_product_ids(event)
        deliverables = pick_deliverables(product_ids)
        
        # 🔥 DEDUPLICATE DELIVERABLES HERE
        deliverables = deduplicate_deliverables(deliverables)
        
        log.info("Product IDs found: %s", product_ids)
        log.info("Unique deliverables after dedup: %s", [d.get("name") for d in deliverables])
        
        if not deliverables:
            log.warning(f"No configured deliverables for IDs: {product_ids}")
            return JSONResponse({"ok": True, "note": "no deliverables matched"})

        # Build download links
        enriched = []
        for d in deliverables:
            name = d.get("name", "Your Download")
            url = d.get("url")
            
            if url:
                link = make_signed_link(APP_BASE_URL, customer_email, name, None, url, ttl_seconds=3600)
                enriched.append({
                    "name": name,
                    "direct_link": link
                })
            else:
                log.warning(f"No URL configured for {name}")

        order_id = obj.get("id") or obj.get("payment_intent")

        # Send customer email
        try:
            email_sent = send_customer_email(
                customer_email=customer_email,
                deliverables=enriched,
                order_id=order_id
            )
            
            if email_sent:
                log.info("✅ Email sent successfully to %s with %d unique items", customer_email, len(enriched))
                return JSONResponse({
                    "ok": True, 
                    "email_sent": True,
                    "customer": customer_email,
                    "items": len(enriched)
                })
            else:
                log.error("❌ Failed to send email to %s", customer_email)
                raise HTTPException(status_code=500, detail="Email delivery failed")
                
        except Exception as e:
            log.exception("Email sending failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Email error: {e}")

    return JSONResponse({"ok": True})

@app.get("/download/{token}")
async def download_with_token(token: str):
    try:
        data = verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired link")

    file_url = data.get("u")
    label = data.get("f", "Your Download")

    if file_url:
        return HTMLResponse(f"""
        <html><head><meta http-equiv="refresh" content="0; url={file_url}"></head>
        <body><p>Redirecting to download <strong>{label}</strong>...</p></body></html>
        """)
    else:
        raise HTTPException(status_code=400, detail="No file configured")