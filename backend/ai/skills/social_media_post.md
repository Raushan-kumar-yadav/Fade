---
name: social_media_post
version: "1.0"
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
Create a polished social media image or short video post with branded visuals,
compelling text overlay, and platform-optimized dimensions.

## Rules
- Keep text minimal — max 8 words in headline
- Use high-contrast colors for readability
- Brand logo or watermark must be visible
- Image must fill the entire canvas (no letterboxing)
- Text must be readable on mobile (minimum 48px equivalent)
- Always preview viewport before export

## Steps

1. CONTEXT | get_library_assets
   Scan library for brand assets, logos, and relevant imagery.

2. CANVAS | create_composition
   Create a 1080x1080 composition for the post.

3. BACKGROUND | place_clip
   Place the primary hero image or video as background, filling the canvas.
   Apply a subtle vignette or color grade for visual polish.

4. OVERLAY | add_solid_clip
   Add a semi-transparent dark overlay (opacity 40-60%) to improve text readability.

5. HEADLINE | add_text_clip
   Add the main headline text. Bold font, white color, centered.
   Position at vertical center or upper third.

6. SUBTEXT | add_text_clip
   Add supporting text or call-to-action below the headline.
   Smaller size, lighter weight, same color scheme.

7. BRANDING | place_clip
   Add brand logo or watermark at bottom-right corner.
   Small size, semi-transparent (70-80% opacity).

8. EFFECTS | apply_effect_to_clip
   Apply subtle color correction to background for visual coherence.
   Optionally add grain or texture overlay for premium feel.

9. REVIEW | get_current_viewport_image
   Review the final composition. Check text readability and visual hierarchy.
   Adjust positioning if needed.

10. EXPORT | export_video
    Export as PNG (image) or MP4 (if animated). High quality.

## Checkpoints
- 3: BACKGROUND_SET
- 6: TEXT_DONE
- 10: EXPORT_DONE
