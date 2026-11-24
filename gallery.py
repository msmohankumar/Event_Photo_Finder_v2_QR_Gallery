import os
import re
import json
import requests
import streamlit as st

from utils import image_bytes_preview

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

DROPBOX_LIST_URL = "https://api.dropboxapi.com/2/files/list_folder"
DROPBOX_CONTINUE_URL = "https://api.dropboxapi.com/2/files/list_folder/continue"
DROPBOX_DOWNLOAD_URL = "https://content.dropboxapi.com/2/sharing/get_shared_link_file"


# ============================================================
# SECRETS
# ============================================================

def _get_secret(name):
    try:
        return st.secrets.get(name, os.getenv(name, ""))
    except Exception:
        return os.getenv(name, "")


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize_link(link):
    if isinstance(link, dict):
        link = link.get("url", "")

    if not isinstance(link, str):
        link = ""

    link = link.strip()

    if not link:
        raise ValueError("Gallery folder link/path is empty.")

    return link


# ============================================================
# GOOGLE DRIVE
# ============================================================

def _drive_folder_id(link):
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", link)

    if match:
        return match.group(1)

    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", link)

    if match:
        return match.group(1)

    raise ValueError(
        "Could not extract Google Drive folder ID from the link."
    )


def drive_images(link):

    key = _get_secret("GOOGLE_DRIVE_API_KEY")

    if not key:
        raise RuntimeError(
            "Configure GOOGLE_DRIVE_API_KEY in Streamlit secrets."
        )

    folder_id = _drive_folder_id(link)

    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
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

    items = []

    for file_item in response.json().get("files", []):

        if file_item.get("mimeType", "").startswith("image/"):

            download_response = requests.get(
                f"https://www.googleapis.com/drive/v3/files/"
                f"{file_item['id']}?alt=media&key={key}",
                timeout=60,
            )

            download_response.raise_for_status()

            image_data = download_response.content

            items.append({
                "name": file_item.get("name", file_item["id"]),
                "original": image_data,
                "preview": image_bytes_preview(image_data),
            })

    return items


# ============================================================
# DROPBOX
# ============================================================

def _dropbox_headers(token):

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _dropbox_error(response):

    try:
        return json.dumps(response.json(), indent=2)

    except Exception:
        return response.text[:1500]


def _list_shared_folder(link, folder_path, token):

    payload = {
        "path": folder_path,
        "recursive": False,
        "shared_link": {
            "url": link
        },
    }

    response = requests.post(
        DROPBOX_LIST_URL,
        headers=_dropbox_headers(token),
        json=payload,
        timeout=60,
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox folder listing failed:\n"
            + _dropbox_error(response)
        )

    data = response.json()

    entries = list(data.get("entries", []))

    while data.get("has_more"):

        response = requests.post(
            DROPBOX_CONTINUE_URL,
            headers=_dropbox_headers(token),
            json={"cursor": data["cursor"]},
            timeout=60,
        )

        if not response.ok:

            raise RuntimeError(
                "Dropbox pagination failed:\n"
                + _dropbox_error(response)
            )

        data = response.json()

        entries.extend(data.get("entries", []))

    return entries


def _collect_shared_images(link, token, folder_path=""):

    collected = []

    entries = _list_shared_folder(
        link,
        folder_path,
        token,
    )

    for entry in entries:

        tag = entry.get(".tag")

        name = entry.get("name", "")

        path = (
            entry.get("path_lower")
            or entry.get("path_display")
        )

        if (
            tag == "file"
            and name.lower().endswith(IMAGE_EXTENSIONS)
            and path
        ):

            collected.append({
                "name": name,
                "path": path,
            })

        elif tag == "folder" and path:

            collected.extend(
                _collect_shared_images(
                    link,
                    token,
                    path,
                )
            )

    return collected


def _download_shared_file(link, path, token):

    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps({
            "url": link,
            "path": path,
        }),
    }

    response = requests.post(
        DROPBOX_DOWNLOAD_URL,
        headers=headers,
        timeout=60,
    )

    if not response.ok:

        raise RuntimeError(
            "Dropbox file download failed:\n"
            + _dropbox_error(response)
        )

    return response.content


@st.cache_data(
    ttl=1800,
    max_entries=3,
    show_spinner=False,
)
def _cached_dropbox_gallery(link, token):

    files = _collect_shared_images(link, token)

    images = []

    for item in files:

        try:

            image_data = _download_shared_file(
                link,
                item["path"],
                token,
            )

            images.append({
                "name": item["name"],
                "original": image_data,
                "preview": image_bytes_preview(image_data),
            })

        except Exception as exc:

            images.append({
                "name": item["name"],
                "original": b"",
                "preview": b"",
                "download_error": str(exc),
            })

    return images


def dropbox_images(link):

    link = _normalize_link(link)

    token = _get_secret("DROPBOX_ACCESS_TOKEN")

    if not token:

        raise RuntimeError(
            "Configure DROPBOX_ACCESS_TOKEN in Streamlit secrets."
        )

    images = _cached_dropbox_gallery(
        link,
        token,
    )

    failed = [
        image
        for image in images
        if image.get("download_error")
    ]

    usable = [
        image
        for image in images
        if image.get("original")
    ]

    if failed and not usable:

        raise RuntimeError(
            "Dropbox listed files but none could be downloaded. "
            "First error: "
            + failed[0]["download_error"]
        )

    return usable


def clear_dropbox_gallery_cache():

    _cached_dropbox_gallery.clear()


# Compatibility alias
clear_gallery_cache = clear_dropbox_gallery_cache


# ============================================================
# LOCAL FOLDER
# ============================================================

def local_images(path):

    if not os.path.isdir(path):

        raise ValueError(
            "The folder path must exist on the Streamlit server/host."
        )

    items = []

    for name in sorted(os.listdir(path)):

        if name.lower().endswith(IMAGE_EXTENSIONS):

            try:

                file_path = os.path.join(path, name)

                with open(file_path, "rb") as file:

                    image_data = file.read()

                items.append({
                    "name": name,
                    "original": image_data,
                    "preview": image_bytes_preview(image_data),
                })

            except Exception:

                pass

    return items


# ============================================================
# AZURE STORAGE
# ============================================================

def azure_images(container_name):

    connection_string = _get_secret(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    if not connection_string:

        raise RuntimeError(
            "Configure AZURE_STORAGE_CONNECTION_STRING "
            "in Streamlit secrets."
        )

    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(
        connection_string
    )

    container = (
        container_name.strip()
        .replace("https://", "")
        .strip("/")
    )

    if container.startswith("blob.core.windows.net/"):

        container = container.split("/", 1)[1]

    container = container.split("/", 1)[0]

    client = service.get_container_client(container)

    items = []

    for blob in client.list_blobs():

        if blob.name.lower().endswith(IMAGE_EXTENSIONS):

            image_data = client.download_blob(
                blob.name
            ).readall()

            items.append({
                "name": blob.name,
                "original": image_data,
                "preview": image_bytes_preview(image_data),
            })

    return items


# ============================================================
# AMAZON S3
# ============================================================

def s3_images(bucket):

    access_key = _get_secret(
        "AWS_ACCESS_KEY_ID"
    )

    secret_key = _get_secret(
        "AWS_SECRET_ACCESS_KEY"
    )

    region = _get_secret(
        "AWS_REGION"
    )

    if not access_key or not secret_key:

        raise RuntimeError(
            "Configure AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in Streamlit secrets."
        )

    from boto3.session import Session

    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region or None,
    )

    s3 = session.client("s3")

    items = []

    paginator = s3.get_paginator(
        "list_objects_v2"
    )

    for page in paginator.paginate(
        Bucket=bucket.strip()
    ):

        for obj in page.get("Contents", []):

            name = obj["Key"]

            if name.lower().endswith(IMAGE_EXTENSIONS):

                image_data = s3.get_object(
                    Bucket=bucket.strip(),
                    Key=name,
                )["Body"].read()

                items.append({
                    "name": name,
                    "original": image_data,
                    "preview": image_bytes_preview(image_data),
                })

    return items


# ============================================================
# TERABOX
# ============================================================

def terabox_images(link):

    raise RuntimeError(
        "TeraBox shared-link access is not supported yet."
    )


# ============================================================
# MAIN PROVIDER ROUTER
# ============================================================

def get_gallery_images(cfg):

    if not isinstance(cfg, dict):

        raise TypeError(
            "get_gallery_images expects a configuration dictionary."
        )

    provider = cfg.get("provider", "")

    link = _normalize_link(
        cfg.get("folder_url", "")
    )

    if provider == "drive":

        return drive_images(link)

    elif provider == "dropbox":

        return dropbox_images(link)

    elif provider == "local":

        return local_images(link)

    elif provider == "azure":

        return azure_images(link)

    elif provider == "s3":

        return s3_images(link)

    elif provider == "terabox":

        return terabox_images(link)

    else:

        raise ValueError(
            f"Unsupported gallery provider: {provider}"
        )
