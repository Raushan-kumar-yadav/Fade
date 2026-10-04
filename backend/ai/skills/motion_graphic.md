---
name: motion_graphic
version: "1.0"
triggers:
  - motion graphic
  - animated intro
  - title sequence
  - kinetic typography
  - kinetic type
  - logo animation
  - animated logo
  - motion design
  - animated title
  - intro animation
comp_type: video
agent_type: video
output_dimensions: [1920, 1080]
fps: 30
max_duration_frames: 1800
---

## Description

Create a polished motion graphic sequence with animated text, geometric shapes,
smooth keyframe animations, and professional easing curves. No footage required —
pure typography and shape animation.

## Rules

- must use WebComp and add_text_clip and add_shape_clip — no video footage needed
- Every element must have keyframe animation (entrance + hold + exit)
- Always pair animate_property with apply_curve_preset immediately after
- Use find_free_overlay_track before every text or shape placement
- Dark background shape goes on track 0; elements layer above it
- Font must be bold, high-contrast (white or accent color on dark)
- Max duration: 60 seconds
- Always review viewport at the midpoint frame before export

## Steps

1. BACKGROUND | add_shape_clip
   Create a full-canvas dark rectangle as the background layer on track 0.
   Width: 1920, Height: 1080, fill color: near-black (r=0.05, g=0.05, b=0.08, a=1.0).
   Place at frame 0 spanning the full composition duration.

2. ACCENT_SHAPE | add_shape_clip
   Add a decorative geometric accent shape (rectangle or circle) as a design element.
   Use a vibrant accent color (deep blue, purple, or teal).
   Find a free overlay track first. Animate scale_x from 0 to 1 over 20 frames.
   Apply curve preset: snap.

3. MAIN_TITLE | add_text_clip
   Add the main title text using add_text_clip on a free overlay track.
   Bold, large font (120px+), white color.
   Animate pos_y: slide in from +200px to 0 over 25 frames, then hold.
   Apply curve preset: ease_out to the entrance.

4. SUBTITLE | add_text_clip
   Add a subtitle or tagline below the main title on a free overlay track.
   Smaller font (48px), lighter weight, slight opacity (0.85).
   Animate opacity from 0 to 1 over 20 frames, delayed by 15 frames after title.
   Apply curve preset: fade_in.

5. HIGHLIGHT_LINE | add_shape_clip
   Add a thin horizontal line (1920x4px) under the title as a separator.
   Color matches accent shape. Animate scale_x from 0 to 1 over 30 frames.
   Apply curve preset: ease_both. Start after title entrance (frame 30).

6. DETAIL_TEXT | add_text_clip
   Add supporting detail text or feature points below the highlight line.
   Font size 36px. Animate pos_x from -100 to 0 and opacity from 0 to 1 over 20 frames.
   Apply curve preset: ease_out.

7. LOGO_BADGE | add_shape_clip
   Add a small circular shape in the bottom-right corner as a logo/badge placeholder.
   Animate scale from 0 to 1 with bounce_out preset over 20 frames.
   Appears at frame 45.

8. EXIT_ANIMATION | animate_property
   Add exit keyframes to the main title and subtitle.
   Main title: animate pos_y from 0 to -200 at the last 20 frames.
   Apply ease_in preset for exits. Creates a clean outro.

9. REVIEW | get_current_viewport_image
   Take a viewport screenshot at the midpoint frame to verify all elements
   are visible, properly layered, and look polished. Adjust any misaligned clips.

10. EXPORT | export_video
    Export final motion graphic as MP4, H.264, high quality (CRF 18).

## Checkpoints

- 3: TITLE_PLACED
- 6: ANIMATION_COMPLETE
- 10: EXPORT_DONE
