
from io import BytesIO
from PIL import Image
import numpy as np
import qrcode
import streamlit as st
import os
from urllib.parse import urlsplit, urlunsplit


def get_image_bytes(pil_img):
    out = BytesIO()
    pil_img.save(out, format="JPEG", quality=90)
    return out.getvalue()


def image_bytes_preview(data, max_side=700):
    img = Image.open(BytesIO(data)).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = BytesIO()
    img.save(out, format="JPEG", quality=80)
    return out.getvalue()


def resized_rgb_array(data, max_side=1000):
    img = Image.open(BytesIO(data)).convert("RGB")
    img.thumbnail((max_side, max_side))
    return np.asarray(img)


def make_guest_url():
    """
    Return the permanent guest URL for the deployed Streamlit app.
    Admin access is handled on the same page by password authentication.
    """

    try:
        base = st.secrets.get("GUEST_URL", "")
    except Exception:
        base = os.getenv("GUEST_URL", "")

    if not base:
        base = "http://localhost:8501"

    base = base.strip()

    if not base.startswith(("https://", "http://")):
        base = "https://" + base

    parsed = urlsplit(base)

    # Remove old query parameters such as ?mode=admin or ?mode=guest.
    clean_url = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )

    return clean_url


def make_qr(url):
    img = qrcode.make(url)
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out
