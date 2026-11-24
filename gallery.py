import os
import json
import requests
import streamlit as st

from utils import image_bytes_preview

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

LIST_URL = "https://api.dropboxapi.com/2/files/list_folder"
CONTINUE_URL = "https://api.dropboxapi.com/2/files/list_folder/continue"
DOWNLOAD_URL = "https://content.dropboxapi.com/2/sharing/get_shared_link_file"


def _secret(name):
    try:
        return st.secrets.get(name, os.getenv(name, ""))
    except Exception:
        return os.getenv(name, "")


def _clean_relative_path(path):
    if not path:
        return ""

    # Dropbox paths used with a shared-link root are relative.
    return path.strip().lstrip("/")


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _error(response):
    try:
        return json.dumps(response.json(), indent=2)
    except Exception:
        return response.text[:2000]


def _list_folder(link, relative_path, token):

    relative_path = _clean_relative_path(relative_path)

    payload = {
        "path": relative_path,
        "recursive": False,
        "shared_link": {
            "url": link
        },
    }

    response = requests.post(
        LIST_URL,
        headers=_headers(token),
        json=payload,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Dropbox list_folder failed ({response.status_code}):\n"
            + _error(response)
        )

    data = response.json()

    entries = list(data.get("entries", []))

    while data.get("has_more"):

        response = requests.post(
            CONTINUE_URL,
            headers=_headers(token),
            json={"cursor": data["cursor"]},
            timeout=60,
        )

        if not response.ok:
            raise RuntimeError(
                f"Dropbox pagination failed ({response.status_code}):\n"
                + _error(response)
            )

        data = response.json()

        entries.extend(data.get("entries", []))

    return entries


def _entry_relative_path(entry, parent_path):

    name = entry.get("name", "")

    # Use the parent's relative path and the entry name to
    # consistently construct a path relative to the shared link.
    if parent_path:
        return f"{parent_path.rstrip('/')}/{name}"

    return name


def _collect_files(link, token, folder_path="", depth=0):

    if depth > 50:
        raise RuntimeError(
            "Dropbox folder nesting exceeds the supported depth."
        )

    entries = _list_folder(
        link,
        folder_path,
        token,
    )

    files = []

    for entry in entries:

        tag = entry.get(".tag")
        name = entry.get("name", "")

        relative_path = _entry_relative_path(
            entry,
            folder_path,
        )

        if (
            tag == "file"
            and name.lower().endswith(IMAGE_EXTENSIONS)
        ):

            files.append({
                "name": name,
                "path": relative_path,
            })

        elif tag == "folder":

            files.extend(
                _collect_files(
                    link,
                    token,
                    relative_path,
                    depth + 1,
                )
            )

    return files


def _download_file(link, path, token):

    path = _clean_relative_path(path)

    args = {
        "url": link,
        "path": path,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": json.dumps(args),
    }

    response = requests.post(
        DOWNLOAD_URL,
        headers=headers,
        timeout=90,
    )

    if not response.ok:
        raise RuntimeError(
            f"Dropbox download failed ({response.status_code}):\n"
            + _error(response)
        )

    return response.content


@st.cache_data(
    ttl=1800,
    max_entries=3,
    show_spinner=False,
)
def _cached_gallery(link, token):

    files = _collect_files(
        link,
        token,
    )

    gallery = []
    errors = []

    for item in files:

        try:

            original = _download_file(
                link,
                item["path"],
                token,
            )

            preview = image_bytes_preview(original)

            gallery.append({
                "name": item["name"],
                "original": original,
                "preview": preview,
            })

        except Exception as exc:

            errors.append(
                f"{item['name']}: {exc}"
            )

    return gallery, errors, len(files)


def dropbox_images(link):

    if isinstance(link, dict):
        link = link.get("url", "")

    if not isinstance(link, str):
        raise ValueError(
            "Dropbox shared link must be a string."
        )

    link = link.strip()

    if not link:
        raise ValueError(
            "Dropbox shared link is empty."
        )

    token = _secret(
        "DROPBOX_ACCESS_TOKEN"
    )

    if not token:
        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing from Streamlit secrets."
        )

    gallery, errors, total_listed = _cached_gallery(
        link,
        token,
    )

    if total_listed == 0:
        raise RuntimeError(
            "Dropbox connection succeeded, but the shared folder "
            "returned no image files. Check the folder link, "
            "permissions and whether the folder contains images."
        )

    if not gallery:

        message = "\n".join(errors[:5])

        raise RuntimeError(
            f"Dropbox listed {total_listed} image files, "
            "but none could be downloaded.\n\n"
            + message
        )

    return gallery


def dropbox_diagnostics(link):

    if isinstance(link, dict):
        link = link.get("url", "")

    link = (link or "").strip()

    token = _secret(
        "DROPBOX_ACCESS_TOKEN"
    )

    if not token:
        raise RuntimeError(
            "DROPBOX_ACCESS_TOKEN is missing."
        )

    gallery, errors, listed = _cached_gallery(
        link,
        token,
    )

    return gallery, errors, listed


def clear_dropbox_gallery_cache():
    _cached_gallery.clear()


# Compatibility alias
clear_gallery_cache = clear_dropbox_gallery_cache


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
            "Unable to extract Google Drive folder ID."
        )

    folder_id = match.group(1)

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

    images = []

    for file_item in response.json().get("files", []):

        if file_item.get("mimeType", "").startswith("image/"):

            download = requests.get(
                f"https://www.googleapis.com/drive/v3/files/"
                f"{file_item['id']}?alt=media&key={key}",
                timeout=60,
            )

            download.raise_for_status()

            original = download.content

            images.append({
                "name": file_item["name"],
                "original": original,
                "preview": image_bytes_preview(original),
            })

    return images


# ============================================================
# LOCAL
# ============================================================

def local_images(path):

    if not os.path.isdir(path):
        raise ValueError(
            "Local folder does not exist."
        )

    images = []

    for name in sorted(os.listdir(path)):

        if name.lower().endswith(IMAGE_EXTENSIONS):

            try:

                with open(
                    os.path.join(path, name),
                    "rb",
                ) as f:

                    original = f.read()

                images.append({
                    "name": name,
                    "original": original,
                    "preview": image_bytes_preview(original),
                })

            except Exception:
                pass

    return images


# ============================================================
# AZURE
# ============================================================

def azure_images(container):

    connection = _secret(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    if not connection:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is missing."
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

        if blob.name.lower().endswith(IMAGE_EXTENSIONS):

            original = client.download_blob(
                blob.name
            ).readall()

            images.append({
                "name": blob.name,
                "original": original,
                "preview": image_bytes_preview(original),
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

    s3 = Session(
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region or None,
    ).client("s3")

    images = []

    for page in s3.get_paginator(
        "list_objects_v2"
    ).paginate(
        Bucket=bucket.strip()
    ):

        for obj in page.get("Contents", []):

            name = obj["Key"]

            if name.lower().endswith(IMAGE_EXTENSIONS):

                original = s3.get_object(
                    Bucket=bucket.strip(),
                    Key=name,
                )["Body"].read()

                images.append({
                    "name": name,
                    "original": original,
                    "preview": image_bytes_preview(original),
                })

    return images


# ============================================================
# PROVIDER ROUTER
# ============================================================

def get_gallery_images(cfg):

    if not isinstance(cfg, dict):
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
        raise RuntimeError(
            "TeraBox is not implemented."
        )

    raise ValueError(
        f"Unsupported provider: {provider}"
    )
