
import os
import json
import requests
import streamlit as st

from utils import image_bytes_preview

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


# =========================================================
# DROPBOX HELPERS
# =========================================================

def _dropbox_headers(token):

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def _dropbox_error(response):

    try:
        details = response.json()
    except Exception:
        details = response.text

    return f"Dropbox API HTTP {response.status_code}: {details}"


def _dropbox_list_folder(link, relative_path, token):

    url = "https://api.dropboxapi.com/2/files/list_folder"

    payload = {
        "path": relative_path,
        "shared_link": {
            "url": link
        },
        "recursive": False
    }

    response = requests.post(
        url,
        headers=_dropbox_headers(token),
        json=payload,
        timeout=60
    )

    if not response.ok:
        raise RuntimeError(_dropbox_error(response))

    data = response.json()

    entries = list(data.get("entries", []))

    # Pagination
    while data.get("has_more"):

        continue_url = (
            "https://api.dropboxapi.com/2/files/list_folder/continue"
        )

        page = requests.post(
            continue_url,
            headers=_dropbox_headers(token),
            json={"cursor": data["cursor"]},
            timeout=60
        )

        if not page.ok:
            raise RuntimeError(_dropbox_error(page))

        data = page.json()

        entries.extend(data.get("entries", []))

    return entries


def _dropbox_download_shared_file(link, relative_path, token):

    url = (
        "https://content.dropboxapi.com/2/sharing/"
        "get_shared_link_file"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps({
            "url": link,
            "path": relative_path
        })
    }

    response = requests.post(
        url,
        headers=headers,
        timeout=120
    )

    if not response.ok:
        raise RuntimeError(_dropbox_error(response))

    return response.content


# =========================================================
# DROPBOX GALLERY
# =========================================================

@st.cache_data(ttl=1800, max_entries=5, show_spinner=False)
def _cached_dropbox_gallery(link, token):

    images = []

    # Folder paths relative to the shared-link root
    folders_to_process = [""]

    while folders_to_process:

        current_folder = folders_to_process.pop(0)

        entries = _dropbox_list_folder(
            link,
            current_folder,
            token
        )

        for entry in entries:

            tag = entry.get(".tag")
            name = entry.get("name", "")

            if tag == "folder":

                if current_folder:

                    child_path = (
                        current_folder.rstrip("/")
                        + "/"
                        + name
                    )

                else:

                    child_path = "/" + name

                folders_to_process.append(child_path)

            elif tag == "file":

                if not name.lower().endswith(IMAGE_EXTENSIONS):
                    continue

                if current_folder:

                    relative_path = (
                        current_folder.rstrip("/")
                        + "/"
                        + name
                    )

                else:

                    relative_path = "/" + name

                image_data = _dropbox_download_shared_file(
                    link,
                    relative_path,
                    token
                )

                images.append({
                    "name": name,
                    "original": image_data,
                    "preview": image_bytes_preview(image_data)
                })

    return images


def dropbox_images(link):

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN",
        os.getenv("DROPBOX_ACCESS_TOKEN", "")
    )

    if not token:

        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing from Streamlit Secrets."
        )

    return _cached_dropbox_gallery(
        link.strip(),
        token
    )


def clear_dropbox_gallery_cache():

    _cached_dropbox_gallery.clear()


# =========================================================
# GOOGLE DRIVE
# =========================================================

def _drive_folder_id(link):

    import re

    match = re.search(
        r"/folders/([a-zA-Z0-9_-]+)",
        link
    )

    if match:
        return match.group(1)

    match = re.search(
        r"[?&]id=([a-zA-Z0-9_-]+)",
        link
    )

    if match:
        return match.group(1)

    raise ValueError("Could not extract Google Drive folder ID.")


def drive_images(link):

    key = st.secrets.get(
        "GOOGLE_DRIVE_API_KEY",
        os.getenv("GOOGLE_DRIVE_API_KEY", "")
    )

    if not key:

        raise RuntimeError(
            "Configure GOOGLE_DRIVE_API_KEY in Secrets."
        )

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

        if not file.get("mimeType", "").startswith("image/"):
            continue

        download = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file['id']}",
            params={
                "alt": "media",
                "key": key
            },
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
# LOCAL FOLDER
# =========================================================

def local_images(path):

    if not os.path.isdir(path):

        raise ValueError(
            "The folder path must exist on the app host."
        )

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
# AZURE STORAGE
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

    container = container_name.strip()

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
            "Configure AWS credentials in Streamlit Secrets."
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

    for page in paginator.paginate(
        Bucket=bucket.strip()
    ):

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

    link = cfg.get(
        "folder_url",
        ""
    ).strip()

    if not link:

        raise ValueError(
            "The organizer has not saved a gallery source."
        )

    if provider == "dropbox":
        return dropbox_images(link)

    if provider == "drive":
        return drive_images(link)

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
