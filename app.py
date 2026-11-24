
import os
import io
import zipfile

import streamlit as st

from config_store import load_config, save_config
from gallery import get_gallery_images
from matcher import find_matches
from utils import make_guest_url, make_qr


st.set_page_config(
    page_title="Event Photo Finder",
    page_icon="📸",
    layout="wide"
)

cfg = load_config()

params = st.query_params
mode = params.get("mode", "guest")

if mode not in ("guest", "admin"):
    mode = "guest"


# ==========================================================
# GUEST PAGE
# ==========================================================

def guest_ui():

    st.title("📸 Find Your Event Photos")

    st.caption(
        "Scan the event QR code, take a selfie, and find your photos."
    )

    if not cfg.get("enabled") or not cfg.get("folder_url"):

        st.info(
            "The event gallery has not been configured yet. "
            "Please check back later."
        )
        return

    st.info(f"Gallery: {cfg.get('event_name', 'Event Gallery')}")

    st.warning(
        "Face matching can make mistakes. "
        "Use only with permission."
    )

    selfie_camera = st.camera_input("Take a selfie")

    selfie_upload = st.file_uploader(
        "Or upload a selfie image",
        type=["jpg", "jpeg", "png"],
        key="guest_selfie"
    )

    selfie_bytes = (
        selfie_camera.getvalue()
        if selfie_camera
        else selfie_upload.getvalue()
        if selfie_upload
        else None
    )

    threshold = st.slider(
        "Matching sensitivity (cosine distance)",
        0.20,
        0.70,
        float(cfg.get("threshold", 0.40)),
        0.01
    )

    if st.button(
        "🔎 Find my photos",
        type="primary",
        disabled=not selfie_bytes
    ):

        with st.spinner(
            "Loading event gallery and searching faces..."
        ):

            try:

                images = get_gallery_images(cfg)

                st.write(
                    f"Loaded {len(images)} gallery photo(s)."
                )

                matches, errors = find_matches(
                    selfie_bytes,
                    images,
                    threshold
                )

            except Exception as exc:

                st.error(
                    f"Gallery search failed: {exc}"
                )
                return

        st.subheader(
            f"Found {len(matches)} matching photo(s)"
        )

        if not matches:

            st.info(
                "No matches found. Try a clearer selfie "
                "or adjust the sensitivity."
            )

        else:

            cols = st.columns(3)

            for idx, m in enumerate(matches):

                with cols[idx % 3]:

                    st.image(
                        m["preview"],
                        caption=(
                            f'{m["name"]} • '
                            f'distance {m["distance"]:.3f}'
                        ),
                        use_container_width=True
                    )

                    st.download_button(
                        "⬇️ Download photo",
                        m["original"],
                        file_name=m["name"],
                        mime="image/jpeg",
                        key=f"dl_{idx}"
                    )

            if len(matches) > 1:

                buffer = io.BytesIO()

                with zipfile.ZipFile(
                    buffer,
                    "w",
                    zipfile.ZIP_DEFLATED
                ) as zf:

                    for m in matches:

                        zf.writestr(
                            m["name"],
                            m["original"]
                        )

                st.download_button(
                    "⬇️ Download all matched photos (ZIP)",
                    buffer.getvalue(),
                    "my_event_photos.zip",
                    "application/zip"
                )

        if errors:

            with st.expander(
                f"{len(errors)} photo(s) skipped"
            ):

                st.write(errors)


# ==========================================================
# ORGANIZER PAGE
# ==========================================================

def admin_ui():

    st.title("⚙️ Event Organizer")

    st.caption(
        "Update the shared event gallery. "
        "The guest QR always points to the app, "
        "so it does not change when the gallery source changes."
    )

    # ------------------------------------------------------
    # ORGANIZER LOGIN
    # ------------------------------------------------------

    if not st.session_state.get(
        "admin_authenticated",
        False
    ):

        password = st.text_input(
            "Organizer password",
            type="password"
        )

        if st.button("Unlock organizer panel"):

            expected = os.getenv(
                "ADMIN_PASSWORD",
                ""
            )

            if expected and password == expected:

                st.session_state.admin_authenticated = True

                st.rerun()

            elif not expected:

                st.error(
                    "Set ADMIN_PASSWORD in Streamlit secrets "
                    "before using the organizer panel."
                )

            else:

                st.error("Incorrect password.")

        return

    # ------------------------------------------------------
    # GALLERY CONFIGURATION
    # ------------------------------------------------------

    st.text_input(
        "Event name",
        value=cfg.get(
            "event_name",
            "Event Gallery"
        ),
        key="event_name"
    )

    provider = st.selectbox(
        "Gallery provider",
        [
            "Google Drive (public folder)",
            "Dropbox (shared folder)"
        ],
        index=(
            0
            if cfg.get("provider", "drive") == "drive"
            else 1
        )
    )

    st.text_input(
        "Gallery folder link",
        value=cfg.get("folder_url", ""),
        key="folder_url"
    )

    st.slider(
        "Default matching sensitivity",
        0.20,
        0.70,
        float(cfg.get("threshold", 0.40)),
        0.01,
        key="threshold"
    )

    enabled = st.toggle(
        "Guest gallery enabled",
        value=bool(cfg.get("enabled", True))
    )

    st.caption(
        "Google Drive folders must be publicly viewable "
        "and require a Google Drive API key. "
        "Dropbox folders require a Dropbox access token "
        "configured in Streamlit secrets."
    )

    # ------------------------------------------------------
    # SAVE CONFIGURATION
    # ------------------------------------------------------

    if st.button(
        "💾 Save / Update Gallery",
        type="primary"
    ):

        new_cfg = {

            "event_name": st.session_state.event_name,

            "provider": (
                "drive"
                if provider.startswith("Google")
                else "dropbox"
            ),

            "folder_url": (
                st.session_state.folder_url.strip()
            ),

            "threshold": (
                st.session_state.threshold
            ),

            "enabled": enabled
        }

        try:

            save_config(new_cfg)

            st.success(
                "Gallery configuration saved. "
                "Guest page now uses the updated gallery."
            )

            st.rerun()

        except Exception as exc:

            st.error(
                f"Could not save shared configuration: {exc}"
            )

    # ------------------------------------------------------
    # QR CODE
    # ------------------------------------------------------

    guest_url = make_guest_url()

    st.subheader("Guest QR code")

    st.write(
        "Print this QR code for guests. "
        "It stays the same when you update the gallery."
    )

    qr_image = make_qr(guest_url)

    st.image(
        qr_image,
        width=240
    )

    st.code(guest_url)

    st.download_button(
        "Download QR code",
        qr_image.getvalue(),
        "event_guest_qr.png",
        "image/png"
    )

    # ------------------------------------------------------
    # TEST GALLERY CONNECTION
    # ------------------------------------------------------

    st.subheader("Gallery connection test")

    if st.button("Test folder link"):

        try:

            test_cfg = {

                **cfg,

                "provider": (
                    "drive"
                    if provider.startswith("Google")
                    else "dropbox"
                ),

                "folder_url": (
                    st.session_state.folder_url
                )
            }

            images = get_gallery_images(test_cfg)

            st.success(
                f"Connection successful. "
                f"Found {len(images)} images."
            )

        except Exception as exc:

            st.error(str(exc))


# ==========================================================
# PAGE ROUTING
# ==========================================================

if mode == "admin":

    admin_ui()

else:

    guest_ui()
