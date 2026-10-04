---
name: short_reel
version: "1.0"
triggers:
  - short reel
  - vertical video
  - tiktok video
  - reels video
  - youtube short
  - instagram reel
  - short form video
  - 60 second video
  - 30 second reel
  - viral short
  - social reel
comp_type: video
agent_type: video
output_dimensions: [1080, 1920]
fps: 30
max_duration_frames: 1800
---

## Description
Create a fast-paced, attention-grabbing short-form vertical video (9:16) optimized
for TikTok, Instagram Reels, and YouTube Shorts. Strong hook in the first 3 seconds,
punchy captions, dynamic text, and energetic pacing.

## Rules
- Output dimensions MUST be 1080x1920 (vertical/portrait)
- Hook must appear in the FIRST 3 seconds — no slow intros
- Keep total duration under 60 seconds (1800 frames at 30fps)
- Captions are mandatory — short-form viewers often watch without sound
- Use punchy, short sentences for all text overlays
- Transitions must be fast — no slow fades, use cuts or snap transitions
- Energy and pacing are the priority — fast cuts every 3-5 seconds
- Always review viewport to check vertical framing

## Steps

1. CANVAS | crop_canvas
   Set the composition to vertical format: 1080x1920.
   This is essential for short-form vertical video output.

2. HOOK | add_text_clip
   Create the opening hook text for the first 3 seconds (0-90 frames).
   Bold, large font (100px+), high contrast. Use a question or bold statement.
   Animate: scale from 1.2 to 1.0 over 10 frames (pop-in effect).
   Apply bounce_out preset. Find free overlay track.

3. BROLL | download_videos
   Download 4-6 fast-paced, visually dynamic B-roll clips matching the topic.
   Prefer clips with motion, action, or visual interest.
   Short clips (5-10 seconds) are preferred for punchy cuts.

4. TIMELINE | place_clip
   Place B-roll clips on video track 0 back-to-back with NO gaps.
   Keep each clip short — trim to 3-5 seconds each for fast pacing.
   Total video duration should be 30-60 seconds.

5. VOICEOVER | generate_tts
   Write and generate a punchy, energetic voiceover script.
   Keep it conversational, fast-paced. No filler words.
   Match the script to the total video duration.
   Use an energetic voice style.

6. CAPTIONS | generate_captions
   Generate auto-synced captions from the voiceover.
   Style: large bold text (52px+), centered, with background box for readability.
   Short-form viewers often watch muted — captions are critical.

7. TEXT_OVERLAYS | add_text_clip
   Add 2-3 key point text overlays that emphasize important moments.
   Bold, punchy, short (3-5 words max each).
   Animate each with a quick pop-in (scale or bounce_out).

8. CTA | add_text_clip
   Add a final call-to-action in the last 3 seconds.
   Text: "Follow for more", "Link in bio", or relevant CTA.
   Bold, centered, with emphasis animation.

9. REVIEW | get_current_viewport_image
   Take a viewport screenshot at frame 45 (1.5 seconds) to verify:
   - Vertical framing looks correct
   - Hook text is visible and impactful
   - No content is cropped at the edges

## Checkpoints
- 4: TIMELINE_BUILT
- 6: CAPTIONS_DONE
- 9: REVIEW_PASSED
