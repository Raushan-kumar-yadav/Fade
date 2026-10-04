---
name: software_intro
version: "1.0"
triggers:
  - software intro
  - app intro
  - product intro
  - saas video
  - software showcase
  - app showcase
  - software demo intro
  - product launch video
  - app launch
  - fade intro
  - tool intro
comp_type: video
agent_type: video
output_dimensions: [1920, 1080]
fps: 30
max_duration_frames: 2700
---

## Description
Create a cinematic 30-90 second software/app intro video with professional voiceover,
animated title cards, B-roll footage of the software in use, feature callout overlays,
smooth transitions, and a strong call-to-action ending.

## Rules
- Always generate voiceover BEFORE placing any video clips
- Search for cinematic B-roll that matches the software/tech aesthetic (dark UI, screens, people working)
- Use bold white text on dark overlays for all title cards
- Feature callouts must be short (max 5 words each)
- Voiceover drives the pacing — sync video cuts to narration timing
- Add fade transitions between all clips
- Max duration: 90 seconds
- Review viewport at frame 900 (30 seconds) to verify layout

## Steps

1. CONTEXT | get_timeline_state
   Check the current timeline and library for any existing assets.
   Note what's already available before downloading anything new.

2. VOICEOVER | generate_tts
   Write and generate a professional, energetic voiceover script that:
   - Opens with a strong hook (the problem being solved)
   - Introduces the software by name
   - Highlights 3 key features with specific benefits
   - Ends with a clear call-to-action
   Use a confident, professional voice. Aim for 30-60 seconds of audio.
   Place the audio on the timeline.

3. BROLL_SEARCH | download_videos
   Search and download cinematic B-roll footage matching the software theme:
   - Dark modern UI interface shots
   - Person working on laptop/computer
   - Abstract technology/data visualization
   - Clean workspace or office environment
   Download 5-7 clips. Prefer dark, moody, high-quality footage.

4. TIMELINE_BUILD | place_clip
   Place B-roll clips on video track 0 in sequence.
   Align clip timing to match the voiceover narration sections:
   - Clip 1-2: during the hook/problem statement
   - Clip 3-4: during feature highlights
   - Clip 5+: during CTA
   Space clips with no gaps (back-to-back).

5. HOOK_TITLE | add_text_clip
   Add an opening title card at frame 0 (first 3 seconds).
   Text: a powerful 3-5 word hook or the problem statement.
   Large font (90px), bold white, centered. Find free overlay track.
   Animate opacity: 0 to 1 at frame 0, hold, then fade out at frame 60.
   Apply fade_in preset.

6. PRODUCT_NAME | add_text_clip
   Add the product/software name as a hero title.
   Font size 120px+, bold, high contrast. Find free overlay track.
   Animate scale from 0.8 to 1.0 and opacity from 0 to 1 over 20 frames.
   Apply ease_out preset. Place at the moment the voiceover says the product name.

7. FEATURE_CALLOUTS | add_text_clip
   Add 3 feature callout text clips, one for each key feature mentioned in voiceover.
   Font size 48px, bold, slightly transparent background box (bgEnabled: true).
   Each callout appears and disappears in sync with the voiceover mentioning it.
   Use find_free_overlay_track for each. Animate with slide-in from left (pos_x).

8. CTA_CARD | add_text_clip
   Add a final call-to-action card for the last 5 seconds.
   Text: website URL or action phrase (e.g. "Try Fade Free Today").
   Large, centered, bold. Animate scale bounce-in with bounce_out preset.
   Add a semi-transparent background rectangle behind the CTA text.

9. TRANSITIONS | add_transitions_between_all_clips
   Add smooth fade transitions between all video clips.
   Duration: 0.5 seconds (15 frames at 30fps).

10. CAPTIONS | generate_captions
    Generate auto-synced captions from the voiceover audio.
    Style: white bold text, center bottom, readable font size (36px).

11. REVIEW | get_current_viewport_image
    Take a viewport screenshot at frame 900 (30 second mark) to verify:
    - B-roll is visible and well-lit
    - Text overlays are readable and properly positioned
    - No clips overlap incorrectly
    Adjust any issues found.

## Checkpoints
- 2: VOICEOVER_READY
- 4: TIMELINE_BUILT
- 9: TRANSITIONS_DONE
- 11: REVIEW_PASSED
