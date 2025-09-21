# token_links.py
import os, time
from itsdangerous import URLSafeSerializer

SECRET = os.environ.get("DOWNLOAD_TOKEN_SECRET", "change-this-secret")
_signer = URLSafeSerializer(SECRET, salt="dl")

def make_signed_link(base_url: str, customer_email: str, file_label: str,
                     file_path: str | None, file_url: str | None, ttl_seconds: int = 3600) -> str:
    payload = {
        "e": (customer_email or "").lower().strip(),
        "f": file_label,
        "p": file_path,
        "u": file_url,
        "exp": int(time.time()) + ttl_seconds,
    }
    token = _signer.dumps(payload)
    return f"{base_url.rstrip('/')}/download/{token}"

def verify_token(token: str) -> dict:
    data = _signer.loads(token)
    if data.get("exp", 0) < time.time():
        raise ValueError("Expired")
    return data
