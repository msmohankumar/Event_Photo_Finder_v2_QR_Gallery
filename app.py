
import os
import io
import zipfile
import streamlit as st

from config_store import load_config, save_config
from gallery import get_gallery_images, clear_dropbox_gallery_cache
from matcher import find_matches
from utils import make_guest_url, make_qr

# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Event Photo Finder",
    page_icon="📸",
    layout="wide"
)

# =========================================================
# LOAD CONFIGURATION
# =========================================================

cfg = load_config()

# =========================================================
# GUEST INTERFACE
# =========================================================

def guest_ui():

    st.title("📸 Find Your Event Photos")

    st.markdown(
        """
        ### Find your photos from the event!

        Take a selfie or upload your photo below.
        We'll search the event gallery and show photos that may contain you.
        """
    )

    if not cfg.get("enabled", False):
        st.warning("The event photo gallery is currently unavailable.")
        return

    if not cfg.get("folder_url"):
        st.warning("The event gallery has not been configured.")
        return

    st.markdown("---")

    st.subheader(cfg.get("event_name", "Event Gallery"))

    # -----------------------------------------------------
    # SELFIE INPUT
    # -----------------------------------------------------

    st.markdown("### 1. Take your selfie")

    camera_photo = st.camera_input(
        "Take a selfie using your camera",
        key="selfie_camera"
    )

    uploaded_photo = st.file_uploader(
        "Or upload a selfie from your phone",
        type=["jpg", "jpeg", "png"],
        key="selfie_upload"
    )

    selfie_bytes = None

    if camera_photo is not None:
        selfie_bytes = camera_photo.getvalue()

    elif uploaded_photo is not None:
        selfie_bytes = uploaded_photo.getvalue()

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    st.markdown("### 2. Find your photos")

    threshold = st.slider(
        "Matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(cfg.get("threshold", 0.40)),
        step=0.01,
        help="Lower values are stricter. Higher values may find more photos but can include false matches."
    )

    if selfie_bytes:

        st.success("Selfie selected. You can now search for your photos.")

        if st.button(
            "🔎 Find My Photos",
            type="primary",
            use_container_width=True
        ):

            # Clear old search results when a new search starts
            st.session_state.pop("guest_matches", None)
            st.session_state.pop("guest_errors", None)

            try:

                with st.spinner("Searching event photos..."):

                    gallery_images = get_gallery_images(cfg)

                    st.write(
                        f"Gallery loaded: {len(gallery_images)} photos"
                    )

                    matches, errors = find_matches(
                        selfie_bytes,
                        gallery_images,
                        threshold
                    )

                    st.session_state["guest_matches"] = matches
                    st.session_state["guest_errors"] = errors

            except Exception as exc:

                st.error(f"Search failed: {exc}")

    else:

        st.info("Take a selfie or upload an image to start searching.")

    # -----------------------------------------------------
    # RESULTS
    # -----------------------------------------------------

    if "guest_matches" in st.session_state:

        matches = st.session_state["guest_matches"]
        errors = st.session_state.get("guest_errors", [])

        st.markdown("---")

        st.subheader(
            f"🎉 Found {len(matches)} matching photo(s)"
        )

        if not matches:

            st.info(
                "No matching photos found. "
                "Try another selfie with better lighting."
            )

        else:

            st.markdown(
                "### Your photos"
            )

            # Individual downloads
            for idx, match in enumerate(matches):

                st.markdown("---")

                st.image(
                    match["preview"],
                    caption=match["name"],
                    use_container_width=True
                )

                st.download_button(
                    label=f"⬇️ Download {match['name']}",
                    data=match["original"],
                    file_name=match["name"],
                    mime="image/jpeg",
                    key=f"individual_download_{idx}",
                    use_container_width=True
                )

            # ------------------------------------------------
            # DOWNLOAD ALL
            # ------------------------------------------------

            if len(matches) > 1:

                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(
                    zip_buffer,
                    "w",
                    zipfile.ZIP_DEFLATED
                ) as zip_file:

                    for match in matches:

                        zip_file.writestr(
                            match["name"],
                            match["original"]
                        )

                st.markdown("---")

                st.download_button(
                    label="📦 Download all my photos",
                    data=zip_buffer.getvalue(),
                    file_name="my_event_photos.zip",
                    mime="application/zip",
                    use_container_width=True
                )

        # ------------------------------------------------
        # ERRORS
        # ------------------------------------------------

        if errors:

            with st.expander("Photos skipped during processing"):

                st.write(errors)

# =========================================================
# ORGANIZER INTERFACE
# =========================================================

def admin_ui():

    st.title("⚙️ Event Organizer")

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    if not st.session_state.get("admin_authenticated", False):

        password = st.text_input(
            "Organizer password",
            type="password",
            key="admin_password_input"
        )

        if st.button("🔐 Login"):

            expected_password = st.secrets.get(
                "ADMIN_PASSWORD",
                os.getenv("ADMIN_PASSWORD", "")
            )

            if expected_password and password == expected_password:

                st.session_state["admin_authenticated"] = True
                st.rerun()

            elif not expected_password:

                st.error(
                    "ADMIN_PASSWORD is not configured in Streamlit Secrets."
                )

            else:

                st.error("Incorrect password.")

        return

    # -----------------------------------------------------
    # CONFIGURATION
    # -----------------------------------------------------

    st.subheader("Event Configuration")

    event_name = st.text_input(
        "Event name",
        value=cfg.get("event_name", "Event Gallery"),
        key="admin_event_name"
    )

    provider_options = {
        "Google Drive": "drive",
        "Dropbox": "dropbox",
        "Local folder": "local",
        "TeraBox": "terabox",
        "Azure Blob Storage": "azure",
        "Amazon S3": "s3"
    }

    current_provider = cfg.get("provider", "dropbox")

    provider_labels = list(provider_options.keys())

    current_label = next(
        (
            label
            for label, value in provider_options.items()
            if value == current_provider
        ),
        "Dropbox"
    )

    provider_label = st.selectbox(
        "Gallery provider",
        provider_labels,
        index=provider_labels.index(current_label)
    )

    provider = provider_options[provider_label]

    folder_labels = {
        "drive": "Google Drive folder link",
        "dropbox": "Dropbox shared folder link",
        "local": "Local folder path",
        "terabox": "TeraBox shared link",
        "azure": "Azure container name or URL",
        "s3": "S3 bucket name or URL"
    }

    folder_url = st.text_input(
        folder_labels[provider],
        value=cfg.get("folder_url", ""),
        key="admin_folder_url"
    )

    threshold = st.slider(
        "Default matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(cfg.get("threshold", 0.40)),
        step=0.01,
        key="admin_threshold"
    )

    enabled = st.toggle(
        "Enable guest photo finder",
        value=bool(cfg.get("enabled", True)),
        key="admin_enabled"
    )

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    if st.button(
        "💾 Save Gallery Configuration",
        type="primary"
    ):

        new_config = {
            "event_name": event_name,
            "provider": provider,
            "folder_url": folder_url.strip(),
            "threshold": threshold,
            "enabled": enabled
        }

        try:

            save_config(new_config)

            st.success("Configuration saved successfully.")

            st.rerun()

        except Exception as exc:

            st.error(f"Unable to save configuration: {exc}")

    # -----------------------------------------------------
    # QR CODE
    # -----------------------------------------------------

    st.markdown("---")

    st.subheader("📱 Guest QR Code")

    guest_url = make_guest_url()

    qr_image = make_qr(guest_url)

    st.image(qr_image, width=250)

    st.caption(
        "Guests should scan this QR code to open the selfie photo finder."
    )

    st.code(guest_url)

    st.download_button(
        "⬇️ Download Guest QR Code",
        data=qr_image.getvalue(),
        file_name="event_guest_qr.png",
        mime="image/png"
    )

    # -----------------------------------------------------
    # DROPBOX CACHE REFRESH
    # -----------------------------------------------------

    if provider == "dropbox":

        st.markdown("---")

        st.subheader("Dropbox Gallery Cache")

        st.caption(
            "Gallery images are cached for 30 minutes."
        )

        if st.button("🔄 Refresh Dropbox Gallery Cache"):

            clear_dropbox_gallery_cache()

            st.success(
                "Dropbox cache cleared. The gallery will reload on the next search."
            )

    # -----------------------------------------------------
    # TEST GALLERY
    # -----------------------------------------------------

    st.markdown("---")

    st.subheader("🧪 Test Gallery Connection")

    if st.button("Test Gallery"):

        try:

            test_config = {
                **cfg,
                "provider": provider,
                "folder_url": folder_url.strip()
            }

            with st.spinner("Connecting to gallery..."):

                images = get_gallery_images(test_config)

            st.success(
                f"Connection successful. Found {len(images)} photos."
            )

        except Exception as exc:

            st.error(f"Gallery test failed: {exc}")

    # -----------------------------------------------------
    # LOGOUT
    # -----------------------------------------------------

    st.markdown("---")

    if st.button("🚪 Logout Organizer"):

        st.session_state["admin_authenticated"] = False

        st.rerun()

# =========================================================
# MAIN APPLICATION
# GUEST PAGE IS ALWAYS THE DEFAULT
# =========================================================

guest_ui()

# =========================================================
# ORGANIZER LOGIN
# =========================================================

with st.expander("⚙️ Organizer Login"):

    admin_ui()
