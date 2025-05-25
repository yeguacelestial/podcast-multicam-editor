import os
import subprocess
from typing import Dict, List, Optional, Tuple

def validate_video_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Valida que un archivo sea un video válido y devuelve sus propiedades.
    
    Args:
        file_path: Ruta al archivo de video
        
    Returns:
        Tuple[bool, Optional[str]]: (es_valido, mensaje_error)
    """
    if not os.path.exists(file_path):
        return False, f"El archivo no existe: {file_path}"
    
    try:
        # Validar con ffprobe
        cmd = ["ffprobe", "-v", "error", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return False, f"Archivo de video no válido: {result.stderr.strip()}"
        
        return True, None
    except Exception as e:
        return False, f"Error al validar video: {str(e)}"

def validate_audio_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Valida que un archivo sea un audio válido y devuelve sus propiedades.
    
    Args:
        file_path: Ruta al archivo de audio
        
    Returns:
        Tuple[bool, Optional[str]]: (es_valido, mensaje_error)
    """
    if not os.path.exists(file_path):
        return False, f"El archivo no existe: {file_path}"
    
    try:
        # Validar con ffprobe
        cmd = ["ffprobe", "-v", "error", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return False, f"Archivo de audio no válido: {result.stderr.strip()}"
        
        return True, None
    except Exception as e:
        return False, f"Error al validar audio: {str(e)}"

def validate_input_files(files: Dict[str, str]) -> List[str]:
    """
    Valida todos los archivos de entrada.
    
    Args:
        files: Diccionario con las rutas de los archivos
        
    Returns:
        List[str]: Lista de errores, vacía si todo es válido
    """
    errors = []
    
    # Validar videos
    for key, file_path in [(k, v) for k, v in files.items() if k.startswith("video")]:
        valid, error = validate_video_file(file_path)
        if not valid:
            errors.append(f"Error en {key}: {error}")
    
    # Validar audios
    for key, file_path in [(k, v) for k, v in files.items() if k.startswith("audio")]:
        valid, error = validate_audio_file(file_path)
        if not valid:
            errors.append(f"Error en {key}: {error}")
    
    return errors 