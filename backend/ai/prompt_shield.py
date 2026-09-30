from __future__ import annotations
import io, logging, sys, os, uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Add cloned repo to sys.path so src.shield.* imports work
_SHIELD_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '..', '..', 'cyberSecurityRepos', 'injection_shield')
)
if _SHIELD_DIR not in sys.path:
    sys.path.insert(0, _SHIELD_DIR)

try:
    from src.shield.models import Segment
    from src.shield.normalize import normalize
    from src.shield.detector import detect
    from src.shield.neutralize import neutralize
    from src.shield.decision import decide, Config as DecConfig
    from src.shield.pdf_extract import extract_pdf, UnreadableDocument
    _SHIELD_AVAILABLE = True
except ImportError as _e:
    logger.warning('injection_shield not importable (%s). PASSTHROUGH mode.', _e)
    _SHIELD_AVAILABLE = False


@dataclass
class ShieldResult:
    allowed: bool
    blocked: bool
    sanitized: str
    findings: list = field(default_factory=list)
    reason: str = ''

    @property
    def decision(self) -> str:
        if self.blocked: return 'BLOCK'
        if not self.allowed: return 'SANITIZE'
        return 'ALLOW'


def _passthrough(text: str) -> ShieldResult:
    return ShieldResult(allowed=True, blocked=False, sanitized=text, reason='shield_unavailable')


def _run_shield_on_segments(segments: list, pre_findings: list, block_ratio: float = 0.30) -> ShieldResult:
    all_findings = list(pre_findings)
    total_chars = neutralized_chars = 0
    sanitized_parts = []

    for seg in segments:
        seg_text = seg.text
        if not seg_text:
            sanitized_parts.append('')
            continue
        total_chars += len(seg_text)

        norm = normalize(seg_text, seg.segment_id)
        all_findings.extend(norm.findings)
        clean_text = norm.clean_text

        det_findings = detect(norm, seg.segment_id)
        all_findings.extend(det_findings)

        seg_findings = [f for f in all_findings if f.segment_id == seg.segment_id]
        neut = neutralize(clean_text, seg_findings)

        if neut.quarantined:
            sanitized_parts.append('')
            neutralized_chars += len(clean_text)
        else:
            sanitized_parts.append(neut.sanitized_text)
            spans = [(f.start, f.end) for f in seg_findings
                     if f.action == 'neutralize' and f.start is not None and f.end is not None]
            spans.sort()
            merged = []
            for s, e in spans:
                if merged and s <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))
            neutralized_chars += sum(e - s for s, e in merged)

    stats = {'total_chars': total_chars, 'neutralized_chars': neutralized_chars}
    screen = decide(all_findings, [], stats, DecConfig(block_ratio=block_ratio))
    decision = screen.decision
    sanitized_text = '\n\n'.join(p for p in sanitized_parts if p).strip()

    if decision == 'BLOCK':
        return ShieldResult(allowed=False, blocked=True, sanitized='', findings=all_findings,
                            reason='; '.join(screen.reasons) or 'Blocked by injection shield')
    if decision == 'SANITIZE':
        return ShieldResult(allowed=False, blocked=False, sanitized=sanitized_text,
                            findings=all_findings,
                            reason='; '.join(screen.reasons) or 'Injection content sanitized')
    return ShieldResult(allowed=True, blocked=False,
                        sanitized=sanitized_text or '\n\n'.join(s.text for s in segments if s.text),
                        findings=all_findings)


def scan_text(text: str, source_id: str | None = None) -> ShieldResult:
    if not _SHIELD_AVAILABLE:
        return _passthrough(text)
    if not text or not text.strip():
        return ShieldResult(allowed=True, blocked=False, sanitized=text)
    sid = source_id or str(uuid.uuid4())
    try:
        segment = Segment(segment_id=f'{sid}_0', text=text, source_type='text')
        return _run_shield_on_segments([segment], [])
    except Exception as exc:
        logger.exception('scan_text failed: %s', exc)
        return _passthrough(text)


def scan_pdf(data: bytes, source_id: str | None = None) -> ShieldResult:
    if not _SHIELD_AVAILABLE:
        return ShieldResult(allowed=True, blocked=False, sanitized='', reason='shield_unavailable')
    sid = source_id or str(uuid.uuid4())
    try:
        segments, pre_findings = extract_pdf(data, sid)
    except UnreadableDocument as exc:
        return ShieldResult(allowed=False, blocked=True, sanitized='', reason=f'PDF unreadable: {exc}')
    except Exception as exc:
        logger.exception('scan_pdf: extract_pdf failed: %s', exc)
        return _passthrough('')
    if not segments:
        return ShieldResult(allowed=True, blocked=False, sanitized='', reason='empty_pdf')
    try:
        return _run_shield_on_segments(segments, pre_findings)
    except Exception as exc:
        logger.exception('scan_pdf: pipeline failed: %s', exc)
        return _passthrough('')


def scan_image(data: bytes, source_id: str | None = None) -> ShieldResult:
    if not _SHIELD_AVAILABLE:
        return ShieldResult(allowed=True, blocked=False, sanitized='', reason='shield_unavailable')
    sid = source_id or str(uuid.uuid4())
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.warning('scan_image: pytesseract/Pillow not installed - skipping OCR scan')
        return ShieldResult(allowed=True, blocked=False, sanitized='', reason='ocr_unavailable')
    try:
        img = Image.open(io.BytesIO(data))
        ocr_text = pytesseract.image_to_string(img).strip()
    except Exception as exc:
        logger.warning('scan_image: OCR failed (%s) - allowing import', exc)
        return ShieldResult(allowed=True, blocked=False, sanitized='', reason='ocr_failed')
    if not ocr_text:
        return ShieldResult(allowed=True, blocked=False, sanitized='', reason='no_text_in_image')
    try:
        segment = Segment(segment_id=f'{sid}_ocr', text=ocr_text, source_type='image_ocr')
        return _run_shield_on_segments([segment], [])
    except Exception as exc:
        logger.exception('scan_image: pipeline failed: %s', exc)
        return _passthrough(ocr_text)


def shield_prompt(message: str):
    result = scan_text(message)
    if result.blocked:
        return False, '', f'Message blocked by security filter: {result.reason}'
    if not result.allowed:
        logger.info('Prompt sanitized: %s', result.reason)
        return True, result.sanitized, ''
    return True, result.sanitized or message, ''
