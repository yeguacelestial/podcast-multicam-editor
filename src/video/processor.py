import os
import logging
from typing import Dict, List, Tuple, Optional, Union
import numpy as np
from rich.progress import Progress, TaskID
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
import tempfile
import subprocess
from moviepy.video.io.ffmpeg_reader import ffmpeg_parse_infos

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Procesa y corta clips de video basado en la timeline de detección de speaker activo."""
    
    def __init__(self, 
                 video_paths: Dict[str, str], 
                 audio_paths: Dict[str, str],
                 master_audio_path: Optional[str] = None,
                 chunk_size: int = 5 * 60,  # 5 minutos en segundos
                 preview_duration: Optional[int] = None,
                 output_quality: str = "high"):
        """
        Inicializa el procesador de video.
        
        Args:
            video_paths: Diccionario de rutas de video {speaker_id: ruta}
            audio_paths: Diccionario de rutas de audio {speaker_id: ruta}
            master_audio_path: Ruta al audio maestro (opcional)
            chunk_size: Tamaño de chunk en segundos para procesamiento
            preview_duration: Duración en segundos para modo preview (None para todo)
            output_quality: Calidad de salida ("low", "medium", "high")
        """
        self.video_paths = video_paths
        self.audio_paths = audio_paths
        self.master_audio_path = master_audio_path
        self.chunk_size = chunk_size
        self.preview_duration = preview_duration
        self.output_quality = output_quality
        self.video_clips = {}
        self.audio_clips = {}
        self.temp_files = []
        
        # Configuraciones de calidad
        self.quality_settings = {
            "low": {"bitrate": "2000k", "preset": "ultrafast"},
            "medium": {"bitrate": "4000k", "preset": "medium"},
            "high": {"bitrate": "8000k", "preset": "slow"}
        }
    
    def __del__(self):
        """Limpia recursos al destruir la instancia."""
        self._cleanup_clips()
        self._cleanup_temp_files()
    
    def _cleanup_clips(self):
        """Cierra todos los clips de video y audio cargados."""
        for clip in list(self.video_clips.values()):
            try:
                clip.close()
            except Exception as e:
                logger.warning(f"Error al cerrar clip de video: {e}")
        
        for clip in list(self.audio_clips.values()):
            try:
                clip.close()
            except Exception as e:
                logger.warning(f"Error al cerrar clip de audio: {e}")
                
        self.video_clips = {}
        self.audio_clips = {}
    
    def _cleanup_temp_files(self):
        """Elimina archivos temporales."""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"Archivo temporal eliminado: {temp_file}")
            except Exception as e:
                logger.warning(f"Error al eliminar archivo temporal {temp_file}: {e}")
        
        self.temp_files = []
    
    def load_videos(self, progress: Optional[Progress] = None, task_id: Optional[TaskID] = None):
        """
        Carga los videos para todos los speakers.
        
        Args:
            progress: Instancia de Progress para actualizar barra de progreso
            task_id: ID de la tarea en la barra de progreso
        """
        logger.info("Cargando videos de cámaras...")
        
        # Limpiamos clips anteriores si existen
        self._cleanup_clips()
        
        total_speakers = len(self.video_paths)
        speakers_loaded = 0
        
        for speaker_id, video_path in self.video_paths.items():
            try:
                logger.info(f"Cargando video para speaker {speaker_id}: {video_path}")
                
                # Cargamos solo hasta preview_duration si está especificado
                if self.preview_duration:
                    self.video_clips[speaker_id] = VideoFileClip(video_path).subclip(0, self.preview_duration)
                    logger.info(f"Modo preview activado: recortando a {self.preview_duration} segundos")
                else:
                    self.video_clips[speaker_id] = VideoFileClip(video_path)
                
                # Cargamos los audios mono correspondientes
                if speaker_id in self.audio_paths:
                    audio_path = self.audio_paths[speaker_id]
                    logger.info(f"Cargando audio para speaker {speaker_id}: {audio_path}")
                    
                    if self.preview_duration:
                        self.audio_clips[speaker_id] = AudioFileClip(audio_path).subclip(0, self.preview_duration)
                    else:
                        self.audio_clips[speaker_id] = AudioFileClip(audio_path)
                
                speakers_loaded += 1
                if progress and task_id:
                    progress.update(task_id, completed=speakers_loaded/total_speakers*100)
                
            except Exception as e:
                logger.error(f"Error al cargar video/audio para speaker {speaker_id}: {e}")
                raise RuntimeError(f"No se pudo cargar el video/audio para {speaker_id}")
        
        logger.info(f"Videos cargados exitosamente: {len(self.video_clips)}")
        
        # Verificar que todos los videos tengan aproximadamente la misma duración
        self._verify_video_durations()
    
    def _verify_video_durations(self, tolerance_seconds: float = 5.0):
        """
        Verifica que las duraciones de los videos sean similares.
        
        Args:
            tolerance_seconds: Tolerancia en segundos para diferencias de duración
        """
        if not self.video_clips:
            return
        
        durations = {speaker_id: clip.duration for speaker_id, clip in self.video_clips.items()}
        logger.info(f"Duraciones de videos: {durations}")
        
        max_duration = max(durations.values())
        min_duration = min(durations.values())
        
        if max_duration - min_duration > tolerance_seconds:
            logger.warning(f"Las duraciones de los videos difieren en más de {tolerance_seconds} segundos")
            logger.warning(f"Diferencia máxima: {max_duration - min_duration} segundos")
        else:
            logger.info("Duraciones de videos verificadas: OK")
    
    def process_active_speaker_timeline(self, 
                                        speaker_timeline: List[Tuple[str, float, float]], 
                                        transition_type: str = "cut", 
                                        min_segment_duration: float = 2.0,
                                        output_path: str = "output.mp4",
                                        progress: Optional[Progress] = None,
                                        task_id: Optional[TaskID] = None):
        """
        Procesa el timeline de speaker activo y genera el video final.
        
        Args:
            speaker_timeline: Lista de tuplas (speaker_id, start_time, end_time)
            transition_type: Tipo de transición entre clips ("cut", "crossfade", "fade")
            min_segment_duration: Duración mínima de cada segmento en segundos
            output_path: Ruta donde guardar el video final
            progress: Instancia de Progress para actualizar barra de progreso
            task_id: ID de la tarea en la barra de progreso
            
        Returns:
            Ruta al video final generado
        """
        if not self.video_clips:
            raise RuntimeError("Debe cargar los videos primero con load_videos()")
        
        logger.info(f"Procesando timeline de speaker activo con {len(speaker_timeline)} segmentos")
        logger.info(f"Tipo de transición: {transition_type}")
        
        # Filtramos segmentos demasiado cortos
        filtered_timeline = self._filter_short_segments(speaker_timeline, min_segment_duration)
        logger.info(f"Timeline filtrado: {len(filtered_timeline)} segmentos")
        
        # Si está en modo preview, filtramos los segmentos
        if self.preview_duration:
            filtered_timeline = [segment for segment in filtered_timeline 
                               if segment[1] < self.preview_duration]
            logger.info(f"Timeline recortado para preview: {len(filtered_timeline)} segmentos")
        
        # Procesamos por chunks para optimizar memoria
        if self.preview_duration:
            # Si es preview, procesamos todo de una vez ya que es corto
            return self._process_timeline_segment(filtered_timeline, transition_type, output_path, progress, task_id)
        else:
            # Procesamos en chunks
            return self._process_timeline_in_chunks(filtered_timeline, transition_type, output_path, progress, task_id)
    
    def _filter_short_segments(self, 
                              timeline: List[Tuple[str, float, float]], 
                              min_duration: float) -> List[Tuple[str, float, float]]:
        """
        Filtra segmentos demasiado cortos y los fusiona con segmentos adyacentes.
        
        Args:
            timeline: Lista de tuplas (speaker_id, start_time, end_time)
            min_duration: Duración mínima de cada segmento en segundos
            
        Returns:
            Timeline filtrado
        """
        filtered = []
        i = 0
        
        while i < len(timeline):
            speaker_id, start_time, end_time = timeline[i]
            duration = end_time - start_time
            
            # Si el segmento es lo suficientemente largo, lo añadimos directamente
            if duration >= min_duration:
                filtered.append((speaker_id, start_time, end_time))
                i += 1
                continue
            
            # Si es demasiado corto y es el último segmento, lo añadimos al anterior
            if i == len(timeline) - 1:
                if filtered:
                    prev_speaker, prev_start, prev_end = filtered[-1]
                    filtered[-1] = (prev_speaker, prev_start, end_time)
                else:
                    filtered.append((speaker_id, start_time, end_time))
                break
            
            # Si es demasiado corto y hay un siguiente segmento, miramos cuál es el mismo speaker
            next_speaker, next_start, next_end = timeline[i + 1]
            
            if i > 0:
                prev_speaker, prev_start, prev_end = filtered[-1]
                
                # Si el speaker actual coincide con el anterior o el siguiente, fusionamos
                if speaker_id == prev_speaker:
                    filtered[-1] = (prev_speaker, prev_start, end_time)
                    i += 1
                elif speaker_id == next_speaker:
                    timeline[i + 1] = (next_speaker, start_time, next_end)
                    i += 1
                else:
                    # Si no coincide con ninguno, lo añadimos al que tenga mayor duración
                    prev_duration = prev_end - prev_start
                    next_duration = next_end - next_start
                    
                    if prev_duration >= next_duration:
                        filtered[-1] = (prev_speaker, prev_start, end_time)
                    else:
                        timeline[i + 1] = (next_speaker, start_time, next_end)
                    i += 1
            else:
                # Si es el primer segmento, lo fusionamos con el siguiente
                timeline[i + 1] = (next_speaker, start_time, next_end)
                i += 1
        
        return filtered
    
    def _create_transition(self, clip1, clip2, transition_type, duration=0.5):
        """
        Crea una transición entre dos clips.
        
        Args:
            clip1: Primer clip
            clip2: Segundo clip
            transition_type: Tipo de transición
            duration: Duración de la transición en segundos
            
        Returns:
            Lista de clips con transición
        """
        logger.info(f"Creando transición de tipo: {transition_type}")
        
        # Para asegurar compatibilidad, usamos transiciones muy básicas
        # o directamente cortes, ya que MoviePy 2.0+ tiene cambios significativos
        
        try:
            if transition_type == "cut" or duration <= 0:
                # Corte directo, sin transición
                logger.info("Usando corte directo (sin transición)")
                return [clip1, clip2]
            
            elif transition_type in ["crossfade", "fade"]:
                # Por ahora, simplemente hacemos un corte directo
                # hasta que se verifique la compatibilidad con MoviePy 2.0+
                logger.warning(f"Transición {transition_type} no implementada en esta versión, usando corte directo")
                return [clip1, clip2]
            
            else:
                logger.warning(f"Tipo de transición desconocida: {transition_type}")
                return [clip1, clip2]
                
        except Exception as e:
            logger.error(f"Error general al crear transición: {e}")
            # Por seguridad, devolvemos los clips sin transición
            return [clip1, clip2]
    
    def _process_timeline_segment(self, 
                                 timeline: List[Tuple[str, float, float]], 
                                 transition_type: str,
                                 output_path: str,
                                 progress: Optional[Progress] = None,
                                 task_id: Optional[TaskID] = None) -> str:
        """
        Procesa un segmento del timeline y genera un video.
        
        Args:
            timeline: Lista de tuplas (speaker_id, start_time, end_time)
            transition_type: Tipo de transición entre clips
            output_path: Ruta de salida para el video
            progress: Instancia de Progress para actualizar barra de progreso
            task_id: ID de la tarea en la barra de progreso
            
        Returns:
            Ruta al video generado
        """
        if not timeline:
            logger.warning("Timeline vacío, no se generó video")
            return None
        
        logger.info(f"Procesando segmento de timeline con {len(timeline)} cortes")
        
        # Mapeamos transición de UI a valores internos
        transition_mapping = {
            "instantáneo": "cut",
            "suave": "crossfade",
            "muy suave": "fade"
        }
        
        if transition_type in transition_mapping:
            transition_type = transition_mapping[transition_type]
        
        logger.info(f"Usando tipo de transición: {transition_type}")
        
        # Configuramos duración de transición según tipo
        transition_duration = 0.0
        if transition_type == "crossfade":
            transition_duration = 0.5
        elif transition_type == "fade":
            transition_duration = 1.0
        
        logger.info(f"Duración de transición: {transition_duration} segundos")
        
        clips = []
        total_segments = len(timeline)
        
        for i, (speaker_id, start_time, end_time) in enumerate(timeline):
            try:
                logger.info(f"Procesando segmento {i+1}/{total_segments}: speaker={speaker_id}, tiempo={start_time}-{end_time}")
                
                if speaker_id not in self.video_clips:
                    available_speakers = list(self.video_clips.keys())
                    logger.warning(f"Speaker {speaker_id} no encontrado, usando alternativa de {available_speakers[0]}")
                    speaker_id = available_speakers[0]
                
                # Obtenemos el clip de video para este speaker
                video_clip = self.video_clips[speaker_id]
                logger.debug(f"Clip de video para {speaker_id} - duración: {video_clip.duration}s")
                
                # Validar que los tiempos estén dentro del rango del video
                if start_time >= video_clip.duration or end_time > video_clip.duration:
                    logger.warning(f"Segmento fuera de rango: {start_time}-{end_time}, duración del video: {video_clip.duration}")
                    # Ajustar tiempos si es necesario
                    start_time = min(start_time, max(0, video_clip.duration - 1))
                    end_time = min(end_time, video_clip.duration)
                    logger.info(f"Ajustando tiempos a: {start_time}-{end_time}")
                
                # Recortamos el clip según el timeline
                logger.debug(f"Recortando clip de {start_time}s a {end_time}s")
                segment_clip = video_clip.subclip(start_time, end_time)
                logger.debug(f"Clip recortado - duración: {segment_clip.duration}s")
                
                # Si es el primer clip, lo añadimos directamente
                if not clips:
                    logger.debug("Añadiendo primer clip directamente")
                    clips.append(segment_clip)
                else:
                    # Si hay un clip anterior, aplicamos transición
                    logger.debug("Aplicando transición con clip anterior")
                    prev_clip = clips.pop()
                    
                    try:
                        transition_clips = self._create_transition(
                            prev_clip, segment_clip, transition_type, transition_duration
                        )
                        logger.debug(f"Transición creada con {len(transition_clips)} clips resultantes")
                        clips.extend(transition_clips)
                    except Exception as e:
                        logger.error(f"Error al crear transición: {e}")
                        # Si falla la transición, añadimos los clips sin transición
                        logger.info("Usando corte directo como alternativa")
                        clips.append(prev_clip)
                        clips.append(segment_clip)
                
                # Actualizamos progreso
                if progress and task_id:
                    progress.update(task_id, completed=(i+1)/total_segments*100)
                
            except Exception as e:
                logger.error(f"Error al procesar segmento {i} ({speaker_id}, {start_time}-{end_time}): {e}")
                # Continuamos con el siguiente segmento
        
        if not clips:
            logger.error("No se pudieron procesar clips")
            return None
        
        try:
            # Concatenamos todos los clips
            logger.info(f"Concatenando {len(clips)} clips...")
            final_clip = concatenate_videoclips(clips, method="compose")
            logger.info(f"Concatenación completada. Duración final: {final_clip.duration}s")
            
            # Si tenemos audio maestro, lo usamos
            if self.master_audio_path and os.path.exists(self.master_audio_path):
                logger.info(f"Usando audio maestro: {self.master_audio_path}")
                try:
                    master_audio = AudioFileClip(self.master_audio_path)
                    
                    if self.preview_duration:
                        master_audio = master_audio.subclip(0, self.preview_duration)
                    
                    # Ajustamos la duración del audio a la del video final
                    if master_audio.duration > final_clip.duration:
                        master_audio = master_audio.subclip(0, final_clip.duration)
                    
                    final_clip = final_clip.set_audio(master_audio)
                    logger.info("Audio maestro aplicado al video final")
                except Exception as e:
                    logger.error(f"Error al aplicar audio maestro: {e}")
                    logger.info("Continuando sin audio maestro")
            
            # Configuramos calidad de salida
            quality_config = self.quality_settings.get(self.output_quality, self.quality_settings["medium"])
            
            # Crear directorio de salida si no existe
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                logger.info(f"Creado directorio de salida: {output_dir}")
            
            # Usamos FFmpeg directamente para mayor eficiencia
            logger.info(f"Guardando video final en {output_path}...")
            
            # Primero verificamos si ffmpeg está disponible
            try:
                subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
                logger.info("FFmpeg disponible en el sistema")
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                logger.warning(f"FFmpeg no disponible o error al verificar: {e}")
                logger.info("Usando moviepy para escribir directamente")
                
                final_clip.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile='temp-audio.m4a',
                    remove_temp=True,
                    bitrate=quality_config["bitrate"],
                    threads=4,
                    logger=None
                )
                
                logger.info(f"Video final guardado directamente en {output_path}")
                return output_path
                
            # Si ffmpeg está disponible, usamos el enfoque en dos pasos
            temp_file = tempfile.mktemp(suffix='.mp4')
            self.temp_files.append(temp_file)
            
            logger.info(f"Escribiendo clip en archivo temporal: {temp_file}")
            # Primero guardamos con moviepy
            final_clip.write_videofile(
                temp_file,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True,
                bitrate=quality_config["bitrate"],
                threads=4,  # Usar múltiples threads para codificación
                logger=None  # Desactivamos logger interno de moviepy
            )
            
            logger.info(f"Optimizando con FFmpeg desde: {temp_file} a {output_path}")
            # Luego optimizamos con ffmpeg directamente
            ffmpeg_cmd = [
                'ffmpeg', '-i', temp_file,
                '-c:v', 'libx264', '-preset', quality_config["preset"],
                '-c:a', 'aac', '-b:a', '192k',
                '-y', output_path
            ]
            
            logger.info(f"Ejecutando comando FFmpeg: {' '.join(ffmpeg_cmd)}")
            subprocess.run(ffmpeg_cmd, check=True)
            
            # Verificar que el archivo se creó correctamente
            if os.path.exists(output_path):
                output_size = os.path.getsize(output_path) / (1024 * 1024)  # tamaño en MB
                logger.info(f"Video final guardado en {output_path} ({output_size:.2f} MB)")
                return output_path
            else:
                logger.error(f"El archivo de salida {output_path} no existe después del procesamiento")
                return None
            
        except Exception as e:
            logger.error(f"Error al generar video final: {e}")
            import traceback
            logger.error(f"Detalles del error: {traceback.format_exc()}")
            raise RuntimeError(f"No se pudo generar el video final: {e}")
        finally:
            # Limpiamos clips
            for clip in clips:
                try:
                    clip.close()
                except Exception as e:
                    logger.warning(f"Error al cerrar clip: {e}")
                    pass
    
    def _process_timeline_in_chunks(self, 
                                   timeline: List[Tuple[str, float, float]],
                                   transition_type: str,
                                   output_path: str,
                                   progress: Optional[Progress] = None,
                                   task_id: Optional[TaskID] = None) -> str:
        """
        Procesa el timeline en chunks para optimizar memoria.
        
        Args:
            timeline: Lista de tuplas (speaker_id, start_time, end_time)
            transition_type: Tipo de transición entre clips
            output_path: Ruta de salida para el video
            progress: Instancia de Progress para actualizar barra de progreso
            task_id: ID de la tarea en la barra de progreso
            
        Returns:
            Ruta al video final generado
        """
        if not timeline:
            return None
        
        # Dividimos el timeline en chunks basados en el tiempo
        chunks = []
        current_chunk = []
        chunk_end_time = self.chunk_size  # Primer chunk termina en chunk_size
        
        for segment in timeline:
            speaker_id, start_time, end_time = segment
            
            # Si el segmento comienza después del final del chunk actual
            if start_time >= chunk_end_time:
                # Guardamos el chunk actual y creamos uno nuevo
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                
                # Actualizamos el final del nuevo chunk
                chunk_end_time = (start_time // self.chunk_size + 1) * self.chunk_size
            
            # Añadimos el segmento al chunk actual
            current_chunk.append(segment)
        
        # Añadimos el último chunk si tiene contenido
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.info(f"Timeline dividido en {len(chunks)} chunks para procesamiento eficiente")
        
        # Procesamos cada chunk y obtenemos archivos temporales
        temp_chunk_files = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Procesando chunk {i+1}/{len(chunks)}")
            
            # Creamos archivo temporal para este chunk
            temp_file = tempfile.mktemp(suffix=f'_chunk_{i}.mp4')
            self.temp_files.append(temp_file)
            
            # Actualizamos progreso
            if progress and task_id:
                chunk_progress = i / len(chunks) * 100
                progress.update(task_id, completed=chunk_progress)
            
            # Procesamos este chunk de timeline
            chunk_file = self._process_timeline_segment(
                chunk, 
                transition_type, 
                temp_file,
                progress, 
                task_id
            )
            
            if chunk_file:
                temp_chunk_files.append(chunk_file)
        
        # Concatenamos todos los chunks con ffmpeg
        if temp_chunk_files:
            # Creamos archivo con lista de archivos para ffmpeg
            concat_list_file = tempfile.mktemp(suffix='.txt')
            self.temp_files.append(concat_list_file)
            
            with open(concat_list_file, 'w') as f:
                for chunk_file in temp_chunk_files:
                    f.write(f"file '{os.path.abspath(chunk_file)}'\n")
            
            # Configuramos calidad de salida
            quality_config = self.quality_settings.get(self.output_quality, self.quality_settings["medium"])
            
            # Concatenamos con ffmpeg
            ffmpeg_cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0',
                '-i', concat_list_file,
                '-c', 'copy',  # Solo copiamos, sin recodificar para mayor eficiencia
                '-y', output_path
            ]
            
            logger.info(f"Concatenando chunks con FFmpeg: {' '.join(ffmpeg_cmd)}")
            
            try:
                subprocess.run(ffmpeg_cmd, check=True)
                logger.info(f"Video final guardado en {output_path}")
                return output_path
            except Exception as e:
                logger.error(f"Error al concatenar chunks: {e}")
                raise RuntimeError(f"No se pudo concatenar los chunks de video: {e}")
        else:
            logger.error("No se generaron chunks de video")
            return None 

    def quick_test(self, output_path: str, duration: int = 30):
        """
        Realiza una prueba rápida extrayendo segmentos cortos de cada video y uniéndolos.
        
        Args:
            output_path: Ruta de salida para el video de prueba
            duration: Duración en segundos de cada segmento
            
        Returns:
            Ruta al video generado
        """
        logger.info(f"Ejecutando prueba rápida con segmentos de {duration} segundos")
        
        clips = []
        
        try:
            # Crear un clip corto para cada speaker
            for i, (speaker_id, video_path) in enumerate(self.video_paths.items()):
                logger.info(f"Cargando video para speaker {speaker_id}: {video_path}")
                
                # Cargar solo los primeros segundos del video
                try:
                    # Obtener directamente la información del video sin cargarlo completo
                    video_info = ffmpeg_parse_infos(video_path)
                    total_duration = video_info['duration']
                    
                    start_time = min(i * duration, max(0, total_duration - duration))
                    end_time = min(start_time + duration, total_duration)
                    
                    logger.info(f"Extrayendo segmento de {start_time}s a {end_time}s del video de {speaker_id}")
                    
                    # Crear clip directamente especificando el fragmento
                    clip = VideoFileClip(video_path, target_resolution=(720, None)).subclip(start_time, end_time)
                    clips.append(clip)
                    
                except Exception as e:
                    logger.error(f"Error al procesar video {speaker_id}: {e}")
            
            if not clips:
                logger.error("No se pudieron crear clips para la prueba")
                return None
                
            # Concatenar los clips directamente
            logger.info(f"Concatenando {len(clips)} clips de prueba")
            final_clip = concatenate_videoclips(clips, method="chain")
            
            # Crear directorio de salida si no existe
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Escribir directamente sin pasar por FFmpeg
            logger.info(f"Escribiendo video de prueba a: {output_path}")
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                audio=True,  # Mantener el audio original
                audio_codec='aac',
                preset='ultrafast',  # Más rápido aunque menos eficiente
                threads=4,
                logger=None
            )
            
            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(f"Video de prueba generado: {output_path} ({size_mb:.1f} MB)")
                return output_path
            else:
                logger.error(f"No se pudo generar el video de prueba: {output_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error en prueba rápida: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        finally:
            # Cerrar clips
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass 

    def ultra_simple_test(self, timeline: List[Tuple[str, float, float]], output_path: str, transition_type: str = "cut"):
        """
        Versión extremadamente simplificada del procesador de timeline para pruebas.
        
        Args:
            timeline: Lista de tuplas (speaker_id, start_time, end_time)
            output_path: Ruta donde guardar el video final
            transition_type: Tipo de transición entre clips ("cut", "crossfade", "fade")
            
        Returns:
            Ruta al video generado
        """
        logger.info(f"Ejecutando prueba ultra simple con {len(timeline)} segmentos")
        logger.info(f"Tipo de transición: {transition_type}")
        
        # Validar que tengamos videos cargados
        if not self.video_clips:
            logger.info("Cargando videos automáticamente")
            self.load_videos()
        
        clips = []
        
        try:
            # Procesar cada segmento del timeline de forma directa
            for i, (speaker_id, start_time, end_time) in enumerate(timeline):
                logger.info(f"Procesando segmento {i+1}/{len(timeline)}: speaker={speaker_id}, tiempo={start_time}-{end_time}")
                
                if speaker_id not in self.video_clips:
                    available_speakers = list(self.video_clips.keys())
                    logger.warning(f"Speaker {speaker_id} no encontrado, usando alternativa de {available_speakers[0]}")
                    speaker_id = available_speakers[0]
                
                video_clip = self.video_clips[speaker_id]
                
                # Validar tiempos
                if start_time >= video_clip.duration:
                    logger.warning(f"Tiempo inicial {start_time} fuera de rango, ajustando")
                    start_time = 0
                
                if end_time > video_clip.duration:
                    logger.warning(f"Tiempo final {end_time} fuera de rango, ajustando a {video_clip.duration}")
                    end_time = video_clip.duration
                
                # Crear subclip y agregar
                segment_clip = video_clip.subclip(start_time, end_time)
                
                # Si es el primer clip, lo añadimos directamente
                if not clips:
                    clips.append(segment_clip)
                else:
                    # Si hay un clip anterior, aplicamos transición
                    prev_clip = clips.pop()
                    
                    try:
                        transition_clips = self._create_transition(
                            prev_clip, segment_clip, transition_type, duration=0.5
                        )
                        clips.extend(transition_clips)
                        logger.info(f"Transición aplicada: {transition_type}")
                    except Exception as e:
                        logger.error(f"Error al crear transición: {e}")
                        # Si falla, añadimos los clips sin transición
                        clips.append(prev_clip)
                        clips.append(segment_clip)
                
                logger.info(f"Segmento {i+1} procesado: duración={segment_clip.duration}s")
            
            # Verificar que haya clips para concatenar
            if not clips:
                logger.error("No se pudieron crear clips para concatenar")
                return None
            
            # Concatenar los clips
            logger.info(f"Concatenando {len(clips)} clips...")
            final_clip = concatenate_videoclips(clips, method="chain")
            logger.info(f"Concatenación completada: duración={final_clip.duration}s")
            
            # Crear directorio de salida si es necesario
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Escribir directamente con configuración mínima
            logger.info(f"Escribiendo video a {output_path}")
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                preset='ultrafast',
                threads=4,
                logger=None
            )
            
            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(f"Video generado exitosamente: {output_path} ({size_mb:.1f} MB)")
                return output_path
            else:
                logger.error(f"El archivo de salida {output_path} no se generó correctamente")
                return None
                
        except Exception as e:
            logger.error(f"Error en prueba ultra simple: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
        finally:
            # Limpiar clips
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass 