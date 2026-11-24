from io import BytesIO

from PIL import Image
import numpy as np
import qrcode
import streamlit as st


def get_image_bytes(pil_img):

    out = BytesIO()

    pil_img.save(
        out,
        format="JPEG",
        quality=90,
    )

    return out.getvalue()


def image_bytes_preview(data, max_side=700):

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
        quality=80,
    )

    return out.getvalue()


def resized_rgb_array(data, max_side=1000):

    img = Image.open(
        BytesIO(data)
    ).convert("RGB")

    img.thumbnail(
        (max_side, max_side)
    )

    return np.asarray(img)


def make_guest_url():

    try:
        base = st.secrets.get(
            "GUEST_URL",
            "",
        )
    except Exception:
        base = ""

    if not base:
        base = "http://localhost:8501"

    return base.rstrip("/") + "/?mode=guest"


def make_qr(url):

    img = qrcode.make(url)

    out = BytesIO()

    img.save(
        out,
        format="PNG",
    )

    out.seek(0)

    return out
