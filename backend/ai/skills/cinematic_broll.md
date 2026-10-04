---
name: cinematic_broll
version: "1.0"
triggers:
  - find broll
  - best broll
  - cinematic footage
  - b-roll search
  - find footage
  - search footage
  - download broll
  - get broll
  - broll for
  - find clips for
  - search clips
  - find video clips
comp_type: video
agent_type: video
output_dimensions: [1920, 1080]
fps: 30
max_duration_frames: 9000
---

## Description
Intelligently search, download, and curate the best cinematic B-roll footage for a
given topic. Analyzes existing timeline context, downloads high-quality matched clips,
and organizes them in the library ready for placement.

## Rules
- Always read the timeline first to understand what topic/context B-roll is needed for
- Download at least 6 clips minimum — give the user variety to choose from
- Prefer longer clips (10s+) over short ones for editing flexibility
- After downloading, index each clip so scene search works on it
- Place clips in a dedicated "B-Roll" track, not on existing content tracks
- Add descriptive label text clips showing the search term used for each batch
- Do not delete or move existing timeline clips

## Steps

1. CONTEXT | get_timeline_state
   Read the full timeline state to understand:
   - What clips already exist and what topic they cover
   - What's in the voiceover/narration (if any) to match B-roll to
   - Which tracks are in use so we place B-roll on a free track

2. LIBRARY_SCAN | get_library_assets
   Scan the library for any existing assets that could serve as B-roll.
   Note asset IDs of relevant footage already imported.

3. TOPIC_ANALYSIS | search_video_scenes
   Search existing video clips for scene descriptions to understand the topic.
   This tells us what visual style and subject matter to match when downloading.

4. BROLL_BATCH_1 | download_videos
   Search and download the first batch of B-roll (3-4 clips) matching the primary topic.
   Use cinematic, high-quality search terms. Prefer 4K or HD footage.
   Focus on: establishing shots, wide angles, atmospheric footage.

5. BROLL_BATCH_2 | download_videos
   Search and download a second batch (3-4 clips) with different search angles.
   Focus on: close-ups, detail shots, action shots related to the topic.
   Vary the search terms from batch 1 to maximize visual diversity.

6. PLACEMENT | place_clip
   Find a free overlay track and place all downloaded B-roll clips in sequence.
   Label this track "B-Roll — [topic]".
   Space clips evenly with small gaps for easy selection.

7. REVIEW | get_current_viewport_image
   Take a viewport screenshot to verify all B-roll clips are visible in the timeline.
   Confirm the library panel shows the new assets indexed correctly.

## Checkpoints
- 4: FIRST_BATCH_READY
- 6: ALL_CLIPS_PLACED
- 7: REVIEW_DONE
