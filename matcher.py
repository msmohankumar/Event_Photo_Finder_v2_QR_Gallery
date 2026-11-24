import numpy as np
import streamlit as st

from deepface import DeepFace
from utils import resized_rgb_array


# ============================================================
# FACE EMBEDDING
# ============================================================

def _embeddings(image_bytes):

    arr = resized_rgb_array(
        image_bytes,
        max_side=1000,
    )

    results = DeepFace.represent(
        img_path=arr,
        model_name="Facenet512",
        detector_backend="opencv",
        enforce_detection=True,
        align=True,
    )

    embeddings = []

    for result in results:

        if "embedding" in result:

            embeddings.append(
                np.asarray(
                    result["embedding"],
                    dtype=np.float32,
                )
            )

    return embeddings


# ============================================================
# CACHE GALLERY FACE EMBEDDINGS
# ============================================================

@st.cache_data(
    show_spinner=False,
    max_entries=500,
)
def _cached_gallery_embedding(image_bytes):

    vectors = _embeddings(
        image_bytes
    )

    return [
        vector.tolist()
        for vector in vectors
    ]


# ============================================================
# COSINE DISTANCE
# ============================================================

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


# ============================================================
# FACE MATCHING
# ============================================================

def find_matches(
    selfie_bytes,
    images,
    threshold,
):

    if not images:

        raise ValueError(
            "The gallery contains no images to compare."
        )

    # Detect face in guest selfie
    query_embeddings = _embeddings(
        selfie_bytes
    )

    if not query_embeddings:

        raise ValueError(
            "No face detected in the uploaded selfie."
        )

    query = query_embeddings[0]

    matches = []
    errors = []

    progress = st.progress(0)

    status = st.empty()

    total = len(images)

    for i, item in enumerate(images):

        status.write(
            f"Analysing photo {i + 1} of {total}: "
            f"{item['name']}"
        )

        try:

            if not item.get("original"):

                raise ValueError(
                    "Image data is empty."
                )

            vectors = (
                _cached_gallery_embedding(
                    item["original"]
                )
            )

            if not vectors:

                raise ValueError(
                    "No faces detected in this photo."
                )

            vectors = [
                np.asarray(
                    vector,
                    dtype=np.float32,
                )
                for vector in vectors
            ]

            # If multiple faces are detected in the event photo,
            # compare against every detected face.
            distances = [
                _cosine_distance(
                    query,
                    vector,
                )
                for vector in vectors
            ]

            best_distance = min(
                distances
            )

            if best_distance <= threshold:

                matches.append({
                    "name": item["name"],
                    "original": item["original"],
                    "preview": item["preview"],
                    "distance": best_distance,
                })

        except Exception as exc:

            errors.append(
                f"{item['name']}: {exc}"
            )

        progress.progress(
            (i + 1) / total
        )

    progress.empty()

    status.empty()

    matches.sort(
        key=lambda item: item["distance"]
    )

    return matches, errors
