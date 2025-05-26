"""
Módulo para detección de speaker activo.
Implementa funciones para identificar qué speaker está hablando en cada momento,
filtrar cambios rápidos y manejar casos de overlap.
"""

import os
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
import librosa
from rich.progress import Progress
from scipy import signal
import json

from src.audio.analyzer import load_audio
from src.detection.vad import detect_voice_activity

logger = logging.getLogger(__name__)

def analyze_energy_by_track(
    audio_paths: List[str],
    window_size: float = 0.1,
    hop_length: float = 0.05,
    progress: Optional[Progress] = None
) -> Dict[str, np.ndarray]:
    """
    Analiza la energía de cada pista de audio a lo largo del tiempo.
    
    Args:
        audio_paths: Lista de rutas a los archivos de audio
        window_size: Tamaño de la ventana de análisis (segundos)
        hop_length: Salto entre ventanas (segundos)
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con los perfiles de energía de cada pista
    """
    energy_profiles = {}
    
    if progress:
        task = progress.add_task("[cyan]Analizando energía por pista", total=len(audio_paths))
    
    for i, audio_path in enumerate(audio_paths):
        if progress:
            progress.update(task, advance=1, description=f"[cyan]Analizando {os.path.basename(audio_path)}")
        
        try:
            # Cargar audio
            y, sr = load_audio(audio_path, mono=True)
            
            # Convertir parámetros de tiempo a muestras
            window_samples = int(window_size * sr)
            hop_samples = int(hop_length * sr)
            
            # Calcular energía RMS en ventanas
            rms = librosa.feature.rms(y=y, frame_length=window_samples, hop_length=hop_samples)[0]
            
            # Almacenar información
            energy_profiles[audio_path] = {
                "rms": rms,
                "times": np.arange(len(rms)) * hop_length,
                "sample_rate": sr,
                "window_size": window_size,
                "hop_length": hop_length
            }
            
            logger.info(f"Energía analizada para {audio_path}: {len(rms)} frames")
            
        except Exception as e:
            logger.error(f"Error analizando energía para {audio_path}: {str(e)}")
            if progress:
                progress.update(task, description=f"[red]Error en {os.path.basename(audio_path)}")
    
    if progress:
        progress.update(task, description=f"[green]Análisis de energía completado")
    
    return energy_profiles

def refine_whisper_segments(
    whisper_segments: List[Dict[str, Any]],
    energy_profiles: Dict[str, Dict[str, Any]],
    speaker_to_audio_map: Dict[str, str],
    energy_threshold_ratio: float = 1.5,
    progress: Optional[Progress] = None
) -> List[Dict[str, Any]]:
    """
    Refina los segmentos de Whisper usando los perfiles de energía para resolver ambigüedades.
    
    Args:
        whisper_segments: Segmentos de voz detectados por Whisper
        energy_profiles: Perfiles de energía de cada pista de audio
        speaker_to_audio_map: Mapeo entre IDs de speaker y rutas de audio
        energy_threshold_ratio: Ratio mínimo de energía entre pistas para confirmar speaker
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Lista de segmentos con speaker refinado
    """
    refined_segments = []
    
    if progress:
        task = progress.add_task("[cyan]Refinando detección de speakers", total=len(whisper_segments))
    
    for segment in whisper_segments:
        if progress:
            progress.update(task, advance=1)
        
        start_time = segment["start"]
        end_time = segment["end"]
        speaker_id = segment.get("speaker", None)
        
        # Si no hay speaker asignado, intentar asignarlo por energía
        if not speaker_id or speaker_id == "unknown":
            # Encontrar qué pista tiene más energía en este segmento
            max_energy = -1
            max_energy_speaker = None
            
            for speaker, audio_path in speaker_to_audio_map.items():
                if audio_path in energy_profiles:
                    profile = energy_profiles[audio_path]
                    times = profile["times"]
                    rms = profile["rms"]
                    
                    # Encontrar índices que corresponden al segmento actual
                    start_idx = np.argmin(np.abs(times - start_time))
                    end_idx = np.argmin(np.abs(times - end_time))
                    
                    # Calcular energía media en el segmento
                    if start_idx <= end_idx and end_idx < len(rms):
                        segment_energy = np.mean(rms[start_idx:end_idx+1])
                        
                        if segment_energy > max_energy:
                            max_energy = segment_energy
                            max_energy_speaker = speaker
            
            if max_energy_speaker:
                speaker_id = max_energy_speaker
                logger.info(f"Speaker asignado por energía: {speaker_id} para segmento {start_time:.2f}-{end_time:.2f}")
        
        # Si hay un speaker asignado por Whisper, verificar con energía
        elif speaker_id in speaker_to_audio_map:
            speaker_audio = speaker_to_audio_map[speaker_id]
            
            # Comparar energía entre pistas para confirmar o corregir
            energies = {}
            
            for spk, audio_path in speaker_to_audio_map.items():
                if audio_path in energy_profiles:
                    profile = energy_profiles[audio_path]
                    times = profile["times"]
                    rms = profile["rms"]
                    
                    # Encontrar índices para el segmento
                    start_idx = np.argmin(np.abs(times - start_time))
                    end_idx = np.argmin(np.abs(times - end_time))
                    
                    if start_idx <= end_idx and end_idx < len(rms):
                        energies[spk] = np.mean(rms[start_idx:end_idx+1])
            
            # Si hay al menos dos speakers para comparar
            if len(energies) >= 2:
                # Ordenar speakers por energía
                sorted_speakers = sorted(energies.keys(), key=lambda x: energies[x], reverse=True)
                
                # Si el speaker con más energía no es el asignado por Whisper
                # y la diferencia es significativa
                if sorted_speakers[0] != speaker_id and energies[sorted_speakers[0]] > energies[speaker_id] * energy_threshold_ratio:
                    logger.info(f"Corrigiendo speaker de {speaker_id} a {sorted_speakers[0]} por energía "+
                               f"({energies[sorted_speakers[0]]:.4f} vs {energies[speaker_id]:.4f})")
                    speaker_id = sorted_speakers[0]
        
        # Crear segmento refinado
        refined_segment = segment.copy()
        refined_segment["speaker"] = speaker_id
        refined_segments.append(refined_segment)
    
    if progress:
        progress.update(task, description=f"[green]Refinamiento completado: {len(refined_segments)} segmentos")
    
    return refined_segments

def filter_rapid_changes(
    segments: List[Dict[str, Any]],
    min_duration: float = 1.0,
    progress: Optional[Progress] = None
) -> List[Dict[str, Any]]:
    """
    Filtra cambios rápidos de speaker para evitar cortes demasiado cortos.
    
    Args:
        segments: Lista de segmentos con speakers asignados
        min_duration: Duración mínima que debe tener un segmento (segundos)
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Lista de segmentos filtrados
    """
    if not segments:
        return []
    
    # Ordenar segmentos por tiempo de inicio
    sorted_segments = sorted(segments, key=lambda x: x["start"])
    
    if progress:
        task = progress.add_task("[cyan]Filtrando cambios rápidos", total=100)
        progress.update(task, advance=20)
    
    # Agrupar segmentos consecutivos del mismo speaker
    grouped_segments = []
    current_group = [sorted_segments[0]]
    
    for segment in sorted_segments[1:]:
        last_segment = current_group[-1]
        
        # Si es el mismo speaker y no hay un gap grande, agrupar
        if segment["speaker"] == last_segment["speaker"] and segment["start"] - last_segment["end"] < 0.5:
            current_group.append(segment)
        else:
            # Finalizar grupo actual y empezar uno nuevo
            grouped_segments.append(current_group)
            current_group = [segment]
    
    # Añadir el último grupo
    grouped_segments.append(current_group)
    
    if progress:
        progress.update(task, advance=30, description=f"[cyan]Procesando {len(grouped_segments)} grupos")
    
    # Procesar grupos para eliminar cambios muy cortos
    filtered_groups = []
    current_filtered = [grouped_segments[0]]
    
    for i in range(1, len(grouped_segments)):
        current_group = grouped_segments[i]
        prev_group = current_filtered[-1]
        
        # Calcular duración del grupo actual
        current_duration = current_group[-1]["end"] - current_group[0]["start"]
        
        # Si es un grupo corto entre dos grupos del mismo speaker, fusionar
        if (i < len(grouped_segments) - 1 and 
            current_duration < min_duration and 
            current_group[0]["speaker"] != prev_group[0]["speaker"] and
            current_group[0]["speaker"] != grouped_segments[i+1][0]["speaker"] and
            prev_group[0]["speaker"] == grouped_segments[i+1][0]["speaker"]):
            
            # Asignar el speaker de los grupos circundantes
            for segment in current_group:
                segment["speaker"] = prev_group[0]["speaker"]
                segment["speaker_source"] = "filtered_short_change"
            
            # Fusionar con el grupo anterior
            current_filtered[-1].extend(current_group)
            logger.info(f"Eliminado cambio corto ({current_duration:.2f}s) en {current_group[0]['start']:.2f}s")
        
        # Si es un grupo muy corto, asignar al speaker más cercano con más duración
        elif current_duration < min_duration:
            prev_duration = prev_group[-1]["end"] - prev_group[0]["start"]
            
            # Decidir si asignar al speaker anterior o mantener
            if i < len(grouped_segments) - 1:
                next_group = grouped_segments[i+1]
                next_duration = next_group[-1]["end"] - next_group[0]["start"]
                
                if prev_duration > next_duration and prev_duration > min_duration:
                    # Asignar al speaker anterior
                    for segment in current_group:
                        segment["speaker"] = prev_group[0]["speaker"]
                        segment["speaker_source"] = "assigned_to_longer_prev"
                    current_filtered[-1].extend(current_group)
                    logger.info(f"Segmento corto ({current_duration:.2f}s) asignado a speaker anterior")
                elif next_duration > min_duration:
                    # Asignar al speaker siguiente
                    for segment in current_group:
                        segment["speaker"] = next_group[0]["speaker"]
                        segment["speaker_source"] = "assigned_to_longer_next"
                    current_filtered.append(current_group)
                    logger.info(f"Segmento corto ({current_duration:.2f}s) asignado a speaker siguiente")
                else:
                    # Mantener como está
                    current_filtered.append(current_group)
            else:
                # Es el último grupo, asignar al anterior si es más largo
                if prev_duration > min_duration:
                    for segment in current_group:
                        segment["speaker"] = prev_group[0]["speaker"]
                        segment["speaker_source"] = "assigned_to_longer_prev"
                    current_filtered[-1].extend(current_group)
                    logger.info(f"Último segmento corto ({current_duration:.2f}s) asignado a speaker anterior")
                else:
                    current_filtered.append(current_group)
        else:
            # Grupo lo suficientemente largo, mantener como está
            current_filtered.append(current_group)
    
    if progress:
        progress.update(task, advance=30, description=f"[cyan]Reconstruyendo timeline")
    
    # Reconstruir la lista de segmentos
    filtered_segments = []
    for group in current_filtered:
        for segment in group:
            filtered_segments.append(segment)
    
    # Ordenar de nuevo por tiempo
    filtered_segments = sorted(filtered_segments, key=lambda x: x["start"])
    
    if progress:
        progress.update(task, completed=100, description=f"[green]Filtrado completado: {len(filtered_segments)} segmentos")
    
    return filtered_segments

def handle_speaker_overlap(
    segments: List[Dict[str, Any]],
    energy_profiles: Dict[str, Dict[str, Any]],
    speaker_to_audio_map: Dict[str, str],
    overlap_threshold: float = 0.5,
    energy_ratio_threshold: float = 2.0,
    progress: Optional[Progress] = None
) -> List[Dict[str, Any]]:
    """
    Maneja casos donde múltiples speakers hablan simultáneamente.
    
    Args:
        segments: Lista de segmentos con speakers asignados
        energy_profiles: Perfiles de energía de cada pista
        speaker_to_audio_map: Mapeo entre IDs de speaker y rutas de audio
        overlap_threshold: Umbral de solapamiento para considerar overlap (0-1)
        energy_ratio_threshold: Ratio de energía para decidir el speaker dominante
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Lista de segmentos con overlap resuelto
    """
    if not segments:
        return []
    
    # Ordenar segmentos por tiempo de inicio
    sorted_segments = sorted(segments, key=lambda x: x["start"])
    
    if progress:
        task = progress.add_task("[cyan]Analizando solapamientos", total=len(sorted_segments))
    
    # Buscar segmentos que se solapan
    resolved_segments = []
    i = 0
    
    while i < len(sorted_segments):
        current = sorted_segments[i]
        
        # Buscar solapamientos con segmentos posteriores
        overlaps = []
        j = i + 1
        
        while j < len(sorted_segments) and sorted_segments[j]["start"] < current["end"]:
            overlap_segment = sorted_segments[j]
            
            # Calcular grado de solapamiento
            overlap_start = max(current["start"], overlap_segment["start"])
            overlap_end = min(current["end"], overlap_segment["end"])
            overlap_duration = overlap_end - overlap_start
            
            # Si el solapamiento es significativo
            if overlap_duration > 0:
                segment_duration = min(current["end"] - current["start"], 
                                     overlap_segment["end"] - overlap_segment["start"])
                overlap_ratio = overlap_duration / segment_duration
                
                if overlap_ratio >= overlap_threshold:
                    overlaps.append((j, overlap_ratio, overlap_start, overlap_end))
            
            j += 1
        
        # Si hay solapamientos, resolverlos
        if overlaps:
            # Caso de solapamiento: decidir qué speaker mantener basado en energía
            for j, ratio, overlap_start, overlap_end in overlaps:
                overlap_segment = sorted_segments[j]
                
                # Si son diferentes speakers, decidir cuál es dominante
                if current["speaker"] != overlap_segment["speaker"]:
                    speaker1 = current["speaker"]
                    speaker2 = overlap_segment["speaker"]
                    
                    # Obtener energía en la región de overlap
                    energy1 = get_segment_energy(
                        speaker_to_audio_map.get(speaker1, ""), 
                        energy_profiles, 
                        overlap_start, 
                        overlap_end
                    )
                    
                    energy2 = get_segment_energy(
                        speaker_to_audio_map.get(speaker2, ""), 
                        energy_profiles, 
                        overlap_start, 
                        overlap_end
                    )
                    
                    # Decidir speaker dominante
                    if energy1 > energy2 * energy_ratio_threshold:
                        # Speaker 1 domina
                        logger.info(f"Overlap: {speaker1} domina sobre {speaker2} " +
                                  f"({overlap_start:.2f}-{overlap_end:.2f}s)")
                        
                        # Acortar el segmento solapado
                        if overlap_end < overlap_segment["end"]:
                            new_overlap = overlap_segment.copy()
                            new_overlap["start"] = overlap_end
                            sorted_segments.insert(j+1, new_overlap)
                        
                        overlap_segment["end"] = overlap_start
                        
                    elif energy2 > energy1 * energy_ratio_threshold:
                        # Speaker 2 domina
                        logger.info(f"Overlap: {speaker2} domina sobre {speaker1} " +
                                  f"({overlap_start:.2f}-{overlap_end:.2f}s)")
                        
                        # Acortar el segmento actual
                        if overlap_end < current["end"]:
                            new_current = current.copy()
                            new_current["start"] = overlap_end
                            sorted_segments.insert(i+1, new_current)
                        
                        current["end"] = overlap_start
                    else:
                        # No hay dominancia clara, crear un segmento de overlap
                        overlap_info = current.copy()
                        overlap_info["start"] = overlap_start
                        overlap_info["end"] = overlap_end
                        overlap_info["speaker"] = f"{speaker1}+{speaker2}"
                        overlap_info["overlap"] = True
                        
                        # Ajustar segmentos originales
                        if overlap_start > current["start"]:
                            new_current = current.copy()
                            new_current["end"] = overlap_start
                            resolved_segments.append(new_current)
                        
                        if overlap_end < current["end"]:
                            new_current2 = current.copy()
                            new_current2["start"] = overlap_end
                            sorted_segments.insert(i+1, new_current2)
                        
                        if overlap_start > overlap_segment["start"]:
                            new_overlap = overlap_segment.copy()
                            new_overlap["end"] = overlap_start
                            sorted_segments.insert(j, new_overlap)
                            j += 1  # Incrementar j porque insertamos un elemento
                        
                        if overlap_end < overlap_segment["end"]:
                            new_overlap2 = overlap_segment.copy()
                            new_overlap2["start"] = overlap_end
                            sorted_segments.insert(j+1, new_overlap2)
                        
                        # Eliminar o ajustar segmentos originales
                        overlap_segment["processed"] = True
                        current["processed"] = True
                        
                        # Añadir segmento de overlap
                        resolved_segments.append(overlap_info)
                        logger.info(f"Creado segmento de overlap: {speaker1}+{speaker2} " +
                                  f"({overlap_start:.2f}-{overlap_end:.2f}s)")
        
        # Si el segmento actual no ha sido procesado, añadirlo a los resueltos
        if not current.get("processed", False):
            resolved_segments.append(current)
        
        if progress:
            progress.update(task, advance=1)
        
        i += 1
    
    # Filtrar segmentos ya procesados y ordenar por tiempo
    final_segments = [s for s in resolved_segments if s["end"] > s["start"]]
    final_segments = sorted(final_segments, key=lambda x: x["start"])
    
    if progress:
        progress.update(task, description=f"[green]Overlap resuelto: {len(final_segments)} segmentos")
    
    return final_segments

def get_segment_energy(
    audio_path: str,
    energy_profiles: Dict[str, Dict[str, Any]],
    start_time: float,
    end_time: float
) -> float:
    """
    Obtiene la energía media para un segmento específico de audio.
    
    Args:
        audio_path: Ruta al archivo de audio
        energy_profiles: Perfiles de energía
        start_time: Tiempo de inicio del segmento (segundos)
        end_time: Tiempo de fin del segmento (segundos)
        
    Returns:
        Energía media del segmento
    """
    if not audio_path or audio_path not in energy_profiles:
        return 0.0
    
    profile = energy_profiles[audio_path]
    times = profile["times"]
    rms = profile["rms"]
    
    # Encontrar índices que corresponden al segmento
    start_idx = np.argmin(np.abs(times - start_time))
    end_idx = np.argmin(np.abs(times - end_time))
    
    # Asegurar que los índices son válidos
    if start_idx <= end_idx and end_idx < len(rms):
        return float(np.mean(rms[start_idx:end_idx+1]))
    
    return 0.0

def generate_camera_changes(
    segments: List[Dict[str, Any]],
    smoothness: str = "normal",
    min_shot_duration: float = 2.0,
    progress: Optional[Progress] = None
) -> List[Dict[str, Any]]:
    """
    Genera timeline de cambios de cámara basado en los segmentos de speaker.
    
    Args:
        segments: Lista de segmentos con speakers asignados
        smoothness: Nivel de suavidad de cambios ('instant', 'normal', 'smooth')
        min_shot_duration: Duración mínima de cada plano (segundos)
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Lista de cambios de cámara con tiempos y transiciones
    """
    if not segments:
        return []
    
    # Mapear nivel de suavidad a duración de transición
    transition_durations = {
        "instant": 0.0,
        "normal": 0.5,
        "smooth": 1.0,
        "very_smooth": 1.5
    }
    transition_duration = transition_durations.get(smoothness, 0.5)
    
    if progress:
        task = progress.add_task("[cyan]Generando cambios de cámara", total=100)
        progress.update(task, advance=10)
    
    # Procesar segmentos para generar cambios de cámara
    camera_changes = []
    current_speaker = segments[0]["speaker"]
    current_start = segments[0]["start"]
    
    # Iniciar con el primer cambio
    camera_changes.append({
        "time": max(0, current_start - 0.2),  # Iniciar un poco antes
        "camera": current_speaker.split("+")[0] if "+" in current_speaker else current_speaker,
        "transition": "cut",
        "duration": 0.0
    })
    
    for i in range(1, len(segments)):
        segment = segments[i]
        prev_segment = segments[i-1]
        
        # Si cambia el speaker principal
        speaker = segment["speaker"]
        main_speaker = speaker.split("+")[0] if "+" in speaker else speaker
        prev_main_speaker = prev_segment["speaker"].split("+")[0] if "+" in prev_segment["speaker"] else prev_segment["speaker"]
        
        if main_speaker != prev_main_speaker:
            # Calcular duración del plano actual
            shot_duration = segment["start"] - current_start
            
            # Solo cambiar si el plano tiene duración suficiente o es el primer segmento
            if shot_duration >= min_shot_duration or i == 1:
                # Añadir cambio de cámara
                transition_type = "dissolve" if transition_duration > 0 else "cut"
                
                camera_changes.append({
                    "time": segment["start"],
                    "camera": main_speaker,
                    "transition": transition_type,
                    "duration": transition_duration
                })
                
                current_start = segment["start"]
                current_speaker = main_speaker
                
                logger.info(f"Cambio de cámara a {main_speaker} en {segment['start']:.2f}s " +
                           f"(duración del plano anterior: {shot_duration:.2f}s)")
    
    if progress:
        progress.update(task, completed=100, 
                      description=f"[green]Generados {len(camera_changes)} cambios de cámara")
    
    return camera_changes

def save_speaker_timeline(
    segments: List[Dict[str, Any]],
    camera_changes: List[Dict[str, Any]],
    output_path: str
) -> None:
    """
    Guarda el timeline de speakers y cambios de cámara en un archivo JSON.
    
    Args:
        segments: Lista de segmentos con speakers asignados
        camera_changes: Lista de cambios de cámara
        output_path: Ruta donde guardar el archivo JSON
    """
    timeline_data = {
        "segments": segments,
        "camera_changes": camera_changes,
        "metadata": {
            "total_segments": len(segments),
            "total_camera_changes": len(camera_changes),
            "version": "1.0"
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(timeline_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Timeline guardado en {output_path}") 