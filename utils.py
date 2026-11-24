
from io import BytesIO

from PIL import Image
import numpy as np
import qrcode
import streamlit as st


# ==========================================================
# IMAGE HELPERS
# ==========================================================

def get_image_bytes(pil_img):

    out = BytesIO()

    pil_img.save(
        out,
        format="JPEG",
        quality=90
    )

    return out.getvalue()


def image_bytes_preview(
    data,
    max_side=700
):

    img = Image.open(
        BytesIO(data)
    ).convert("RGB")

    img.thumbnail(
        (max_side, max_side)
    )

    out = BytesIO()

    img.save(
        out,
        format="JPEG",
        quality=80
    )

    return out.getvalue()


def resized_rgb_array(
    data,
    max_side=1000
):

    img = Image.open(
        BytesIO(data)
    ).convert("RGB")

    img.thumbnail(
        (max_side, max_side)
    )

    return np.asarray(img)


# ==========================================================
# GUEST URL
# ==========================================================

def make_guest_url():

    try:

        base = st.secrets.get(
            "GUEST_URL",
            ""
        )

    except Exception:

        base = ""

    if not base:

        base = "http://localhost:8501"

    base = base.rstrip("/")

    if "?" in base:

        base = base.split("?")[0]

    return base + "/?mode=guest"


# ==========================================================
# QR CODE
# ==========================================================

def make_qr(url):

    img = qrcode.make(url)

    out = BytesIO()

    img.save(
        out,
        format="PNG"
    )

    out.seek(0)

    return out
