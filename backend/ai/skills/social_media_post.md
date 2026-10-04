---
name: social_media_post
version: "1.1"
triggers:
  - social media post
  - instagram post
  - linkedin post
  - twitter post
  - facebook post
  - social post
  - reel
  - short video
  - social content
comp_type: image
agent_type: image
output_dimensions: [1080, 1080]
fps: 30
max_duration_frames: 900
---

## Description
Create a polished social media image or short animated video post with branded visuals,
compelling text overlays, animated WebComp elements (animated counters, gradient wipes,
ticker scrolls, icon animations), and platform-optimized dimensions.
WebComps add the motion design polish that makes posts stand out in feeds.

## Rules
- Keep text minimal — max 8 words in headline
- Use high-contrast colors for readability
- Brand logo or watermark must be visible
- Image must fill the entire canvas (no letterboxing)
- Text must be readable on mobile (minimum 48px equivalent)
- WebComps should enhance — not clutter — keep them subtle and purposeful
- Always preview viewport before export
- add_webcomp_to_timeline immediately after every create_webcomp call

## Steps

1. CONTEXT | get_library_assets
   Scan library for brand assets, logos, and relevant imagery.
   Note any existing brand colors or style guides in asset names.

2. CANVAS | create_composition
   Create a 1080x1080 composition for the post.

3. BACKGROUND | place_clip
   Place the primary hero image or video as background, filling the canvas.
   Apply a subtle vignette or color grade for visual polish.

4. OVERLAY | add_solid_clip
   Add a semi-transparent dark overlay (opacity 40-60%) to improve text readability.

5. ANIMATED_BG_WEBCOMP | create_webcomp
   Create a WebComp for a subtle animated background texture or effect.
   Options (pick what fits the post topic):
   - Gradient mesh that shifts slowly through brand colors (CSS @keyframes hue-rotate)
   - Floating geometric shapes (SVG triangles/circles) drifting across the frame
   - Noise/grain animated texture for a premium editorial feel
   - Glowing radial gradient that pulses gently
   Size: 1080x1080. Use CSS animations only (no heavy JS).
   Name it "animated_bg". Add to timeline with add_webcomp_to_timeline on a free overlay track,
   spanning the full post duration. Set opacity low (20-30%) so background image shows through.

6. HEADLINE | add_text_clip
   Add the main headline text. Bold font, white color, centered.
   Position at vertical center or upper third.
   Animate: scale from 0.9 to 1.0 and opacity from 0 to 1 over 15 frames.
   Apply ease_out preset.

7. SUBTEXT | add_text_clip
   Add supporting text or call-to-action below the headline.
   Smaller size, lighter weight, same color scheme.
   Animate opacity from 0 to 1 after headline finishes. Apply fade_in preset.

8. METRIC_WEBCOMP | create_webcomp
   Create a WebComp for an animated metric, stat, or highlight badge.
   Options (pick the most relevant for the post):
   - Animated number counter (e.g. "10,000+ Users") counting up on loop
   - Progress bar filling to a percentage
   - Ticker/marquee scrolling key features or hashtags
   - Emoji burst animation for engagement posts
   HTML: clean card design with brand colors. CSS animation loops smoothly.
   Size: 400x120px. Name it "metric_badge".
   Add to timeline with add_webcomp_to_timeline on a free overlay track.
   Position at bottom third of the frame.

9. BRANDING_WEBCOMP | create_webcomp
   Create a WebComp for an animated brand logo badge.
   SVG logo that draws itself in (stroke-dashoffset) or fades in with a subtle glow.
   Add a "verified" checkmark or brand icon if relevant.
   Size: 180x60px. Name it "brand_badge".
   Add to timeline with add_webcomp_to_timeline, positioned bottom-right corner.

10. EFFECTS | apply_effect_to_clip
    Apply subtle color correction to background for visual coherence.
    Optionally add grain or texture overlay for premium editorial feel.

11. REVIEW | get_current_viewport_image
    Review the final composition. Check:
    - Text readability and visual hierarchy
    - WebComps rendering at correct positions
    - Overall visual balance and brand consistency
    Adjust positioning if needed.

12. EXPORT | export_video
    Export as PNG (static image) or MP4 (animated post). High quality.

## Checkpoints
- 3: BACKGROUND_SET
- 5: WEBCOMP_BG_ACTIVE
- 9: ALL_WEBCOMPS_PLACED
- 12: EXPORT_DONE
