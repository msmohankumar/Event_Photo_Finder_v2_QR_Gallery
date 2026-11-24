
import requests
import streamlit as st
import json
import time


# ============================================================
# DROPBOX API CONFIGURATION
# ============================================================

DROPBOX_LIST_FOLDER_URL = (
    "https://api.dropboxapi.com/2/files/list_folder"
)

DROPBOX_LIST_FOLDER_CONTINUE_URL = (
    "https://api.dropboxapi.com/2/files/list_folder/continue"
)

DROPBOX_DOWNLOAD_URL = (
    "https://content.dropboxapi.com/2/sharing/get_shared_link_file"
)


# ============================================================
# HEADERS
# ============================================================

def _dropbox_headers(token):

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


# ============================================================
# ERROR HANDLING
# ============================================================

def _dropbox_error(response):

    try:
        error_data = response.json()
        return json.dumps(error_data, indent=2)

    except Exception:
        return response.text[:2000]


# ============================================================
# DROPBOX API TEST
# ============================================================

def test_dropbox_shared_link(link, token):

    url = "https://api.dropboxapi.com/2/sharing/get_shared_link_metadata"

    payload = {
        "url": link
    }

    response = requests.post(
        url,
        headers=_dropbox_headers(token),
        json=payload,
        timeout=30
    )

    if response.ok:
        return response.json()

    raise RuntimeError(
        "Dropbox metadata test failed:\n"
        + _dropbox_error(response)
    )


# ============================================================
# LIST SHARED FOLDER CONTENTS
# ============================================================

def _list_shared_folder(link, path="", token=None):

    payload = {
        "path": path,
        "shared_link": {
            "url": link
        },
        "recursive": False
    }

    response = requests.post(
        DROPBOX_LIST_FOLDER_URL,
        headers=_dropbox_headers(token),
        json=payload,
        timeout=60
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox list_folder failed:\n"
            + _dropbox_error(response)
        )

    data = response.json()

    entries = data.get("entries", [])

    while data.get("has_more"):

        response = requests.post(
            DROPBOX_LIST_FOLDER_CONTINUE_URL,
            headers=_dropbox_headers(token),
            json={
                "cursor": data["cursor"]
            },
            timeout=60
        )

        if not response.ok:

            raise RuntimeError(
                "Dropbox pagination failed:\n"
                + _dropbox_error(response)
            )

        data = response.json()

        entries.extend(
            data.get("entries", [])
        )

    return entries


# ============================================================
# RECURSIVE IMAGE DISCOVERY
# ============================================================

def _get_all_images_from_folder(
    shared_link,
    token,
    folder_path=""
):

    images = []

    entries = _list_shared_folder(
        link=shared_link,
        path=folder_path,
        token=token
    )

    for entry in entries:

        entry_type = entry.get(".tag")
        entry_name = entry.get("name", "")
        entry_path = entry.get("path_lower", "")

        # ----------------------------------------------------
        # FILE
        # ----------------------------------------------------

        if entry_type == "file":

            extension = entry_name.lower()

            if extension.endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".bmp"
                )
            ):

                images.append({
                    "name": entry_name,
                    "path": entry_path,
                    "original": entry_path,
                    "preview": entry_path
                })

        # ----------------------------------------------------
        # SUBFOLDER
        # ----------------------------------------------------

        elif entry_type == "folder":

            subfolder_images = (
                _get_all_images_from_folder(
                    shared_link=shared_link,
                    token=token,
                    folder_path=entry_path
                )
            )

            images.extend(subfolder_images)

    return images


# ============================================================
# DOWNLOAD FILE FROM SHARED LINK
# ============================================================

def _download_shared_file(
    shared_link,
    file_path,
    token
):

    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps({
            "url": shared_link,
            "path": file_path
        })
    }

    response = requests.post(
        DROPBOX_DOWNLOAD_URL,
        headers=headers,
        timeout=60
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox file download failed:\n"
            + _dropbox_error(response)
        )

    return response.content


# ============================================================
# TEST GALLERY
# ============================================================

def test_gallery(folder_url):

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN",
        ""
    )

    if not token:

        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing "
            "from Streamlit secrets."
        )

    metadata = test_dropbox_shared_link(
        folder_url,
        token
    )

    entries = _list_shared_folder(
        link=folder_url,
        path="",
        token=token
    )

    return {
        "metadata": metadata,
        "entries": entries,
        "entry_count": len(entries)
    }


# ============================================================
# CACHE GALLERY
# ============================================================

@st.cache_data(ttl=1800)
def get_gallery_images(folder_url):

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN",
        ""
    )

    if not token:

        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing."
        )

    # Validate shared link first

    test_dropbox_shared_link(
        folder_url,
        token
    )

    # Collect image paths recursively

    image_files = _get_all_images_from_folder(
        shared_link=folder_url,
        token=token,
        folder_path=""
    )

    # Download images

    downloaded_images = []

    for image in image_files:

        try:

            image_bytes = _download_shared_file(
                shared_link=folder_url,
                file_path=image["path"],
                token=token
            )

            downloaded_images.append({
                "name": image["name"],
                "original": image["path"],
                "preview": image_bytes,
                "bytes": image_bytes
            })

        except Exception as exc:

            print(
                "Failed to download:",
                image["name"],
                str(exc)
            )

    return downloaded_images


# ============================================================
# CACHE REFRESH
# ============================================================

def clear_gallery_cache():

    get_gallery_images.clear()
