"""
Módulo para análisis de archivos de audio, validación y carga.
Incluye funciones para verificar si un archivo es mono y analizar sus características.
"""

import os
import logging
import numpy as np
from typing import Tuple, Dict, Optional, Any
import librosa
import soundfile as sf
from rich.progress import Progress

logger = logging.getLogger(__name__)

def validate_audio_file(audio_path: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Valida un archivo de audio y extrae sus características básicas.
    
    Args:
        audio_path: Ruta al archivo de audio a validar
        
    Returns:
        Tuple con (es_válido, info_audio)
        
    Raises:
        FileNotFoundError: Si el archivo no existe
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"El archivo de audio no existe: {audio_path}")
    
    try:
        # Cargar el archivo con librosa para obtener información
        y, sr = librosa.load(audio_path, sr=None, mono=False)
        
        # Determinar si es mono o estéreo
        is_mono = True if y.ndim == 1 else False
        channels = 1 if is_mono else y.shape[0]
        
        # Duración en segundos
        duration = librosa.get_duration(y=y, sr=sr)
        
        # Información básica del archivo
        audio_info = {
            "path": audio_path,
            "sample_rate": sr,
            "channels": channels,
            "is_mono": is_mono,
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "valid": True
        }
        
        logger.info(f"Archivo validado: {audio_path} - {audio_info['duration_formatted']} - {'Mono' if is_mono else 'Estéreo'}")
        return True, audio_info
        
    except Exception as e:
        logger.error(f"Error al validar archivo de audio {audio_path}: {str(e)}")
        return False, {"path": audio_path, "valid": False, "error": str(e)}

def load_audio(audio_path: str, mono: bool = True, normalize: bool = True) -> Tuple[np.ndarray, int]:
    """
    Carga un archivo de audio con librosa.
    
    Args:
        audio_path: Ruta al archivo de audio
        mono: Si True, convierte el audio a mono
        normalize: Si True, normaliza el audio entre -1 y 1
        
    Returns:
        Tuple (datos_audio, sample_rate)
        
    Raises:
        FileNotFoundError: Si el archivo no existe
    """
    logger.info(f"Cargando audio: {audio_path}")
    
    try:
        # Cargar audio con librosa
        y, sr = librosa.load(audio_path, sr=None, mono=mono)
        
        # Normalizar si es necesario
        if normalize and y.size > 0:
            y = y / np.max(np.abs(y))
            
        return y, sr
    
    except Exception as e:
        logger.error(f"Error al cargar audio {audio_path}: {str(e)}")
        raise

def convert_to_mono(audio_path: str, output_path: Optional[str] = None) -> str:
    """
    Convierte un archivo de audio estéreo a mono.
    
    Args:
        audio_path: Ruta al archivo de audio estéreo
        output_path: Ruta para el archivo mono de salida (opcional)
        
    Returns:
        Ruta al archivo mono resultante
    """
    # Validar archivo
    valid, info = validate_audio_file(audio_path)
    
    if not valid:
        raise ValueError(f"Archivo de audio no válido: {audio_path}")
    
    # Si ya es mono, devolver la ruta original
    if info["is_mono"]:
        logger.info(f"El archivo ya es mono, no se requiere conversión: {audio_path}")
        return audio_path
    
    # Crear ruta de salida si no se proporciona
    if output_path is None:
        base_name = os.path.splitext(audio_path)[0]
        output_path = f"{base_name}_mono.wav"
    
    try:
        # Cargar audio y convertir a mono
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        
        # Guardar como mono
        sf.write(output_path, y, sr, subtype='PCM_16')
        
        logger.info(f"Archivo convertido a mono: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error al convertir a mono {audio_path}: {str(e)}")
        raise

def analyze_audio_file(audio_path: str, progress: Optional[Progress] = None) -> Dict[str, Any]:
    """
    Analiza un archivo de audio para extraer características útiles.
    
    Args:
        audio_path: Ruta al archivo de audio
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con características del audio
    """
    if progress:
        task = progress.add_task(f"[cyan]Analizando audio: {os.path.basename(audio_path)}", total=100)
        progress.update(task, advance=10)
    
    # Validar y obtener información básica
    valid, info = validate_audio_file(audio_path)
    
    if not valid:
        if progress:
            progress.update(task, completed=100, description=f"[red]Error: {os.path.basename(audio_path)}")
        return info
    
    if progress:
        progress.update(task, advance=20, description=f"[cyan]Cargando audio: {os.path.basename(audio_path)}")
    
    # Cargar audio
    y, sr = load_audio(audio_path, mono=True)
    
    if progress:
        progress.update(task, advance=20, description=f"[cyan]Calculando características: {os.path.basename(audio_path)}")
    
    try:
        # Calcular características adicionales
        # RMS (volumen)
        rms = librosa.feature.rms(y=y)[0]
        
        # Energía promedio
        energy = np.mean(y**2)
        
        # Silencio (porcentaje de muestras por debajo de un umbral)
        silence_threshold = 0.01
        silence_percentage = np.mean(np.abs(y) < silence_threshold) * 100
        
        # Añadir características al diccionario
        info.update({
            "rms_mean": float(np.mean(rms)),
            "rms_std": float(np.std(rms)),
            "energy": float(energy),
            "silence_percentage": float(silence_percentage)
        })
        
        if progress:
            progress.update(task, completed=100, description=f"[green]Completado: {os.path.basename(audio_path)}")
        
        return info
        
    except Exception as e:
        logger.error(f"Error al analizar audio {audio_path}: {str(e)}")
        if progress:
            progress.update(task, completed=100, description=f"[red]Error: {os.path.basename(audio_path)}")
        
        info.update({"error": str(e)})
        return info

def format_duration(seconds: float) -> str:
    """
    Formatea una duración en segundos a formato HH:MM:SS.
    
    Args:
        seconds: Duración en segundos
        
    Returns:
        String formateado
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
    else:
        return f"{minutes:02d}:{secs:02d}.{ms:03d}" 