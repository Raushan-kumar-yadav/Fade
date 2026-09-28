"""
backend/tests/test_pii.py
=========================
PII detection + sanitization test suite.

Run from repo root:
    python -m pytest backend/tests/test_pii.py -v

All tests work offline — no network, no GPU.
Image/video tests use synthetic PIL/cv2 data so Tesseract is NOT required
for the unit tests (those that call detect_image use mocking).
"""
from __future__ import annotations

import io
import json
import sys
import os
import types
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Make scrubber importable without cd-ing to pii/
# ---------------------------------------------------------------------------
_PII_DIR = Path(__file__).resolve().parent.parent.parent / "pii"
if str(_PII_DIR) not in sys.path:
    sys.path.insert(0, str(_PII_DIR))

# Make backend importable
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.pii.detector  import detect_text, detect_image, detect_video, _make_id
from backend.pii.sanitizer import sanitize_text, sanitize_image, sanitize_video


# ─────────────────────────────────────────────────────────────────────────────
# 1. Text detection
# ─────────────────────────────────────────────────────────────────────────────

def test_text_detection_email():
    """Email pattern is detected with correct span."""
    text = "Contact: alice@example.com for support."
    dets = detect_text(text, use_ner=False)
    email_dets = [d for d in dets if d["type"] == "EMAIL"]
    assert email_dets, "Expected at least one EMAIL detection"
    d = email_dets[0]
    assert text[d["start"]:d["end"]] == "alice@example.com"
    assert d["confidence"] > 0.9


def test_text_detection_phone():
    """Indian phone number detected."""
    text = "Call me on +91 9876543210 anytime."
    dets = detect_text(text, use_ner=False)
    phone_dets = [d for d in dets if d["type"] == "PHONE"]
    assert phone_dets, "Expected PHONE detection"


def test_text_detection_credit_card():
    """Luhn-valid card detected; invalid skipped."""
    valid_text   = "Card: 4111 1111 1111 1111"
    invalid_text = "Card: 1234 5678 9012 3456"  # fails Luhn
    valid_dets   = detect_text(valid_text, use_ner=False)
    invalid_dets = detect_text(invalid_text, use_ner=False)
    assert any(d["type"] == "CREDIT_CARD" for d in valid_dets)
    assert not any(d["type"] == "CREDIT_CARD" for d in invalid_dets)


def test_text_detection_no_pii():
    """Clean text returns empty detection list."""
    text = "The quick brown fox jumps over the lazy dog."
    dets = detect_text(text, use_ner=False)
    assert dets == [], f"Expected no detections, got {dets}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Detection schema
# ─────────────────────────────────────────────────────────────────────────────

def test_text_detection_schema():
    """TextDetection dict has all required keys."""
    text = "Email: bob@fade.io"
    dets = detect_text(text, use_ner=False)
    assert dets
    d = dets[0]
    for key in ("id", "type", "confidence", "start", "end", "value"):
        assert key in d, f"Missing key: {key}"
    assert d["id"].startswith("det_")
    assert isinstance(d["confidence"], float)
    assert 0.0 <= d["confidence"] <= 1.0


def test_image_detection_schema():
    """ImageDetection dict has all required keys when _ocr_boxes returns results."""
    # Mock _ocr_boxes to return a synthetic bbox so OCR is not needed
    with mock.patch("backend.pii.detector._ocr_boxes", return_value=([(10, 20, 100, 30)], ["EMAIL"])):
        from PIL import Image
        img = Image.new("RGB", (640, 480), color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(buf.read())
            tmp_path = tmp.name

        try:
            dets = detect_image(tmp_path)
        finally:
            os.unlink(tmp_path)

    assert dets
    d = dets[0]
    for key in ("id", "type", "confidence", "bbox", "coordinateSpace", "sourceWidth", "sourceHeight"):
        assert key in d, f"Missing key: {key}"
    assert d["coordinateSpace"] == "source"
    assert d["bbox"]["x"] == 10
    assert d["bbox"]["y"] == 20
    assert d["sourceWidth"]  == 640
    assert d["sourceHeight"] == 480


# ─────────────────────────────────────────────────────────────────────────────
# 3. Coordinate normalization
# ─────────────────────────────────────────────────────────────────────────────

def test_image_coordinate_normalization():
    """Coords returned are in source resolution, not OCR-upscaled resolution."""
    # Simulate: OCR finds a box at (200, 100, 50, 20) in the OCR-upscaled space.
    # scrubber._ocr_boxes already divides by OCR_SCALE (=2), so detector gets (100, 50, 25, 10).
    ocr_result = ([(100, 50, 25, 10)], ["EMAIL"])   # already source-res
    with mock.patch("backend.pii.detector._ocr_boxes", return_value=ocr_result):
        from PIL import Image
        img = Image.new("RGB", (1920, 1080))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(buf.read())
            tmp_path = tmp.name

        try:
            dets = detect_image(tmp_path)
        finally:
            os.unlink(tmp_path)

    assert dets[0]["bbox"]["x"] == 100
    assert dets[0]["bbox"]["y"] == 50
    assert dets[0]["sourceWidth"]  == 1920
    assert dets[0]["sourceHeight"] == 1080


# ─────────────────────────────────────────────────────────────────────────────
# 4. Text sanitization
# ─────────────────────────────────────────────────────────────────────────────

def test_sanitize_text_basic():
    """Enabled redaction replaces the span with [REDACTED]."""
    text = "Contact alice@example.com for details."
    redactions = [{
        "id": "det_001", "type": "EMAIL", "action": "redact",
        "enabled": True, "start": 8, "end": 25,
    }]
    result = sanitize_text(text, redactions)
    assert "[REDACTED]" in result
    assert "alice@example.com" not in result


def test_sanitize_text_disabled():
    """Disabled redaction must NOT alter the text."""
    text = "Contact alice@example.com for details."
    redactions = [{
        "id": "det_001", "type": "EMAIL", "action": "redact",
        "enabled": False, "start": 8, "end": 25,
    }]
    result = sanitize_text(text, redactions)
    assert result == text, "Disabled redaction should leave text unchanged"


def test_sanitize_text_pseudonymize():
    """Pseudonymize action replaces with a stable hash token."""
    text = "Contact alice@example.com for details."
    redactions = [{
        "id": "det_001", "type": "EMAIL", "action": "pseudonymize",
        "enabled": True, "start": 8, "end": 25,
    }]
    result = sanitize_text(text, redactions)
    assert "[EMAIL_" in result
    assert "alice@example.com" not in result


# ─────────────────────────────────────────────────────────────────────────────
# 5. Critical: user-modified coordinates are respected
# ─────────────────────────────────────────────────────────────────────────────

def test_sanitize_text_uses_fade_coordinates_not_detector():
    """THE KEY CONTRACT: sanitizer MUST use FADE coordinates, not detector coords.

    Scenario:
        Detector found EMAIL at start=8, end=25.
        FADE user moved the selection to start=0, end=7.
        Sanitizer must redact start=0..7, NOT 8..25.
    """
    text = "Contact alice@example.com for details."
    # FADE sends different coords than detector found
    redactions = [{
        "id": "det_001", "type": "EMAIL", "action": "redact",
        "enabled": True,
        "start": 0,   # FADE moved it here
        "end":   7,
    }]
    result = sanitize_text(text, redactions)
    # "Contact" (0..7) should be redacted
    assert result.startswith("[REDACTED]")
    # The original detector target should be untouched
    assert "alice@example.com" in result


def test_sanitize_image_uses_fade_bbox():
    """Sanitize image at bbox x=250 even though detector found x=100."""
    from PIL import Image, ImageDraw
    import io, tempfile, os

    # Create a white 400x400 image
    img = Image.new("RGB", (400, 400), "white")
    # Put a red mark at x=100 (where detector would have found it)
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 150, 130], fill="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(buf.read())
        tmp_path = tmp.name

    # FADE user moved the box to x=250
    redactions = [{
        "id": "det_001", "type": "EMAIL", "action": "redact",
        "enabled": True,
        "bbox": {"x": 250, "y": 100, "width": 50, "height": 30},
        "coordinateSpace": "source",
    }]

    try:
        result_bytes = sanitize_image(tmp_path, redactions)
    finally:
        os.unlink(tmp_path)

    result_img = Image.open(io.BytesIO(result_bytes))
    px = result_img.getpixel

    # x=250 area must be black (redacted)
    assert px((252, 102)) == (0, 0, 0), "Expected x=250 area to be blacked out"

    # x=100 area should still be red (NOT redacted — detector coords ignored)
    assert px((125, 115)) == (255, 0, 0), "x=100 area should NOT be redacted — FADE moved the box"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Manual redaction accepted
# ─────────────────────────────────────────────────────────────────────────────

def test_manual_redaction_accepted():
    """A redaction with no original detection ID (manual) must be applied."""
    text = "The secret phrase is abracadabra and nothing else."
    redactions = [{
        "id": "manual_001", "type": "MANUAL", "action": "redact",
        "enabled": True, "start": 21, "end": 32,
    }]
    result = sanitize_text(text, redactions)
    assert "[REDACTED]" in result
    assert "abracadabra" not in result


# ─────────────────────────────────────────────────────────────────────────────
# 7. Detection and sanitization are separate operations
# ─────────────────────────────────────────────────────────────────────────────

def test_detect_does_not_modify_source():
    """detect_text must return detections without altering the original string."""
    text = "Email: test@example.com, card: 4111 1111 1111 1111"
    original = text
    dets = detect_text(text, use_ner=False)
    assert text == original, "detect_text mutated the source string!"
    assert dets  # some detections found


def test_sanitize_does_not_call_detector(monkeypatch):
    """sanitize_text must NOT call find_spans or any detection function."""
    called = []

    def _spy(*args, **kwargs):
        called.append("find_spans_called")
        return []

    monkeypatch.setattr("backend.pii.sanitizer.__builtins__", {})  # harmless
    # If sanitizer imported find_spans it would be in its own module namespace
    import backend.pii.sanitizer as san_mod
    if hasattr(san_mod, "find_spans"):
        monkeypatch.setattr(san_mod, "find_spans", _spy)

    text = "Nothing sensitive here."
    redactions: list = []
    result = sanitize_text(text, redactions)
    assert result == text
    assert not called, "sanitizer must not call find_spans"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Image sanitize: disabled redactions not applied
# ─────────────────────────────────────────────────────────────────────────────

def test_image_disabled_redaction_not_applied():
    """Disabled image redaction must leave the pixel untouched."""
    from PIL import Image
    import io, tempfile, os

    img = Image.new("RGB", (200, 200), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(buf.read())
        tmp_path = tmp.name

    redactions = [{
        "id": "det_001", "type": "EMAIL", "action": "redact",
        "enabled": False,   # <-- disabled
        "bbox": {"x": 50, "y": 50, "width": 60, "height": 20},
        "coordinateSpace": "source",
    }]

    try:
        result_bytes = sanitize_image(tmp_path, redactions)
    finally:
        os.unlink(tmp_path)

    result_img = Image.open(io.BytesIO(result_bytes))
    # Pixel at x=80,y=60 should still be white (no redaction applied)
    assert result_img.getpixel((80, 60)) == (255, 255, 255), (
        "Disabled redaction should not black out pixel"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Integration: detect -> FADE edits -> sanitize (full contract simulation)
# ─────────────────────────────────────────────────────────────────────────────

def test_full_text_contract():
    """
    Simulate the complete FADE contract for text:
        asset -> /pii/detect -> DetectionResult
              -> [FADE moves detection]
              -> RedactionRequest -> /pii/sanitize -> SanitizedAsset
    """
    original_text = "Contact alice@example.com for info."

    # Step 1: detect
    detections = detect_text(original_text, use_ner=False)
    assert detections, "Should detect at least one item"
    det = detections[0]
    detected_start = det["start"]
    detected_end   = det["end"]

    # Step 2: FADE user moves the selection (simulated)
    fade_start = detected_start + 5   # deliberately different from detector
    fade_end   = detected_end   + 2

    # Step 3: FADE generates RedactionRequest
    redaction_request = {
        "assetId":   "test_asset_001",
        "assetType": "text",
        "redactions": [{
            "id":      det["id"],
            "type":    det["type"],
            "action":  "redact",
            "enabled": True,
            "start":   fade_start,
            "end":     fade_end,
        }],
    }

    # Step 4: sanitize
    result = sanitize_text(original_text, redaction_request["redactions"])

    # The redacted range must be gone; original detector range may still be present
    assert "[REDACTED]" in result
    assert original_text[fade_start:fade_end] not in result, (
        "FADE coords must be used; the user-moved range must be redacted"
    )


if __name__ == "__main__":
    import traceback
    tests = [
        test_text_detection_email,
        test_text_detection_phone,
        test_text_detection_credit_card,
        test_text_detection_no_pii,
        test_text_detection_schema,
        test_sanitize_text_basic,
        test_sanitize_text_disabled,
        test_sanitize_text_pseudonymize,
        test_sanitize_text_uses_fade_coordinates_not_detector,
        test_sanitize_image_uses_fade_bbox,
        test_manual_redaction_accepted,
        test_detect_does_not_modify_source,
        test_image_disabled_redaction_not_applied,
        test_full_text_contract,
    ]
    passed = failed = 0
    for t in tests:
        try:
            # Handle monkeypatch-requiring tests
            if t.__name__ == "test_sanitize_does_not_call_detector":
                print(f"  SKIP {t.__name__} (requires pytest monkeypatch)")
                continue
            t()
            print(f"  PASS {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
