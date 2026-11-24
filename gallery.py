import os
import io
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
)


def is_image_file(filename):
    return str(filename).lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)


def make_image_item(name, data):
    return {
        "name": name,
        "bytes": data,
        "preview": image_bytes_preview(data),
    }


# ============================================================
# GOOGLE DRIVE
# ============================================================

def _drive_folder_id(link):

    if not link:
        raise ValueError("Google Drive folder link is empty.")

    if "/folders/" in link:
        return link.split("/folders/")[1].split("?")[0]

    raise ValueError("Invalid Google Drive folder URL.")


def drive_images(link):

    api_key = st.secrets.get("GOOGLE_DRIVE_API_KEY", "")

    if not api_key:
        raise RuntimeError("Google Drive API key is missing.")

    folder_id = _drive_folder_id(link)

    headers = {
        "Accept": "application/json"
    }

    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "key": api_key,
        "fields": "files(id,name,mimeType)",
        "pageSize": 1000,
    }

    endpoint = "https://www.googleapis.com/drive/v3/files"

    response = requests.get(
        endpoint,
        headers=headers,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    files = response.json().get("files", [])

    images = []

    for file in files:

        if file.get("mimeType", "").startswith("image/"):

            download_url = (
                "https://www.googleapis.com/drive/v3/files/"
                + file["id"]
            )

            download_params = {
                "alt": "media",
                "key": api_key,
            }

            download_response = requests.get(
                download_url,
                params=download_params,
                timeout=60,
            )

            download_response.raise_for_status()

            images.append(
                make_image_item(
                    file.get("name", "image"),
                    download_response.content,
                )
            )

    return images


# ============================================================
# DROPBOX
# ============================================================

def dropbox_images(link):

    token = st.secrets.get("DROPBOX_ACCESS_TOKEN", "")

    if not token:
        raise RuntimeError("Dropbox access token is missing.")

    if not link:
        raise ValueError("Dropbox shared folder link is empty.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    list_endpoint = (
        "https://api.dropboxapi.com/2/files/list_folder"
    )

    continue_endpoint = (
        "https://api.dropboxapi.com/2/files/list_folder/continue"
    )

    download_endpoint = (
        "https://content.dropboxapi.com/2/sharing/get_shared_link_file"
    )

    # Shared-link listing is non-recursive.
    # We traverse subfolders manually using a queue.
    folders_to_scan = [""]

    visited_folders = set()
    image_entries = []

    while folders_to_scan:

        current_path = folders_to_scan.pop(0)

        if current_path in visited_folders:
            continue

        visited_folders.add(current_path)

        payload = {
            "path": current_path,
            "recursive": False,
            "shared_link": {
                "url": link
            },
        }

        response = requests.post(
            list_endpoint,
            headers=headers,
            json=payload,
            timeout=60,
        )

        if response.status_code != 200:
            raise RuntimeError(
                "Dropbox folder listing failed "
                f"({response.status_code}): {response.text}"
            )

        data = response.json()

        while True:

            entries = data.get("entries", [])

            for entry in entries:

                entry_type = entry.get(".tag")
                entry_name = entry.get("name", "")

                # Add subfolders to the traversal queue
                if entry_type == "folder":

                    folder_path = entry.get("path_lower")

                    if folder_path:
                        folders_to_scan.append(folder_path)

                    continue

                # Collect image files
                if entry_type == "file" and is_image_file(entry_name):

                    image_entries.append(entry)

            if not data.get("has_more"):
                break

            continue_payload = {
                "cursor": data["cursor"]
            }

            continue_response = requests.post(
                continue_endpoint,
                headers=headers,
                json=continue_payload,
                timeout=60,
            )

            if continue_response.status_code != 200:
                raise RuntimeError(
                    "Dropbox pagination failed "
                    f"({continue_response.status_code}): "
                    f"{continue_response.text}"
                )

            data = continue_response.json()

    # --------------------------------------------------------
    # Download image files from the shared link
    # --------------------------------------------------------

    images = []

    for entry in image_entries:

        file_name = entry.get("name", "image")

        # Use the shared-link download endpoint
        download_headers = {
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": (
                '{"url":"' + link.replace('"', '\\"') + '",'
                '"path":"' +
                entry.get("path_lower", "").replace('"', '\\"') +
                '"}'
            ),
        }

        download_response = requests.post(
            download_endpoint,
            headers=download_headers,
            timeout=120,
        )

        if download_response.status_code != 200:

            raise RuntimeError(
                f"Dropbox download failed for {file_name} "
                f"({download_response.status_code}): "
                f"{download_response.text}"
            )

        images.append(
            make_image_item(
                file_name,
                download_response.content,
            )
        )

    return images


# ============================================================
# LOCAL FOLDER
# ============================================================

def local_images(path):

    if not path:
        raise ValueError("Local folder path is empty.")

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Folder does not exist: {path}"
        )

    images = []

    for root, _, filenames in os.walk(path):

        for filename in filenames:

            if not is_image_file(filename):
                continue

            full_path = os.path.join(root, filename)

            try:

                with open(full_path, "rb") as file:
                    data = file.read()

                images.append(
                    make_image_item(filename, data)
                )

            except Exception as e:

                st.warning(
                    f"Unable to read {filename}: {e}"
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
        from azure.storage.blob import BlobServiceClient

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

        data = blob_client.download_blob().readall()

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

        for item in page.get("Contents", []):

            key = item.get("Key", "")

            if not is_image_file(key):
                continue

            response = client.get_object(
                Bucket=bucket,
                Key=key,
            )

            data = response["Body"].read()

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
        "Google Photos Picker API and OAuth integration "
        "are not yet implemented."
    )


# ============================================================
# TERABOX
# ============================================================

def terabox_images(link):

    raise NotImplementedError(
        "TeraBox API integration is not yet implemented."
    )


# ============================================================
# GALLERY ROUTER
# ============================================================

def get_gallery_images(cfg):

    provider = cfg.get("provider", "").lower().strip()

    folder_url = cfg.get("folder_url", "").strip()

    # --------------------------------------------------------
    # Dropbox
    # --------------------------------------------------------

    if provider == "dropbox":

        return dropbox_images(folder_url)

    # --------------------------------------------------------
    # Google Drive
    # --------------------------------------------------------

    if provider == "drive":

        return drive_images(folder_url)

    # --------------------------------------------------------
    # Local folder
    # --------------------------------------------------------

    if provider == "local":

        return local_images(folder_url)

    # --------------------------------------------------------
    # Azure
    # --------------------------------------------------------

    if provider == "azure":

        return azure_images(folder_url)

    # --------------------------------------------------------
    # Amazon S3
    # --------------------------------------------------------

    if provider == "s3":

        return s3_images(folder_url)

    # --------------------------------------------------------
    # Google Photos
    # --------------------------------------------------------

    if provider == "google_photos":

        return google_photos_images(folder_url)

    # --------------------------------------------------------
    # TeraBox
    # --------------------------------------------------------

    if provider == "terabox":

        return terabox_images(folder_url)

    raise ValueError(
        f"Unsupported gallery provider: {provider}"
    )
