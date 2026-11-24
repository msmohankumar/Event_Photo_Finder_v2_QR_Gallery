
import os
import streamlit as st


def _secrets():

    try:
        return st.secrets

    except Exception:
        return {}


# ==========================================================
# LOAD SHARED CONFIGURATION
# ==========================================================

def load_config():

    secrets = _secrets()

    url = secrets.get(
        "SUPABASE_URL",
        os.getenv("SUPABASE_URL", "")
    )

    key = secrets.get(
        "SUPABASE_KEY",
        os.getenv("SUPABASE_KEY", "")
    )

    if url and key:

        try:

            from supabase import create_client

            client = create_client(
                url,
                key
            )

            response = (
                client
                .table("event_config")
                .select("*")
                .eq("id", 1)
                .limit(1)
                .execute()
            )

            if response.data:

                row = response.data[0]

                return {

                    "event_name": row.get(
                        "event_name",
                        "Event Gallery"
                    ),

                    "provider": row.get(
                        "provider",
                        "drive"
                    ),

                    "folder_url": row.get(
                        "folder_url",
                        ""
                    ),

                    "threshold": row.get(
                        "threshold",
                        0.40
                    ),

                    "enabled": row.get(
                        "enabled",
                        False
                    )
                }

        except Exception as exc:

            st.warning(
                f"Unable to load event configuration from Supabase: {exc}"
            )

    return {

        "event_name": "Event Gallery",

        "provider": "drive",

        "folder_url": "",

        "threshold": 0.40,

        "enabled": False
    }


# ==========================================================
# SAVE SHARED CONFIGURATION
# ==========================================================

def save_config(cfg):

    secrets = _secrets()

    url = secrets.get(
        "SUPABASE_URL",
        os.getenv("SUPABASE_URL", "")
    )

    key = secrets.get(
        "SUPABASE_KEY",
        os.getenv("SUPABASE_KEY", "")
    )

    if not url or not key:

        raise RuntimeError(
            "Supabase credentials are missing. "
            "Configure SUPABASE_URL and SUPABASE_KEY."
        )

    from supabase import create_client

    client = create_client(
        url,
        key
    )

    payload = {

        "id": 1,

        "event_name": cfg.get(
            "event_name",
            "Event Gallery"
        ),

        "provider": cfg.get(
            "provider",
            "drive"
        ),

        "folder_url": cfg.get(
            "folder_url",
            ""
        ),

        "threshold": cfg.get(
            "threshold",
            0.40
        ),

        "enabled": cfg.get(
            "enabled",
            False
        )
    }

    client.table(
        "event_config"
    ).upsert(payload).execute()
