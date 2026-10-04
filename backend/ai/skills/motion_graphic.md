---
name: motion_graphic
version: "1.1"
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
Create a polished motion graphic sequence using animated WebComp widgets for complex
motion design effects (particle systems, animated counters, gradient wipes, SVG morphs),
combined with keyframe-animated text/shapes and professional easing curves.
WebComps power the effects that native clips cannot achieve.

## Rules
- Use create_webcomp for any complex animation not achievable with keyframes alone
- Every WebComp must be added to the timeline with add_webcomp_to_timeline immediately after creation
- Use find_free_overlay_track before every text, shape, or webcomp placement
- Dark background shape goes on track 0; all elements layer above it
- Font must be bold, high-contrast (white or accent color on dark)
- Pair animate_property with apply_curve_preset immediately after every animation
- Max duration: 60 seconds
- Always review viewport at the midpoint frame before export

## Steps

1. BACKGROUND | add_shape_clip
   Create a full-canvas dark rectangle as the background layer on track 0.
   Width: 1920, Height: 1080, fill color: near-black (r=0.05, g=0.05, b=0.08, a=1.0).
   Place at frame 0 spanning the full composition duration.

2. PARTICLE_WEBCOMP | create_webcomp
   Create a WebComp for the animated particle / ambient background effect.
   Use HTML5 Canvas with requestAnimationFrame to render floating particles or
   a grid of dots that pulse gently. Use a vibrant accent color (deep blue or teal).
   Style: full 1920x1080, transparent background so the shape layer shows through.
   JavaScript: animate 60-80 particles with random velocities, wrap at edges.
   Name it "particle_bg". Then immediately add it to the timeline with add_webcomp_to_timeline
   on a free overlay track, spanning the full composition duration.

3. ACCENT_WEBCOMP | create_webcomp
   Create a WebComp for a decorative animated geometric accent.
   Use SVG with CSS animations: a rotating ring or morphing polygon that pulses.
   Position it off-center (e.g. bottom-right quadrant) as a design element.
   Size: 400x400px. Accent color matches the particle system.
   Name it "accent_shape". Add to timeline with add_webcomp_to_timeline on a free track.

4. MAIN_TITLE | add_text_clip
   Add the main title text on a free overlay track.
   Bold, large font (120px+), white color.
   Animate pos_y: slide in from +200px to 0 over 25 frames.
   Apply curve preset: ease_out to the entrance.
   Then animate opacity: hold at 1.0, then at the outro animate to 0 over 15 frames.

5. SUBTITLE | add_text_clip
   Add a subtitle or tagline below the main title on a free overlay track.
   Smaller font (48px), lighter weight, opacity 0.85.
   Animate opacity from 0 to 1 over 20 frames, starting 15 frames after title entrance.
   Apply curve preset: fade_in.

6. COUNTER_WEBCOMP | create_webcomp
   Create a WebComp for an animated stat or number counter (optional — use if the
   motion graphic includes data or metrics).
   HTML: large bold number that counts up from 0 to target value over 2 seconds.
   CSS: monospace font, accent color glow effect. Size: 600x200px.
   Name it "counter". Add to timeline with add_webcomp_to_timeline on a free track,
   timed to appear during the main content section.

7. HIGHLIGHT_LINE | add_shape_clip
   Add a thin horizontal line (1920x4px) under the title as a separator.
   Color matches accent. Animate scale_x from 0 to 1 over 30 frames.
   Apply curve preset: ease_both. Starts 30 frames after title entrance.

8. LOGO_WEBCOMP | create_webcomp
   Create a WebComp for an animated logo badge or icon in the bottom-right corner.
   Use SVG path animation: the logo/icon draws itself (stroke-dashoffset animation)
   or fades in with a scale bounce. Size: 200x200px.
   CSS: @keyframes drawIn with stroke-dashoffset from 100% to 0 over 1.5s.
   Name it "logo_badge". Add to timeline with add_webcomp_to_timeline on a free track,
   appearing at frame 45 and staying until the end.

9. REVIEW | get_current_viewport_image
   Take a viewport screenshot at the midpoint frame to verify all elements are
   visible, properly layered, and look polished. Check WebComps are rendering.
   Adjust any misaligned clips or WebComp sizes.

10. EXPORT | export_video
    Export final motion graphic as MP4, H.264, high quality (CRF 18).

## Checkpoints
- 3: WEBCOMPS_CREATED
- 5: TITLES_ANIMATED
- 8: LOGO_PLACED
- 10: EXPORT_DONE
