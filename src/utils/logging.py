import os
import logging
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler

console = Console()

def setup_logger(log_dir: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """
    Configura un logger para la aplicación.
    
    Args:
        log_dir: Directorio donde guardar los logs, si es None no se guardan en archivo
        level: Nivel de logging
        
    Returns:
        logging.Logger: Logger configurado
    """
    # Configurar formato
    format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Crear logger
    logger = logging.getLogger("podcast_editor")
    logger.setLevel(level)
    
    # Eliminar handlers previos
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Agregar handler para consola con rich
    console_handler = RichHandler(rich_tracebacks=True)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)
    
    # Agregar handler para archivo si se especificó un directorio
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"podcast_editor_{timestamp}.log")
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(format_string))
        logger.addHandler(file_handler)
        
        logger.info(f"Log file created at: {log_file}")
    
    return logger

def log_processing_start(logger: logging.Logger, files: dict, params: dict) -> None:
    """
    Registra el inicio del procesamiento con los archivos y parámetros seleccionados.
    
    Args:
        logger: Logger configurado
        files: Diccionario con las rutas de los archivos
        params: Diccionario con los parámetros de procesamiento
    """
    logger.info("=== INICIO DE PROCESAMIENTO ===")
    logger.info("Archivos seleccionados:")
    for key, value in files.items():
        logger.info(f"  - {key}: {value}")
    
    logger.info("Parámetros de procesamiento:")
    for key, value in params.items():
        logger.info(f"  - {key}: {value}")

def log_processing_end(logger: logging.Logger, output_file: str, success: bool = True) -> None:
    """
    Registra el fin del procesamiento.
    
    Args:
        logger: Logger configurado
        output_file: Ruta del archivo de salida
        success: Si el procesamiento fue exitoso
    """
    if success:
        logger.info("=== PROCESAMIENTO COMPLETADO CON ÉXITO ===")
        logger.info(f"Archivo de salida: {output_file}")
    else:
        logger.error("=== PROCESAMIENTO FALLIDO ===")
    
    logger.info(f"Tiempo total: {datetime.now().strftime('%H:%M:%S')}")

def log_error(logger: logging.Logger, error: str, fatal: bool = False) -> None:
    """
    Registra un error en el procesamiento.
    
    Args:
        logger: Logger configurado
        error: Mensaje de error
        fatal: Si el error es fatal y debe abortar el procesamiento
    """
    if fatal:
        logger.critical(f"ERROR FATAL: {error}")
    else:
        logger.error(f"ERROR: {error}") 