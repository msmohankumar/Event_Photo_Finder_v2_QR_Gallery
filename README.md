# 📸 Event Photo Finder

Find your event photos using AI-powered face recognition. Guests can scan a QR code, take a selfie or upload their photos, and automatically discover pictures of themselves from the event gallery.

## 🚀 Live Application

**[Open Event Photo Finder](https://eventphotofinderv2qrgallery-9twqcj87f3sdvcvguvkkkt.streamlit.app/)**

## ✨ Features

- **QR Code Access:** Guests can scan a QR code to access the event photo finder directly from their mobile phones.
- **Camera Selfie:** Capture a selfie directly using the browser camera.
- **Multiple Photo Uploads:** Upload or drag and drop multiple photos for face matching.
- **AI Face Recognition:** Automatically identify matching photos using facial recognition.
- **Multiple Gallery Sources:** Connect the application to supported gallery storage providers.
- **Dropbox Integration:** Search photos stored in a Dropbox shared folder.
- **Google Drive Integration:** Retrieve images from a configured Google Drive folder.
- **Matching Sensitivity:** Adjust the face-matching threshold.
- **Individual Downloads:** Download matching photos individually.
- **ZIP Download:** Download all matching photos together.
- **Organizer Dashboard:** Configure the event gallery and application settings.
- **Gallery Testing:** Check gallery connectivity and image downloads.
- **QR Code Generator:** Generate and download a QR code for guest access.
- **Gallery Caching:** Reduce repeated gallery loading through caching.

## 🔄 How It Works

1. The organizer configures the event and connects the photo gallery.
2. The application generates a QR code for guests.
3. Guests scan the QR code using their mobile phones.
4. Guests take a selfie or upload one or more photos.
5. The application processes the uploaded images using face recognition.
6. The application searches the configured event gallery.
7. Matching photos are displayed.
8. Guests download individual photos or all matching photos as a ZIP file.

## 🛠️ Technology Stack

- Python
- Streamlit
- DeepFace
- Face Recognition / Facial Embeddings
- Facenet512
- NumPy
- Pillow
- Requests
- Dropbox API
- Google Drive API
- QR Code Generation

## 📂 Project Structure

```text
Event-Photo-Finder/
│
├── app.py
├── gallery.py
├── matcher.py
├── utils.py
├── config_store.py
├── requirements.txt
├── packages.txt
└── README.md
```

## ⚙️ Application Configuration

The application uses configuration and secrets to manage event settings, gallery access and organizer authentication.

Configure the required secrets in Streamlit Cloud.

Example:

```toml
DROPBOX_ACCESS_TOKEN = "your_dropbox_access_token"
ADMIN_PASSWORD = "your_admin_password"
```

Additional secrets may be required depending on the gallery provider.

## 📸 Gallery Providers

The application is designed to support configurable photo storage sources, including:

- Dropbox
- Google Drive
- Local folders
- Azure Blob Storage
- Amazon S3

Provider availability depends on the corresponding credentials and configuration.

## 👨‍💻 Application Usage

### Guest

1. Open the application using the event QR code or live application link.
2. Take a selfie or upload one or more images.
3. Click **Find My Photos**.
4. Wait for face recognition to complete.
5. Review the matching photos.
6. Download individual images or the ZIP file.

### Organizer

1. Open the Organizer Login section.
2. Enter the organizer password.
3. Configure the event name and gallery provider.
4. Enter the gallery folder link.
5. Configure matching sensitivity.
6. Enable the guest photo finder.
7. Save the configuration.
8. Test the gallery.
9. Generate and download the guest QR code.

## 🌐 Live Deployment

The application is deployed using Streamlit Community Cloud.

**Live App:** https://eventphotofinderv2qrgallery-9twqcj87f3sdvcvguvkkkt.streamlit.app/

## 🔒 Privacy

The application is intended to help event guests find photos in a configured event gallery.

Access to gallery storage requires the configured credentials and permissions. Organizers should ensure that event photos and facial-recognition processing are handled with appropriate consent and privacy safeguards.

## 📌 Project

An AI-powered event photo discovery application designed to simplify finding and downloading event photos using facial recognition.

---

**Built with Python and Streamlit.**
