import os
import json
import requests
import streamlit as st

from utils import image_bytes_preview


# ============================================================
# CONSTANTS
# ============================================================

IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
)

DROPBOX_LIST_URL = (
    "https://api.dropboxapi.com/2/files/list_folder"
)

DROPBOX_CONTINUE_URL = (
    "https://api.dropboxapi.com/2/files/list_folder/continue"
)

DROPBOX_DOWNLOAD_URL = (
    "https://content.dropboxapi.com/2/sharing/get_shared_link_file"
)


# ============================================================
# SECRETS
# ============================================================

def _secret(name):

    try:
        value = st.secrets.get(name, None)

        if value is not None:
            return value

    except Exception:
        pass

    return os.getenv(name, "")


# ============================================================
# GENERAL HELPERS
# ============================================================

def _normalize_link(link):

    if isinstance(link, dict):
        link = link.get("url", "")

    if not isinstance(link, str):
        link = ""

    link = link.strip()

    if not link:
        raise ValueError(
            "Dropbox shared folder URL is empty."
        )

    if not link.startswith("https://"):
        raise ValueError(
            "The shared link must begin with https://"
        )

    return link


def _normalize_relative_path(path):

    if path is None:
        return ""

    path = str(path).strip()

    return path.strip("/")


def _error_text(response):

    try:
        return json.dumps(
            response.json(),
            indent=2,
        )

    except Exception:
        return response.text[:2000]


# ============================================================
# DROPBOX LISTING
# ============================================================

def _list_folder(link, path, token):

    path = _normalize_relative_path(path)

    payload = {
        "path": path,
        "recursive": False,
        "shared_link": {
            "url": link,
        },
    }

    response = requests.post(
        DROPBOX_LIST_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox list_folder error "
            f"({response.status_code}): "
            + _error_text(response)
        )

    data = response.json()

    entries = data.get(
        "entries",
        [],
    )

    entries = list(entries)

    while data.get("has_more", False):

        response = requests.post(
            DROPBOX_CONTINUE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "cursor": data["cursor"],
            },
            timeout=60,
        )

        if not response.ok:

            raise RuntimeError(
                "Dropbox list_folder/continue error "
                f"({response.status_code}): "
                + _error_text(response)
            )

        data = response.json()

        entries.extend(
            data.get("entries", [])
        )

    return entries


# ============================================================
# RECURSIVE FILE COLLECTION
# ============================================================

def _collect_files(
    link,
    token,
    parent_path="",
    depth=0,
):

    if depth > 50:

        raise RuntimeError(
            "Dropbox folder nesting is too deep."
        )

    parent_path = _normalize_relative_path(
        parent_path
    )

    entries = _list_folder(
        link,
        parent_path,
        token,
    )

    files = []

    for entry in entries:

        tag = entry.get(".tag")

        name = entry.get(
            "name",
            "",
        )

        if not name:
            continue

        if parent_path:

            relative_path = (
                parent_path
                + "/"
                + name
            )

        else:

            relative_path = name

        relative_path = (
            _normalize_relative_path(
                relative_path
            )
        )

        # ----------------------------------------------------
        # IMAGE FILE
        # ----------------------------------------------------

        if (
            tag == "file"
            and name.lower().endswith(
                IMAGE_EXTENSIONS
            )
        ):

            files.append({
                "name": name,
                "path": relative_path,
            })

        # ----------------------------------------------------
        # SUBFOLDER
        # ----------------------------------------------------

        elif tag == "folder":

            subfolder_files = (
                _collect_files(
                    link,
                    token,
                    relative_path,
                    depth + 1,
                )
            )

            files.extend(
                subfolder_files
            )

    return files


# ============================================================
# DROPBOX FILE DOWNLOAD
# ============================================================

def _download_file(
    link,
    relative_path,
    token,
):

    relative_path = (
        _normalize_relative_path(
            relative_path
        )
    )

    # IMPORTANT:
    # Dropbox requires the path for
    # sharing/get_shared_link_file to start with "/".
    #
    # Example:
    # IMG_1234.jpg
    # becomes:
    # /IMG_1234.jpg

    if not relative_path.startswith("/"):
        relative_path = "/" + relative_path

    download_args = {
        "url": link,
        "path": relative_path,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps(
            download_args
        ),
    }

    response = requests.post(
        DROPBOX_DOWNLOAD_URL,
        headers=headers,
        timeout=90,
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox download error "
            f"({response.status_code}): "
            + _error_text(response)
        )

    return response.content


# ============================================================
# FETCH ALL GALLERY IMAGES
# ============================================================

def _fetch_gallery(
    link,
    token,
):

    # --------------------------------------------------------
    # LIST FILES
    # --------------------------------------------------------

    files = _collect_files(
        link,
        token,
    )

    images = []

    errors = []

    # --------------------------------------------------------
    # DOWNLOAD FILES
    # --------------------------------------------------------

    for item in files:

        name = item["name"]

        path = item["path"]

        try:

            original = _download_file(
                link,
                path,
                token,
            )

            preview = image_bytes_preview(
                original
            )

            images.append({
                "name": name,
                "original": original,
                "preview": preview,
            })

        except Exception as exc:

            errors.append(
                f"{name} | {path} | {exc}"
            )

    return (
        images,
        errors,
        len(files),
    )


# ============================================================
# CACHED GALLERY
# ============================================================

@st.cache_data(
    ttl=1800,
    max_entries=3,
    show_spinner=False,
)
def _cached_gallery(
    link,
    token,
):

    return _fetch_gallery(
        link,
        token,
    )


# ============================================================
# DROPBOX DIAGNOSTICS
# ============================================================

def dropbox_diagnostics(link):

    link = _normalize_link(
        link
    )

    token = _secret(
        "DROPBOX_ACCESS_TOKEN"
    )

    if not token:

        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing "
            "from Streamlit secrets or environment variables."
        )

    # Diagnostic test bypasses cache.

    images, errors, listed = _fetch_gallery(
        link,
        token,
    )

    return (
        images,
        errors,
        listed,
    )


# ============================================================
# DROPBOX GUEST GALLERY
# ============================================================

def dropbox_images(link):

    link = _normalize_link(
        link
    )

    token = _secret(
        "DROPBOX_ACCESS_TOKEN"
    )

    if not token:

        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing."
        )

    images, errors, listed = (
        _cached_gallery(
            link,
            token,
        )
    )

    if listed == 0:

        raise RuntimeError(
            "No images were found in the Dropbox folder."
        )

    if not images:

        error_summary = "\n".join(
            errors[:5]
        )

        raise RuntimeError(
            f"Dropbox listed {listed} images, "
            "but none could be downloaded.\n"
            f"{error_summary}"
        )

    return images


# ============================================================
# CLEAR DROPBOX CACHE
# ============================================================

def clear_dropbox_gallery_cache():

    _cached_gallery.clear()


# Compatibility alias

clear_gallery_cache = (
    clear_dropbox_gallery_cache
)


# ============================================================
# GOOGLE DRIVE
# ============================================================

def drive_images(link):

    key = _secret(
        "GOOGLE_DRIVE_API_KEY"
    )

    if not key:

        raise RuntimeError(
            "GOOGLE_DRIVE_API_KEY is missing."
        )

    import re

    match = re.search(
        r"/folders/([a-zA-Z0-9_-]+)",
        link,
    )

    if not match:

        match = re.search(
            r"[?&]id=([a-zA-Z0-9_-]+)",
        )

    if not match:

        raise ValueError(
            "Google Drive folder ID could not be found."
        )

    folder_id = match.group(1)

    params = {
        "q": (
            f"'{folder_id}' in parents "
            "and trashed=false"
        ),
        "fields": (
            "files(id,name,mimeType)"
        ),
        "pageSize": 1000,
        "key": key,
    }

    response = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    images = []

    for item in response.json().get(
        "files",
        [],
    ):

        if not item.get(
            "mimeType",
            "",
        ).startswith("image/"):

            continue

        download_url = (
            "https://www.googleapis.com/drive/v3/files/"
            + item["id"]
            + "?alt=media&key="
            + key
        )

        download = requests.get(
            download_url,
            timeout=60,
        )

        download.raise_for_status()

        original = download.content

        images.append({
            "name": item["name"],
            "original": original,
            "preview": image_bytes_preview(
                original
            ),
        })

    return images


# ============================================================
# LOCAL FOLDER
# ============================================================

def local_images(path):

    if not os.path.isdir(path):

        raise ValueError(
            "Local folder does not exist."
        )

    images = []

    for name in sorted(
        os.listdir(path)
    ):

        if not name.lower().endswith(
            IMAGE_EXTENSIONS
        ):

            continue

        full_path = os.path.join(
            path,
            name,
        )

        try:

            with open(
                full_path,
                "rb",
            ) as file:

                original = file.read()

            images.append({
                "name": name,
                "original": original,
                "preview": image_bytes_preview(
                    original
                ),
            })

        except Exception:
            continue

    return images


# ============================================================
# AZURE STORAGE
# ============================================================

def azure_images(container):

    connection = _secret(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    if not connection:

        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is missing."
        )

    from azure.storage.blob import (
        BlobServiceClient,
    )

    service = BlobServiceClient.from_connection_string(
        connection
    )

    client = service.get_container_client(
        container.strip()
    )

    images = []

    for blob in client.list_blobs():

        if not blob.name.lower().endswith(
            IMAGE_EXTENSIONS
        ):

            continue

        original = client.download_blob(
            blob.name
        ).readall()

        images.append({
            "name": blob.name,
            "original": original,
            "preview": image_bytes_preview(
                original
            ),
        })

    return images


# ============================================================
# AMAZON S3
# ============================================================

def s3_images(bucket):

    access = _secret(
        "AWS_ACCESS_KEY_ID"
    )

    secret = _secret(
        "AWS_SECRET_ACCESS_KEY"
    )

    region = _secret(
        "AWS_REGION"
    )

    if not access or not secret:

        raise RuntimeError(
            "AWS credentials are missing."
        )

    from boto3.session import Session

    session = Session(
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region or None,
    )

    s3 = session.client(
        "s3"
    )

    images = []

    paginator = s3.get_paginator(
        "list_objects_v2"
    )

    for page in paginator.paginate(
        Bucket=bucket.strip()
    ):

        for item in page.get(
            "Contents",
            [],
        ):

            name = item["Key"]

            if not name.lower().endswith(
                IMAGE_EXTENSIONS
            ):

                continue

            original = s3.get_object(
                Bucket=bucket.strip(),
                Key=name,
            )["Body"].read()

            images.append({
                "name": name,
                "original": original,
                "preview": image_bytes_preview(
                    original
                ),
            })

    return images


# ============================================================
# PROVIDER ROUTER
# ============================================================

def get_gallery_images(cfg):

    if not isinstance(
        cfg,
        dict,
    ):

        raise TypeError(
            "Gallery configuration must be a dictionary."
        )

    provider = cfg.get(
        "provider",
        "",
    )

    folder_url = cfg.get(
        "folder_url",
        "",
    )

    # --------------------------------------------------------
    # DROPBOX
    # --------------------------------------------------------

    if provider == "dropbox":

        return dropbox_images(
            folder_url
        )

    # --------------------------------------------------------
    # GOOGLE DRIVE
    # --------------------------------------------------------

    elif provider == "drive":

        return drive_images(
            folder_url
        )

    # --------------------------------------------------------
    # LOCAL
    # --------------------------------------------------------

    elif provider == "local":

        return local_images(
            folder_url
        )

    # --------------------------------------------------------
    # AZURE
    # --------------------------------------------------------

    elif provider == "azure":

        return azure_images(
            folder_url
        )

    # --------------------------------------------------------
    # S3
    # --------------------------------------------------------

    elif provider == "s3":

        return s3_images(
            folder_url
        )

    # --------------------------------------------------------
    # TERABOX
    # --------------------------------------------------------

    elif provider == "terabox":

        raise RuntimeError(
            "TeraBox provider is not implemented."
        )

    # --------------------------------------------------------
    # UNKNOWN
    # --------------------------------------------------------

    else:

        raise ValueError(
            f"Unsupported gallery provider: {provider}"
        )
