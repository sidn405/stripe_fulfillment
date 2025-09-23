# notifier.py
import os, requests, logging
from typing import List, Dict, Optional
log = logging.getLogger("notifier")

# Try to import your helper. If it explodes or the signature doesn't match,
# we fall back to raw POST with env-provided webhook URLs.
try:
    from stripe_fulfillment.email_sender import send_discord_notification as _core_send
except Exception:
    _core_send = None

def _get_webhook_url(kind: str) -> Optional[str]:
    m = {
        "customer": os.getenv("WEBHOOK_CUSTOMER") or os.getenv("WEBHOOK_URL"),
        "admin":    os.getenv("WEBHOOK_ADMIN") or os.getenv("WEBHOOK_URL") or os.getenv("WEBHOOK_CUSTOMER"),
        "system":   os.getenv("WEBHOOK_SYSTEM") or os.getenv("WEBHOOK_ADMIN") or os.getenv("WEBHOOK_URL") or os.getenv("WEBHOOK_CUSTOMER"),
    }
    return m.get(kind)

def _post_direct(webhook_url: str, title: str, description: str, fields: List[Dict], color: int) -> bool:
    if not webhook_url:
        log.error("No webhook_url provided")
        return False
    payload = {"content": "", "embeds": [{"title": title, "description": description, "fields": fields, "color": color}]}
    r = requests.post(webhook_url, json=payload, timeout=10)
    if not r.ok:
        log.error("Discord POST failed status=%s body=%s", r.status_code, r.text[:200])
    return r.ok

def _send_any(webhook_type: str, title: str, description: str, fields: List[Dict], color: int) -> bool:
    if _core_send:
        try:
            ok = _core_send(webhook_type=webhook_type, title=title, description=description, fields=fields, color=color)
            if isinstance(ok, bool): return ok
        except Exception as e:
            log.warning("Core notifier failed: %s", e)
    return _post_direct(_get_webhook_url(webhook_type), title, description, fields, color)

def send_fulfillment_card(
    *, customer_email: str, deliverables: List[Dict[str, str]], order_id: Optional[str] = None, mode: str = "customer"
) -> bool:
    title = "New Digital Order — Ready to Send"
    desc  = f"Order for **{customer_email or '(unknown)'}**"
    if order_id: desc += f"\nSession/Payment: `{order_id}`"

    lines = [f"Hi {customer_email},", "", "Thanks for your purchase! Here are your downloads:"]
    fields = [{"name": "Customer", "value": customer_email or "(unknown)", "inline": True}]

    for d in deliverables:
        label = d.get("name", "Your Download")
        link  = d.get("direct_link"); attach = d.get("attach_path")
        if link:
            lines.append(f"• **{label}** → {link}")
            fields.append({"name": label, "value": link, "inline": False})
        elif attach:
            lines.append(f"• **{label}** → local file: `{attach}`")
            fields.append({"name": label, "value": f"(local file) {attach}", "inline": False})
        else:
            lines.append(f"• **{label}** → (no link generated)")
            fields.append({"name": label, "value": "(no link)", "inline": False})

    lines += ["", "Links expire in 1 hour. If a link times out, reply and I’ll refresh it.", "Best,\nLead Generator Empire"]
    fields.append({"name": "Customer Email Template", "value": "\n".join(lines), "inline": False})
    return _send_any(mode, title, desc, fields, 3066993)
