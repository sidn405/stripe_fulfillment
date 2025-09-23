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
    """Create branded HTML email content matching Lead Generator Empire theme"""
    
    # Build download links
    download_links = []
    for i, d in enumerate(deliverables, 1):
        name = d.get("name", "Your Download")
        link = d.get("direct_link")
        if link:
            download_links.append(f'''
            <tr>
                <td style="padding: 20px; border-bottom: 1px solid #2d3748;">
                    <div style="display: flex; align-items: center;">
                        <div style="background: linear-gradient(135deg, #BF9940 0%, #ed8936 100%); color: #1a202c; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 20px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 12px rgba(246, 173, 85, 0.4);">{i}</div>
                        <div style="flex: 1;">
                            <div style="font-weight: 700; margin-bottom: 8px; color: #e2e8f0; font-size: 18px;">{name}</div>
                            <a href="{link}" style="background: linear-gradient(135deg, #BF9940 0%, #ed8936 100%); color: #1a202c; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-size: 14px; display: inline-block; font-weight: 600; box-shadow: 0 4px 12px rgba(246, 173, 85, 0.3); transition: all 0.3s ease;">👑 Download Now</a>
                        </div>
                    </div>
                </td>
            </tr>
            ''')
    
    downloads_html = "\n".join(download_links) if download_links else '<tr><td style="padding: 20px; text-align: center; color: #a0aec0;">No downloads available</td></tr>'
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Your Digital Downloads - Lead Generator Empire</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        </style>
    </head>
    <body style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #e2e8f0; margin: 0; padding: 0; background-color: #0f1419;">
        <div style="max-width: 600px; margin: 0 auto; background: #1a202c; box-shadow: 0 20px 40px rgba(0,0,0,0.3);">
            
            <!-- Header with Crown Logo -->
            <div style="background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%); padding: 40px 30px; text-align: center; border-bottom: 3px solid #BF9940;">
                <div style="margin-bottom: 20px;">
                    <!-- Logo from Railway static files -->
                    <img src="https://stripefulfillment-production.up.railway.app/static/logo.png" alt="Lead Generator Empire Logo" style="max-height: 80px; max-width: 200px; height: auto; margin-bottom: 15px;" />
                    <!-- Fallback Crown if logo doesn't load -->
                    <div style="display: none; background: linear-gradient(135deg, #BF9940 0%, #ed8936 100%); width: 80px; height: 80px; border-radius: 50%; align-items: center; justify-content: center; margin-bottom: 15px; box-shadow: 0 8px 24px rgba(246, 173, 85, 0.4);">
                        <span style="font-size: 40px;">👑</span>
                    </div>
                </div>
                <h1 style="color: #BF9940; margin: 0; font-size: 32px; font-weight: 700; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">Your Downloads Are Ready!</h1>
                <p style="color: #a0aec0; margin: 15px 0 0 0; font-size: 18px; font-weight: 400;">Lead Generator Empire</p>
            </div>
            
            <!-- Content -->
            <div style="padding: 40px 30px; background: #1a202c;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h2 style="color: #BF9940; font-size: 24px; margin: 0 0 10px 0; font-weight: 700;">Hi there!</h2>
                    <p style="color: #cbd5e0; font-size: 16px; margin: 0; line-height: 1.6;">Thank you for your purchase! Your premium lead packages are ready for download.</p>
                </div>
                
                <p style="margin-bottom: 30px; color: #a0aec0; line-height: 1.6; font-size: 16px;">Your digital downloads are ready and waiting for you. Click the download buttons below to get your files:</p>
                
                <!-- Downloads Table -->
                <div style="border: 2px solid #2d3748; border-radius: 12px; overflow: hidden; margin: 30px 0; background: #2d3748;">
                    <div style="background: linear-gradient(135deg, #BF9940 0%, #ed8936 100%); padding: 20px; text-align: center;">
                        <h3 style="margin: 0; color: #1a202c; font-size: 20px; font-weight: 700;">📦 Your Premium Downloads</h3>
                    </div>
                    <table style="width: 100%; border-collapse: collapse; background: #1a202c;">
                        {downloads_html}
                    </table>
                </div>
                
                <!-- Important Notice -->
                <div style="background: linear-gradient(135deg, #742a2a 0%, #9c4221 100%); border: 2px solid #f56565; border-radius: 12px; padding: 25px; margin: 30px 0;">
                    <div style="display: flex; align-items: flex-start;">
                        <div style="color: #feb2b2; font-size: 24px; margin-right: 15px;">⚠️</div>
                        <div>
                            <p style="margin: 0 0 8px 0; color: #feb2b2; font-weight: 700; font-size: 18px;">Security Notice</p>
                            <p style="margin: 0; color: #fed7d7; font-size: 14px; line-height: 1.5;">Download links expire in 1 hour for your security and to prevent unauthorized access. Please download your files promptly.</p>
                        </div>
                    </div>
                </div>
                
                <!-- Empire Stats Box -->
                <div style="background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%); border-radius: 12px; padding: 25px; margin: 30px 0; border: 1px solid #BF9940;">
                    <div style="text-align: center;">
                        <h3 style="color: #BF9940; margin: 0 0 15px 0; font-size: 18px; font-weight: 700;">🏆 Empire Stats</h3>
                        <div style="display: flex; justify-content: space-around; text-align: center;">
                            <div>
                                <div style="color: #BF9940; font-size: 24px; font-weight: 700;">8</div>
                                <div style="color: #a0aec0; font-size: 12px;">Platforms</div>
                            </div>
                            <div>
                                <div style="color: #BF9940; font-size: 24px; font-weight: 700;">12+</div>
                                <div style="color: #a0aec0; font-size: 12px;">Languages</div>
                            </div>
                            <div>
                                <div style="color: #BF9940; font-size: 24px; font-weight: 700;">1M+</div>
                                <div style="color: #a0aec0; font-size: 12px;">Leads</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Order Info -->
                <div style="text-align: center; margin: 30px 0; padding: 20px; background: #2d3748; border-radius: 8px; border-left: 4px solid #BF9940;">
                    <p style="color: #a0aec0; font-size: 14px; margin: 0;">Order ID: <span style="color: #BF9940; font-weight: 600;">{order_id or 'N/A'}</span></p>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background: linear-gradient(135deg, #0f1419 0%, #1a202c 100%); color: #a0aec0; padding: 30px; text-align: center; border-top: 2px solid #BF9940;">
                <div style="margin-bottom: 15px;">
                    <img src="https://stripefulfillment-production.up.railway.app/static/logo.png" alt="Lead Generator Empire" style="max-height: 40px; max-width: 150px; height: auto;" />
                </div>
                <p style="margin: 0 0 15px 0; font-size: 18px; font-weight: 700; color: #BF9940;">Lead Generator Empire</p>
                <p style="margin: 0 0 20px 0; color: #cbd5e0; font-size: 14px;">Generate Quality Leads • 8 Platforms • 12+ Languages</p>
                <hr style="border: none; border-top: 1px solid #4a5568; margin: 20px 0;">
                <p style="margin: 0; color: #a0aec0; font-size: 14px;">Questions? Reply to this email - we're here to help!</p>
                <p style="margin: 10px 0 0 0; color: #718096; font-size: 12px;">Lead Generator Empire | Secure & Private</p>
            </div>
        </div>
    </body>
    </html>
    """