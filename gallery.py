
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

DROPBOX_DOWNLOAD_URL = (
    "https://content.dropboxapi.com/2/sharing/get_shared_link_file"
)


# ============================================================
# NORMALIZE INPUT
# Accept URL or configuration dictionary
# ============================================================

def _normalize_link(link):

    if isinstance(link, dict):

        link = link.get(
            "folder_url",
            ""
        )

    if link is None:
        link = ""

    if not isinstance(link, str):

        raise RuntimeError(
            "Invalid Dropbox shared link."
        )

    link = link.strip()

    if not link:

        raise RuntimeError(
            "Dropbox shared folder URL is empty. "
            "Enter and save the folder link in Organizer settings."
        )

    if not link.startswith("https://"):

        raise RuntimeError(
            "The Dropbox link must begin with https://"
        )

    return link


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
# DROPBOX HEADERS
# ============================================================

def _dropbox_headers(token):

    return {

        "Authorization": f"Bearer {token}",

        "Content-Type": "application/json"

    }


# ============================================================
# FORMAT DROPBOX ERROR
# ============================================================

def _dropbox_error(response):

    try:

        data = response.json()

        return json.dumps(
            data,
            indent=2
        )

    except Exception:

        return response.text[:2000]


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

        error_text = _dropbox_error(
            response
        )

        if "shared_link_not_found" in error_text:

            raise RuntimeError(
                "Dropbox cannot find this shared link.\n\n"
                "Check the following:\n"
                "1. Copy the shared folder link again from Dropbox.\n"
                "2. Confirm the link is still active.\n"
                "3. Make sure the link opens in an incognito browser "
                "without requiring your Dropbox login.\n"
                "4. Check whether the folder is password protected.\n"
                "5. Make sure the link is a folder link, not an image/file link.\n\n"
                "Dropbox response:\n"
                + error_text
            )

        if response.status_code == 401:

            raise RuntimeError(
                "Dropbox access token is invalid or expired.\n\n"
                + error_text
            )

        if response.status_code == 403:

            raise RuntimeError(
                "Dropbox denied access to this folder.\n\n"
                "Check Dropbox token permissions and shared folder access.\n\n"
                + error_text
            )

        raise RuntimeError(
            "Dropbox folder listing failed.\n\n"
            + error_text
        )

    data = response.json()

    entries = data.get(
        "entries",
        []
    )

    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------

    while data.get(
        "has_more",
        False
    ):

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
                "Dropbox pagination failed:\n\n"
                + _dropbox_error(response)
            )

        data = response.json()

        entries.extend(
            data.get(
                "entries",
                []
            )
        )

    return entries


# ============================================================
# RECURSIVELY FIND IMAGES
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

        entry_type = entry.get(
            ".tag"
        )

        name = entry.get(
            "name",
            ""
        )

        path = entry.get(
            "path_lower",
            entry.get(
                "path_display",
                ""
            )
        )

        # ----------------------------------------------------
        # IMAGE FILES
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # SUBFOLDERS
        # ----------------------------------------------------

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
# DOWNLOAD SHARED FILE
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
            "Dropbox image download failed:\n\n"
            + _dropbox_error(response)
        )

    return response.content


# ============================================================
# TEST GALLERY CONNECTION
# ============================================================

def test_gallery(folder_url):

    folder_url = _normalize_link(
        folder_url
    )

    token = _get_dropbox_token()

    # Validate by directly listing the folder
    entries = _list_shared_folder(
        link=folder_url,
        path="",
        token=token
    )

    return {

        "entries": entries,

        "entry_count": len(entries)

    }


# ============================================================
# LOAD GALLERY IMAGES
# ============================================================

@st.cache_data(ttl=1800)
def get_gallery_images(folder_url):

    folder_url = _normalize_link(
        folder_url
    )

    token = _get_dropbox_token()

    # --------------------------------------------------------
    # DIRECT FOLDER TEST
    # --------------------------------------------------------

    _list_shared_folder(
        link=folder_url,
        path="",
        token=token
    )

    # --------------------------------------------------------
    # FIND ALL IMAGE FILES
    # --------------------------------------------------------

    image_files = _collect_images(
        link=folder_url,
        token=token,
        folder_path=""
    )

    # --------------------------------------------------------
    # DOWNLOAD IMAGES
    # --------------------------------------------------------

    downloaded_images = []

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
