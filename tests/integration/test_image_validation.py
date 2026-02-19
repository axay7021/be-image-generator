"""
Integration tests for image validation functions.
These tests use the REAL OpenCV (not mocked) and live in tests/integration/
so they are unaffected by the main conftest.py which mocks cv2 for unit tests.

Tests:
- detect_face_mediapipe: must report correct face count
- is_real_human_face: must distinguish real photos from cartoons/illustrations
"""

import cv2
import numpy as np

from app.routers.image import detect_face_mediapipe, is_real_human_face

# ---------------------------------------------------------------------------
# Helpers to generate synthetic test images (no real photos needed in CI)
# ---------------------------------------------------------------------------


def _encode_to_jpeg(img: np.ndarray) -> bytes:
    """Encode an OpenCV BGR image to JPEG bytes."""
    ok, buf = cv2.imencode(".jpg", img)
    assert ok, "Failed to encode test image to JPEG"
    return buf.tobytes()


def _encode_to_png(img: np.ndarray) -> bytes:
    """Encode an OpenCV BGR image to PNG bytes (lossless — no compression artifacts)."""
    ok, buf = cv2.imencode(".png", img)
    assert ok, "Failed to encode test image to PNG"
    return buf.tobytes()


def _make_flat_cartoon_image(size: int = 256) -> bytes:
    """
    Build a synthetic 'cartoon' image:
    - A 100% uniform solid color fill — no edges, no texture.
    - Encoded as lossless PNG so JPEG DCT artifacts cannot inflate
      the Laplacian variance and cause a false 'real photo' classification.
    Both sat_std AND laplacian_var will be 0.0, well below both thresholds.
    """
    img = np.full((size, size, 3), (60, 180, 60), dtype=np.uint8)
    return _encode_to_png(img)


def _make_textured_realistic_image(size: int = 256) -> bytes:
    """
    Build a synthetic 'realistic' image:
    - Random noise (high saturation variance, high Laplacian variance).
    This simulates a real photographic texture.
    """
    rng = np.random.default_rng(seed=42)
    img = (rng.random((size, size, 3)) * 255).astype(np.uint8)
    return _encode_to_jpeg(img)


def _make_corrupt_bytes() -> bytes:
    """Return bytes that are not a valid image."""
    return b"not_an_image_at_all"


# ---------------------------------------------------------------------------
# Tests: is_real_human_face
# ---------------------------------------------------------------------------


class TestIsRealHumanFace:
    def test_flat_cartoon_image_is_rejected(self):
        """A flat-colored cartoon-style image must return False."""
        cartoon_bytes = _make_flat_cartoon_image()
        result = is_real_human_face(cartoon_bytes)
        assert result is False, "Flat cartoon image should be flagged as non-real"

    def test_textured_realistic_image_is_accepted(self):
        """A high-texture realistic image must return True."""
        real_bytes = _make_textured_realistic_image()
        result = is_real_human_face(real_bytes)
        assert result is True, "High-texture realistic image should pass realism check"

    def test_corrupt_bytes_fail_open(self):
        """Corrupt / undecodable image bytes must return True (fail open)."""
        result = is_real_human_face(_make_corrupt_bytes())
        assert result is True, "Corrupt image should fail open (True) to avoid false-negatives"

    def test_empty_bytes_fail_open(self):
        """Empty bytes must return True (fail open)."""
        result = is_real_human_face(b"")
        assert result is True, "Empty bytes should fail open (True)"


# ---------------------------------------------------------------------------
# Tests: detect_face_mediapipe (edge cases)
# ---------------------------------------------------------------------------


class TestDetectFaceMediapipe:
    def test_no_face_in_blank_image(self):
        """A blank white image should return 0 faces."""
        img = np.full((256, 256, 3), 255, dtype=np.uint8)
        face_count = detect_face_mediapipe(_encode_to_jpeg(img))
        assert face_count == 0, "Blank white image should have 0 detected faces"

    def test_corrupt_bytes_return_zero(self):
        """Corrupt image bytes should safely return 0 (not raise)."""
        face_count = detect_face_mediapipe(_make_corrupt_bytes())
        assert face_count == 0, "Corrupt bytes should return 0, not raise an exception"
