import os
import io
import zipfile

import streamlit as st

from config_store import load_config, save_config
from gallery import (
    get_gallery_images,
    clear_dropbox_gallery_cache,
    dropbox_diagnostics,
)
from matcher import find_matches
from utils import make_guest_url, make_qr


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="Event Photo Finder",
    page_icon="📸",
    layout="wide",
)

cfg = load_config()


# ============================================================
# GUEST PAGE
# ============================================================

def guest_ui():

    st.title("📸 Find Your Event Photos")

    st.markdown(
        """
        ### Find your photos from the event!

        Take a selfie or upload a photo.
        We'll compare your face with the event gallery.
        """
    )

    if not cfg.get("enabled", False):

        st.warning(
            "The event photo finder is currently disabled."
        )

        return

    if not cfg.get("folder_url"):

        st.warning(
            "The gallery has not been configured."
        )

        return

    st.markdown("---")

    st.subheader(
        cfg.get(
            "event_name",
            "Event Gallery",
        )
    )

    # --------------------------------------------------------
    # SELFIE
    # --------------------------------------------------------

    st.subheader("1. Take or upload your selfie")

    camera = st.camera_input(
        "Take a selfie",
        key="guest_camera",
    )

    uploaded = st.file_uploader(
        "Or upload your selfie",
        type=["jpg", "jpeg", "png"],
        key="guest_upload",
    )

    selfie = None

    if camera is not None:

        selfie = camera.getvalue()

    elif uploaded is not None:

        selfie = uploaded.getvalue()

    # --------------------------------------------------------
    # THRESHOLD
    # --------------------------------------------------------

    threshold = st.slider(
        "Matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(
            cfg.get(
                "threshold",
                0.40,
            )
        ),
        step=0.01,
        help=(
            "Lower values are stricter. "
            "Higher values may return more matches "
            "but may also produce false matches."
        ),
    )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if selfie is not None:

        st.success(
            "Selfie selected."
        )

        if st.button(
            "🔎 Find My Photos",
            type="primary",
            use_container_width=True,
        ):

            st.session_state.pop(
                "guest_matches",
                None,
            )

            st.session_state.pop(
                "guest_errors",
                None,
            )

            try:

                with st.spinner(
                    "Loading event gallery..."
                ):

                    images = get_gallery_images(
                        cfg
                    )

                if not images:

                    st.error(
                        "The gallery returned zero images. "
                        "Face recognition cannot proceed."
                    )

                    return

                st.info(
                    f"Loaded {len(images)} gallery images. "
                    "Starting face recognition..."
                )

                with st.spinner(
                    "Comparing faces..."
                ):

                    matches, errors = find_matches(
                        selfie,
                        images,
                        threshold,
                    )

                st.session_state[
                    "guest_matches"
                ] = matches

                st.session_state[
                    "guest_errors"
                ] = errors

                st.session_state[
                    "guest_total_images"
                ] = len(images)

            except Exception as exc:

                st.error(
                    f"Search failed: {exc}"
                )

    else:

        st.info(
            "Take a selfie or upload an image to search."
        )

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    if "guest_matches" not in st.session_state:

        return

    matches = st.session_state[
        "guest_matches"
    ]

    errors = st.session_state.get(
        "guest_errors",
        [],
    )

    total_images = st.session_state.get(
        "guest_total_images",
        0,
    )

    st.markdown("---")

    st.subheader("Search Results")

    st.write(
        f"Gallery images analysed: {total_images}"
    )

    st.write(
        f"Matching photos: {len(matches)}"
    )

    st.write(
        f"Images skipped or failed: {len(errors)}"
    )

    # --------------------------------------------------------
    # MATCHES
    # --------------------------------------------------------

    if not matches:

        st.warning(
            "No matching photos were found. "
            "Try another selfie or adjust matching sensitivity."
        )

    else:

        st.success(
            f"Found {len(matches)} matching photo(s)!"
        )

        for index, match in enumerate(matches):

            st.markdown("---")

            st.image(
                match["preview"],
                caption=(
                    f"{match['name']} | "
                    f"Distance: {match['distance']:.4f}"
                ),
                use_container_width=True,
            )

            st.download_button(
                label=f"⬇️ Download {match['name']}",
                data=match["original"],
                file_name=match["name"],
                mime="application/octet-stream",
                key=f"download_{index}",
                use_container_width=True,
            )

        # ----------------------------------------------------
        # ZIP
        # ----------------------------------------------------

        if len(matches) > 1:

            buffer = io.BytesIO()

            with zipfile.ZipFile(
                buffer,
                "w",
                zipfile.ZIP_DEFLATED,
            ) as archive:

                for match in matches:

                    archive.writestr(
                        match["name"],
                        match["original"],
                    )

            st.download_button(
                label="📦 Download all matching photos",
                data=buffer.getvalue(),
                file_name="event_matching_photos.zip",
                mime="application/zip",
                use_container_width=True,
            )

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    if errors:

        with st.expander(
            "Details of images skipped"
        ):

            for error in errors:

                st.write(error)


# ============================================================
# ORGANIZER
# ============================================================

def admin_ui():

    st.title("⚙️ Event Organizer")

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    if not st.session_state.get(
        "admin_authenticated",
        False,
    ):

        password = st.text_input(
            "Organizer password",
            type="password",
        )

        if st.button("🔐 Login"):

            expected = st.secrets.get(
                "ADMIN_PASSWORD",
                os.getenv(
                    "ADMIN_PASSWORD",
                    "",
                ),
            )

            if expected and password == expected:

                st.session_state[
                    "admin_authenticated"
                ] = True

                st.rerun()

            elif not expected:

                st.error(
                    "ADMIN_PASSWORD is not configured."
                )

            else:

                st.error(
                    "Incorrect password."
                )

        return

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    st.subheader("Event Configuration")

    event_name = st.text_input(
        "Event name",
        value=cfg.get(
            "event_name",
            "Event Gallery",
        ),
    )

    providers = {
        "Google Drive": "drive",
        "Dropbox": "dropbox",
        "Local folder": "local",
        "Azure Blob Storage": "azure",
        "Amazon S3": "s3",
        "TeraBox": "terabox",
    }

    labels = list(
        providers.keys()
    )

    current_provider = cfg.get(
        "provider",
        "dropbox",
    )

    current_label = next(
        (
            label
            for label, value
            in providers.items()
            if value == current_provider
        ),
        "Dropbox",
    )

    provider_label = st.selectbox(
        "Gallery provider",
        labels,
        index=labels.index(
            current_label
        ),
    )

    provider = providers[
        provider_label
    ]

    label_map = {
        "drive": "Google Drive folder link",
        "dropbox": "Dropbox shared folder link",
        "local": "Local folder path",
        "azure": "Azure container name",
        "s3": "S3 bucket name",
        "terabox": "TeraBox link",
    }

    folder_url = st.text_input(
        label_map[provider],
        value=cfg.get(
            "folder_url",
            "",
        ),
        key="admin_folder",
    )

    threshold = st.slider(
        "Default matching sensitivity",
        0.20,
        0.70,
        float(
            cfg.get(
                "threshold",
                0.40,
            )
        ),
        0.01,
    )

    enabled = st.toggle(
        "Enable guest photo finder",
        value=bool(
            cfg.get(
                "enabled",
                True,
            )
        ),
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    if st.button(
        "💾 Save Configuration",
        type="primary",
    ):

        new_config = {
            "event_name": event_name,
            "provider": provider,
            "folder_url": folder_url.strip(),
            "threshold": threshold,
            "enabled": enabled,
        }

        try:

            save_config(
                new_config
            )

            st.success(
                "Configuration saved."
            )

            st.rerun()

        except Exception as exc:

            st.error(
                f"Save failed: {exc}"
            )

    # --------------------------------------------------------
    # QR
    # --------------------------------------------------------

    st.markdown("---")

    st.subheader("📱 Guest QR Code")

    guest_url = make_guest_url()

    qr = make_qr(
        guest_url
    )

    st.image(
        qr,
        width=250,
    )

    st.code(
        guest_url
    )

    st.download_button(
        "⬇️ Download QR Code",
        data=qr.getvalue(),
        file_name="event_guest_qr.png",
        mime="image/png",
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if provider == "dropbox":

        st.markdown("---")

        st.subheader("Dropbox Cache")

        if st.button(
            "🔄 Clear Dropbox Cache",
        ):

            clear_dropbox_gallery_cache()

            st.success(
                "Cache cleared."
            )

    # --------------------------------------------------------
    # TEST
    # --------------------------------------------------------

    st.markdown("---")

    st.subheader("🧪 Test Gallery")

    if st.button(
        "Test Gallery",
    ):

        test_cfg = {
            **cfg,
            "provider": provider,
            "folder_url": folder_url.strip(),
        }

        try:

            with st.spinner(
                "Testing gallery..."
            ):

                if provider == "dropbox":

                    images, errors, listed = (
                        dropbox_diagnostics(
                            folder_url.strip()
                        )
                    )

                else:

                    images = get_gallery_images(
                        test_cfg
                    )

                    errors = []

                    listed = len(images)

            if listed == 0:

                st.warning(
                    "Connection completed, but no images were listed."
                )

            else:

                st.success(
                    f"Gallery test completed. "
                    f"Images listed: {listed}. "
                    f"Images downloaded: {len(images)}."
                )

            if images:

                st.subheader(
                    "Sample gallery images"
                )

                sample = images[:5]

                cols = st.columns(
                    min(3, len(sample))
                )

                for index, image in enumerate(sample):

                    with cols[
                        index % len(cols)
                    ]:

                        st.image(
                            image["preview"],
                            caption=image["name"],
                        )

            if errors:

                with st.expander(
                    f"Download errors ({len(errors)})"
                ):

                    for error in errors:

                        st.write(error)

        except Exception as exc:

            st.error(
                f"Gallery test failed: {exc}"
            )

    # --------------------------------------------------------
    # LOGOUT
    # --------------------------------------------------------

    st.markdown("---")

    if st.button(
        "🚪 Logout",
    ):

        st.session_state[
            "admin_authenticated"
        ] = False

        st.rerun()


# ============================================================
# APPLICATION
# ============================================================

guest_ui()

with st.expander(
    "⚙️ Organizer Login",
):

    admin_ui()
