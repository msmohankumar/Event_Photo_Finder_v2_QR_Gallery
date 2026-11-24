
import numpy as np
import streamlit as st

from deepface import DeepFace
from utils import resized_rgb_array


# ==========================================================
# FACE EMBEDDINGS
# ==========================================================

def _embeddings(image_bytes):

    arr = resized_rgb_array(
        image_bytes,
        max_side=1000
    )

    results = DeepFace.represent(
        img_path=arr,
        model_name="Facenet512",
        detector_backend="opencv",
        enforce_detection=True,
        align=True
    )

    return [
        np.asarray(
            result["embedding"],
            dtype=np.float32
        )
        for result in results
        if "embedding" in result
    ]


# ==========================================================
# CACHE GALLERY EMBEDDINGS
# ==========================================================

@st.cache_data(
    show_spinner=False,
    max_entries=500
)
def _cached_gallery_embedding(image_bytes):

    return [
        vector.tolist()
        for vector in _embeddings(image_bytes)
    ]


# ==========================================================
# COSINE DISTANCE
# ==========================================================

def _cosine_distance(a, b):

    denominator = (
        np.linalg.norm(a)
        * np.linalg.norm(b)
    )

    if denominator == 0:

        return 1.0

    return float(
        1.0
        - np.dot(a, b) / denominator
    )


# ==========================================================
# FIND MATCHES
# ==========================================================

def find_matches(
    selfie_bytes,
    images,
    threshold
):

    query_vectors = _embeddings(
        selfie_bytes
    )

    if not query_vectors:

        raise ValueError(
            "No face was detected in the selfie."
        )

    query = query_vectors[0]

    matches = []
    errors = []

    progress = st.progress(0)

    status = st.empty()

    total = len(images)

    for i, item in enumerate(images):

        status.write(
            f"Checking {i + 1}/{total}: "
            f'{item["name"]}'
        )

        try:

            vectors = [
                np.asarray(
                    vector,
                    dtype=np.float32
                )
                for vector in _cached_gallery_embedding(
                    item["original"]
                )
            ]

            if not vectors:

                raise ValueError(
                    "No face detected in this image."
                )

            best_distance = min(
                _cosine_distance(
                    query,
                    vector
                )
                for vector in vectors
            )

            if best_distance <= threshold:

                matches.append({

                    "name": item["name"],

                    "original": item["original"],

                    "preview": item["preview"],

                    "distance": best_distance
                })

        except Exception as exc:

            errors.append(
                f'{item["name"]}: {exc}'
            )

        progress.progress(
            (i + 1) / max(1, total)
        )

    progress.empty()

    status.empty()

    matches.sort(
        key=lambda match: match["distance"]
    )

    return matches, errors
