
import requests
import streamlit as st
import json


# ============================================================
# DROPBOX API ENDPOINTS
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
# DROPBOX HEADERS
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
        return json.dumps(response.json(), indent=2)

    except Exception:
        return response.text[:2000]


# ============================================================
# GET TOKEN
# ============================================================

def _get_dropbox_token():

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN",
        ""
    )

    if not token:

        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing "
            "from Streamlit secrets."
        )

    return token


# ============================================================
# TEST SHARED LINK METADATA
# ============================================================

def test_dropbox_shared_link(link, token):

    endpoint = (
        "https://api.dropboxapi.com/2/sharing/"
        "get_shared_link_metadata"
    )

    payload = {
        "url": link
    }

    response = requests.post(
        endpoint,
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
            "Dropbox folder listing failed:\n"
            + _dropbox_error(response)
        )

    data = response.json()

    entries = data.get("entries", [])

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
# RECURSIVE IMAGE COLLECTION
# ============================================================

def _collect_images(
    link,
    token,
    folder_path=""
):

    image_list = []

    entries = _list_shared_folder(
        link=link,
        path=folder_path,
        token=token
    )

    for entry in entries:

        tag = entry.get(".tag")
        name = entry.get("name", "")
        path = entry.get("path_lower", "")

        # ----------------------------------------------------
        # IMAGE FILE
        # ----------------------------------------------------

        if tag == "file":

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

        # ----------------------------------------------------
        # SUBFOLDER
        # ----------------------------------------------------

        elif tag == "folder":

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
# DOWNLOAD SHARED FILE
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
            "Dropbox download failed:\n"
            + _dropbox_error(response)
        )

    return response.content


# ============================================================
# TEST GALLERY
# ============================================================

def test_gallery(folder_url):

    token = _get_dropbox_token()

    # Test metadata

    metadata = test_dropbox_shared_link(
        folder_url,
        token
    )

    # Test folder listing

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
# LOAD GALLERY IMAGES
# ============================================================

@st.cache_data(ttl=1800)
def get_gallery_images(folder_url):

    token = _get_dropbox_token()

    # Verify link

    test_dropbox_shared_link(
        folder_url,
        token
    )

    # Find images

    image_files = _collect_images(
        link=folder_url,
        token=token,
        folder_path=""
    )

    downloaded_images = []

    # Download images

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
                f"Image download error: "
                f"{image['name']}: {exc}"
            )

    return downloaded_images


# ============================================================
# CLEAR GALLERY CACHE
# ============================================================

def clear_gallery_cache():

    get_gallery_images.clear()


# ============================================================
# COMPATIBILITY FUNCTION FOR app.py
# ============================================================

def clear_dropbox_gallery_cache():

    clear_gallery_cache()
