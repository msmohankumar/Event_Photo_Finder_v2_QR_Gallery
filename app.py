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
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Event Photo Finder",
    page_icon="📸",
    layout="wide",
)

cfg = load_config()


# ============================================================
# GUEST INTERFACE
# ============================================================

def guest_ui():

    st.title("📸 Find Your Event Photos")

    st.markdown(
        """
        ### Find your photos from the event!

        Take a selfie or upload one or more photos.
        We'll search the event gallery for photos containing you.
        """
    )

    if not cfg.get("enabled", False):

        st.warning(
            "The event photo finder is currently disabled."
        )
        return

    if not cfg.get("folder_url", ""):

        st.warning(
            "The gallery has not been configured."
        )
        return

    st.markdown("---")

    st.subheader(
        cfg.get("event_name", "Event Gallery")
    )

    # --------------------------------------------------------
    # SELFIE CAMERA
    # --------------------------------------------------------

    st.subheader("1. Take a selfie")

    camera = st.camera_input(
        "Take a selfie using your camera",
        key="guest_camera",
    )

    # --------------------------------------------------------
    # MULTIPLE SELFIE UPLOADS
    # --------------------------------------------------------

    st.subheader("2. Or upload one or more photos")

    uploaded_files = st.file_uploader(
        "Drag and drop your photos here",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="guest_uploads",
    )

    # --------------------------------------------------------
    # COLLECT ALL SELFIES
    # --------------------------------------------------------

    selfies = []

    if camera is not None:

        selfies.append({
            "name": "Camera selfie",
            "bytes": camera.getvalue(),
        })

    if uploaded_files:

        for file in uploaded_files:

            selfies.append({
                "name": file.name,
                "bytes": file.getvalue(),
            })

    # --------------------------------------------------------
    # PREVIEW
    # --------------------------------------------------------

    if selfies:

        st.success(
            f"{len(selfies)} selfie/photo(s) selected."
        )

        preview_columns = st.columns(
            min(4, len(selfies))
        )

        for index, selfie in enumerate(selfies):

            with preview_columns[
                index % len(preview_columns)
            ]:

                st.image(
                    selfie["bytes"],
                    caption=selfie["name"],
                )

    # --------------------------------------------------------
    # THRESHOLD
    # --------------------------------------------------------

    threshold = st.slider(
        "Matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(
            cfg.get("threshold", 0.40)
        ),
        step=0.01,
        help=(
            "Lower values are stricter. "
            "Higher values may find more matches, "
            "but can also produce false matches."
        ),
    )

    # --------------------------------------------------------
    # SEARCH BUTTON
    # --------------------------------------------------------

    if selfies:

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

                # --------------------------------------------
                # LOAD EVENT GALLERY
                # --------------------------------------------

                with st.spinner(
                    "Loading event gallery..."
                ):

                    gallery_images = (
                        get_gallery_images(cfg)
                    )

                if not gallery_images:

                    st.error(
                        "No gallery images were loaded."
                    )

                    return

                st.success(
                    f"{len(gallery_images)} gallery images loaded."
                )

                # --------------------------------------------
                # SEARCH USING EACH SELFIE
                # --------------------------------------------

                combined_matches = {}

                combined_errors = []

                progress = st.progress(0)

                status = st.empty()

                for selfie_index, selfie in enumerate(
                    selfies
                ):

                    status.write(
                        f"Searching using "
                        f"{selfie['name']} "
                        f"({selfie_index + 1}/"
                        f"{len(selfies)})..."
                    )

                    try:

                        matches, errors = find_matches(
                            selfie["bytes"],
                            gallery_images,
                            threshold,
                        )

                        combined_errors.extend(
                            errors
                        )

                        # ------------------------------------
                        # MERGE MATCHES
                        # ------------------------------------

                        for match in matches:

                            name = match["name"]

                            if name not in combined_matches:

                                combined_matches[name] = match

                            else:

                                # Keep the best distance.
                                if (
                                    match["distance"]
                                    < combined_matches[name]["distance"]
                                ):

                                    combined_matches[name] = match

                    except Exception as exc:

                        combined_errors.append(
                            f"{selfie['name']}: {exc}"
                        )

                    progress.progress(
                        (selfie_index + 1)
                        / len(selfies)
                    )

                status.empty()

                progress.empty()

                # --------------------------------------------
                # SORT MATCHES
                # --------------------------------------------

                final_matches = sorted(
                    combined_matches.values(),
                    key=lambda item: item["distance"],
                )

                st.session_state[
                    "guest_matches"
                ] = final_matches

                st.session_state[
                    "guest_errors"
                ] = combined_errors

                st.session_state[
                    "guest_total_images"
                ] = len(gallery_images)

                st.session_state[
                    "guest_selfie_count"
                ] = len(selfies)

            except Exception as exc:

                st.error(
                    f"Search failed: {exc}"
                )

    else:

        st.info(
            "Take a selfie or upload one or more photos "
            "to begin searching."
        )

    # ========================================================
    # RESULTS
    # ========================================================

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

    st.subheader("🎉 Search Results")

    st.write(
        f"Gallery images: {total_images}"
    )

    st.write(
        f"Matching photos: {len(matches)}"
    )

    # --------------------------------------------------------
    # MATCHES
    # --------------------------------------------------------

    if not matches:

        st.warning(
            "No matching photos were found. "
            "Try another selfie or adjust the sensitivity."
        )

    else:

        st.success(
            f"Found {len(matches)} matching photos!"
        )

        # --------------------------------------------
        # DISPLAY MATCHES
        # --------------------------------------------

        columns = st.columns(3)

        for index, match in enumerate(matches):

            with columns[index % 3]:

                st.image(
                    match["preview"],
                    use_container_width=True,
                )

                st.caption(
                    f"{match['name']}"
                )

                st.caption(
                    f"Match distance: "
                    f"{match['distance']:.4f}"
                )

                st.download_button(
                    "⬇️ Download",
                    data=match["original"],
                    file_name=match["name"],
                    mime="application/octet-stream",
                    key=f"download_{index}",
                    use_container_width=True,
                )

        # ----------------------------------------------------
        # DOWNLOAD ALL MATCHES
        # ----------------------------------------------------

        if len(matches) > 1:

            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(
                zip_buffer,
                "w",
                zipfile.ZIP_DEFLATED,
            ) as archive:

                for match in matches:

                    archive.writestr(
                        match["name"],
                        match["original"],
                    )

            st.download_button(
                "📦 Download all matching photos",
                data=zip_buffer.getvalue(),
                file_name="my_event_photos.zip",
                mime="application/zip",
                use_container_width=True,
            )

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    if errors:

        st.markdown(
            "### Processing errors"
        )

        for error in errors[:20]:

            st.warning(
                str(error)
            )

        if len(errors) > 20:

            st.caption(
                f"{len(errors) - 20} additional errors omitted."
            )


# ============================================================
# ORGANIZER INTERFACE
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
            key="admin_password",
        )

        if st.button("🔐 Login"):

            expected = st.secrets.get(
                "ADMIN_PASSWORD",
                os.getenv("ADMIN_PASSWORD", ""),
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
    # CONFIGURATION
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

    labels = list(providers.keys())

    current_provider = cfg.get(
        "provider",
        "dropbox",
    )

    current_label = next(
        (
            label
            for label, value in providers.items()
            if value == current_provider
        ),
        "Dropbox",
    )

    provider_label = st.selectbox(
        "Gallery provider",
        labels,
        index=labels.index(current_label),
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
        "terabox": "TeraBox shared link",
    }

    folder_url = st.text_input(
        label_map[provider],
        value=cfg.get(
            "folder_url",
            "",
        ),
    )

    threshold = st.slider(
        "Default matching sensitivity",
        min_value=0.20,
        max_value=0.70,
        value=float(
            cfg.get(
                "threshold",
                0.40,
            )
        ),
        step=0.01,
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
                "Configuration saved successfully."
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
    # DROPBOX CACHE
    # --------------------------------------------------------

    if provider == "dropbox":

        st.markdown("---")

        st.subheader(
            "Dropbox Cache"
        )

        if st.button(
            "🔄 Clear Dropbox Cache",
        ):

            clear_dropbox_gallery_cache()

            st.success(
                "Dropbox cache cleared."
            )

    # --------------------------------------------------------
    # GALLERY TEST
    # --------------------------------------------------------

    st.markdown("---")

    st.subheader("🧪 Test Gallery")

    if st.button("Test Gallery"):

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

            st.write(
                f"Images listed: {listed}"
            )

            st.write(
                f"Images downloaded: {len(images)}"
            )

            st.write(
                f"Download failures: {len(errors)}"
            )

            if listed and images:

                st.success(
                    "Gallery test completed successfully."
                )

            elif listed:

                st.warning(
                    "Files were listed, but downloads failed."
                )

            else:

                st.warning(
                    "No images were found."
                )

            if images:

                st.markdown(
                    "### Sample photos"
                )

                sample = images[:5]

                columns = st.columns(
                    min(3, len(sample))
                )

                for index, item in enumerate(sample):

                    with columns[
                        index % len(columns)
                    ]:

                        st.image(
                            item["preview"],
                            caption=item["name"],
                        )

            if errors:

                st.markdown(
                    "### Download errors"
                )

                for error in errors[:20]:

                    st.error(
                        str(error)
                    )

                if len(errors) > 20:

                    st.caption(
                        f"{len(errors) - 20} "
                        "additional errors omitted."
                    )

        except Exception as exc:

            st.error(
                f"Gallery test failed: {exc}"
            )

    # --------------------------------------------------------
    # LOGOUT
    # --------------------------------------------------------

    st.markdown("---")

    if st.button("🚪 Logout"):

        st.session_state[
            "admin_authenticated"
        ] = False

        st.rerun()


# ============================================================
# MAIN
# ============================================================

guest_ui()

with st.expander("⚙️ Organizer Login"):

    admin_ui()
