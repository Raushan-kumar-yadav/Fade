import cv2
import numpy as np
import pytesseract
from pytesseract import Output

def find_text_target(image: np.ndarray, target_text: str) -> dict:
    """
    Use OCR to find the target_text in the image.
    Returns the bounding box of the matched text.
    """
    if image is None or image.size == 0:
        return {"found": False, "message": "Invalid image"}
        
    target_text = target_text.strip().lower()
    if not target_text:
        return {"found": False, "message": "Empty target text"}

    # Convert to grayscale for better OCR
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    try:
        data = pytesseract.image_to_data(gray, output_type=Output.DICT)
        with open("scratch/ocr_log.txt", "w") as _log_f:
            _log_f.write(f"Target: {target_text}\n")
            _log_f.write("OCR Output:\n")
            for _i in range(len(data['text'])):
                _log_f.write(f"{data['conf'][_i]}% : '{data['text'][_i]}'\n")
    except Exception as e:
        return {"found": False, "message": f"OCR failed: {str(e)}"}
        
    n_boxes = len(data['text'])
    
    # Simple single-word or substring match
    best_match = None
    best_conf = -1
    
    for i in range(n_boxes):
        text = data['text'][i].strip().lower()
        conf = float(data['conf'][i])
        
        if conf < 10 or not text:
            continue
            
        if target_text == text:
            if conf > best_conf:
                best_conf = conf
                best_match = i
                
    # Fallback to substring
    if best_match is None:
        for i in range(n_boxes):
            text = data['text'][i].strip().lower()
            conf = float(data['conf'][i])
            if conf < 10 or not text:
                continue
            if target_text in text or text in target_text:
                if conf > best_conf:
                    best_conf = conf
                    best_match = i

    target_words = target_text.split()
    
    # Fallback to multi-word sliding window
    if best_match is None and len(target_words) > 1:
        for i in range(n_boxes - len(target_words) + 1):
            window_text = " ".join([data['text'][j].strip().lower() for j in range(i, i + len(target_words))])
            if target_text in window_text:
                x_min = min([data['left'][j] for j in range(i, i + len(target_words)) if data['text'][j].strip()])
                y_min = min([data['top'][j] for j in range(i, i + len(target_words)) if data['text'][j].strip()])
                x_max = max([data['left'][j] + data['width'][j] for j in range(i, i + len(target_words)) if data['text'][j].strip()])
                y_max = max([data['top'][j] + data['height'][j] for j in range(i, i + len(target_words)) if data['text'][j].strip()])
                
                valid_confs = [float(data['conf'][j]) for j in range(i, i + len(target_words)) if data['text'][j].strip() and float(data['conf'][j]) > 0]
                avg_conf = sum(valid_confs) / len(valid_confs) if valid_confs else 50.0
                
                return {
                    "found": True,
                    "x": float(x_min),
                    "y": float(y_min),
                    "width": float(x_max - x_min),
                    "height": float(y_max - y_min),
                    "confidence": avg_conf / 100.0
                }

    if best_match is not None:
        return {
            "found": True,
            "x": float(data['left'][best_match]),
            "y": float(data['top'][best_match]),
            "width": float(data['width'][best_match]),
            "height": float(data['height'][best_match]),
            "confidence": best_conf / 100.0
        }
        
    return {"found": False, "message": "Text not found"}


def find_image_target(image: np.ndarray, reference_image: np.ndarray) -> dict:
    """
    Use ORB feature matching to find the reference_image inside the target image.
    """
    if image is None or reference_image is None or image.size == 0 or reference_image.size == 0:
        return {"found": False, "message": "Invalid images"}

    img1 = cv2.cvtColor(reference_image, cv2.COLOR_BGR2GRAY)
    img2 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=5000)
    
    kp1, des1 = orb.detectAndCompute(img1, None)
    kp2, des2 = orb.detectAndCompute(img2, None)
    
    if des1 is None or des2 is None or len(des1) < 4 or len(des2) < 4:
        res = cv2.matchTemplate(img2, img1, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= 0.7:
            return {
                "found": True,
                "x": float(max_loc[0]),
                "y": float(max_loc[1]),
                "width": float(img1.shape[1]),
                "height": float(img1.shape[0]),
                "confidence": float(max_val)
            }
        return {"found": False, "message": "Not enough features found"}

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    matches = sorted(matches, key=lambda x: x.distance)
    
    MIN_MATCH_COUNT = 10
    if len(matches) < MIN_MATCH_COUNT:
        res = cv2.matchTemplate(img2, img1, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= 0.7:
            return {
                "found": True,
                "x": float(max_loc[0]),
                "y": float(max_loc[1]),
                "width": float(img1.shape[1]),
                "height": float(img1.shape[0]),
                "confidence": float(max_val)
            }
        return {"found": False, "message": f"Not enough matches ({len(matches)}/{MIN_MATCH_COUNT}) and matchTemplate failed ({max_val:.2f})"}

    num_good = max(MIN_MATCH_COUNT, int(len(matches) * 0.2))
    good_matches = matches[:min(num_good, 50)]
    
    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    
    if M is None:
        res = cv2.matchTemplate(img2, img1, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= 0.7:
            return {
                "found": True,
                "x": float(max_loc[0]),
                "y": float(max_loc[1]),
                "width": float(img1.shape[1]),
                "height": float(img1.shape[0]),
                "confidence": float(max_val)
            }
        return {"found": False, "message": "Homography failed"}

    matchesMask = mask.ravel().tolist()
    inliers = sum(matchesMask)
    
    if inliers < MIN_MATCH_COUNT * 0.8:
         return {"found": False, "message": f"Too many outliers (only {inliers} inliers)"}
         
    confidence = min(1.0, inliers / 30.0)
    
    h, w = img1.shape
    pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
    dst = cv2.perspectiveTransform(pts, M)
    
    x_min = np.min(dst[:, 0, 0])
    x_max = np.max(dst[:, 0, 0])
    y_min = np.min(dst[:, 0, 1])
    y_max = np.max(dst[:, 0, 1])
    
    h2, w2 = img2.shape
    x_min = max(0.0, min(float(w2-1), float(x_min)))
    x_max = max(0.0, min(float(w2-1), float(x_max)))
    y_min = max(0.0, min(float(h2-1), float(y_min)))
    y_max = max(0.0, min(float(h2-1), float(y_max)))
    
    bw = x_max - x_min
    bh = y_max - y_min
    
    if bw <= 0 or bh <= 0:
        return {"found": False, "message": "Invalid bounding box derived from homography"}

    return {
        "found": True,
        "x": float(x_min),
        "y": float(y_min),
        "width": float(bw),
        "height": float(bh),
        "confidence": float(confidence)
    }
