import re, hashlib, functools, logging

logger = logging.getLogger(__name__)


SALT = "fade-demo-salt"

PATTERNS = [
    ("PRIVATE_KEY", r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    ("JWT", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", 0),
    ("AWS_KEY", r"\bAKIA[0-9A-Z]{16}\b", 0),
    ("GITHUB_TOKEN", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", 0),
    ("BEARER_TOKEN", r"\bbearer\s+[A-Za-z0-9._~+/-]{16,}", re.I),
    ("SECRET", r"\b(?:password|passwd|pwd|secret|api[_-]?key|token)\b\s*[:=]\s*\S+", re.I),
    ("EMAIL", r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", 0),
    ("CREDIT_CARD", r"\b(?:\d[ -]?){13,16}\b", 0),
    ("AADHAAR", r"\b\d{4}\s?\d{4}\s?\d{4}\b", 0),
    ("PAN", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0),
    ("PHONE", r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", 0),
    ("IPV4", r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", 0),
]

def _luhn(s):
    d = [int(c) for c in re.sub(r"\D", "", s)]
    if not 13 <= len(d) <= 16:
        return False
    total = 0
    for i, n in enumerate(reversed(d)):
        if i % 2:
            n *= 2
            if n > 9: n -= 9
        total += n
    return total % 10 == 0

@functools.lru_cache(maxsize=1)
def _nlp():
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except Exception:
        return None

def find_spans(text, use_ner=True):
    cands = []
    for prio, (label, pat, flags) in enumerate(PATTERNS):
        for m in re.finditer(pat, text, flags):
            if label == "CREDIT_CARD" and not _luhn(m.group()):
                continue
            cands.append((prio, m.start(), m.end(), label))
    nlp = _nlp() if use_ner else None
    if nlp:
        for e in nlp(text).ents:
            if e.label_ == "PERSON":
                nxt = text[e.end_char:e.end_char + 2].lstrip()
                if nxt.startswith(":"):      # "Aadhaar:" is a field label, not a name
                    continue
                cands.append((99, e.start_char, e.end_char, "PERSON"))
    cands.sort()
    taken, out = [], []
    for _, s, e, label in cands:
        if any(s < te and e > ts for ts, te in taken):
            continue
        taken.append((s, e)); out.append((s, e, label))
    return sorted(out)

def _replacement(value, label, mode):
    if mode == "redact":
        return "[REDACTED]"
    h = hashlib.sha256((SALT + value).encode()).hexdigest()[:4]
    return f"[{label}_{h}]"

def scrub_text(text, mode="pseudonym", use_ner=True):
    spans = find_spans(text, use_ner)
    out, last = [], 0
    for s, e, label in spans:
        out.append(text[last:s]); out.append(_replacement(text[s:e], label, mode)); last = e
    out.append(text[last:])
    return "".join(out), [{"type": l, "start": s, "end": e} for s, e, l in spans]

OCR_SCALE = 2   # small text (e.g. screen recordings) is missed at 1x


def _ocr_boxes(img):
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        logger.warning(
            "[PII] pytesseract not installed — OCR-based text detection skipped. "
            "Install with: pip install pytesseract"
        )
        return [], []
    import os
    from PIL import Image

    #   locate Tesseract — prefer portable copy bundled in AIModels/tesseract/
    _REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
    _PORTABLE  = os.path.join(_REPO_ROOT, 'AIModels', 'tesseract', 'tesseract.exe')
    if os.path.isfile(_PORTABLE):
        pytesseract.pytesseract.tesseract_cmd = _PORTABLE
    # else: use whatever 'tesseract' is on PATH (Linux / macOS / system install)

    #   point TESSDATA_PREFIX to AIModels/tessdata/ so eng.traineddata is found
    _TESSDATA = os.path.join(_REPO_ROOT, 'AIModels', 'tessdata')
    if os.path.isdir(_TESSDATA):
        os.environ.setdefault('TESSDATA_PREFIX', _TESSDATA)

    big = img.convert("L").resize((img.width * OCR_SCALE, img.height * OCR_SCALE), Image.LANCZOS)
    d = pytesseract.image_to_data(big, output_type=Output.DICT)
    lines = {}
    for i, w in enumerate(d["text"]):
        if w.strip():
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            lines.setdefault(key, []).append((w, d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
    boxes, found = [], []
    for words in lines.values():
        line, offsets, pos = "", [], 0
        for w in words:
            offsets.append((pos, pos + len(w[0]))); line += w[0] + " "; pos += len(w[0]) + 1
        spans = find_spans(line, use_ner=False)
        if not spans:
            continue
        found += [label for _, _, label in spans]
         
        first = min(s for s, _, _ in spans)
        k = OCR_SCALE
        sel = [wd for (ws, we), wd in zip(offsets, words) if we > first]
        x0 = min(wd[1] for wd in sel); y0 = min(wd[2] for wd in sel)
        x1 = max(wd[1] + wd[3] for wd in sel); y1 = max(wd[2] + wd[4] for wd in sel)
        boxes.append((x0 // k, y0 // k, -(-(x1 - x0) // k), -(-(y1 - y0) // k)))
    return boxes, found

def scrub_image(in_path, out_path):
    from PIL import Image, ImageDraw
    img = Image.open(in_path).convert("RGB")
    boxes, found = _ocr_boxes(img)
    draw = ImageDraw.Draw(img)
    for x, y, w, h in boxes:
        draw.rectangle([x - 2, y - 2, x + w + 2, y + h + 2], fill="black")
    img.save(out_path)
    return [{"type": t} for t in found]

def scrub_video(in_path, out_path, every_sec=1.0):
    """OCR every `every_sec`, reuse boxes in between, then copy the original audio back in."""
    import cv2, shutil, subprocess, tempfile, os
    from PIL import Image
    cap = cv2.VideoCapture(str(in_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w, h = int(cap.get(3)), int(cap.get(4))
    silent = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    vw = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    step, i, boxes, found_all = max(1, int(fps * every_sec)), 0, [], []
    last_small, last_ocr = None, 0
    while True:
        ok, frame = cap.read()
        if not ok: break
        if i % step == 0:
            small = cv2.cvtColor(cv2.resize(frame, (w // 4, h // 4)), cv2.COLOR_BGR2GRAY)
            changed = last_small is None or cv2.absdiff(small, last_small).mean() > 1.5
            if changed or i - last_ocr >= fps * 5:      # re-OCR on change, or every 5 s as a safety net
                boxes, found = _ocr_boxes(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                found_all += found
                last_small, last_ocr = small, i
        for x, y, bw, bh in boxes:
            cv2.rectangle(frame, (x - 2, y - 2), (x + bw + 2, y + bh + 2), (0, 0, 0), -1)
        vw.write(frame); i += 1
    cap.release(); vw.release()
    if shutil.which("ffmpeg"):   # re-encode to h264 + bring audio back
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", str(in_path),
                        "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", "-shortest", str(out_path)], check=True)
        os.remove(silent)
    else:
        shutil.move(silent, str(out_path))   # no ffmpeg: video only, no audio
    return [{"type": t} for t in found_all]
