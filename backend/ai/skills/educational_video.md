---
name: educational_video
version: "1.0"
triggers:
  - educational video
  - tutorial video
  - explainer video
  - lesson video
  - teaching video
  - how to video
  - learning video
  - course video
  - instructional video
comp_type: video
agent_type: video
output_dimensions: [1920, 1080]
fps: 30
max_duration_frames: 9000
---

## Description
Create an optimized educational video with structured narration, synced captions,
chapter title overlays, B-roll footage, and clean fade transitions.

## Rules
- Always generate captions (required for accessibility)
- Use only fade transitions between clips
- Add chapter lower-thirds at the start of each section
- Font must be bold and high-contrast (white on dark)
- Max 5 minutes total duration
- Place narration audio BEFORE placing visuals
- Each content section must have at least one B-roll clip
- Review viewport after placing clips to verify layout

## Steps

1. CONTEXT | get_library_assets
   Scan the library to discover all available assets (videos, images, audio).
   Note any footage that is relevant to the topic.

2. SCRIPT | get_timeline_state
   Write the full narration script for the requested topic as plain text in your reply.
   If the user supplied narration text or a scene breakdown, use it verbatim.
   Otherwise break it into Introduction, Main Content, Summary, sized to the
   requested duration. Do NOT generate audio in this step.

3. VOICEOVER | generate_tts
   Generate narration audio from the script using a professional voice.
   Add an audio track if none exists and place the audio on it at frame 0.

4. VISUALS | download_videos
   Download B-roll footage matching each script section (one search query per
   section, or the exact queries the user listed). Also download any images the
   user asked for. If the library already has relevant footage, reuse it.

5. TIMELINE | place_clip
   Place the footage assets from the VISUALS step on video track 0 in script
   order, back to back, covering the narration duration. Use only assetIds
   returned by earlier steps or get_library_assets (never a composition id).

6. TITLES | add_text_clip
   Add chapter title lower-thirds at the start of each section.
   Style: bold white text, 80% from bottom, 1-second fade in/out.

7. CAPTIONS | generate_captions
   Generate auto-synced captions from the narration audio.
   Style: white bold text, center bottom.

8. TRANSITIONS | add_transitions_between_all_clips
   Add fade transitions between all video clips. Duration: 0.5s each.

9. REVIEW | get_current_viewport_image
   Take a viewport screenshot at the midpoint of the video to verify
   the layout looks correct. Adjust any misaligned clips.

10. EXPORT | export_video
    Export final video as MP4, H.264 codec, high quality (CRF 18).

## Checkpoints
- 3: VOICEOVER_READY
- 5: TIMELINE_BUILT
- 7: CAPTIONS_ADDED
- 10: EXPORT_DONE
