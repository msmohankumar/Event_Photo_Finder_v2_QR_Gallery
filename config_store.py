import os
import streamlit as st

def _secrets():
    try:
        return st.secrets
    except Exception:
        return {}

def load_config():
    # Shared configuration stored in Supabase, not Streamlit session state.
    secrets = _secrets()
    url = secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
    key = secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))
    if url and key:
        try:
            from supabase import create_client
            client = create_client(url, key)
            response = client.table("event_config").select("*").eq("id", 1).limit(1).execute()
            if response.data:
                row = response.data[0]
                return {k: row.get(k) for k in ["event_name", "provider", "folder_url", "threshold", "enabled"]}
        except Exception:
            pass
    # For local preview only. This is not multi-user shared storage.
    return {"event_name": "Event Gallery", "provider": "drive", "folder_url": "", "threshold": 0.40, "enabled": False}

def save_config(cfg):
    secrets = _secrets()
    url = secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
    key = secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))
    if not url or not key:
        raise RuntimeError("Supabase credentials are missing. Configure SUPABASE_URL and SUPABASE_KEY in Streamlit secrets.")
    from supabase import create_client
    client = create_client(url, key)
    payload = {"id": 1, **cfg}
    client.table("event_config").upsert(payload).execute()
