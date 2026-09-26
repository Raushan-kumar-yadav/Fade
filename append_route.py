import sys

code = """
class TransformBatchRequest(BaseModel):
    clip_id: str
    before: dict
    after: dict

@router.post("/clips/transform-batch")
def transformBatch(req: TransformBatchRequest):
    \"\"\"
    Apply a batch of parameter changes and record them as a single command in CommandStack.
    \"\"\"
    from backend.editor_tools.commands import TransformClipCommand
    cmd = TransformClipCommand(req.clip_id, req.before, req.after)
    engine.commandStack.execute(cmd)
    return {"status": "ok"}
"""

with open('backend/routers/clips.py', 'a') as f:
    f.write(code)
