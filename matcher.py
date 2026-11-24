import numpy as np
import streamlit as st
from deepface import DeepFace
from utils import resized_rgb_array

@st.cache_resource
def _model_ready():
    # Warm-up is intentionally modest. DeepFace still lazily initializes its model.
    return True

def _embeddings(image_bytes):
    arr = resized_rgb_array(image_bytes, max_side=1000)
    results = DeepFace.represent(img_path=arr, model_name="Facenet512", detector_backend="opencv", enforce_detection=True, align=True)
    return [np.asarray(x["embedding"], dtype=np.float32) for x in results if "embedding" in x]

@st.cache_data(show_spinner=False, max_entries=500)
def _cached_gallery_embedding(image_bytes):
    # Cache the embedding keyed by the image content, not its filename.
    return [v.tolist() for v in _embeddings(image_bytes)]

def _cosine_distance(a,b):
    denom=np.linalg.norm(a)*np.linalg.norm(b)
    if denom==0: return 1.0
    return float(1.0-np.dot(a,b)/denom)

def find_matches(selfie_bytes, images, threshold):
    query = _embeddings(selfie_bytes)
    if not query: raise ValueError("No face was detected in the selfie.")
    query = query[0]
    matches, errors = [], []
    progress = st.progress(0)
    status = st.empty()
    for i, item in enumerate(images):
        status.write(f"Checking {i+1}/{len(images)}: {item['name']}")
        try:
            vectors = [np.asarray(v,dtype=np.float32) for v in _cached_gallery_embedding(item["original"])]
            if not vectors: raise ValueError("No face detected")
            best = min(_cosine_distance(query, v) for v in vectors)
            if best <= threshold:
                matches.append({"name":item["name"],"original":item["original"],"preview":item["preview"],"distance":best})
        except Exception as exc:
            errors.append(f"{item['name']}: {exc}")
        progress.progress((i+1)/max(1,len(images)))
    progress.empty(); status.empty()
    matches.sort(key=lambda m:m["distance"])
    return matches, errors
