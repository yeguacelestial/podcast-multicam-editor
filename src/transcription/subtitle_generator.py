"""
Módulo para generar subtítulos a partir de transcripciones de Whisper.
Soporta formatos SRT y VTT para su uso en reproductores de video.
"""

import os
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from rich.progress import Progress, TaskID

logger = logging.getLogger(__name__)

def generate_subtitles(
    timeline: List[Dict[str, Any]],
    output_file: str,
    format_type: str = "srt",
    include_speaker_names: bool = True,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None
) -> str:
    """
    Genera archivo de subtítulos a partir de un timeline de segmentos.
    
    Args:
        timeline: Lista de segmentos con información de tiempo y texto
        output_file: Ruta para el archivo de subtítulos
        format_type: Formato de subtítulos ('srt' o 'vtt')
        include_speaker_names: Si se debe incluir el nombre del speaker en el subtítulo
        progress: Objeto Progress para mostrar progreso
        task_id: ID de la tarea en el objeto Progress
        
    Returns:
        Ruta al archivo de subtítulos generado
    """
    if progress and task_id:
        progress.update(task_id, advance=10, description=f"[cyan]Generando subtítulos en formato {format_type}...")
    
    try:
        # Asegurar que la extensión del archivo sea correcta
        base_name = os.path.splitext(output_file)[0]
        if format_type.lower() == "srt":
            output_file = f"{base_name}.srt"
            subtitle_content = generate_srt(timeline, include_speaker_names)
        elif format_type.lower() == "vtt":
            output_file = f"{base_name}.vtt"
            subtitle_content = generate_vtt(timeline, include_speaker_names)
        else:
            raise ValueError(f"Formato de subtítulos no soportado: {format_type}")
        
        if progress and task_id:
            progress.update(task_id, advance=40, description=f"[cyan]Guardando archivo de subtítulos...")
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        # Guardar archivo
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(subtitle_content)
        
        if progress and task_id:
            progress.update(task_id, completed=100, description=f"[green]Subtítulos generados: {os.path.basename(output_file)}")
        
        return output_file
        
    except Exception as e:
        logger.error(f"Error al generar subtítulos: {str(e)}")
        if progress and task_id:
            progress.update(task_id, completed=100, description=f"[red]Error al generar subtítulos")
        raise

def generate_srt(timeline: List[Dict[str, Any]], include_speaker_names: bool = True) -> str:
    """
    Genera subtítulos en formato SRT.
    
    Args:
        timeline: Lista de segmentos con información de tiempo y texto
        include_speaker_names: Si se debe incluir el nombre del speaker en el subtítulo
        
    Returns:
        Contenido del archivo SRT
    """
    srt_content = ""
    
    for i, segment in enumerate(timeline, 1):
        # Convertir tiempos a formato SRT (HH:MM:SS,mmm)
        start_time = format_srt_time(segment["start"])
        end_time = format_srt_time(segment["end"])
        
        # Formatear texto con nombre del speaker si es necesario
        text = segment["text"].strip()
        if include_speaker_names and "speaker" in segment and segment["speaker"]:
            text = f"[{segment['speaker']}] {text}"
        
        # Añadir subtítulo
        srt_content += f"{i}\n{start_time} --> {end_time}\n{text}\n\n"
    
    return srt_content

def generate_vtt(timeline: List[Dict[str, Any]], include_speaker_names: bool = True) -> str:
    """
    Genera subtítulos en formato WebVTT.
    
    Args:
        timeline: Lista de segmentos con información de tiempo y texto
        include_speaker_names: Si se debe incluir el nombre del speaker en el subtítulo
        
    Returns:
        Contenido del archivo VTT
    """
    vtt_content = "WEBVTT\n\n"
    
    for i, segment in enumerate(timeline, 1):
        # Convertir tiempos a formato VTT (HH:MM:SS.mmm)
        start_time = format_vtt_time(segment["start"])
        end_time = format_vtt_time(segment["end"])
        
        # Formatear texto con nombre del speaker si es necesario
        text = segment["text"].strip()
        if include_speaker_names and "speaker" in segment and segment["speaker"]:
            text = f"<v {segment['speaker']}>{text}</v>"
        
        # Añadir subtítulo
        vtt_content += f"{start_time} --> {end_time}\n{text}\n\n"
    
    return vtt_content

def format_srt_time(seconds: float) -> str:
    """
    Formatea segundos a formato de tiempo SRT (HH:MM:SS,mmm).
    
    Args:
        seconds: Tiempo en segundos
        
    Returns:
        String con formato de tiempo SRT
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_vtt_time(seconds: float) -> str:
    """
    Formatea segundos a formato de tiempo VTT (HH:MM:SS.mmm).
    
    Args:
        seconds: Tiempo en segundos
        
    Returns:
        String con formato de tiempo VTT
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def generate_transcript_file(
    timeline: List[Dict[str, Any]],
    output_file: str,
    include_timestamps: bool = True,
    include_speaker_names: bool = True,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None
) -> str:
    """
    Genera un archivo de transcripción en texto plano.
    
    Args:
        timeline: Lista de segmentos con información de tiempo y texto
        output_file: Ruta para el archivo de transcripción
        include_timestamps: Si se deben incluir marcas de tiempo
        include_speaker_names: Si se debe incluir el nombre del speaker
        progress: Objeto Progress para mostrar progreso
        task_id: ID de la tarea en el objeto Progress
        
    Returns:
        Ruta al archivo de transcripción generado
    """
    if progress and task_id:
        progress.update(task_id, advance=10, description=f"[cyan]Generando transcripción en texto plano...")
    
    try:
        # Asegurar que la extensión del archivo sea correcta
        base_name = os.path.splitext(output_file)[0]
        output_file = f"{base_name}.txt"
        
        # Generar contenido
        transcript_content = ""
        
        for segment in timeline:
            line = ""
            
            # Añadir timestamp si es necesario
            if include_timestamps:
                timestamp = format_readable_time(segment["start"])
                line += f"[{timestamp}] "
            
            # Añadir nombre del speaker si es necesario
            if include_speaker_names and "speaker" in segment and segment["speaker"]:
                line += f"{segment['speaker']}: "
            
            # Añadir texto
            line += f"{segment['text'].strip()}\n"
            
            transcript_content += line
        
        if progress and task_id:
            progress.update(task_id, advance=40, description=f"[cyan]Guardando archivo de transcripción...")
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        # Guardar archivo
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(transcript_content)
        
        if progress and task_id:
            progress.update(task_id, completed=100, description=f"[green]Transcripción generada: {os.path.basename(output_file)}")
        
        return output_file
        
    except Exception as e:
        logger.error(f"Error al generar transcripción: {str(e)}")
        if progress and task_id:
            progress.update(task_id, completed=100, description=f"[red]Error al generar transcripción")
        raise

def format_readable_time(seconds: float) -> str:
    """
    Formatea segundos a un formato de tiempo legible (HH:MM:SS).
    
    Args:
        seconds: Tiempo en segundos
        
    Returns:
        String con formato de tiempo legible
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}" 