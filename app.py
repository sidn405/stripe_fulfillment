import os, json, logging
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

def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return None

def extract_product_ids(event: Dict[str, Any]):
    """
    Return a list of price/product IDs from the checkout session or line items.
    Works for Checkout and PaymentIntent events.
    """
    obj = event.get("data", {}).get("object", {})
    product_ids = []

    # Checkout session path
    if obj.get("object") == "checkout.session":
        cs = obj
        # Expand line items if not present
        if "line_items" not in cs:
            try:
                cs = stripe.checkout.Session.retrieve(cs["id"], expand=["line_items.data.price.product"])
            except Exception as e:
                log.exception("Unable to expand line_items")
        for item in cs.get("line_items", {}).get("data", []):
            price = item.get("price", {})
            price_id = price.get("id")
            product = price.get("product")
            if price_id:
                product_ids.append(price_id)
            if product and isinstance(product, dict) and product.get("id"):
                product_ids.append(product["id"])

    # PaymentIntent (fallback)
    if obj.get("object") == "payment_intent":
        pi = obj
        # If PI originated from Checkout, the session event will be more reliable; keep this as backup
        if "latest_charge" in pi:
            pass
        # You could expand associated invoice/lines here if needed

    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for pid in product_ids:
        if pid not in seen:
            uniq.append(pid)
            seen.add(pid)
    return uniq

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
    log.info(f"▶︎ Stripe event: {event_type}")

    # Handle after successful checkout
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
        if not deliverables:
            log.warning(f"No configured deliverables for IDs: {product_ids}")
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
                    # Fall back to link if you mount files at /static; else skip
                    item["error"] = f"missing file: {p}"
                else:
                    if p.stat().st_size <= ATTACHMENT_SIZE_LIMIT:
                        item["attach_path"] = str(p)
                    else:
                        # Too big—issue a signed link to our own download endpoint
                        link = make_signed_link(APP_BASE_URL, customer_email, name, str(p), None, ttl_seconds=3600)
                        item["direct_link"] = link
            enriched.append(item)

        # Compose & send
        html = format_email_body(customer_email, enriched)
        # If any item uses attachments, attach the first one only? Or multiple:
        # We'll attach up to 3 to keep emails light; rest via links.
        attachments = [i["attach_path"] for i in enriched if "attach_path" in i][:3]
        try:
            if attachments:
                # Send one email; if multiple attachments, zip beforehand in future enhancement
                # Here: attach first file only to avoid provider limits; rest use links
                first = attachments[0]
                # Convert the others to links if needed
                # (Already handled above; keeping implementation simple)
                ok = send_fulfillment_card(
                    customer_email=customer_email,
                    deliverables=enriched,
                    order_id=obj.get("id") or obj.get("payment_intent"),
                    mode="customer"   # posts to WEBHOOK_CUSTOMER
                )
                if not ok:
                    log.error("Discord notification failed")
        except Exception as e:
            log.exception("Email sending failed")
            raise HTTPException(status_code=500, detail=f"Email error: {e}")

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
