import os
import requests
import streamlit as st

from utils import image_bytes_preview


# ============================================================
# COMMON HELPERS
# ============================================================

SUPPORTED_IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
)


def is_image_file(filename):
    return str(filename).lower().endswith(
        SUPPORTED_IMAGE_EXTENSIONS
    )


def make_image_item(name, data):
    return {
        "name": name,
        "bytes": data,
        "preview": image_bytes_preview(data),
    }


# ============================================================
# DROPBOX HELPERS
# ============================================================

def _dropbox_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _dropbox_api_error(response, operation):

    try:
        details = response.json()
    except Exception:
        details = response.text

    raise RuntimeError(
        f"Dropbox {operation} failed "
        f"({response.status_code}): {details}"
    )


def _dropbox_list_folder(token, shared_link, relative_path):

    endpoint = "https://api.dropboxapi.com/2/files/list_folder"

    payload = {
        "path": relative_path,
        "recursive": False,
        "shared_link": {
            "url": shared_link
        },
    }

    response = requests.post(
        endpoint,
        headers=_dropbox_headers(token),
        json=payload,
        timeout=60,
    )

    if response.status_code != 200:
        _dropbox_api_error(response, "folder listing")

    return response.json()


def _dropbox_list_folder_continue(token, cursor):

    endpoint = (
        "https://api.dropboxapi.com/2/files/list_folder/continue"
    )

    response = requests.post(
        endpoint,
        headers=_dropbox_headers(token),
        json={"cursor": cursor},
        timeout=60,
    )

    if response.status_code != 200:
        _dropbox_api_error(response, "pagination")

    return response.json()


def _dropbox_download_shared_file(
    token,
    shared_link,
    relative_file_path,
):

    endpoint = (
        "https://content.dropboxapi.com/2/sharing/"
        "get_shared_link_file"
    )

    api_argument = {
        "url": shared_link,
        "path": relative_file_path,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": (
            __import__("json").dumps(api_argument)
        ),
    }

    response = requests.post(
        endpoint,
        headers=headers,
        timeout=120,
    )

    if response.status_code != 200:
        _dropbox_api_error(
            response,
            f"download of {relative_file_path}",
        )

    return response.content


def _dropbox_join_path(parent, child):

    child = str(child).strip("/")

    if not parent:
        return "/" + child

    return parent.rstrip("/") + "/" + child


# ============================================================
# DROPBOX SHARED FOLDER
# ============================================================

def dropbox_images(link):

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN", ""
    )

    if not token:
        raise RuntimeError(
            "Dropbox access token is missing."
        )

    if not link:
        raise ValueError(
            "Dropbox shared folder link is empty."
        )

    images = []
    folders_to_scan = [""]
    visited = set()

    # --------------------------------------------------------
    # STEP 1: Recursively collect image paths
    # --------------------------------------------------------

    image_files = []

    while folders_to_scan:

        current_path = folders_to_scan.pop(0)

        if current_path in visited:
            continue

        visited.add(current_path)

        data = _dropbox_list_folder(
            token,
            link,
            current_path,
        )

        while True:

            for entry in data.get("entries", []):

                entry_type = entry.get(".tag")
                entry_name = entry.get("name", "")

                # ------------------------------------------------
                # FOLDER
                # ------------------------------------------------

                if entry_type == "folder":

                    folder_path = _dropbox_join_path(
                        current_path,
                        entry_name,
                    )

                    folders_to_scan.append(
                        folder_path
                    )

                # ------------------------------------------------
                # FILE
                # ------------------------------------------------

                elif entry_type == "file":

                    if is_image_file(entry_name):

                        file_path = _dropbox_join_path(
                            current_path,
                            entry_name,
                        )

                        image_files.append({
                            "name": entry_name,
                            "path": file_path,
                            "size": entry.get("size", 0),
                        })

            # ----------------------------------------------------
            # PAGINATION
            # ----------------------------------------------------

            if not data.get("has_more"):
                break

            data = _dropbox_list_folder_continue(
                token,
                data["cursor"],
            )

    # --------------------------------------------------------
    # STEP 2: Download images
    # --------------------------------------------------------

    if not image_files:
        return []

    progress = st.progress(0)

    status = st.empty()

    total = len(image_files)

    for index, item in enumerate(image_files):

        status.text(
            f"Downloading Dropbox photos "
            f"{index + 1}/{total}: {item['name']}"
        )

        data = _dropbox_download_shared_file(
            token,
            link,
            item["path"],
        )

        images.append(
            make_image_item(
                item["name"],
                data,
            )
        )

        progress.progress(
            (index + 1) / total
        )

    progress.empty()
    status.empty()

    return images


# ============================================================
# GOOGLE DRIVE
# ============================================================

def _drive_folder_id(link):

    if not link:
        raise ValueError(
            "Google Drive folder link is empty."
        )

    if "/folders/" in link:

        return (
            link.split("/folders/")[1]
            .split("?")[0]
            .split("/")[0]
        )

    raise ValueError(
        "Invalid Google Drive folder URL."
    )


def drive_images(link):

    api_key = st.secrets.get(
        "GOOGLE_DRIVE_API_KEY", ""
    )

    if not api_key:
        raise RuntimeError(
            "Google Drive API key is missing."
        )

    folder_id = _drive_folder_id(link)

    endpoint = (
        "https://www.googleapis.com/drive/v3/files"
    )

    images = []
    page_token = None

    while True:

        params = {
            "q": (
                f"'{folder_id}' in parents "
                "and trashed=false"
            ),
            "key": api_key,
            "fields": (
                "nextPageToken,"
                "files(id,name,mimeType)"
            ),
            "pageSize": 1000,
        }

        if page_token:
            params["pageToken"] = page_token

        response = requests.get(
            endpoint,
            params=params,
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        files = data.get("files", [])

        for file in files:

            if not file.get(
                "mimeType", ""
            ).startswith("image/"):
                continue

            download_endpoint = (
                "https://www.googleapis.com/drive/v3/files/"
                + file["id"]
            )

            download_response = requests.get(
                download_endpoint,
                params={
                    "alt": "media",
                    "key": api_key,
                },
                timeout=120,
            )

            download_response.raise_for_status()

            images.append(
                make_image_item(
                    file.get("name", "image"),
                    download_response.content,
                )
            )

        page_token = data.get(
            "nextPageToken"
        )

        if not page_token:
            break

    return images


# ============================================================
# LOCAL FOLDER
# ============================================================

def local_images(path):

    if not path:
        raise ValueError(
            "Local folder path is empty."
        )

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Folder does not exist: {path}"
        )

    images = []

    for root, _, filenames in os.walk(path):

        for filename in filenames:

            if not is_image_file(filename):
                continue

            full_path = os.path.join(
                root,
                filename,
            )

            try:

                with open(
                    full_path,
                    "rb",
                ) as file:

                    data = file.read()

                images.append(
                    make_image_item(
                        filename,
                        data,
                    )
                )

            except Exception as error:

                st.warning(
                    f"Unable to read {filename}: "
                    f"{error}"
                )

    return images


# ============================================================
# AZURE BLOB STORAGE
# ============================================================

def azure_images(container_name):

    connection_string = st.secrets.get(
        "AZURE_STORAGE_CONNECTION_STRING", ""
    )

    if not connection_string:
        raise RuntimeError(
            "Azure Storage connection string is missing."
        )

    if not container_name:
        raise ValueError(
            "Azure container name is missing."
        )

    try:

        from azure.storage.blob import (
            BlobServiceClient
        )

    except ImportError:

        raise RuntimeError(
            "azure-storage-blob is not installed."
        )

    service = BlobServiceClient.from_connection_string(
        connection_string
    )

    container = service.get_container_client(
        container_name
    )

    images = []

    for blob in container.list_blobs():

        if not is_image_file(blob.name):
            continue

        blob_client = container.get_blob_client(
            blob.name
        )

        data = (
            blob_client
            .download_blob()
            .readall()
        )

        images.append(
            make_image_item(
                blob.name,
                data,
            )
        )

    return images


# ============================================================
# AMAZON S3
# ============================================================

def s3_images(bucket):

    access_key = st.secrets.get(
        "AWS_ACCESS_KEY_ID", ""
    )

    secret_key = st.secrets.get(
        "AWS_SECRET_ACCESS_KEY", ""
    )

    region = st.secrets.get(
        "AWS_REGION", "ap-south-1"
    )

    if not access_key or not secret_key:
        raise RuntimeError(
            "AWS credentials are missing."
        )

    if not bucket:
        raise ValueError(
            "S3 bucket name is missing."
        )

    try:

        import boto3

    except ImportError:

        raise RuntimeError(
            "boto3 is not installed."
        )

    client = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )

    images = []

    paginator = client.get_paginator(
        "list_objects_v2"
    )

    for page in paginator.paginate(
        Bucket=bucket
    ):

        for item in page.get(
            "Contents", []
        ):

            key = item.get(
                "Key", ""
            )

            if not is_image_file(key):
                continue

            response = client.get_object(
                Bucket=bucket,
                Key=key,
            )

            data = (
                response["Body"].read()
            )

            images.append(
                make_image_item(
                    key,
                    data,
                )
            )

    return images


# ============================================================
# GOOGLE PHOTOS
# ============================================================

def google_photos_images(link):

    raise NotImplementedError(
        "Google Photos Picker API integration "
        "is not yet implemented."
    )


# ============================================================
# TERABOX
# ============================================================

def terabox_images(link):

    raise NotImplementedError(
        "TeraBox integration is not yet implemented."
    )


# ============================================================
# PROVIDER ROUTER
# ============================================================

def get_gallery_images(cfg):

    provider = (
        cfg.get("provider", "")
        .lower()
        .strip()
    )

    folder_url = (
        cfg.get("folder_url", "")
        .strip()
    )

    if provider == "dropbox":
        return dropbox_images(folder_url)

    if provider == "drive":
        return drive_images(folder_url)

    if provider == "local":
        return local_images(folder_url)

    if provider == "azure":
        return azure_images(folder_url)

    if provider == "s3":
        return s3_images(folder_url)

    if provider == "google_photos":
        return google_photos_images(folder_url)

    if provider == "terabox":
        return terabox_images(folder_url)

    raise ValueError(
        f"Unsupported gallery provider: {provider}"
    )
