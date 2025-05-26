"""
Módulo para transcripción de audio utilizando Whisper.
Proporciona funciones para transcribir audio, detectar speakers y segmentar por actividad vocal.
"""

import os
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import whisper
from rich.progress import Progress, TaskID
import json

logger = logging.getLogger(__name__)

# Definición de modelos disponibles de Whisper
WHISPER_MODELS = {
    "tiny": {"descripcion": "Muy rápido, precisión básica (~1GB VRAM)", "multilingual": True},
    "base": {"descripcion": "Rápido, buena precisión (~1GB VRAM)", "multilingual": True},
    "small": {"descripcion": "Equilibrado, muy buena precisión (~2GB VRAM)", "multilingual": True},
    "medium": {"descripcion": "Alta precisión, más lento (~5GB VRAM)", "multilingual": True},
    "large-v3": {"descripcion": "Máxima precisión, muy lento (~10GB VRAM)", "multilingual": True},
}

def transcribe_audio(
    audio_path: str,
    model_name: str = "medium",
    language: str = "es-MX",
    output_dir: Optional[str] = None,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None
) -> Dict[str, Any]:
    """
    Transcribe un archivo de audio utilizando Whisper.
    
    Args:
        audio_path: Ruta al archivo de audio
        model_name: Tamaño del modelo de Whisper a utilizar
        language: Código de idioma para la transcripción
        output_dir: Directorio para guardar la transcripción
        progress: Objeto Progress para mostrar progreso
        task_id: ID de la tarea en el objeto Progress
        
    Returns:
        Diccionario con la transcripción y metadatos
    """
    if progress and task_id:
        progress.update(task_id, advance=10, description=f"[cyan]Cargando modelo Whisper {model_name}...")
    
    try:
        # Validar archivo de entrada
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"El archivo de audio no existe: {audio_path}")
        
        # Cargar modelo de Whisper
        model = whisper.load_model(model_name)
        
        if progress and task_id:
            progress.update(task_id, advance=20, description=f"[cyan]Transcribiendo audio...")
        
        # Realizar transcripción
        result = model.transcribe(
            audio_path,
            language=language,
            verbose=False
        )
        
        if progress and task_id:
            progress.update(task_id, advance=50, description=f"[cyan]Procesando resultados...")
        
        # Extraer información de segmentos
        segments = []
        for segment in result["segments"]:
            segments.append({
                "id": segment["id"],
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"],
                "speaker": None  # Se llenará más adelante
            })
        
        # Crear resultado final
        transcription_result = {
            "text": result["text"],
            "segments": segments,
            "language": result["language"],
            "audio_path": audio_path
        }
        
        # Guardar transcripción en formato JSON si se proporciona output_dir
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{Path(audio_path).stem}_transcription.json")
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(transcription_result, f, ensure_ascii=False, indent=2)
            
            transcription_result["output_file"] = output_file
        
        if progress and task_id:
            progress.update(task_id, completed=100, description=f"[green]Transcripción completada")
        
        return transcription_result
        
    except Exception as e:
        logger.error(f"Error al transcribir audio {audio_path}: {str(e)}")
        if progress and task_id:
            progress.update(task_id, completed=100, description=f"[red]Error en transcripción")
        raise

def detect_speakers(
    transcription_results: List[Dict[str, Any]],
    speaker_names: List[str],
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Asigna speakers a segmentos de transcripción basado en archivos de audio específicos por speaker.
    
    Args:
        transcription_results: Lista de resultados de transcripción, uno por speaker
        speaker_names: Lista de nombres de los speakers correspondientes a cada transcripción
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con segmentos asignados a speakers
    """
    if len(transcription_results) != len(speaker_names):
        raise ValueError("Debe haber la misma cantidad de transcripciones que de nombres de speakers")
    
    if progress:
        task = progress.add_task("[cyan]Asignando speakers a segmentos...", total=100)
        progress.update(task, advance=10)
    
    try:
        # Crear timeline unificado con todos los segmentos
        all_segments = []
        for idx, result in enumerate(transcription_results):
            speaker_name = speaker_names[idx]
            
            # Añadir cada segmento con su speaker asignado
            for segment in result["segments"]:
                segment_copy = segment.copy()
                segment_copy["speaker"] = speaker_name
                segment_copy["source_audio"] = result["audio_path"]
                all_segments.append(segment_copy)
        
        # Ordenar por tiempo de inicio
        all_segments.sort(key=lambda x: x["start"])
        
        if progress:
            progress.update(task, advance=40, description="[cyan]Resolviendo solapamientos...")
        
        # Resolver solapamientos
        timeline = resolve_overlaps(all_segments)
        
        if progress:
            progress.update(task, completed=100, description="[green]Detección de speakers completada")
        
        return {
            "timeline": timeline,
            "speakers": speaker_names,
            "speaker_count": len(speaker_names)
        }
        
    except Exception as e:
        logger.error(f"Error al asignar speakers: {str(e)}")
        if progress:
            progress.update(task, completed=100, description="[red]Error en detección de speakers")
        raise

def resolve_overlaps(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Resuelve solapamientos entre segmentos de diferentes speakers.
    
    Args:
        segments: Lista de segmentos con información de speaker
        
    Returns:
        Lista de segmentos sin solapamientos
    """
    if not segments:
        return []
    
    # Si solo hay un segmento, no hay solapamientos
    if len(segments) == 1:
        return segments
    
    resolved_segments = [segments[0]]
    
    for current in segments[1:]:
        last = resolved_segments[-1]
        
        # Verificar si hay solapamiento
        if current["start"] < last["end"]:
            # Caso 1: El segmento actual está completamente dentro del anterior
            if current["end"] <= last["end"]:
                # Si el segmento actual es más corto que 1 segundo, ignorarlo
                if current["end"] - current["start"] < 1.0:
                    continue
                
                # Si no, dividir el segmento anterior
                if current["start"] - last["start"] > 1.0:
                    # Crear un segmento para la primera parte
                    first_part = last.copy()
                    first_part["end"] = current["start"]
                    first_part["text"] = first_part["text"].split(".")[0] + "." if "." in first_part["text"] else first_part["text"]
                    
                    # Reemplazar el último segmento con la primera parte
                    resolved_segments[-1] = first_part
                    
                    # Añadir el segmento actual
                    resolved_segments.append(current)
                
            # Caso 2: Solapamiento parcial
            else:
                # Si el solapamiento es pequeño (<0.5s), ajustar los tiempos
                overlap_duration = last["end"] - current["start"]
                if overlap_duration < 0.5:
                    last["end"] = current["start"]
                    resolved_segments.append(current)
                else:
                    # Si hay solapamiento significativo, decidir basado en duración
                    # Preferir el segmento más largo
                    last_duration = last["end"] - last["start"]
                    current_duration = current["end"] - current["start"]
                    
                    if current_duration > last_duration:
                        # Recortar el segmento anterior
                        last["end"] = current["start"]
                        resolved_segments.append(current)
                    else:
                        # Recortar el segmento actual
                        current["start"] = last["end"]
                        if current["end"] - current["start"] > 0.5:  # Solo añadir si queda suficiente duración
                            resolved_segments.append(current)
        else:
            # No hay solapamiento, añadir el segmento
            resolved_segments.append(current)
    
    return resolved_segments

def get_voice_segments(
    timeline: List[Dict[str, Any]],
    speaker_name: str,
    format_type: str = "seconds"
) -> List[Dict[str, Any]]:
    """
    Extrae los segmentos de voz de un speaker específico.
    
    Args:
        timeline: Lista de segmentos con información de speaker
        speaker_name: Nombre del speaker a filtrar
        format_type: Formato de salida ('seconds', 'frames', 'timecode')
        
    Returns:
        Lista de segmentos del speaker especificado
    """
    # Filtrar segmentos por speaker
    speaker_segments = [s for s in timeline if s["speaker"] == speaker_name]
    
    # Formato de salida
    fps = 30  # Frames por segundo para formato de video
    result = []
    
    for segment in speaker_segments:
        start_sec = segment["start"]
        end_sec = segment["end"]
        
        if format_type == "seconds":
            formatted_segment = {
                "start": start_sec,
                "end": end_sec,
                "duration": end_sec - start_sec,
                "text": segment["text"]
            }
        elif format_type == "frames":
            # Convertir a frames (para edición de video)
            start_frame = int(start_sec * fps)
            end_frame = int(end_sec * fps)
            formatted_segment = {
                "start_frame": start_frame,
                "end_frame": end_frame,
                "duration_frames": end_frame - start_frame,
                "text": segment["text"]
            }
        elif format_type == "timecode":
            # Convertir a timecode HH:MM:SS.ms
            start_tc = format_timecode(start_sec)
            end_tc = format_timecode(end_sec)
            formatted_segment = {
                "start_tc": start_tc,
                "end_tc": end_tc,
                "duration_seconds": end_sec - start_sec,
                "text": segment["text"]
            }
        else:
            raise ValueError(f"Formato desconocido: {format_type}")
            
        result.append(formatted_segment)
    
    return result

def format_timecode(seconds: float) -> str:
    """
    Formatea segundos a timecode HH:MM:SS.ms.
    
    Args:
        seconds: Tiempo en segundos
        
    Returns:
        String con formato de timecode
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}" 