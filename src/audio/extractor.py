"""
Módulo para extracción de audio de archivos de video usando FFmpeg.
Permite extraer pistas de audio de videos de iPhone y otros formatos.
"""

import os
import subprocess
from typing import Optional
from pathlib import Path
import logging
from rich.progress import Progress, TaskID

logger = logging.getLogger(__name__)

def extract_audio_from_video(
    video_path: str, 
    output_path: Optional[str] = None,
    mono: bool = True,
    sample_rate: int = 44100,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None
) -> str:
    """
    Extrae audio de un archivo de video usando FFmpeg.
    
    Args:
        video_path: Ruta al archivo de video
        output_path: Ruta para el archivo de audio de salida (opcional)
        mono: Si True, convierte el audio a mono
        sample_rate: Frecuencia de muestreo para el audio resultante
        progress: Objeto Progress de Rich para mostrar progreso
        task_id: ID de la tarea en el objeto Progress
        
    Returns:
        Ruta al archivo de audio extraído
    
    Raises:
        FileNotFoundError: Si el archivo de video no existe
        RuntimeError: Si la extracción falla
    """
    # Validar archivo de entrada
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"El archivo de video no existe: {video_path}")
    
    # Crear ruta de salida si no se proporciona
    if output_path is None:
        video_name = Path(video_path).stem
        output_dir = Path(video_path).parent
        output_path = str(output_dir / f"{video_name}_audio.wav")
    
    # Configurar comandos de FFmpeg
    channels = "1" if mono else "2"
    
    # Comando completo de FFmpeg
    cmd = [
        "ffmpeg", 
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # Formato PCM 16-bit
        "-ar", str(sample_rate),  # Sample rate
        "-ac", channels,  # Canales (mono/estéreo)
        "-y",  # Sobrescribir si existe
        output_path
    ]
    
    try:
        logger.info(f"Extrayendo audio de {video_path}")
        
        # Ejecutar FFmpeg sin mostrar su salida
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Monitorear progreso si se proporciona el objeto Progress
        if progress and task_id:
            # Actualizar progreso mientras se ejecuta
            progress.update(task_id, advance=50)
            
        # Esperar a que termine el proceso
        stdout, stderr = process.communicate()
        
        if progress and task_id:
            progress.update(task_id, advance=50)
            
        # Verificar si hubo errores
        if process.returncode != 0:
            raise RuntimeError(f"Error al extraer audio: {stderr}")
        
        logger.info(f"Audio extraído correctamente: {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Error durante la extracción de audio: {str(e)}")
        raise

def extract_audio_batch(
    video_paths: list[str],
    output_dir: Optional[str] = None,
    mono: bool = True,
    sample_rate: int = 44100,
    progress: Optional[Progress] = None
) -> list[str]:
    """
    Extrae audio de múltiples videos en batch.
    
    Args:
        video_paths: Lista de rutas a archivos de video
        output_dir: Directorio para los archivos de audio extraídos
        mono: Si True, convierte el audio a mono
        sample_rate: Frecuencia de muestreo para el audio resultante
        progress: Objeto Progress de Rich para mostrar progreso
        
    Returns:
        Lista de rutas a los archivos de audio extraídos
    """
    extracted_paths = []
    
    # Crear directorio de salida si se proporciona y no existe
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Configurar barra de progreso si se proporciona
    if progress:
        main_task = progress.add_task("[cyan]Extrayendo audio de videos...", total=len(video_paths))
    
    # Procesar cada video
    for video_path in video_paths:
        try:
            video_name = Path(video_path).stem
            
            # Determinar ruta de salida
            if output_dir:
                output_path = os.path.join(output_dir, f"{video_name}_audio.wav")
            else:
                output_path = None
            
            # Mostrar subtarea en la barra de progreso
            if progress:
                progress.update(main_task, description=f"Extrayendo audio: {video_name}")
                task_id = progress.add_task(f"[green]Procesando {video_name}", total=100, visible=True)
            else:
                task_id = None
            
            # Extraer audio
            result_path = extract_audio_from_video(
                video_path, 
                output_path, 
                mono, 
                sample_rate,
                progress, 
                task_id
            )
            
            extracted_paths.append(result_path)
            
            # Finalizar subtarea
            if progress and task_id:
                progress.remove_task(task_id)
                progress.update(main_task, advance=1)
                
        except Exception as e:
            logger.error(f"Error al procesar {video_path}: {str(e)}")
            if progress:
                progress.update(main_task, advance=1)
    
    return extracted_paths 