"""
Módulo para validación de archivos de entrada y salida.
"""

import os
import logging
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

def validate_file_exists(file_path: str) -> bool:
    """
    Valida que un archivo exista.
    
    Args:
        file_path: Ruta al archivo
        
    Returns:
        True si el archivo existe, False en caso contrario
    """
    if not file_path:
        return False
    
    return os.path.isfile(file_path)

def validate_directory_exists(dir_path: str, create_if_missing: bool = False) -> bool:
    """
    Valida que un directorio exista, opcionalmente lo crea si no existe.
    
    Args:
        dir_path: Ruta al directorio
        create_if_missing: Si True, crea el directorio si no existe
        
    Returns:
        True si el directorio existe o fue creado, False en caso contrario
    """
    if not dir_path:
        return False
    
    if os.path.isdir(dir_path):
        return True
    
    if create_if_missing:
        try:
            os.makedirs(dir_path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Error al crear directorio {dir_path}: {str(e)}")
            return False
    
    return False

def validate_video_file(file_path: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Valida que un archivo sea un video válido.
    
    Args:
        file_path: Ruta al archivo de video
        
    Returns:
        Tuple con (es_válido, info_video)
    """
    if not validate_file_exists(file_path):
        return False, {"error": "El archivo no existe"}
    
    # Verificar extensión
    valid_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    extension = os.path.splitext(file_path)[1].lower()
    
    if extension not in valid_extensions:
        return False, {"error": f"Extensión no válida: {extension}. Extensiones válidas: {', '.join(valid_extensions)}"}
    
    # En una implementación real, aquí podríamos usar ffprobe para verificar
    # que el archivo de video sea válido y obtener información adicional
    
    return True, {
        "path": file_path,
        "extension": extension,
        "size_mb": os.path.getsize(file_path) / (1024 * 1024)
    }

def validate_audio_file(file_path: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Valida que un archivo sea un audio válido.
    
    Args:
        file_path: Ruta al archivo de audio
        
    Returns:
        Tuple con (es_válido, info_audio)
    """
    if not validate_file_exists(file_path):
        return False, {"error": "El archivo no existe"}
    
    # Verificar extensión
    valid_extensions = [".wav", ".mp3", ".aac", ".flac", ".ogg"]
    extension = os.path.splitext(file_path)[1].lower()
    
    if extension not in valid_extensions:
        return False, {"error": f"Extensión no válida: {extension}. Extensiones válidas: {', '.join(valid_extensions)}"}
    
    # En una implementación real, aquí podríamos usar librosa o ffprobe para verificar
    # que el archivo de audio sea válido y obtener información adicional
    
    return True, {
        "path": file_path,
        "extension": extension,
        "size_mb": os.path.getsize(file_path) / (1024 * 1024)
    }

def check_output_file_path(output_path: str, overwrite: bool = False) -> Tuple[bool, str]:
    """
    Verifica si la ruta de salida es válida y si el archivo ya existe.
    
    Args:
        output_path: Ruta al archivo de salida
        overwrite: Si True, permite sobrescribir archivos existentes
        
    Returns:
        Tuple con (es_válido, mensaje)
    """
    if not output_path:
        return False, "La ruta de salida no puede estar vacía"
    
    # Verificar extensión
    valid_extensions = [".mp4", ".mov", ".avi", ".mkv"]
    extension = os.path.splitext(output_path)[1].lower()
    
    if extension not in valid_extensions:
        return False, f"Extensión no válida: {extension}. Extensiones válidas: {', '.join(valid_extensions)}"
    
    # Verificar directorio de salida
    output_dir = os.path.dirname(output_path)
    if not validate_directory_exists(output_dir, create_if_missing=True):
        return False, f"No se pudo crear o acceder al directorio de salida: {output_dir}"
    
    # Verificar si el archivo ya existe
    if os.path.exists(output_path):
        if not overwrite:
            return False, f"El archivo ya existe: {output_path}. Usa overwrite=True para sobrescribir."
        try:
            # Verificar si podemos escribir en el archivo
            with open(output_path, 'a'):
                pass
        except Exception as e:
            return False, f"No se puede escribir en el archivo existente: {str(e)}"
    
    return True, "Ruta de salida válida"

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