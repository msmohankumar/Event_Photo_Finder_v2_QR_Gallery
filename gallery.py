
import os
import re
import json
import requests

from utils import image_bytes_preview


# ==========================================================
# GOOGLE DRIVE
# ==========================================================

def _drive_folder_id(link):

    m = re.search(
        r"/folders/([a-zA-Z0-9_-]+)",
        link
    )

    if m:
        return m.group(1)

    m = re.search(
        r"[?&]id=([a-zA-Z0-9_-]+)",
        link
    )

    if m:
        return m.group(1)

    raise ValueError(
        "Could not extract Google Drive folder ID."
    )


def drive_images(link):

    import streamlit as st

    key = st.secrets.get(
        "GOOGLE_DRIVE_API_KEY",
        os.getenv("GOOGLE_DRIVE_API_KEY", "")
    )

    if not key:

        raise RuntimeError(
            "Configure GOOGLE_DRIVE_API_KEY in Streamlit Secrets."
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

        if file.get("mimeType", "").startswith("image/"):

            download = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file['id']}?alt=media&key={key}",
                timeout=60
            )

            download.raise_for_status()

            data = download.content

            items.append({

                "name": file.get("name", file["id"]),

                "original": data,

                "preview": image_bytes_preview(data)
            })

    return items


# ==========================================================
# DROPBOX
# ==========================================================

def dropbox_images(link):

    import streamlit as st

    token = st.secrets.get(
        "DROPBOX_ACCESS_TOKEN",
        os.getenv("DROPBOX_ACCESS_TOKEN", "")
    )

    if not token:

        raise RuntimeError(
            "Configure DROPBOX_ACCESS_TOKEN in Streamlit Secrets."
        )

    headers = {

        "Authorization": f"Bearer {token}",

        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.dropboxapi.com/2/files/list_shared_link_files",
        headers=headers,
        json={"url": link},
        timeout=30
    )

    response.raise_for_status()

    entries = response.json().get("entries", [])

    items = []

    for entry in entries:

        if (
            entry.get(".tag") == "file"
            and entry.get("name", "").lower().endswith(
                (".jpg", ".jpeg", ".png")
            )
        ):

            download = requests.post(
                "https://content.dropboxapi.com/2/files/download",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Dropbox-API-Arg": json.dumps({
                        "path": entry["path_lower"]
                    })
                },
                timeout=60
            )

            download.raise_for_status()

            data = download.content

            items.append({

                "name": entry["name"],

                "original": data,

                "preview": image_bytes_preview(data)
            })

    return items


# ==========================================================
# LOCAL FOLDER
# ==========================================================

def local_images(path):

    path = path.strip()

    if not os.path.isdir(path):

        raise ValueError(
            "The specified folder does not exist "
            "on the machine running Streamlit."
        )

    items = []

    for name in sorted(os.listdir(path)):

        if name.lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):

            full_path = os.path.join(path, name)

            try:

                with open(full_path, "rb") as file:

                    data = file.read()

                items.append({

                    "name": name,

                    "original": data,

                    "preview": image_bytes_preview(data)
                })

            except Exception:

                continue

    return items


# ==========================================================
# AZURE BLOB STORAGE
# ==========================================================

def azure_images(container_name):

    import streamlit as st

    connection_string = st.secrets.get(
        "AZURE_STORAGE_CONNECTION_STRING",
        os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING",
            ""
        )
    )

    if not connection_string:

        raise RuntimeError(
            "Configure AZURE_STORAGE_CONNECTION_STRING "
            "in Streamlit Secrets."
        )

    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(
        connection_string
    )

    container_name = (
        container_name.strip()
        .replace("https://", "")
        .strip("/")
    )

    if container_name.startswith(
        "blob.core.windows.net/"
    ):

        container_name = container_name.split(
            "/", 1
        )[1]

    container_name = container_name.split(
        "/", 1
    )[0]

    container = service.get_container_client(
        container_name
    )

    items = []

    for blob in container.list_blobs():

        if blob.name.lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):

            data = container.download_blob(
                blob.name
            ).readall()

            items.append({

                "name": blob.name,

                "original": data,

                "preview": image_bytes_preview(data)
            })

    return items


# ==========================================================
# AMAZON S3
# ==========================================================

def s3_images(bucket):

    import streamlit as st

    access_key = st.secrets.get(
        "AWS_ACCESS_KEY_ID",
        os.getenv("AWS_ACCESS_KEY_ID", "")
    )

    secret_key = st.secrets.get(
        "AWS_SECRET_ACCESS_KEY",
        os.getenv("AWS_SECRET_ACCESS_KEY", "")
    )

    region = st.secrets.get(
        "AWS_REGION",
        os.getenv("AWS_REGION", "")
    )

    if not access_key or not secret_key:

        raise RuntimeError(
            "Configure AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in Streamlit Secrets."
        )

    from boto3.session import Session

    session = Session(

        aws_access_key_id=access_key,

        aws_secret_access_key=secret_key,

        region_name=region or None
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

            if name.lower().endswith(
                (".jpg", ".jpeg", ".png")
            ):

                data = s3.get_object(
                    Bucket=bucket.strip(),
                    Key=name
                )["Body"].read()

                items.append({

                    "name": name,

                    "original": data,

                    "preview": image_bytes_preview(data)
                })

    return items


# ==========================================================
# GOOGLE PHOTOS
# ==========================================================

def google_photos_images(link):

    raise RuntimeError(
        "Google Photos Picker API integration is not yet implemented. "
        "Google Photos requires OAuth authorization, a Picker session, "
        "selection by the user, and retrieval of the selected media. "
        "Pasting an album link alone is not supported."
    )


# ==========================================================
# TERABOX
# ==========================================================

def terabox_images(link):

    raise RuntimeError(
        "TeraBox integration is not currently supported. "
        "This application does not use unofficial scraping "
        "or bypass login/access restrictions."
    )


# ==========================================================
# PROVIDER ROUTER
# ==========================================================

def get_gallery_images(cfg):

    provider = cfg.get("provider")

    link = cfg.get(
        "folder_url",
        ""
    ).strip()

    if not link:

        raise ValueError(
            "Organizer has not saved a gallery source."
        )

    if provider == "drive":

        return drive_images(link)

    elif provider == "google_photos":

        return google_photos_images(link)

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
