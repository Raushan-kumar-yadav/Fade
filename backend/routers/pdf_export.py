 
from __future__ import annotations
import io
import os
import tempfile
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

# Output directory for exported PDFs
_EXPORT_DIR = Path(__file__).parent.parent.parent / "exports"
_EXPORT_DIR.mkdir(exist_ok=True)


def _get_pdf_doc(doc_id: str) -> dict:
    """Retrieve PDF doc metadata from the project state."""
    from backend.state import engine as _engine
    tl = _engine.activeTimeline if _engine else None
    if tl is None:
        raise HTTPException(503, "No active project")
    # Find the PDF doc in project state
    pdf_docs = getattr(tl, "pdfDocs", {})
    doc = pdf_docs.get(doc_id)
    if not doc:
        raise HTTPException(404, f"PDF doc {doc_id!r} not found")
    return doc


def _render_comp_to_png(comp_id: str, width: int, height: int) -> bytes:
    """Render a composition at its first frame and return PNG bytes."""
    import skia
    from backend.state import engine as _engine
    from backend.compositor.compositor import render_comp

    # Get the composition
    tl = _engine.activeTimeline
    comp = tl.getComp(comp_id) if hasattr(tl, "getComp") else None
    if comp is None:
        # Try to find comp by iterating comps
        for c in getattr(tl, "compositions", {}).values():
            if getattr(c, "compId", None) == comp_id or str(c) == comp_id:
                comp = c
                break

    if comp is None:
        raise HTTPException(404, f"Comp {comp_id!r} not found for rendering")

    # Render frame 0 of the comp
    info = skia.ImageInfo.MakeN32Premul(width, height)
    surface = skia.Surface.MakeRaster(info)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorWHITE)

    try:
        render_comp(comp, canvas, frame=0)
    except Exception as e:
        logger.warning(f"[PDFExport] Render error for comp {comp_id}: {e}")

    img = surface.makeImageSnapshot()
    data = img.encodeToData(skia.kPNG, 100)
    return bytes(data)


def _build_pdf(pages: list[dict], dpi: int = 150) -> bytes:
    """Stitch rendered PNG pages into a real PDF using ReportLab."""
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    import PIL.Image

    buf = io.BytesIO()

    if not pages:
        raise HTTPException(400, "No pages to export")

 
    first = pages[0]
    w_px, h_px = first.get("width", 2480), first.get("height", 3508)
    pts_per_px = 72.0 / dpi
    w_pt = w_px * pts_per_px
    h_pt = h_px * pts_per_px

    pdf = rl_canvas.Canvas(buf, pagesize=(w_pt, h_pt))
    pdf.setTitle(first.get("docName", "Fade Document"))
    pdf.setAuthor("Fade Editor")

    tmp_files: list[str] = []
    try:
        for page in pages:
            comp_id = page["compId"]
            pw = page.get("width", w_px)
            ph = page.get("height", h_px)
            pw_pt = pw * pts_per_px
            ph_pt = ph * pts_per_px

            # Set page size (supports mixed-size pages)
            pdf.setPageSize((pw_pt, ph_pt))

            try:
                png_bytes = _render_comp_to_png(comp_id, pw, ph)
                pil_img = PIL.Image.open(io.BytesIO(png_bytes)).convert("RGB")
            except Exception as e:
                logger.warning(f"[PDFExport] Page {comp_id} render failed: {e} — using blank")
                pil_img = PIL.Image.new("RGB", (pw, ph), (255, 255, 255))

            # Save PIL image to temp file so ReportLab can read it
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            pil_img.save(tmp.name, "JPEG", quality=95)
            tmp.close()
            tmp_files.append(tmp.name)

            pdf.drawImage(tmp.name, 0, 0, width=pw_pt, height=ph_pt)
            pdf.showPage()

        pdf.save()
    finally:
        for f in tmp_files:
            try:
                os.unlink(f)
            except Exception:
                pass

    return buf.getvalue()


@router.get("/pdf-docs/{doc_id}/export")
def export_pdf_doc_route(doc_id: str, dpi: int = 150, quality: int = 95):
    """Export a PDF document to a real .pdf file.

    Renders each page composition via Skia (preserving all layers, effects, and
    animations at frame 0) then stitches them into a single PDF using ReportLab.

    The user keeps full canvas control — this only produces the final output.

    Query params:
        dpi:     Resolution for conversion (72=screen, 150=print-ready, 300=high-res)
        quality: JPEG quality for embedded page images (85-100)

    Returns:
        application/pdf binary response (inline or download).
    """
    try:
        doc = _get_pdf_doc(doc_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Could not load PDF doc: {e}")

    pages = doc.get("pages", [])
    if not pages:
        raise HTTPException(400, "PDF document has no pages")

    # Attach doc metadata to each page for rendering
    for p in pages:
        p["docName"] = doc.get("name", "Document")

    try:
        pdf_bytes = _build_pdf(pages, dpi=dpi)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PDFExport] Build failed: {e}", exc_info=True)
        raise HTTPException(500, f"PDF export failed: {e}")

    doc_name = doc.get("name", "document").replace(" ", "_")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{doc_name}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
