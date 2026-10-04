---
name: product_demo
version: "1.0"
triggers:
  - product demo
  - product video
  - demo video
  - showcase video
  - feature demo
  - product showcase
  - app demo
  - walkthrough video
comp_type: video
agent_type: video
output_dimensions: [1920, 1080]
fps: 30
max_duration_frames: 5400
---

## Description
Create a professional product demo video with feature highlights, 
text callouts, smooth transitions, and a strong call-to-action ending.

## Rules
- Keep total video under 3 minutes
- Every feature must have a text callout label
- Use smooth slide or fade transitions only
- End with a clear call-to-action screen
- Color grade for consistency across all clips
- Add background music at low volume (20-30%)

## Steps

1. CONTEXT | get_library_assets
   Scan library for product footage, screenshots, logos, and brand assets.

2. STRUCTURE | get_timeline_state
   Understand current timeline state. Plan 4 sections: Hook, Features, Benefits, CTA.

3. HOOK | place_clip
   Place the most compelling product clip first (0-10 seconds).
   This is the attention-grabber — use the best visual available.

4. FEATURES | place_clip
   Place feature demonstration clips in sequence.
   Each feature gets 15-30 seconds of screen time.

5. CALLOUTS | add_text_clip
   Add animated text callouts for each feature.
   Style: clean sans-serif, product brand colors, slide-in animation.

6. MUSIC | place_clip
   Place background music on audio track 1.
   Set volume to 25% so it does not overpower narration.

7. TRANSITIONS | add_transitions_between_all_clips
   Add smooth transitions between all sections. Use slide or fade style.

8. CTA | add_text_clip
   Add a final call-to-action screen with product name and tagline.
   Bold text, brand colors, centered layout.

9. COLOR | apply_effect_to_clip
   Apply consistent color correction across all video clips.
   Boost contrast slightly, normalize white balance.

10. REVIEW | get_current_viewport_image
    Review the complete edit. Verify callouts are readable and CTA is impactful.

11. EXPORT | export_video
    Export as MP4, H.264, 1080p, high quality.

## Checkpoints
- 4: FOOTAGE_PLACED
- 6: AUDIO_DONE
- 8: CTA_DONE
- 11: EXPORT_DONE
