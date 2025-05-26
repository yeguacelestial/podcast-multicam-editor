"""
Módulo para procesamiento de video usando ffmpeg
"""
import os
import subprocess
import json
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path
import tempfile
from rich.progress import Progress, TaskID
from rich.console import Console

console = Console()

def cut_video_for_preview(
    video_path: str, 
    output_path: str, 
    duration_minutes: int = 5,
    log_progress: bool = True
) -> str:
    """
    Corta un video a la duración especificada para modo preview
    
    Args:
        video_path: Ruta al video original
        output_path: Ruta donde guardar el video cortado
        duration_minutes: Duración en minutos del preview
        log_progress: Si mostrar logs del progreso
        
    Returns:
        Ruta al video cortado
    """
    duration_seconds = duration_minutes * 60
    
    if log_progress:
        console.log(f"Cortando video para preview: {video_path} -> {duration_minutes} minutos")
    
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-t", str(duration_seconds),
        "-c:v", "copy",
        "-c:a", "copy",
        "-y",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if log_progress:
            console.log(f"Video cortado exitosamente: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        console.log(f"[bold red]Error al cortar video: {e}[/]")
        raise RuntimeError(f"Error al cortar video: {e}")

def normalize_audio(
    audio_path: str,
    output_path: str,
    target_level: float = -23.0,
    log_progress: bool = True
) -> str:
    """
    Normaliza un archivo de audio a un nivel específico
    
    Args:
        audio_path: Ruta al audio original
        output_path: Ruta donde guardar el audio normalizado
        target_level: Nivel objetivo en LUFS
        log_progress: Si mostrar logs del progreso
        
    Returns:
        Ruta al audio normalizado
    """
    # Verificar que el archivo de entrada existe
    if not os.path.exists(audio_path):
        raise ValueError(f"El archivo de audio no existe: {audio_path}")
    
    if os.path.getsize(audio_path) == 0:
        raise ValueError(f"El archivo de audio está vacío: {audio_path}")
    
    # Crear el directorio de salida si no existe
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        if log_progress:
            console.log(f"Creado directorio de salida: {output_dir}")
    
    if log_progress:
        console.log(f"Normalizando audio: {audio_path}")
    
    # Primero medir el nivel actual
    measure_cmd = [
        "ffmpeg",
        "-i", audio_path,
        "-af", "loudnorm=print_format=json",
        "-f", "null",
        "-"
    ]
    
    try:
        if log_progress:
            console.log(f"Midiendo niveles de audio...")
        result = subprocess.run(measure_cmd, check=True, capture_output=True, text=True)
        
        # Extraer el JSON de la salida
        json_data = result.stderr
        start_idx = json_data.find('{')
        end_idx = json_data.rfind('}') + 1
        if start_idx >= 0 and end_idx > 0:
            json_data = json_data[start_idx:end_idx]
            loudness_info = json.loads(json_data)
            
            if log_progress:
                input_i = loudness_info.get('input_i', 'N/A')
                console.log(f"Nivel actual: {input_i} LUFS, normalizando a {target_level} LUFS")
            
            # Aplicar la normalización
            normalize_cmd = [
                "ffmpeg",
                "-i", audio_path,
                "-af", f"loudnorm=I={target_level}:TP=-1.0:LRA=11.0:"
                       f"measured_I={loudness_info.get('input_i', '-23.0')}:"
                       f"measured_TP={loudness_info.get('input_tp', '0.0')}:"
                       f"measured_LRA={loudness_info.get('input_lra', '0.0')}:"
                       f"measured_thresh={loudness_info.get('input_thresh', '-70.0')}:"
                       f"offset={loudness_info.get('target_offset', '0.0')}",
                "-ar", "48000",
                "-y",
                output_path
            ]
            
            if log_progress:
                console.log(f"Aplicando normalización...")
            
            try:
                subprocess.run(normalize_cmd, check=True, capture_output=True, text=True)
                
                # Verificar que el archivo de salida existe y no está vacío
                if not os.path.exists(output_path):
                    raise ValueError(f"El archivo de salida no se generó: {output_path}")
                
                file_size = os.path.getsize(output_path)
                if file_size == 0:
                    raise ValueError(f"El archivo de salida está vacío: {output_path}")
                
                if log_progress:
                    console.log(f"Audio normalizado exitosamente: {output_path} ({file_size/1024/1024:.2f} MB)")
                return output_path
            except subprocess.CalledProcessError as e:
                console.log(f"[bold red]Error al aplicar normalización: {e}[/]")
                
                # Mostrar la salida de error de ffmpeg
                if e.stderr:
                    console.log(f"[red]FFmpeg error: {e.stderr}[/]")
                
                # Proporcionar información adicional
                console.log(f"[yellow]Comando ejecutado: {' '.join(normalize_cmd)}[/]")
                
                raise RuntimeError(f"Error al normalizar audio: {e}")
        else:
            raise ValueError("No se pudo extraer información de loudness del audio")
    except subprocess.CalledProcessError as e:
        console.log(f"[bold red]Error al medir niveles de audio: {e}[/]")
        
        # Mostrar la salida de error de ffmpeg
        if e.stderr:
            console.log(f"[red]FFmpeg error: {e.stderr}[/]")
        
        # Proporcionar información adicional
        console.log(f"[yellow]Comando ejecutado: {' '.join(measure_cmd)}[/]")
        
        raise RuntimeError(f"Error al normalizar audio: {e}")
    except Exception as e:
        console.log(f"[bold red]Error inesperado al normalizar audio: {e}[/]")
        raise

def mix_audio_tracks(
    audio_paths: List[str],
    output_path: str,
    volumes: List[float] = None,
    normalize_output: bool = True,
    log_progress: bool = True
) -> str:
    """
    Mezcla múltiples pistas de audio con volúmenes configurables
    
    Args:
        audio_paths: Lista de rutas a los archivos de audio
        output_path: Ruta donde guardar la mezcla
        volumes: Lista de volúmenes relativos para cada pista (1.0 = sin cambio)
        normalize_output: Si normalizar el audio resultante
        log_progress: Si mostrar logs del progreso
        
    Returns:
        Ruta al audio mezclado
    """
    if not audio_paths:
        raise ValueError("No se proporcionaron archivos de audio para mezclar")
    
    if volumes is None:
        volumes = [1.0] * len(audio_paths)
    
    if len(audio_paths) != len(volumes):
        raise ValueError("La cantidad de volúmenes debe coincidir con la cantidad de archivos de audio")
    
    # Verificar que todos los archivos de audio existan
    for i, audio_path in enumerate(audio_paths):
        if not os.path.exists(audio_path):
            raise ValueError(f"El archivo de audio {i+1} no existe: {audio_path}")
        
        if os.path.getsize(audio_path) == 0:
            raise ValueError(f"El archivo de audio {i+1} está vacío: {audio_path}")
    
    if log_progress:
        console.log(f"Mezclando {len(audio_paths)} pistas de audio")
        for i, (audio, vol) in enumerate(zip(audio_paths, volumes)):
            console.log(f"  - Audio {i+1}: {os.path.basename(audio)} (volumen: {vol})")
    
    # Crear el directorio de salida si no existe
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        if log_progress:
            console.log(f"Creado directorio de salida: {output_dir}")
    
    # Crear el filtro de mezcla
    filter_complex = ""
    for i, (audio, vol) in enumerate(zip(audio_paths, volumes)):
        filter_complex += f"[{i}:a]volume={vol}[a{i}];"
    
    # Concatenar todas las pistas
    inputs = []
    for audio in audio_paths:
        inputs.extend(["-i", audio])
    
    # Añadir las referencias a las pistas
    filter_complex += "".join(f"[a{i}]" for i in range(len(audio_paths)))
    
    # Aplicar el amerge y normalización si es necesario
    filter_complex += f"amix=inputs={len(audio_paths)}:normalize=0"
    if normalize_output:
        filter_complex += f",loudnorm=I=-23:TP=-1.0:LRA=11.0"
    
    cmd = [
        "ffmpeg",
        *inputs,
        "-filter_complex", filter_complex,
        "-ar", "48000",
        "-y",
        output_path
    ]
    
    if log_progress:
        console.log(f"Ejecutando comando ffmpeg para mezcla de audio...")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Verificar que el archivo de salida existe y no está vacío
        if not os.path.exists(output_path):
            raise ValueError(f"El archivo de salida no se generó: {output_path}")
        
        file_size = os.path.getsize(output_path)
        if file_size == 0:
            raise ValueError(f"El archivo de salida está vacío: {output_path}")
        
        if log_progress:
            console.log(f"Audio mezclado exitosamente: {output_path} ({file_size/1024/1024:.2f} MB)")
        return output_path
    except subprocess.CalledProcessError as e:
        console.log(f"[bold red]Error al mezclar audio: {e}[/]")
        
        # Mostrar la salida de error de ffmpeg
        if e.stderr:
            console.log(f"[red]FFmpeg error: {e.stderr}[/]")
        
        # Proporcionar información adicional
        console.log(f"[yellow]Comando ejecutado: {' '.join(cmd)}[/]")
        
        raise RuntimeError(f"Error al mezclar audio: {e}")
    except Exception as e:
        console.log(f"[bold red]Error inesperado al mezclar audio: {e}[/]")
        raise

def extract_frame(
    video_path: str,
    output_path: str,
    timestamp: float = 0.0,
    log_progress: bool = False
) -> str:
    """
    Extrae un frame de un video en un timestamp específico
    
    Args:
        video_path: Ruta al video
        output_path: Ruta donde guardar el frame
        timestamp: Tiempo en segundos para extraer el frame
        log_progress: Si mostrar logs del progreso
        
    Returns:
        Ruta al frame extraído
    """
    cmd = [
        "ffmpeg",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        "-y",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if log_progress:
            console.log(f"Frame extraído exitosamente: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        console.log(f"[bold red]Error al extraer frame: {e}[/]")
        raise RuntimeError(f"Error al extraer frame: {e}")

def get_video_info(video_path: str) -> Dict:
    """
    Obtiene información de un archivo de video usando ffprobe
    
    Args:
        video_path: Ruta al video
        
    Returns:
        Diccionario con información del video
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        console.log(f"[bold red]Error al obtener información del video: {e}[/]")
        raise RuntimeError(f"Error al obtener información del video: {e}") 