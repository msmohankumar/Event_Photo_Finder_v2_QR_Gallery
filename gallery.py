
import json
import requests
import streamlit as st


# ============================================================
# DROPBOX API ENDPOINTS
# ============================================================

DROPBOX_LIST_FOLDER_URL = (
    "https://api.dropboxapi.com/2/files/list_folder"
)

DROPBOX_LIST_FOLDER_CONTINUE_URL = (
    "https://api.dropboxapi.com/2/files/list_folder/continue"
)

DROPBOX_METADATA_URL = (
    "https://api.dropboxapi.com/2/sharing/get_shared_link_metadata"
)

DROPBOX_DOWNLOAD_URL = (
    "https://content.dropboxapi.com/2/sharing/get_shared_link_file"
)


# ============================================================
# NORMALIZE CONFIGURATION / SHARED LINK
# ============================================================

def _normalize_link(link):

    # Allow the entire configuration dictionary
    if isinstance(link, dict):

        provider = link.get("provider", "dropbox")

        if provider != "dropbox":
            raise RuntimeError(
                f"Gallery provider is '{provider}', not Dropbox."
            )

        link = link.get("folder_url", "")

    # Allow None
    if link is None:
        link = ""

    # Validate type
    if not isinstance(link, str):

        raise RuntimeError(
            "Invalid Dropbox shared link type: "
            + str(type(link).__name__)
        )

    link = link.strip()

    if not link:

        raise RuntimeError(
            "Dropbox shared folder URL is empty. "
            "Please save the Dropbox folder link in Organizer settings."
        )

    return link


# ============================================================
# DROPBOX HEADERS
# ============================================================

def _dropbox_headers(token):

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


# ============================================================
# DROPBOX ERROR
# ============================================================

def _dropbox_error(response):

    try:

        return json.dumps(
            response.json(),
            indent=2
        )

    except Exception:

        return response.text[:2000]


# ============================================================
# GET DROPBOX TOKEN
# ============================================================

def _get_dropbox_token():

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN",
        ""
    )

    if not token:

        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing "
            "from Streamlit Secrets."
        )

    return token


# ============================================================
# TEST SHARED LINK METADATA
# ============================================================

def test_dropbox_shared_link(link, token):

    link = _normalize_link(link)

    payload = {
        "url": link
    }

    response = requests.post(
        DROPBOX_METADATA_URL,
        headers=_dropbox_headers(token),
        json=payload,
        timeout=30
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox metadata test failed:\n"
            + _dropbox_error(response)
        )

    return response.json()


# ============================================================
# LIST SHARED FOLDER
# ============================================================

def _list_shared_folder(
    link,
    path,
    token
):

    link = _normalize_link(link)

    payload = {
        "path": path,
        "recursive": False,
        "shared_link": {
            "url": link
        }
    }

    response = requests.post(
        DROPBOX_LIST_FOLDER_URL,
        headers=_dropbox_headers(token),
        json=payload,
        timeout=60
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox folder listing failed:\n"
            + _dropbox_error(response)
        )

    data = response.json()

    entries = data.get(
        "entries",
        []
    )

    # Pagination
    while data.get("has_more", False):

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
# RECURSIVELY COLLECT IMAGE FILES
# ============================================================

def _collect_images(
    link,
    token,
    folder_path=""
):

    link = _normalize_link(link)

    image_list = []

    entries = _list_shared_folder(
        link=link,
        path=folder_path,
        token=token
    )

    for entry in entries:

        entry_type = entry.get(".tag")

        name = entry.get(
            "name",
            ""
        )

        path = entry.get(
            "path_lower",
            entry.get("path_display", "")
        )

        # Files
        if entry_type == "file":

            if name.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".bmp"
                )
            ):

                image_list.append({

                    "name": name,

                    "path": path,

                    "original": path,

                    "preview": path

                })

        # Subfolders
        elif entry_type == "folder":

            subfolder_images = _collect_images(
                link=link,
                token=token,
                folder_path=path
            )

            image_list.extend(
                subfolder_images
            )

    return image_list


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def _download_shared_file(
    shared_link,
    file_path,
    token
):

    shared_link = _normalize_link(
        shared_link
    )

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
            "Dropbox image download failed:\n"
            + _dropbox_error(response)
        )

    return response.content


# ============================================================
# TEST GALLERY
# ============================================================

def test_gallery(folder_url):

    # Accept either URL or config dictionary
    folder_url = _normalize_link(
        folder_url
    )

    token = _get_dropbox_token()

    # Metadata test
    metadata = test_dropbox_shared_link(
        folder_url,
        token
    )

    # Folder listing test
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
# LOAD GALLERY
# ============================================================

@st.cache_data(ttl=1800)
def get_gallery_images(folder_url):

    # FIX: Accept either a URL or configuration dictionary
    folder_url = _normalize_link(
        folder_url
    )

    token = _get_dropbox_token()

    # Validate Dropbox shared link
    test_dropbox_shared_link(
        folder_url,
        token
    )

    # Find images recursively
    image_files = _collect_images(
        link=folder_url,
        token=token,
        folder_path=""
    )

    downloaded_images = []

    # Download images
    for image_file in image_files:

        try:

            image_bytes = _download_shared_file(
                shared_link=folder_url,
                file_path=image_file["path"],
                token=token
            )

            downloaded_images.append({

                "name": image_file["name"],

                "original": image_bytes,

                "preview": image_bytes,

                "bytes": image_bytes

            })

        except Exception as exc:

            print(
                "Image download failed:",
                image_file["name"],
                str(exc)
            )

    return downloaded_images


# ============================================================
# CLEAR CACHE
# ============================================================

def clear_gallery_cache():

    get_gallery_images.clear()


# ============================================================
# APP.PY COMPATIBILITY
# ============================================================

def clear_dropbox_gallery_cache():

    clear_gallery_cache()
