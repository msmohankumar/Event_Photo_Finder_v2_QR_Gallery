import streamlit as st
from supabase import create_client

st.title("Supabase Connection Test")

url = st.secrets.get("SUPABASE_URL", "")
key = st.secrets.get("SUPABASE_KEY", "")

st.write("URL configured:", bool(url))
st.write("Key configured:", bool(key))

if key:
    st.write("Key prefix:", key[:12])

try:
    client = create_client(url, key)

    result = client.table("event_config").select("*").limit(1).execute()

    st.success("Supabase connection successful!")
    st.write(result.data)

except Exception as e:
    st.error("Supabase test failed")
    st.code(str(e))
