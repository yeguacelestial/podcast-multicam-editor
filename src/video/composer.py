import os
import logging
from typing import Dict, List, Tuple, Optional, Union
from rich.progress import Progress, TaskID
import time
from concurrent.futures import ThreadPoolExecutor

from src.video.processor import VideoProcessor

logger = logging.getLogger(__name__)

class VideoComposer:
    """Compone el video final utilizando los resultados de los módulos de sincronización y detección."""
    
    def __init__(self, 
                 video_paths: Dict[str, str], 
                 audio_paths: Dict[str, str],
                 master_audio_path: Optional[str] = None,
                 output_dir: str = "output",
                 preview_mode: bool = False,
                 preview_duration: int = 300,  # 5 minutos en segundos
                 output_quality: str = "high",
                 transition_type: str = "instantáneo",
                 min_segment_duration: float = 2.0):
        """
        Inicializa el compositor de video.
        
        Args:
            video_paths: Diccionario de rutas de video {speaker_id: ruta}
            audio_paths: Diccionario de rutas de audio {speaker_id: ruta}
            master_audio_path: Ruta al audio maestro (opcional)
            output_dir: Directorio donde guardar los videos generados
            preview_mode: Si es True, genera solo un preview de duración limitada
            preview_duration: Duración en segundos para modo preview
            output_quality: Calidad de salida ("low", "medium", "high")
            transition_type: Tipo de transición entre clips ("instantáneo", "suave", "muy suave")
            min_segment_duration: Duración mínima de cada segmento en segundos
        """
        self.video_paths = video_paths
        self.audio_paths = audio_paths
        self.master_audio_path = master_audio_path
        self.output_dir = output_dir
        self.preview_mode = preview_mode
        self.preview_duration = preview_duration if preview_mode else None
        self.output_quality = output_quality
        self.transition_type = transition_type
        self.min_segment_duration = min_segment_duration
        
        # Creamos el directorio de salida si no existe
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.info(f"Directorio de salida creado: {output_dir}")
    
    def generate_video(self, 
                       speaker_timeline: List[Tuple[str, float, float]],
                       output_filename: str = "podcast_multicam.mp4",
                       progress: Optional[Progress] = None) -> str:
        """
        Genera el video final a partir del timeline de speaker activo.
        
        Args:
            speaker_timeline: Lista de tuplas (speaker_id, start_time, end_time)
            output_filename: Nombre del archivo de salida
            progress: Instancia de Progress para actualizar barra de progreso
            
        Returns:
            Ruta al video final generado
        """
        if not speaker_timeline:
            logger.error("Timeline de speaker vacío, no se puede generar video")
            raise ValueError("El timeline de speaker está vacío")
        
        # Configuramos task_ids para las barras de progreso
        task_ids = {}
        if progress:
            task_ids['load'] = progress.add_task("[cyan]Cargando videos...", total=100)
            task_ids['process'] = progress.add_task("[green]Procesando timeline...", total=100)
        
        start_time = time.time()
        logger.info(f"Iniciando generación de video {'(PREVIEW)' if self.preview_mode else ''}")
        
        # Configuramos la ruta de salida
        if self.preview_mode:
            base_name, ext = os.path.splitext(output_filename)
            output_filename = f"{base_name}_preview{ext}"
        
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Creamos el procesador de video
        processor = VideoProcessor(
            video_paths=self.video_paths,
            audio_paths=self.audio_paths,
            master_audio_path=self.master_audio_path,
            preview_duration=self.preview_duration,
            output_quality=self.output_quality
        )
        
        try:
            # Cargamos los videos
            processor.load_videos(
                progress=progress, 
                task_id=task_ids.get('load')
            )
            
            if progress:
                progress.update(task_ids['load'], completed=100)
            
            # Procesamos el timeline
            result_path = processor.process_active_speaker_timeline(
                speaker_timeline=speaker_timeline,
                transition_type=self.transition_type,
                min_segment_duration=self.min_segment_duration,
                output_path=output_path,
                progress=progress,
                task_id=task_ids.get('process')
            )
            
            # Calculamos tiempo total de procesamiento
            elapsed_time = time.time() - start_time
            logger.info(f"Video generado en {elapsed_time:.2f} segundos")
            logger.info(f"Video guardado en: {result_path}")
            
            if progress:
                progress.update(task_ids['process'], completed=100)
                
            return result_path
            
        except Exception as e:
            logger.error(f"Error en la generación de video: {e}")
            raise RuntimeError(f"No se pudo generar el video: {e}")
        finally:
            # Aseguramos que se limpien los recursos
            del processor
    
    def generate_batch_videos(self, 
                             speaker_timelines: Dict[str, List[Tuple[str, float, float]]],
                             progress: Optional[Progress] = None,
                             max_workers: int = 2) -> Dict[str, str]:
        """
        Genera múltiples videos en paralelo.
        
        Args:
            speaker_timelines: Diccionario {nombre_archivo: timeline}
            progress: Instancia de Progress para actualizar barra de progreso
            max_workers: Número máximo de workers para procesamiento paralelo
            
        Returns:
            Diccionario {nombre_archivo: ruta_video}
        """
        if not speaker_timelines:
            return {}
        
        result_paths = {}
        
        # Configuramos la barra de progreso general
        if progress:
            task_id = progress.add_task("[yellow]Generando videos...", total=len(speaker_timelines))
        
        # Función para procesar cada video
        def process_video(name, timeline):
            try:
                result_path = self.generate_video(timeline, f"{name}.mp4", progress)
                return name, result_path
            except Exception as e:
                logger.error(f"Error al generar video {name}: {e}")
                return name, None
        
        # Procesamos en paralelo con límite de workers
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_video, name, timeline): name 
                       for name, timeline in speaker_timelines.items()}
            
            for future in futures:
                name, path = future.result()
                if path:
                    result_paths[name] = path
                
                completed += 1
                if progress:
                    progress.update(task_id, completed=completed)
        
        return result_paths 