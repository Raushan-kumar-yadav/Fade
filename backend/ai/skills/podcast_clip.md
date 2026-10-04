---
name: podcast_clip
version: "1.0"
triggers:
  - podcast clip
  - talking head
  - interview clip
  - clip from podcast
  - highlight clip
  - quote clip
  - audiogram
  - video podcast
  - podcast highlight
  - speaker clip
comp_type: video
agent_type: video
output_dimensions: [1920, 1080]
fps: 30
max_duration_frames: 5400
---

## Description
Transform a podcast or interview recording into a shareable highlight clip with
animated captions, speaker name lower-third, quote callout overlay, waveform
visualization, and clean branded styling.

## Rules
- Always read existing library assets first — the source audio/video must already be imported
- Captions are the most important element — large, readable, synced perfectly
- Speaker lower-third appears at start and stays for 5 seconds
- Quote overlay highlights the most impactful sentence in the clip
- Keep the clip focused: 60-180 seconds maximum
- Use clean, minimal design — content is king in podcast clips
- Review viewport to verify captions are readable at small sizes

## Steps

1. ASSET_SCAN | get_library_assets
   Scan the library to find the source podcast/interview video or audio file.
   Note the asset_id, duration, and any existing transcript data.

2. TRANSCRIPT | get_transcript
   Get the full transcript of the source audio/video clip.
   This drives the caption placement and quote selection.
   If no transcript exists, generate_captions will create one.

3. TRIM | trim_clip
   Trim the source clip to the highlight section.
   Based on the transcript, identify the most impactful 60-180 second segment.
   Use trim_clip to set the in/out points.

4. CAPTIONS | generate_captions
   Generate auto-synced captions for the trimmed clip.
   Style: large bold text (52px), white, centered bottom, with dark background box.
   This is the most important step — captions drive engagement.

5. LOWER_THIRD | add_text_clip
   Add a speaker name lower-third at the bottom-left.
   Two lines: Speaker Name (bold, 36px) and Title/Role (regular, 28px, gray).
   Find free overlay track. Animate slide-in from left over 20 frames at frame 0.
   Stays visible for 5 seconds (150 frames), then fades out.
   Apply ease_out preset.

6. QUOTE_OVERLAY | add_text_clip
   Find the most impactful quote or statement in the transcript.
   Add it as a large quote overlay in the center-bottom area.
   Font: 48px bold italic, white. With quotation marks.
   Animate: fade in at the moment the speaker says that line.
   Find free overlay track.

7. BACKGROUND_BAR | add_shape_clip
   Add a thin colored bar at the very bottom (brand accent color).
   Width: 1920px, Height: 6px. No animation needed.
   Adds polish and brand identity to the clip.

8. REVIEW | get_current_viewport_image
   Take a viewport screenshot at the midpoint frame to verify:
   - Captions are clearly readable
   - Lower-third looks clean and professional
   - Quote overlay doesn't overlap with captions
   Adjust any overlapping text elements.

## Checkpoints
- 3: CLIP_TRIMMED
- 4: CAPTIONS_READY
- 8: REVIEW_DONE
