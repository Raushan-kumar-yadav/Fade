import cv2
import numpy as np
import pytest
from backend.tracking.target_detector import find_text_target, find_image_target

def test_find_text_target():
    # Create a synthetic image with text
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    img.fill(255) # White background
    
    # Put text "HELLO" at (50, 100)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, "HELLO", (50, 100), font, 2, (0, 0, 0), 3, cv2.LINE_AA)
    
    # Also add some noise text
    cv2.putText(img, "WORLD", (50, 150), font, 1, (0, 0, 0), 2, cv2.LINE_AA)
    
    # Detect
    res = find_text_target(img, "hello")
    assert res["found"] is True
    assert res["confidence"] > 0
    
    # Check bounding box roughly
    # We know it's around (50, 100) but top is higher (y ~ 50).
    assert 40 <= res["x"] <= 60
    assert 40 <= res["y"] <= 70
    assert res["width"] > 50
    assert res["height"] > 20

def test_find_text_not_found():
    img = np.zeros((200, 400, 3), dtype=np.uint8)
    img.fill(255)
    cv2.putText(img, "HELLO", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
    
    res = find_text_target(img, "MISSING")
    assert res["found"] is False
    assert "not found" in res.get("message", "").lower()

def test_find_image_target():
    # Create a synthetic background image
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    
    # Draw some shapes to give it features
    for i in range(50):
        cv2.circle(img, (np.random.randint(0, 600), np.random.randint(0, 400)), 10, (255, 255, 255), -1)
    
    # Create a unique reference pattern
    ref_img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(ref_img, (10, 10), (90, 90), (128, 128, 128), -1)
    cv2.circle(ref_img, (30, 30), 10, (255, 0, 0), -1)
    cv2.circle(ref_img, (70, 70), 15, (0, 255, 0), -1)
    cv2.circle(ref_img, (30, 70), 5, (0, 0, 255), -1)
    cv2.line(ref_img, (0,0), (100,100), (255,255,0), 3)
    
    # Place reference image at (200, 150) in target image
    img[150:250, 200:300] = ref_img
    
    # Add some noise to make it realistic
    noise = np.random.randint(0, 50, (400, 600, 3), dtype=np.uint8)
    img = cv2.add(img, noise)
    
    res = find_image_target(img, ref_img)
    
    assert res["found"] is True
    # Should be close to x=200, y=150, w=100, h=100
    assert abs(res["x"] - 200) < 5
    assert abs(res["y"] - 150) < 5
    assert abs(res["width"] - 100) < 5
    assert abs(res["height"] - 100) < 5
    assert res["confidence"] > 0.5

def test_find_image_not_found():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    ref_img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(ref_img, (10, 10), (90, 90), (255, 255, 255), -1)
    
    # Reference image is completely blank except for a white square. Target is totally blank.
    res = find_image_target(img, ref_img)
    
    assert res["found"] is False
