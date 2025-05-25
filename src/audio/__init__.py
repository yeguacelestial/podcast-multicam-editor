"""
Módulo para procesamiento y análisis de audio.
Incluye funciones para extracción, sincronización y análisis de pistas de audio.
"""

from src.audio.analyzer import validate_audio_file, load_audio, analyze_audio_file
from src.audio.extractor import extract_audio_from_video
from src.audio.synchronizer import find_offset_between_audios, create_audio_fingerprint
