"""
Módulo para la detección de actividad vocal y identificación de speakers.
"""

from src.detection.vad import detect_voice_activity, auto_threshold_vad, get_voice_timestamps
from src.detection.speaker import (
    analyze_energy_by_track,
    refine_whisper_segments,
    filter_rapid_changes,
    handle_speaker_overlap,
    generate_camera_changes,
    save_speaker_timeline
)
