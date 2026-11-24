import os
import json
import requests
import streamlit as st

from utils import image_bytes_preview

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

DROPBOX_LIST_URL = "https://api.dropboxapi.com/2/files/list_folder"
DROPBOX_CONTINUE_URL = "https://api.dropboxapi.com/2/files/list_folder/continue"
DROPBOX_DOWNLOAD_URL = "https://api.dropboxapi.com/2/sharing/get_shared_link_file"


# ============================================================
# SECRETS
# ============================================================

def _secret(name):

    try:
        return st.secrets.get(
            name,
            os.getenv(name, ""),
        )

    except Exception:
        return os.getenv(name, "")


# ============================================================
# DROPBOX HELPERS
# ============================================================

def _headers(token):

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _error_text(response):

    try:
        return json.dumps(
            response.json(),
            indent=2,
        )

    except Exception:
        return response.text[:2000]


def _normalize_link(link):

    if isinstance(link, dict):
        link = link.get("url", "")

    if not isinstance(link, str):
        link = ""

    link = link.strip()

    if not link:
        raise ValueError(
            "Dropbox shared link is empty."
        )

    return link


def _normalize_relative_path(path):

    if path is None:
        return ""

    path = str(path).strip()

    return path.strip("/")


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
        headers=_headers(token),
        json=payload,
        timeout=60,
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox folder listing error "
            f"({response.status_code}):\n"
            + _error_text(response)
        )

    data = response.json()

    entries = list(
        data.get("entries", [])
    )

    while data.get("has_more"):

        response = requests.post(
            DROPBOX_CONTINUE_URL,
            headers=_headers(token),
            json={
                "cursor": data["cursor"],
            },
            timeout=60,
        )

        if not response.ok:

            raise RuntimeError(
                "Dropbox pagination error "
                f"({response.status_code}):\n"
                + _error_text(response)
            )

        data = response.json()

        entries.extend(
            data.get("entries", [])
        )

    return entries


# ============================================================
# RECURSIVE FILE DISCOVERY
# ============================================================

def _collect_files(
    link,
    token,
    parent_path="",
    depth=0,
):

    if depth > 50:

        raise RuntimeError(
            "Maximum Dropbox folder depth exceeded."
        )

    entries = _list_folder(
        link,
        parent_path,
        token,
    )

    results = []

    parent_path = _normalize_relative_path(
        parent_path
    )

    for entry in entries:

        tag = entry.get(".tag")

        name = entry.get(
            "name",
            "",
        )

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

        if (
            tag == "file"
            and name.lower().endswith(
                IMAGE_EXTENSIONS
            )
        ):

            results.append({
                "name": name,
                "path": relative_path,
            })

        elif tag == "folder":

            results.extend(
                _collect_files(
                    link,
                    token,
                    relative_path,
                    depth + 1,
                )
            )

    return results


# ============================================================
# DROPBOX DOWNLOAD
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

    # The shared-link file endpoint accepts the
    # shared link and a path relative to the link.
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
            f"Dropbox download error "
            f"({response.status_code}): "
            + _error_text(response)
        )

    return response.content


# ============================================================
# FETCH GALLERY
# ============================================================

def _fetch_gallery(link, token):

    files = _collect_files(
        link,
        token,
    )

    images = []

    errors = []

    for index, item in enumerate(files):

        try:

            original = _download_file(
                link,
                item["path"],
                token,
            )

            preview = image_bytes_preview(
                original
            )

            images.append({
                "name": item["name"],
                "original": original,
                "preview": preview,
            })

        except Exception as exc:

            errors.append(
                f"{item['name']} | "
                f"{item['path']} | "
                f"{exc}"
            )

    return images, errors, len(files)


# ============================================================
# CACHE
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
            "DROPBOX_ACCESS_TOKEN is missing."
        )

    # Diagnostics intentionally bypass cache so the
    # organizer test can inspect the latest result.
    images, errors, listed = _fetch_gallery(
        link,
        token,
    )

    return images, errors, listed


# ============================================================
# DROPBOX GUEST LOADING
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

    images, errors, listed = _cached_gallery(
        link,
        token,
    )

    if listed == 0:

        raise RuntimeError(
            "Dropbox returned zero image files."
        )

    if len(images) == 0:

        error_message = "\n".join(
            errors[:5]
        )

        raise RuntimeError(
            f"Dropbox listed {listed} images, "
            "but none could be downloaded.\n"
            + error_message
        )

    return images


# ============================================================
# CACHE CLEAR
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
            link,
        )

    if not match:

        raise ValueError(
            "Google Drive folder ID not found."
        )

    folder_id = match.group(1)

    params = {
        "q": (
            f"'{folder_id}' in parents "
            "and trashed=false"
        ),
        "fields": "files(id,name,mimeType)",
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

        if item.get(
            "mimeType",
            "",
        ).startswith("image/"):

            download = requests.get(
                (
                    "https://www.googleapis.com/drive/v3/files/"
                    + item["id"]
                    + "?alt=media&key="
                    + key
                ),
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
            "Local folder path does not exist."
        )

    images = []

    for name in sorted(
        os.listdir(path)
    ):

        if name.lower().endswith(
            IMAGE_EXTENSIONS
        ):

            try:

                with open(
                    os.path.join(
                        path,
                        name,
                    ),
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
                pass

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
            "Azure storage connection string is missing."
        )

    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(
        connection
    )

    client = service.get_container_client(
        container.strip()
    )

    images = []

    for blob in client.list_blobs():

        if blob.name.lower().endswith(
            IMAGE_EXTENSIONS
        ):

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
# S3
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

            if name.lower().endswith(
                IMAGE_EXTENSIONS
            ):

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

    link = cfg.get(
        "folder_url",
        "",
    )

    if provider == "dropbox":

        return dropbox_images(
            link
        )

    if provider == "drive":

        return drive_images(
            link
        )

    if provider == "local":

        return local_images(
            link
        )

    if provider == "azure":

        return azure_images(
            link
        )

    if provider == "s3":

        return s3_images(
            link
        )

    if provider == "terabox":

        raise RuntimeError(
            "TeraBox access is not implemented."
        )

    raise ValueError(
        f"Unsupported provider: {provider}"
    )
