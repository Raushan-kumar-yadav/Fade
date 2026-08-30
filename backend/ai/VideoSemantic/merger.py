def merge_and_chunk(
    scenes: list[dict],
    transcript: list[dict],
    window_sec: float = 4.0,
) -> list[dict]:
    duration = max(
        max((s["end"] for s in scenes), default=0),
        max((t["end"] for t in transcript), default=0),
    )
    chunks = []
    t = 0.0
    while t < duration:
        end = t + window_sec
        scene_texts  = [s["text"] for s in scenes if s["start"] < end and s["end"] > t]
        speech_texts = [s["text"] for s in transcript if s["start"] < end and s["end"] > t]

        combined = ""
        if scene_texts:
            combined += "Visual: " + " ".join(scene_texts)
        if speech_texts:
            combined += (" | " if combined else "") + "Speech: " + " ".join(speech_texts)

        if combined.strip():
            chunks.append({"text": combined, "start_sec": t, "end_sec": end})
        t += window_sec

    return chunks
