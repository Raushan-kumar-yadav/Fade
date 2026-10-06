  
from backend.ai.tools import (
    # Read-only / shared  
    get_library,
    get_library_assets,
    get_pending_jobs,
    search_news,
    generate_image,
    get_playback_state,
    seek_to,
    play,
    pause,
    undo,
    redo,

    # Composition management  
    create_composition,
    list_compositions,
    add_comp_to_timeline,
    activate_comp,
    get_comp_state,
    get_comp_layers,
    update_comp_layer,
    move_comp_layer,
    rename_composition,
    delete_composition,

    # Video / Timeline tools  
    get_timeline_state,
    get_timeline_range,
    get_timeline_context,
    split_clip,
    trim_clip,
    move_clip,
    reposition_clip,
    delete_clip,
    place_clip,
    add_clip_to_comp,
    update_clip,
    bulk_update_clips,
    get_clip_info,
    get_clip_context,
    get_clip_about,
    get_selected_clip,
    get_selected_clips,
    list_timeline_clips,
    describe_clip,
    describe_selected_clip,
    get_clip_params,
    set_clip_param,
    get_effects_catalog,
    add_effect,
    remove_effect,
    set_effect_param,
    list_effects_catalog,
    apply_effect_to_clip,
    patch_clip_effect,
    add_text_clip,
    set_text_style,
    get_comp_resolution,
    layout_text_block,
    layout_element,

    add_solid_clip,
    add_shape_clip,
    add_svg_clip,
    get_transitions_catalog,
    add_transition,
    add_transitions_between_all_clips,
    add_track,
    remove_track,
    remove_track_at_index,
    find_free_overlay_track,
    mute_track,
    move_track,
    lock_track,
    solo_track,
    add_video_clip_by_scene,
    search_video_scenes,
    download_videos,
    schedule_download,
    create_news_video,
    get_current_viewport_image,
    get_viewport_at_frame,
    get_comp_thumbnail,
    crop_canvas,
    add_mask,
    update_mask,
    remove_mask,
    list_masks,
    analyze_virality,
    export_video,
    set_in_out_points,
    remove_clip,

    # Animation tools  
    animate_property,
    remove_keyframe,
    clear_animation,
    get_keyframes,
    list_curve_presets,
    apply_curve_preset,
    move_keyframe,
    set_expression,
    clear_expression,
    test_expression,
    transform_batch,

    # Audio tools  
    set_clip_volume,
    mute_clip,
    get_clip_volume,
    generate_tts,
    list_kokoro_voices,
    generate_captions,
    remove_silence,
    get_transcript,

    #   Image tools  
    add_image_clip_by_scene,
    schedule_image_download,
    download_images,
    get_asset_context,
    get_index_status,
    set_text_content,
    check_job_status,
    cancel_job,

    #   PDF tools  
    create_pdf_doc,
    list_pdf_docs,
    list_pdf_pages,
    add_pdf_page,
    delete_pdf_page,
    reorder_pdf_pages,
    export_pdf_doc,
    get_pdf_page_summary,
    get_pdf_doc_summary,

    #   WebComp tools  
    create_webcomp,
    list_webcomps,
    list_webcomp_templates,
    add_webcomp_to_timeline,
    get_webcomp_clip_info,
    read_webcomp_file,
    edit_webcomp_file,
    set_webcomp_params,
    set_webcomp_transform,
    set_webcomp_opacity,
    delete_webcomp,
    reload_webcomp,
    update_webcomp_meta,

    #   Social  
    get_social_connections,
    get_youtube_videos,

    # Tracking & Privacy
    start_track,
    check_track_job,
    wait_for_track,
    list_tracks_for_clip,
    delete_track,
    add_blur_to_track,
    add_follow_to_track,
    track_and_blur_face,
    track_and_blur_text,

    ALL_TOOLS,
)

# Background removal 
from backend.ai.bg_remove_tools import BG_REMOVE_TOOLS
from backend.ai.skill_tools import SKILL_TOOLS
from backend.ai.plan_tools import PLAN_TOOLS

#   Shared read-only tools every agent gets  
_SHARED = [
    get_library,
    get_library_assets,
    get_pending_jobs,
    generate_image,
    check_job_status,
    cancel_job,
    undo,
    redo,
    # Skill management  
    *SKILL_TOOLS,
    # Plan management  
    *PLAN_TOOLS,
]

#   Video Agent  
VIDEO_TOOLS = _SHARED + [
    get_timeline_state, get_timeline_range, get_timeline_context,
    split_clip, trim_clip, move_clip, reposition_clip, delete_clip,
    place_clip, add_clip_to_comp, update_clip, bulk_update_clips,
    get_clip_info, get_clip_context, get_clip_about,
    get_selected_clip, get_selected_clips, list_timeline_clips,
    describe_clip, describe_selected_clip, get_clip_params, set_clip_param,
    get_effects_catalog, add_effect, remove_effect, set_effect_param,
    list_effects_catalog, apply_effect_to_clip, patch_clip_effect,
    add_text_clip, set_text_style, layout_text_block, layout_element,
    add_solid_clip, add_shape_clip, add_svg_clip,
    get_transitions_catalog, add_transition, add_transitions_between_all_clips,
    add_track, remove_track, remove_track_at_index,
    find_free_overlay_track, mute_track, move_track, lock_track, solo_track,
    add_video_clip_by_scene, search_video_scenes,
    download_videos, schedule_download, create_news_video,
    get_current_viewport_image, get_viewport_at_frame, get_comp_thumbnail,
    crop_canvas, add_mask, update_mask, remove_mask, list_masks,
    analyze_virality, export_video, set_in_out_points, remove_clip,
    animate_property, remove_keyframe, clear_animation, get_keyframes,
    list_curve_presets, apply_curve_preset, move_keyframe,
    set_expression, clear_expression, test_expression, transform_batch,
    set_clip_volume, mute_clip, get_clip_volume,
    generate_captions, remove_silence, get_transcript,
    create_composition, list_compositions, add_comp_to_timeline,
    activate_comp, get_comp_state, get_comp_layers,
    update_comp_layer, move_comp_layer, rename_composition, delete_composition,
    seek_to, play, pause,
    create_webcomp, list_webcomps, list_webcomp_templates,
    add_webcomp_to_timeline, get_webcomp_clip_info, read_webcomp_file,
    edit_webcomp_file, set_webcomp_params, set_webcomp_transform,
    set_webcomp_opacity, delete_webcomp, reload_webcomp, update_webcomp_meta,
    get_social_connections, get_youtube_videos,
    search_news,
    # Tracking & Privacy
    start_track, check_track_job, wait_for_track,
    list_tracks_for_clip, delete_track,
    add_blur_to_track, add_follow_to_track,
    track_and_blur_face, track_and_blur_text,
    # Background removal (video)
    *BG_REMOVE_TOOLS,
]

#   Image Agent  
IMAGE_TOOLS = _SHARED + [
    create_composition, list_compositions, activate_comp,
    get_comp_state, get_comp_layers, update_comp_layer, move_comp_layer,
    rename_composition, delete_composition,
    place_clip, add_clip_to_comp, add_image_clip_by_scene,
    get_clip_info, get_clip_params, set_clip_param, update_clip,
    add_text_clip, set_text_style, layout_text_block, layout_element,
    add_solid_clip, add_shape_clip, add_svg_clip,
    get_effects_catalog, add_effect, remove_effect, set_effect_param,
    list_effects_catalog, apply_effect_to_clip, patch_clip_effect,
    add_mask, update_mask, remove_mask, list_masks,
    animate_property, remove_keyframe, clear_animation, get_keyframes,
    set_expression, clear_expression,
    get_current_viewport_image, get_comp_thumbnail,
    crop_canvas,
    schedule_image_download, download_images, get_asset_context, get_index_status,
    set_text_content,
    export_video,  # export as image frame too
    create_webcomp, list_webcomps, add_webcomp_to_timeline,
    search_news,
    # Background removal (image)
    *BG_REMOVE_TOOLS,
]

#   Audio Agent  
AUDIO_TOOLS = _SHARED + [
    get_timeline_state, list_timeline_clips, get_clip_info,
    get_clip_params, set_clip_param, update_clip,
    add_track, remove_track, mute_track, move_track, lock_track, solo_track,
    set_clip_volume, mute_clip, get_clip_volume,
    generate_tts, list_kokoro_voices,
    generate_captions, remove_silence, get_transcript,
    add_effect, remove_effect, set_effect_param, apply_effect_to_clip,
    animate_property, remove_keyframe, clear_animation, get_keyframes,
    seek_to, play, pause,
]

PDF_TOOLS = _SHARED + [
    create_pdf_doc, list_pdf_docs, list_pdf_pages,
    add_pdf_page, delete_pdf_page, reorder_pdf_pages,
    export_pdf_doc,
    get_pdf_page_summary, get_pdf_doc_summary,
    # Text layout — the core of PDF creation
    add_text_clip, set_text_style, layout_text_block, layout_element, set_text_content,
    add_solid_clip, add_shape_clip, place_clip,
    find_free_overlay_track,
    animate_property, remove_keyframe, clear_animation,
    list_curve_presets, apply_curve_preset,
    get_current_viewport_image, get_comp_thumbnail,
    create_composition, list_compositions, activate_comp, get_comp_state,
    search_news,
    get_asset_context,
    schedule_image_download, download_images,
    create_webcomp, add_webcomp_to_timeline, read_webcomp_file, edit_webcomp_file,
    *BG_REMOVE_TOOLS,
]

#   General / Home Agent (read-heavy, no destructive edits)  
GENERAL_TOOLS = _SHARED + [
    get_timeline_state, list_timeline_clips, list_compositions,
    get_comp_state, get_current_viewport_image,
    search_news, download_videos, download_images,
    generate_tts, list_kokoro_voices,
    get_asset_context, get_index_status,
    get_social_connections,
    # BG removal available in general context too
    *BG_REMOVE_TOOLS,
]

# Director Agent 
 
DIRECTOR_TOOLS = ALL_TOOLS  


#   Registry  
TOOL_SETS: dict[str, list] = {
    "video": VIDEO_TOOLS,
    "image": IMAGE_TOOLS,
    "audio": AUDIO_TOOLS,
    "pdf": PDF_TOOLS,
    "director": DIRECTOR_TOOLS,
    "home": GENERAL_TOOLS,
    "ai": GENERAL_TOOLS,
    "export":   VIDEO_TOOLS,   # export tab uses video pipeline
    "tracking": VIDEO_TOOLS,   # tracking tab — full video toolset
}

def get_tools_for(agent_type: str) -> list:
    return TOOL_SETS.get(agent_type, VIDEO_TOOLS)
