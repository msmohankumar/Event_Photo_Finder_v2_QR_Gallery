# Event Photo Finder v2

A QR-first guest photo finder prototype. An organizer updates a shared event-gallery configuration in the organizer panel. Guests scan a permanent app QR, take/upload a selfie, and the app searches the configured gallery.

## Workflow

1. Organizer opens `/?mode=admin`, authenticates, selects provider, enters gallery folder URL and saves.
2. Organizer downloads/prints the QR. The QR points to the app guest URL, not the storage folder.
3. Guests scan the QR (`/?mode=guest`), take/upload selfie, and search.
4. The app retrieves images from the selected gallery provider, matches faces and offers downloads.

## Important prototype requirements

- Shared organizer configuration is stored in Supabase. Streamlit session state alone is not shared across guests.
- **Google Drive**: folder must be shared/viewable to the app's API access. Configure a Google Drive API key in Streamlit secrets. This prototype lists/downloads files through Drive API; API quota, folder permissions and image access should be tested.
- **Dropbox**: configure a Dropbox access token in Streamlit secrets. Shared-folder API access may require appropriate app permissions and token setup.
- This prototype is not production-ready. Face recognition involves biometric data. Obtain informed consent, minimize retention, secure credentials, and validate storage permissions. Avoid storing selfies/embeddings beyond the intended search. Consider a dedicated event, access controls, rate limiting, deletion and audit policy.
- Provider integration may require adjustments for specific folder link types and provider account/API settings. Do not promise that arbitrary private folders are accessible from a link alone.

## Deploy on Streamlit Community Cloud

1. Create a Supabase project.
2. Run `supabase_schema.sql` in the Supabase SQL editor.
3. Create a GitHub repo and upload this project.
4. Deploy `app.py` on Streamlit Community Cloud with Python 3.11.
5. Add secrets in Streamlit Cloud Settings → Secrets (copy keys from `.streamlit/secrets.toml.example`).
6. Set `ADMIN_PASSWORD`, `SUPABASE_URL`, `SUPABASE_KEY`, and `GUEST_URL`.
7. Add provider credentials if using Drive/Dropbox.
8. Open `/?mode=admin` to configure gallery and download the QR.
9. Print the QR and test with guest access on a phone.

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## URLs

- Organizer: `https://YOUR-APP.streamlit.app/?mode=admin`
- Guest: `https://YOUR-APP.streamlit.app/?mode=guest`

## Included files

- `app.py` — organizer and guest UI
- `config_store.py` — Supabase shared configuration
- `gallery.py` — gallery provider listing/download logic
- `matcher.py` — face recognition, caching and matching
- `utils.py` — image helpers and QR generation
- `supabase_schema.sql` — database table setup
- `requirements.txt`, `packages.txt` — dependencies
