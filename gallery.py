import os, re, requests
from utils import image_bytes_preview

def _drive_folder_id(link):
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", link)
    if m: return m.group(1)
    raise ValueError("Could not extract Google Drive folder ID from the link.")

def drive_images(link):
    import streamlit as st
    key = st.secrets.get("GOOGLE_DRIVE_API_KEY", os.getenv("GOOGLE_DRIVE_API_KEY", ""))
    if not key: raise RuntimeError("Configure GOOGLE_DRIVE_API_KEY in Streamlit secrets.")
    folder_id = _drive_folder_id(link)
    url = "https://www.googleapis.com/drive/v3/files"
    params = {"q": f"'{folder_id}' in parents and trashed=false", "fields": "files(id,name,mimeType)", "pageSize": 1000, "key": key}
    r = requests.get(url, params=params, timeout=30); r.raise_for_status()
    data = r.json().get("files", [])
    items = []
    for f in data:
        if f.get("mimeType","").startswith("image/"):
            dl = requests.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media&key={key}", timeout=60)
            dl.raise_for_status()
            b = dl.content
            items.append({"name": f.get("name", f["id"]), "original": b, "preview": image_bytes_preview(b)})
    return items

def dropbox_images(link):
    import streamlit as st
    token = st.secrets.get("DROPBOX_ACCESS_TOKEN", os.getenv("DROPBOX_ACCESS_TOKEN", ""))
    if not token: raise RuntimeError("Configure DROPBOX_ACCESS_TOKEN in Streamlit secrets.")
    # Shared links can be queried using Dropbox API list_shared_link_files.
    headers = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    r = requests.post("https://api.dropboxapi.com/2/files/list_shared_link_files", headers=headers, json={"url": link}, timeout=30)
    r.raise_for_status()
    entries = r.json().get("entries", [])
    items=[]
    for e in entries:
        if e.get(".tag") == "file" and e.get("name","").lower().endswith((".jpg",".jpeg",".png")):
            dl = requests.post("https://content.dropboxapi.com/2/files/download", headers={"Authorization": f"Bearer {token}", "Dropbox-API-Arg": __import__("json").dumps({"path": e["path_lower"]})}, timeout=60)
            dl.raise_for_status()
            b=dl.content
            items.append({"name":e["name"],"original":b,"preview":image_bytes_preview(b)})
    return items

def get_gallery_images(cfg):
    provider = cfg.get("provider")
    link = cfg.get("folder_url","")
    if not link: raise ValueError("Organizer has not saved a gallery folder link.")
    if provider == "drive": return drive_images(link)
    if provider == "dropbox": return dropbox_images(link)
    raise ValueError("Unsupported gallery provider.")
