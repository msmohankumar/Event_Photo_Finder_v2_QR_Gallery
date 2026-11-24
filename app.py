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

mode = st.query_params.get("mode", "guest")

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

    st.info(
        f"Gallery: {cfg.get('event_name', 'Event Gallery')}"
    )

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
        else (
            selfie_upload.getvalue()
            if selfie_upload
            else None
        )
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
        "not the storage location."
    )

    # ------------------------------------------------------
    # LOGIN
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

            expected = st.secrets.get(
                "ADMIN_PASSWORD",
                os.getenv("ADMIN_PASSWORD", "")
            )

            if expected and password == expected:

                st.session_state.admin_authenticated = True
                st.rerun()

            elif not expected:

                st.error(
                    "Set ADMIN_PASSWORD in Streamlit Secrets."
                )

            else:

                st.error("Incorrect password.")

        return

    # ------------------------------------------------------
    # EVENT NAME
    # ------------------------------------------------------

    st.text_input(
        "Event name",
        value=cfg.get("event_name", "Event Gallery"),
        key="event_name"
    )

    # ------------------------------------------------------
    # PROVIDER
    # ------------------------------------------------------

    provider_options = {
        "Local folder (app host)": "local",
        "Google Drive": "drive",
        "Dropbox": "dropbox",
        "TeraBox (not yet supported)": "terabox",
        "Microsoft Azure Blob Storage": "azure",
        "Amazon S3": "s3"
    }

    current_provider = cfg.get("provider", "drive")

    current_label = next(
        (
            label
            for label, value in provider_options.items()
            if value == current_provider
        ),
        "Google Drive"
    )

    provider_label = st.selectbox(
        "Gallery provider",
        list(provider_options.keys()),
        index=list(provider_options.keys()).index(
            current_label
        )
    )

    provider = provider_options[provider_label]

    # ------------------------------------------------------
    # PROVIDER-SPECIFIC INPUT
    # ------------------------------------------------------

    input_labels = {
        "local": "Folder path on the Streamlit server",
        "drive": "Google Drive folder link",
        "dropbox": "Dropbox shared folder link",
        "terabox": "TeraBox shared link",
        "azure": "Azure Blob container name",
        "s3": "Amazon S3 bucket name"
    }

    folder_url = st.text_input(
        input_labels[provider],
        value=cfg.get("folder_url", ""),
        key="folder_url"
    )

    if provider == "local":

        st.info(
            "Local folder refers to the folder on the machine "
            "running Streamlit. On Streamlit Cloud, this is the "
            "cloud server, not your personal computer."
        )

    elif provider == "drive":

        st.caption(
            "Requires a Google Drive API key and accessible folder."
        )

    elif provider == "dropbox":

        st.caption(
            "Requires a Dropbox access token with appropriate API permissions."
        )

    elif provider == "azure":

        st.caption(
            "Enter the Azure Blob container name. "
            "The connection string is configured in Streamlit Secrets."
        )

    elif provider == "s3":

        st.caption(
            "Enter the S3 bucket name. AWS credentials "
            "and region are configured in Streamlit Secrets."
        )

    elif provider == "terabox":

        st.warning(
            "TeraBox is listed as a source, but photo retrieval "
            "is not implemented in this version."
        )

    # ------------------------------------------------------
    # SETTINGS
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # SAVE
    # ------------------------------------------------------

    if st.button(
        "💾 Save / Update Gallery",
        type="primary"
    ):

        new_cfg = {

            "event_name": st.session_state.event_name,

            "provider": provider,

            "folder_url": (
                st.session_state.folder_url.strip()
            ),

            "threshold": st.session_state.threshold,

            "enabled": enabled
        }

        try:

            save_config(new_cfg)

            st.success(
                "Gallery configuration saved successfully."
            )

            st.rerun()

        except Exception as exc:

            st.error(
                f"Could not save configuration: {exc}"
            )

    # ------------------------------------------------------
    # QR CODE
    # ------------------------------------------------------

    st.subheader("📱 Guest QR code")

    guest_url = make_guest_url()

    st.write(
        "Print this QR code for guests. "
        "It remains the same when you change the gallery."
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
    # CONNECTION TEST
    # ------------------------------------------------------

    st.subheader("🔍 Gallery connection test")

    if st.button("Test gallery source"):

        try:

            test_cfg = {
                **cfg,
                "provider": provider,
                "folder_url": folder_url.strip()
            }

            images = get_gallery_images(test_cfg)

            st.success(
                f"Connection successful. "
                f"Found {len(images)} images."
            )

        except Exception as exc:

            st.error(
                f"Connection failed: {exc}"
            )


# ==========================================================
# ROUTING
# ==========================================================

if mode == "admin":

    admin_ui()

else:

    guest_ui()
