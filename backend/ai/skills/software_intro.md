---
name: software_intro
version: "1.1"
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
animated WebComp widgets (live UI mockups, animated feature cards, stat counters,
tech HUD overlays), B-roll footage, animated title cards, transitions, captions,
and a strong CTA. WebComps simulate the software interface and make the video feel
like an actual product demo.

## Rules
- Always generate voiceover BEFORE placing any video clips
- Use create_webcomp to build animated UI mockup panels — this is the key differentiator
- add_webcomp_to_timeline immediately after every create_webcomp call
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

7. UI_MOCKUP_WEBCOMP | create_webcomp
   Create a WebComp that simulates an animated UI dashboard or app interface panel.
   This is the KEY motion design element — it shows the software "in action".
   HTML: a realistic-looking dark-themed app UI panel with:
     - A navigation sidebar with icon items
     - A main content area with cards or data
     - Animated progress bars or charts that fill on load
     - Subtle loading shimmer effects using CSS keyframes
   Size: 800x500px. Dark theme (#0f0f1a background, accent color highlights).
   CSS: @keyframes shimmer, fadeIn, barFill animations.
   Name it "ui_mockup". Add to timeline with add_webcomp_to_timeline on a free overlay track.
   Position center-right. Appear during the feature highlights section.

8. FEATURE_CARDS_WEBCOMP | create_webcomp
   Create a WebComp showing animated feature highlight cards that slide in one by one.
   HTML: 3 cards stacked vertically, each with an icon + title + 1-line description.
   CSS: @keyframes slideInLeft — each card animates in with a 0.3s delay between them.
   Use glassmorphism style: backdrop-filter blur, semi-transparent white border.
   Size: 380x320px. Name it "feature_cards".
   Add to timeline with add_webcomp_to_timeline on a free overlay track.
   Timed to appear during the "3 key features" section of the voiceover.

9. STAT_COUNTER_WEBCOMP | create_webcomp
   Create a WebComp for animated social proof stats/metrics.
   HTML: 3 large numbers side-by-side (e.g. "10K+ Users", "99% Uptime", "4.9★ Rating").
   JavaScript: countUp animation — each number counts from 0 to target over 2 seconds.
   Style: large bold font (72px), accent color, minimal dark card background.
   Size: 900x180px. Name it "stats_bar".
   Add to timeline with add_webcomp_to_timeline on a free overlay track.
   Position at the bottom third, timed to the social proof moment in the voiceover.

10. HUD_OVERLAY_WEBCOMP | create_webcomp
    Create a subtle tech HUD (heads-up display) overlay WebComp for cinematic feel.
    HTML: thin corner brackets in the four corners of the frame (1920x1080).
    SVG corner marks that pulse gently. Scanline or grid overlay at low opacity.
    CSS: @keyframes pulse — opacity 0.3 to 0.7 over 2s, infinite alternate.
    Color: accent color at 30% opacity. Name it "hud_overlay".
    Add to timeline with add_webcomp_to_timeline spanning the full middle section.
    This gives the video a premium tech-product aesthetic.

11. CTA_CARD | add_text_clip
    Add a final call-to-action card for the last 5 seconds.
    Text: website URL or action phrase (e.g. "Try Fade Free Today").
    Large, centered, bold. Animate scale bounce-in with bounce_out preset.
    Add a semi-transparent background rectangle behind the CTA text.

12. TRANSITIONS | add_transitions_between_all_clips
    Add smooth fade transitions between all video clips.
    Duration: 0.5 seconds (15 frames at 30fps).

13. CAPTIONS | generate_captions
    Generate auto-synced captions from the voiceover audio.
    Style: white bold text, center bottom, readable font size (36px).

14. REVIEW | get_current_viewport_image
    Take a viewport screenshot at frame 900 (30 second mark) to verify:
    - B-roll is visible and well-lit
    - WebComp UI mockup is rendering correctly
    - Feature cards and stat counters are positioned well
    - HUD overlay is subtle (not distracting)
    - Text overlays are readable
    Adjust any sizing or position issues.

## Checkpoints
- 2: VOICEOVER_READY
- 4: TIMELINE_BUILT
- 7: UI_MOCKUP_LIVE
- 10: ALL_WEBCOMPS_PLACED
- 13: CAPTIONS_DONE
- 14: REVIEW_PASSED
