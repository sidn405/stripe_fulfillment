# email_sender.py - HTTP-based email (works on Railway)
import os, requests, logging
from typing import List, Dict, Optional

log = logging.getLogger("email_sender")

# Email service configuration
EMAIL_SERVICE = os.getenv("EMAIL_SERVICE", "resend")  # resend, sendgrid, or mailgun
API_KEY = os.getenv("EMAIL_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")
FROM_NAME = os.getenv("FROM_NAME", "Lead Generator Empire")

def send_customer_email(
    customer_email: str, 
    deliverables: List[Dict], 
    order_id: Optional[str] = None
) -> bool:
    """Send email using HTTP API (Railway compatible)"""
    
    if not API_KEY or not FROM_EMAIL:
        log.error("Email not configured - missing API_KEY or FROM_EMAIL")
        return False
    
    html_content = create_email_html(customer_email, deliverables, order_id)
    subject = f"Your Digital Downloads - Order {order_id or 'Confirmed'}"
    
    # Choose email service
    if EMAIL_SERVICE == "resend":
        return send_via_resend(customer_email, subject, html_content)
    elif EMAIL_SERVICE == "sendgrid":
        return send_via_sendgrid(customer_email, subject, html_content)
    elif EMAIL_SERVICE == "mailgun":
        return send_via_mailgun(customer_email, subject, html_content)
    else:
        log.error("Unknown email service: %s", EMAIL_SERVICE)
        return False

def send_via_resend(to_email: str, subject: str, html_content: str) -> bool:
    """Send via Resend API (recommended - simple and reliable)"""
    try:
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "from": f"{FROM_NAME} <{FROM_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            log.info("✅ Email sent via Resend to %s", to_email)
            return True
        else:
            log.error("❌ Resend API error %s: %s", response.status_code, response.text)
            return False
            
    except Exception as e:
        log.error("❌ Resend email failed: %s", e)
        return False

def send_via_sendgrid(to_email: str, subject: str, html_content: str) -> bool:
    """Send via SendGrid API"""
    try:
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "personalizations": [{
                "to": [{"email": to_email}],
                "subject": subject
            }],
            "from": {"email": FROM_EMAIL, "name": FROM_NAME},
            "content": [{"type": "text/html", "value": html_content}]
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 202:
            log.info("✅ Email sent via SendGrid to %s", to_email)
            return True
        else:
            log.error("❌ SendGrid API error %s: %s", response.status_code, response.text)
            return False
            
    except Exception as e:
        log.error("❌ SendGrid email failed: %s", e)
        return False

def send_via_mailgun(to_email: str, subject: str, html_content: str) -> bool:
    """Send via Mailgun API"""
    try:
        domain = os.getenv("MAILGUN_DOMAIN", "")
        if not domain:
            log.error("MAILGUN_DOMAIN not set")
            return False
            
        url = f"https://api.mailgun.net/v3/{domain}/messages"
        auth = ("api", API_KEY)
        data = {
            "from": f"{FROM_NAME} <{FROM_EMAIL}>",
            "to": to_email,
            "subject": subject,
            "html": html_content
        }
        
        response = requests.post(url, auth=auth, data=data, timeout=30)
        
        if response.status_code == 200:
            log.info("✅ Email sent via Mailgun to %s", to_email)
            return True
        else:
            log.error("❌ Mailgun API error %s: %s", response.status_code, response.text)
            return False
            
    except Exception as e:
        log.error("❌ Mailgun email failed: %s", e)
        return False

def create_email_html(customer_email: str, deliverables: List[Dict], order_id: Optional[str]) -> str:
    """Create beautiful HTML email content"""
    
    # Build download links
    download_links = []
    for i, d in enumerate(deliverables, 1):
        name = d.get("name", "Your Download")
        link = d.get("direct_link")
        if link:
            download_links.append(f'''
            <tr>
                <td style="padding: 15px; border-bottom: 1px solid #e9ecef;">
                    <div style="display: flex; align-items: center;">
                        <div style="background: #007cba; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-weight: bold; font-size: 14px;">{i}</div>
                        <div>
                            <div style="font-weight: bold; margin-bottom: 5px;">{name}</div>
                            <a href="{link}" style="background: #007cba; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; font-size: 14px; display: inline-block;">Download Now</a>
                        </div>
                    </div>
                </td>
            </tr>
            ''')
    
    downloads_html = "\n".join(download_links) if download_links else '<tr><td style="padding: 15px; text-align: center; color: #6c757d;">No downloads available</td></tr>'
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Your Digital Downloads</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f8f9fa;">
        <div style="max-width: 600px; margin: 0 auto; background: white;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 600;">🎉 Your Downloads Are Ready!</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0; font-size: 16px;">Thank you for your purchase</p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                <p style="font-size: 18px; margin-bottom: 25px; color: #2c3e50;">Hi there!</p>
                
                <p style="margin-bottom: 30px; color: #5a6c7d; line-height: 1.6;">Your digital downloads are ready and waiting for you. Click the download buttons below to get your files:</p>
                
                <!-- Downloads Table -->
                <div style="border: 1px solid #e9ecef; border-radius: 8px; overflow: hidden; margin: 25px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        {downloads_html}
                    </table>
                </div>
                
                <!-- Important Notice -->
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px; padding: 20px; margin: 25px 0;">
                    <div style="display: flex; align-items: flex-start;">
                        <div style="color: #856404; font-size: 20px; margin-right: 10px;">⚠️</div>
                        <div>
                            <p style="margin: 0; color: #856404; font-weight: 600;">Important Security Notice</p>
                            <p style="margin: 5px 0 0 0; color: #856404; font-size: 14px;">Download links expire in 1 hour for your security. Please download your files promptly.</p>
                        </div>
                    </div>
                </div>
                
                <!-- Order Info -->
                <div style="text-align: center; margin: 30px 0; padding: 20px; background: #f8f9fa; border-radius: 6px;">
                    <p style="color: #6c757d; font-size: 14px; margin: 0;">Order ID: <strong>{order_id or 'N/A'}</strong></p>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background: #2c3e50; color: white; padding: 25px 30px; text-align: center;">
                <p style="margin: 0 0 10px 0; font-size: 16px; font-weight: 600;">{FROM_NAME}</p>
                <p style="margin: 0; color: rgba(255,255,255,0.8); font-size: 14px;">Questions? Reply to this email - we're here to help!</p>
            </div>
        </div>
    </body>
    </html>
    """