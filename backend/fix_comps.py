import ast

lines = open('backend/routers/comps.py', encoding='utf-8', errors='replace').readlines()
good = lines[:545]  # keep lines 1-545

tail = (
    "\n"
    "@router.delete(\"/pdf-docs/{docId}/pages/{pageId}\")\n"
    "def deletePdfPage(docId: str, pageId: str):\n"
    "    \"\"\"Delete a page from the PDF document (also deletes the imageComp).\"\"\"\n"
    "    if engine.project is None:\n"
    "        raise HTTPException(400, \"No active project\")\n"
    "    doc = _get_pdf_doc(docId)\n"
    "    if pageId not in doc.page_ids:\n"
    "        raise HTTPException(404, f\"Page {pageId!r} not in document {docId!r}\")\n"
    "    if len(doc.page_ids) <= 1:\n"
    "        raise HTTPException(400, \"Cannot delete the last page\")\n"
    "    doc.page_ids.remove(pageId)\n"
    "    engine.deleteComposition(pageId)\n"
    "    from backend.events import notify; notify(\"comps\")\n"
    "    return {\"status\": \"ok\", \"docId\": docId, \"deletedPageId\": pageId}\n"
    "\n"
    "\n"
    "@router.post(\"/pdf-docs/{docId}/pages/reorder\")\n"
    "def reorderPdfPages(docId: str, req: ReorderPagesRequest):\n"
    "    \"\"\"Reorder pages by providing the new complete ordered list of compIds.\"\"\"\n"
    "    doc = _get_pdf_doc(docId)\n"
    "    if set(req.page_ids) != set(doc.page_ids):\n"
    "        raise HTTPException(400, \"page_ids must contain the same pages, just reordered\")\n"
    "    doc.page_ids = list(req.page_ids)\n"
    "    from backend.events import notify; notify(\"comps\")\n"
    "    return {\"status\": \"ok\", \"pageIds\": doc.page_ids}\n"
    "\n"
    "\n"
    "@router.post(\"/pdf-docs-repair-sizes\")\n"
    "def repairPdfPageSizes():\n"
    "    \"\"\"Fix any PDF page comps whose width/height does not match their parent doc.\"\"\"\n"
    "    if engine.project is None:\n"
    "        raise HTTPException(400, \"No active project\")\n"
    "    fixed = []\n"
    "    for tl in engine.project.timelines:\n"
    "        if getattr(tl, \"kind\", \"video\") != \"pdf\":\n"
    "            continue\n"
    "        doc_w = int(getattr(tl, \"width\",  1920))\n"
    "        doc_h = int(getattr(tl, \"height\", 1080))\n"
    "        for pid in getattr(tl, \"page_ids\", []):\n"
    "            page = engine.getTimeline(pid)\n"
    "            if page is None:\n"
    "                continue\n"
    "            page_w = int(getattr(page, \"width\",  1920))\n"
    "            page_h = int(getattr(page, \"height\", 1080))\n"
    "            if page_w != doc_w or page_h != doc_h:\n"
    "                page.width  = doc_w\n"
    "                page.height = doc_h\n"
    "                fixed.append({\"pageId\": pid, \"newWidth\": doc_w, \"newHeight\": doc_h})\n"
    "                print(f\"[RepairPageSizes] {page.name}: {page_w}x{page_h} -> {doc_w}x{doc_h}\", flush=True)\n"
    "    from backend.events import notify; notify(\"comps\")\n"
    "    return {\"fixed\": fixed, \"count\": len(fixed)}\n"
)

with open('backend/routers/comps.py', 'w', encoding='utf-8') as f:
    f.writelines(good)
    f.write(tail)

try:
    ast.parse(open('backend/routers/comps.py', encoding='utf-8').read())
    print('OK - comps.py syntax clean')
except SyntaxError as e:
    print(f'SYNTAX ERROR at line {e.lineno}: {e.msg}')
