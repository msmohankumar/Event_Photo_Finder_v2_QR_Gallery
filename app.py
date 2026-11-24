
import os
import io
import zipfile
import streamlit as st

from config_store import load_config, save_config
from gallery import get_gallery_images
from matcher import find_matches
from utils import make_guest_url, make_qr


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Event Photo Finder",
    page_icon="📸",
    layout="wide"
)

cfg = load_config()


# ============================================================
# ADMIN PASSWORD
# ============================================================

def get_admin_password():

    try:
        return st.secrets.get(
            "ADMIN_PASSWORD",
            os.getenv("ADMIN_PASSWORD", "")
        )
    except Exception:
        return os.getenv("ADMIN_PASSWORD", "")


# ============================================================
# GUEST PHOTO FINDER
# ============================================================

def guest_ui():

    st.title("📸 Find Your Event Photos")

    st.markdown(
        """
        ### Welcome!

        Take a selfie and we'll search the event gallery
        to find photos in which you appear.
        """
    )

    # --------------------------------------------------------
    # GALLERY CONFIGURATION CHECK
    # --------------------------------------------------------

    if not cfg.get("enabled", False):

        st.info(
            "The event photo gallery is currently unavailable."
        )

        return

    if not cfg.get("folder_url", "").strip():

        st.info(
            "The event photo gallery has not been configured."
        )

        return

    st.markdown("---")

    st.subheader(
        cfg.get("event_name", "Event Gallery")
    )

    st.caption(
        "Take a selfie below. The app will search the saved event gallery "
        "and show only photos matching your face."
    )

    # --------------------------------------------------------
    # SELFIE
    # --------------------------------------------------------

    selfie_camera = st.camera_input(
        "📷 Take your selfie",
        key="guest_camera"
    )

    selfie_upload = st.file_uploader(
        "Or upload your selfie",
        type=["jpg", "jpeg", "png"],
        key="guest_upload"
    )

    selfie_bytes = None

    if selfie_camera:

        selfie_bytes = selfie_camera.getvalue()

    elif selfie_upload:

        selfie_bytes = selfie_upload.getvalue()

    # --------------------------------------------------------
    # SEARCH BUTTON
    # --------------------------------------------------------

    threshold = float(cfg.get("threshold", 0.40))

    st.caption(
        "The search uses the event gallery configured by the organizer."
    )

    search_button = st.button(
        "🔎 Find My Photos",
        type="primary",
        disabled=not selfie_bytes
    )

    # --------------------------------------------------------
    # MATCH SEARCH
    # --------------------------------------------------------

    if search_button:

        st.session_state.pop("photo_matches", None)
        st.session_state.pop("photo_match_errors", None)

        try:

            with st.spinner(
                "Loading event photos and searching for your face..."
            ):

                # Load saved gallery from Dropbox / configured provider.
                gallery_images = get_gallery_images(cfg)

                if not gallery_images:

                    st.warning(
                        "No event photos were found in the gallery."
                    )

                    return

                st.info(
                    f"Searching {len(gallery_images)} event photos..."
                )

                # Search the selfie against the saved event gallery.
                matches, errors = find_matches(
                    selfie_bytes,
                    gallery_images,
                    threshold
                )

                st.session_state["photo_matches"] = matches
                st.session_state["photo_match_errors"] = errors

        except Exception as exc:

            st.error(
                f"Unable to search the event gallery: {exc}"
            )

            return

    # --------------------------------------------------------
    # DISPLAY MATCHES
    # --------------------------------------------------------

    matches = st.session_state.get(
        "photo_matches",
        None
    )

    errors = st.session_state.get(
        "photo_match_errors",
        []
    )

    if matches is not None:

        st.divider()

        st.subheader(
            f"🎉 {len(matches)} matching photo(s) found"
        )

        if len(matches) == 0:

            st.info(
                "No matching photos found. "
                "Try another selfie with better lighting."
            )

        else:

            st.markdown(
                "Select **Download photo** under any picture "
                "to save it individually."
            )

            # ------------------------------------------------
            # INDIVIDUAL PHOTO DISPLAY
            # ------------------------------------------------

            for idx, match in enumerate(matches):

                st.divider()

                col1, col2 = st.columns(
                    [3, 1],
                    vertical_alignment="center"
                )

                with col1:

                    st.image(
                        match["preview"],
                        caption=match["name"],
                        use_container_width=True
                    )

                with col2:

                    st.markdown(
                        f"**{match['name']}**"
                    )

                    st.caption(
                        f"Match distance: {match['distance']:.4f}"
                    )

                    st.download_button(
                        label="⬇️ Download photo",
                        data=match["original"],
                        file_name=match["name"],
                        mime="application/octet-stream",
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
                    mode="w",
                    compression=zipfile.ZIP_DEFLATED
                ) as zip_file:

                    for match in matches:

                        zip_file.writestr(
                            match["name"],
                            match["original"]
                        )

                st.divider()

                st.download_button(
                    label="📦 Download all matching photos",
                    data=zip_buffer.getvalue(),
                    file_name="event_matching_photos.zip",
                    mime="application/zip",
                    type="primary"
                )

        # ----------------------------------------------------
        # ERRORS
        # ----------------------------------------------------

        if errors:

            with st.expander(
                f"⚠️ {len(errors)} photos could not be processed"
            ):

                for error in errors:

                    st.write(error)


# ============================================================
# ADMIN PANEL
# ============================================================

def admin_ui():

    st.title("⚙️ Event Organizer Dashboard")

    if not st.session_state.get(
        "admin_authenticated",
        False
    ):

        with st.form("admin_login_form"):

            password = st.text_input(
                "Admin password",
                type="password"
            )

            login = st.form_submit_button(
                "🔓 Login"
            )

            if login:

                expected = get_admin_password()

                if not expected:

                    st.error(
                        "ADMIN_PASSWORD is missing in Streamlit Secrets."
                    )

                elif password == expected:

                    st.session_state[
                        "admin_authenticated"
                    ] = True

                    st.rerun()

                else:

                    st.error(
                        "Incorrect password."
                    )

        return

    # --------------------------------------------------------
    # LOGOUT
    # --------------------------------------------------------

    if st.button("🔒 Logout"):

        st.session_state[
            "admin_authenticated"
        ] = False

        st.rerun()

    # --------------------------------------------------------
    # CONFIGURATION
    # --------------------------------------------------------

    st.subheader("Event Gallery Settings")

    event_name = st.text_input(
        "Event name",
        value=cfg.get(
            "event_name",
            "Event Gallery"
        ),
        key="admin_event_name"
    )

    provider_options = {
        "Local folder": "local",
        "Google Drive": "drive",
        "Dropbox": "dropbox",
        "TeraBox": "terabox",
        "Azure Blob Storage": "azure",
        "Amazon S3": "s3",
    }

    providers = list(provider_options.values())

    current_provider = cfg.get(
        "provider",
        "dropbox"
    )

    if current_provider not in providers:

        current_provider = "dropbox"

    current_index = providers.index(
        current_provider
    )

    provider_label = st.selectbox(
        "Gallery storage",
        list(provider_options.keys()),
        index=current_index,
        key="admin_provider"
    )

    provider = provider_options[
        provider_label
    ]

    labels = {
        "local": "Folder path",
        "drive": "Google Drive folder link",
        "dropbox": "Dropbox shared folder link",
        "terabox": "TeraBox shared link",
        "azure": "Azure container name",
        "s3": "S3 bucket name",
    }

    folder_url = st.text_input(
        labels[provider],
        value=cfg.get(
            "folder_url",
            ""
        ),
        key="admin_folder_url"
    )

    threshold = st.slider(
        "Default matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(
            cfg.get(
                "threshold",
                0.40
            )
        ),
        step=0.01
    )

    enabled = st.toggle(
        "Enable gallery for guests",
        value=bool(
            cfg.get(
                "enabled",
                False
            )
        )
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    if st.button(
        "💾 Save Gallery Settings",
        type="primary"
    ):

        new_cfg = {
            "event_name": event_name.strip(),
            "provider": provider,
            "folder_url": folder_url.strip(),
            "threshold": threshold,
            "enabled": enabled,
        }

        try:

            save_config(new_cfg)

            st.success(
                "Gallery configuration saved successfully."
            )

            st.rerun()

        except Exception as exc:

            st.error(
                f"Unable to save settings: {exc}"
            )

    # --------------------------------------------------------
    # TEST GALLERY
    # --------------------------------------------------------

    st.divider()

    st.subheader("Test Gallery Connection")

    if st.button("🔌 Test Gallery"):

        test_cfg = {
            **cfg,
            "event_name": event_name,
            "provider": provider,
            "folder_url": folder_url.strip(),
            "enabled": enabled,
            "threshold": threshold
        }

        try:

            with st.spinner(
                "Connecting to gallery..."
            ):

                images = get_gallery_images(
                    test_cfg
                )

            st.success(
                f"Connected successfully. {len(images)} images found."
            )

        except Exception as exc:

            st.error(
                f"Gallery connection failed: {exc}"
            )

    # --------------------------------------------------------
    # QR CODE
    # --------------------------------------------------------

    st.divider()

    st.subheader("Guest QR Code")

    guest_url = make_guest_url()

    qr_image = make_qr(
        guest_url
    )

    st.image(
        qr_image,
        width=250
    )

    st.code(
        guest_url
    )

    st.download_button(
        "⬇️ Download QR Code",
        data=qr_image.getvalue(),
        file_name="event_guest_qr.png",
        mime="image/png"
    )


# ============================================================
# APPLICATION ROUTING
# ============================================================

st.title("📸 Event Photo Finder")

if st.session_state.get(
    "admin_authenticated",
    False
):

    admin_ui()

else:

    guest_ui()

    # --------------------------------------------------------
    # ADMIN LOGIN
    # --------------------------------------------------------

    st.divider()

    with st.expander(
        "🔐 Organizer Login"
    ):

        admin_ui()


# ============================================================
# FOOTER
# ============================================================

st.caption(
    "Event Photo Finder | Please use face matching with appropriate consent."
)
