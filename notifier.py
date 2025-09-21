# notifier.py
from typing import List, Dict, Optional
from discord_notification_system import send_discord_notification  # your helper

def send_fulfillment_card(
    *,
    customer_email: str,
    deliverables: List[Dict[str, str]],
    order_id: Optional[str] = None,
    mode: str = "customer"
) -> bool:
    """
    Post a fulfillment card to Discord with per-item links and a ready-to-paste
    customer email message.
    """
    title = "New Digital Order — Ready to Send"
    desc  = f"Order for **{customer_email}**"
    if order_id:
        desc += f"\nSession/Payment: `{order_id}`"

    # Build a ready-to-paste message
    lines = [
        f"Hi {customer_email},",
        "",
        "Thanks for your purchase! Here are your downloads:",
    ]
    fields = [{"name": "Customer", "value": customer_email, "inline": True}]

    for d in deliverables:
        label = d.get("name", "Your Download")
        link  = d.get("direct_link")
        attach = d.get("attach_path")
        if link:
            lines.append(f"• **{label}** → {link}")
            fields.append({"name": label, "value": link, "inline": False})
        elif attach:
            lines.append(f"• **{label}** → local file: `{attach}`")
            fields.append({"name": label, "value": f"(local file) {attach}", "inline": False})
        else:
            lines.append(f"• **{label}** → (no link generated)")
            fields.append({"name": label, "value": "(no link)", "inline": False})

    lines += [
        "",
        "Links expire in 1 hour. If a link times out, reply and I’ll refresh it.",
        "Best,\nLead Generator Empire",
    ]
    customer_template = "\n".join(lines)
    fields.append({"name": "Customer Email Template", "value": customer_template, "inline": False})

    return send_discord_notification(
        webhook_type=mode,  # "customer" / "admin" / "system"
        title=title,
        description=desc,
        fields=fields,
        color=3066993
    )
