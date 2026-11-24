
import os
import io
import zipfile
import streamlit as st

from config_store import load_config, save_config
from gallery import get_gallery_images
from matcher import find_matches
from utils import make_guest_url, make_qr


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Event Photo Finder",
    page_icon="📸",
    layout="wide"
)

cfg = load_config()


# ============================================================
# HELPERS
# ============================================================

def get_admin_password():
    try:
        return st.secrets.get("ADMIN_PASSWORD", os.getenv("ADMIN_PASSWORD", ""))
    except Exception:
        return os.getenv("ADMIN_PASSWORD", "")


def logout_admin():
    st.session_state["admin_authenticated"] = False
    st.rerun()


# ============================================================
# GUEST PAGE
# ============================================================

def guest_ui():

    st.title("📸 Find Your Event Photos")

    st.markdown(
        """
        Take a selfie or upload your photo to find pictures
        from the event gallery.
        """
    )

    if not cfg.get("enabled") or not cfg.get("folder_url"):
        st.info(
            "The event gallery has not been configured yet. "
            "Please check back later."
        )
        return

    st.success(f"Event: {cfg.get('event_name', 'Event Gallery')}")

    st.caption(
        "Your selfie is used to search the event gallery. "
        "Face matching may make mistakes."
    )

    selfie_camera = st.camera_input("📷 Take a selfie")

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
        "Matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(cfg.get("threshold", 0.40)),
        step=0.01,
        help="Lower values are stricter. Higher values allow more possible matches."
    )

    if st.button(
        "🔎 Find my photos",
        type="primary",
        disabled=not selfie_bytes
    ):

        with st.spinner("Loading gallery and searching for your photos..."):

            try:

                images = get_gallery_images(cfg)

                st.write(f"Gallery photos loaded: {len(images)}")

                matches, errors = find_matches(
                    selfie_bytes,
                    images,
                    threshold
                )

            except Exception as exc:

                st.error(f"Gallery search failed: {exc}")
                return

        st.subheader(f"🎉 Found {len(matches)} matching photo(s)")

        if not matches:

            st.info(
                "No matching photos found. "
                "Try a clearer selfie or adjust the matching sensitivity."
            )

        else:

            cols = st.columns(3)

            for idx, match in enumerate(matches):

                with cols[idx % 3]:

                    st.image(
                        match["preview"],
                        caption=f'{match["name"]} | Distance: {match["distance"]:.3f}',
                        use_container_width=True
                    )

                    st.download_button(
                        "⬇️ Download photo",
                        data=match["original"],
                        file_name=match["name"],
                        mime="image/jpeg",
                        key=f"download_photo_{idx}"
                    )

            # Download all matching images
            if len(matches) > 1:

                buffer = io.BytesIO()

                with zipfile.ZipFile(
                    buffer,
                    "w",
                    zipfile.ZIP_DEFLATED
                ) as zip_file:

                    for match in matches:

                        zip_file.writestr(
                            match["name"],
                            match["original"]
                        )

                st.download_button(
                    "⬇️ Download all matching photos",
                    data=buffer.getvalue(),
                    file_name="my_event_photos.zip",
                    mime="application/zip"
                )

        if errors:

            with st.expander(f"⚠️ {len(errors)} photos skipped"):

                for error in errors:
                    st.write(error)


# ============================================================
# ADMIN PAGE
# ============================================================

def admin_ui():

    st.title("⚙️ Event Organizer Dashboard")

    st.caption(
        "Manage your event gallery, storage source and guest QR code."
    )

    if st.button("🔒 Logout from Admin"):

        logout_admin()

    st.divider()

    # --------------------------------------------------------
    # EVENT CONFIGURATION
    # --------------------------------------------------------

    st.subheader("Event Configuration")

    event_name = st.text_input(
        "Event name",
        value=cfg.get("event_name", "Event Gallery"),
        key="admin_event_name"
    )

    provider_options = {
        "Local folder (self-hosted app)": "local",
        "Google Drive": "drive",
        "Dropbox": "dropbox",
        "TeraBox (limited support)": "terabox",
        "Microsoft Azure Blob Storage": "azure",
        "Amazon S3": "s3",
    }

    provider_values = list(provider_options.values())

    current_provider = cfg.get("provider", "dropbox")

    if current_provider not in provider_values:
        current_provider = "dropbox"

    current_index = provider_values.index(current_provider)

    provider_label = st.selectbox(
        "Gallery provider",
        list(provider_options.keys()),
        index=current_index,
        key="admin_provider"
    )

    provider = provider_options[provider_label]

    folder_labels = {
        "local": "Folder path on app host",
        "drive": "Google Drive folder link",
        "dropbox": "Dropbox shared folder link",
        "terabox": "TeraBox shared link",
        "azure": "Azure Blob container name or URL",
        "s3": "S3 bucket name or URL",
    }

    folder_url = st.text_input(
        folder_labels[provider],
        value=cfg.get("folder_url", ""),
        key="admin_folder_url"
    )

    # --------------------------------------------------------
    # PROVIDER INFORMATION
    # --------------------------------------------------------

    if provider == "local":

        st.info(
            "Local folder means a folder accessible to the computer "
            "running Streamlit. Streamlit Cloud cannot access folders "
            "on your personal laptop."
        )

    elif provider == "dropbox":

        st.caption(
            "Paste your Dropbox shared folder link. "
            "The Dropbox API token must be configured in Streamlit Secrets."
        )

    elif provider == "azure":

        st.caption(
            "Azure credentials must be configured in Streamlit Secrets."
        )

    elif provider == "s3":

        st.caption(
            "AWS credentials must be configured in Streamlit Secrets."
        )

    elif provider == "terabox":

        st.warning(
            "TeraBox support is limited. The app does not bypass "
            "authentication or access restrictions."
        )

    # --------------------------------------------------------
    # MATCHING SETTINGS
    # --------------------------------------------------------

    threshold = st.slider(
        "Default matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(cfg.get("threshold", 0.40)),
        step=0.01,
        key="admin_threshold"
    )

    enabled = st.toggle(
        "Enable guest photo search",
        value=bool(cfg.get("enabled", False)),
        key="admin_enabled"
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    if st.button("💾 Save / Update Gallery", type="primary"):

        new_cfg = {
            "event_name": event_name.strip(),
            "provider": provider,
            "folder_url": folder_url.strip(),
            "threshold": threshold,
            "enabled": enabled,
        }

        try:

            save_config(new_cfg)

            st.success("Gallery configuration saved successfully!")

            st.rerun()

        except Exception as exc:

            st.error(f"Unable to save configuration: {exc}")

    # --------------------------------------------------------
    # TEST GALLERY CONNECTION
    # --------------------------------------------------------

    st.divider()

    st.subheader("🔌 Test Gallery Connection")

    if st.button("Test gallery source"):

        test_cfg = {
            **cfg,
            "event_name": event_name,
            "provider": provider,
            "folder_url": folder_url.strip(),
            "threshold": threshold,
            "enabled": enabled,
        }

        with st.spinner("Connecting to gallery..."):

            try:

                images = get_gallery_images(test_cfg)

                st.success(
                    f"Connection successful! "
                    f"{len(images)} image(s) found."
                )

            except Exception as exc:

                st.error(f"Connection failed: {exc}")

    # --------------------------------------------------------
    # QR CODE
    # --------------------------------------------------------

    st.divider()

    st.subheader("📱 Guest QR Code")

    guest_url = make_guest_url()

    st.write(
        "This QR code opens the Guest Photo Finder. "
        "It does not point directly to Dropbox."
    )

    qr_image = make_qr(guest_url)

    st.image(qr_image, width=250)

    st.code(guest_url)

    st.download_button(
        "⬇️ Download Guest QR Code",
        data=qr_image.getvalue(),
        file_name="event_guest_qr.png",
        mime="image/png"
    )


# ============================================================
# MAIN APPLICATION
# ============================================================

st.title("📸 Event Photo Finder")

# If an admin has authenticated during this session, show admin dashboard.
if st.session_state.get("admin_authenticated", False):

    admin_ui()

else:

    guest_ui()

    # --------------------------------------------------------
    # ADMIN LOGIN
    # --------------------------------------------------------

    st.divider()

    with st.expander("🔐 Event Organizer Login"):

        st.write("Organizer access is password protected.")

        admin_password_input = st.text_input(
            "Admin password",
            type="password",
            key="admin_password_input"
        )

        if st.button("🔓 Login as Organizer"):

            expected_password = get_admin_password()

            if not expected_password:

                st.error(
                    "ADMIN_PASSWORD is not configured in Streamlit Secrets."
                )

            elif admin_password_input == expected_password:

                st.session_state["admin_authenticated"] = True

                st.success("Login successful!")

                st.rerun()

            else:

                st.error("Incorrect password.")

# ============================================================
# FOOTER
# ============================================================

st.caption(
    "Event Photo Finder | Use face matching only with appropriate consent."
)
