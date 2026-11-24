
import os
import re
import json
import requests
import streamlit as st

from utils import image_bytes_preview

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


# =========================================================
# GOOGLE DRIVE
# =========================================================

def _drive_folder_id(link):

    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", link)

    if m:
        return m.group(1)

    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", link)

    if m:
        return m.group(1)

    raise ValueError("Could not extract Google Drive folder ID.")


def drive_images(link):

    key = st.secrets.get(
        "GOOGLE_DRIVE_API_KEY",
        os.getenv("GOOGLE_DRIVE_API_KEY", "")
    )

    if not key:
        raise RuntimeError("Configure GOOGLE_DRIVE_API_KEY in Secrets.")

    folder_id = _drive_folder_id(link)

    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,mimeType)",
        "pageSize": 1000,
        "key": key
    }

    response = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        params=params,
        timeout=30
    )

    response.raise_for_status()

    items = []

    for file in response.json().get("files", []):

        if file.get("mimeType", "").startswith("image/"):

            download = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file['id']}",
                params={"alt": "media", "key": key},
                timeout=60
            )

            download.raise_for_status()

            image_data = download.content

            items.append({
                "name": file.get("name", file["id"]),
                "original": image_data,
                "preview": image_bytes_preview(image_data)
            })

    return items


# =========================================================
# DROPBOX
# =========================================================

def _dropbox_error(response):

    try:
        data = response.json()
    except Exception:
        data = response.text

    return (
        f"Dropbox API HTTP {response.status_code}: "
        f"{data}"
    )


@st.cache_data(ttl=1800, max_entries=5, show_spinner=False)
def _cached_dropbox_gallery(link, token):

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    endpoint = (
        "https://api.dropboxapi.com/2/files/"
        "list_shared_link_files"
    )

    response = requests.post(
        endpoint,
        headers=headers,
        json={"url": link, "limit": 1000},
        timeout=60
    )

    if not response.ok:
        raise RuntimeError(_dropbox_error(response))

    data = response.json()

    entries = list(data.get("entries", []))

    cursor = data.get("cursor")
    has_more = data.get("has_more", False)

    # Pagination
    while has_more and cursor:

        page = requests.post(
            "https://api.dropboxapi.com/2/files/"
            "list_shared_link_files/continue",
            headers=headers,
            json={"cursor": cursor},
            timeout=60
        )

        if not page.ok:
            raise RuntimeError(_dropbox_error(page))

        page_data = page.json()

        entries.extend(page_data.get("entries", []))

        cursor = page_data.get("cursor")
        has_more = page_data.get("has_more", False)

    items = []

    # Download image files
    for entry in entries:

        if entry.get(".tag") != "file":
            continue

        name = entry.get("name", "")

        if not name.lower().endswith(IMAGE_EXTENSIONS):
            continue

        path = entry.get("path_lower") or entry.get("path_display")

        if not path:
            continue

        download_headers = {
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": path})
        }

        download = requests.post(
            "https://content.dropboxapi.com/2/files/download",
            headers=download_headers,
            timeout=120
        )

        if not download.ok:
            raise RuntimeError(
                f"Failed to download {name}: "
                f"{_dropbox_error(download)}"
            )

        image_data = download.content

        items.append({
            "name": name,
            "original": image_data,
            "preview": image_bytes_preview(image_data)
        })

    return items


def dropbox_images(link):

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN",
        os.getenv("DROPBOX_ACCESS_TOKEN", "")
    )

    if not token:
        raise RuntimeError(
            "Configure DROPBOX_ACCESS_TOKEN in Streamlit Secrets."
        )

    return _cached_dropbox_gallery(
        link.strip(),
        token
    )


def clear_dropbox_gallery_cache():

    _cached_dropbox_gallery.clear()


# =========================================================
# LOCAL FOLDER
# =========================================================

def local_images(path):

    if not os.path.isdir(path):
        raise ValueError("The folder path must exist on the app host.")

    items = []

    for name in sorted(os.listdir(path)):

        if not name.lower().endswith(IMAGE_EXTENSIONS):
            continue

        full_path = os.path.join(path, name)

        try:

            with open(full_path, "rb") as file:
                image_data = file.read()

            items.append({
                "name": name,
                "original": image_data,
                "preview": image_bytes_preview(image_data)
            })

        except Exception:
            continue

    return items


# =========================================================
# AZURE
# =========================================================

def azure_images(container_name):

    connection = st.secrets.get(
        "AZURE_STORAGE_CONNECTION_STRING",
        os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    )

    if not connection:
        raise RuntimeError(
            "Configure AZURE_STORAGE_CONNECTION_STRING in Secrets."
        )

    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(connection)

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

            image_data = client.download_blob(blob.name).readall()

            items.append({
                "name": blob.name,
                "original": image_data,
                "preview": image_bytes_preview(image_data)
            })

    return items


# =========================================================
# AMAZON S3
# =========================================================

def s3_images(bucket):

    access = st.secrets.get(
        "AWS_ACCESS_KEY_ID",
        os.getenv("AWS_ACCESS_KEY_ID", "")
    )

    secret = st.secrets.get(
        "AWS_SECRET_ACCESS_KEY",
        os.getenv("AWS_SECRET_ACCESS_KEY", "")
    )

    region = st.secrets.get(
        "AWS_REGION",
        os.getenv("AWS_REGION", "")
    )

    if not access or not secret:
        raise RuntimeError(
            "Configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
        )

    from boto3.session import Session

    session = Session(
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region or None
    )

    s3 = session.client("s3")

    items = []

    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket.strip()):

        for obj in page.get("Contents", []):

            name = obj["Key"]

            if name.lower().endswith(IMAGE_EXTENSIONS):

                image_data = s3.get_object(
                    Bucket=bucket.strip(),
                    Key=name
                )["Body"].read()

                items.append({
                    "name": name,
                    "original": image_data,
                    "preview": image_bytes_preview(image_data)
                })

    return items


# =========================================================
# TERABOX
# =========================================================

def terabox_images(link):

    raise RuntimeError(
        "TeraBox shared-link access is not supported yet."
    )


# =========================================================
# GALLERY ROUTER
# =========================================================

def get_gallery_images(cfg):

    provider = cfg.get("provider")

    link = cfg.get("folder_url", "").strip()

    if not link:
        raise ValueError(
            "Organizer has not saved a gallery source."
        )

    if provider == "drive":
        return drive_images(link)

    if provider == "dropbox":
        return dropbox_images(link)

    if provider == "local":
        return local_images(link)

    if provider == "azure":
        return azure_images(link)

    if provider == "s3":
        return s3_images(link)

    if provider == "terabox":
        return terabox_images(link)

    raise ValueError(
        f"Unsupported gallery provider: {provider}"
    )
