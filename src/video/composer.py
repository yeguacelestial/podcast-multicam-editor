"""
Módulo para composición de video final usando ffmpeg
"""
import os
import subprocess
import json
import tempfile
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path
import shutil
from rich.progress import Progress, TaskID
from rich.console import Console
import time

console = Console()

def compose_video_from_timeline(
    timeline: List[Dict],
    video_paths: Dict[str, str],
    audio_path: str,
    output_path: str,
    preview_mode: bool = False,
    preview_duration: int = 5,
    transition_type: str = "cut",
    transition_duration: float = 0.5,
    output_quality: str = "high",
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
    log_progress: bool = True
) -> str:
    """
    Compone un video final basado en un timeline de cambios de cámara
    
    Args:
        timeline: Lista de diccionarios con {speaker_id, start_time, end_time}
        video_paths: Diccionario de {speaker_id: video_path}
        audio_path: Ruta al audio maestro
        output_path: Ruta donde guardar el video final
        preview_mode: Si procesar solo los primeros N minutos
        preview_duration: Duración en minutos del preview
        transition_type: Tipo de transición ("cut", "fade", "dissolve")
        transition_duration: Duración de la transición en segundos
        output_quality: Calidad de salida ("low", "medium", "high")
        progress: Objeto Progress de rich para actualizar barra general
        task_id: ID de la tarea en el objeto Progress
        log_progress: Si mostrar logs del progreso
        
    Returns:
        Ruta al video final
    """
    if log_progress:
        console.log(f"Iniciando composición de video a partir del timeline...")
    
    # Validaciones iniciales
    if not timeline:
        raise ValueError("No se proporcionó ningún segmento en el timeline")
    
    if not video_paths:
        raise ValueError("No se proporcionaron rutas de video")
    
    if not os.path.exists(audio_path):
        raise ValueError(f"El archivo de audio maestro no existe: {audio_path}")
    
    # Verificar que al menos un video exista
    video_exists = False
    for speaker_id, path in video_paths.items():
        if os.path.exists(path):
            video_exists = True
            break
    
    if not video_exists:
        raise ValueError("Ninguno de los videos proporcionados existe")
    
    # Verificar que el directorio de salida exista
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        if log_progress:
            console.log(f"Creando directorio de salida: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)
    
    # Crear directorio temporal para archivos intermedios
    temp_dir = tempfile.mkdtemp()
    segments_list_file = os.path.join(temp_dir, "segments.txt")
    
    try:
        # Filtrar timeline para preview si es necesario
        if preview_mode:
            max_time = preview_duration * 60  # convertir a segundos
            timeline = [segment for segment in timeline if segment["start_time"] < max_time]
            if timeline and timeline[-1]["end_time"] > max_time:
                timeline[-1]["end_time"] = max_time
        
        if not timeline:
            raise ValueError("Timeline vacío o no hay segmentos en el rango de preview")
        
        # Crear segmentos de video
        segments = []
        total_segments = len(timeline)
        
        if log_progress:
            console.log(f"Procesando {total_segments} segmentos de video...")
        
        # Determinar parámetros de calidad
        if preview_mode or output_quality == "low":
            video_params = ["-vf", "scale=-2:480", "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast"]
            audio_params = ["-c:a", "aac", "-b:a", "128k"]
        elif output_quality == "medium":
            video_params = ["-c:v", "libx264", "-crf", "23", "-preset", "medium"]
            audio_params = ["-c:a", "aac", "-b:a", "192k"]
        else:  # high
            video_params = ["-c:v", "libx264", "-crf", "18", "-preset", "slow"]
            audio_params = ["-c:a", "aac", "-b:a", "256k"]
        
        # Usar barra de progreso externa si se proporciona
        if progress is not None and task_id is not None:
            # Función para actualizar el progreso del segmento
            def update_segment_progress(current, total):
                # Calculamos cuánto avance representa cada segmento en el total
                segment_portion = 0.5 / total
                # Actualizamos el progreso general
                progress.update(task_id, advance=segment_portion)
            
            for i, segment in enumerate(timeline):
                speaker_id = segment["speaker_id"]
                start_time = segment["start_time"]
                end_time = segment["end_time"]
                duration = end_time - start_time
                
                # Validar duración del segmento
                if duration <= 0:
                    if log_progress:
                        console.log(f"[yellow]Advertencia: Segmento {i} tiene duración no positiva ({duration}s), ignorando[/]")
                    continue
                
                if speaker_id not in video_paths:
                    if log_progress:
                        console.log(f"[yellow]Advertencia: No hay video para speaker {speaker_id}, usando video alternativo[/]")
                    # Usar el primer video disponible como fallback
                    video_path = next(iter(video_paths.values()))
                else:
                    video_path = video_paths[speaker_id]
                
                # Verificar que el video exista
                if not os.path.exists(video_path):
                    if log_progress:
                        console.log(f"[yellow]Advertencia: Video no encontrado: {video_path}, buscando alternativa[/]")
                    # Buscar otro video disponible
                    alternate_found = False
                    for alt_path in video_paths.values():
                        if os.path.exists(alt_path):
                            video_path = alt_path
                            alternate_found = True
                            if log_progress:
                                console.log(f"[green]Video alternativo encontrado: {alt_path}[/]")
                            break
                    
                    if not alternate_found:
                        if log_progress:
                            console.log(f"[bold red]Error: No hay videos disponibles para el segmento {i}[/]")
                        continue
                
                segment_output = os.path.join(temp_dir, f"segment_{i:04d}.mp4")
                
                try:
                    # Cortar segmento de video
                    cmd = [
                        "ffmpeg",
                        "-ss", str(start_time),
                        "-i", video_path,
                        "-t", str(duration),
                        *video_params,
                        "-an",  # sin audio, se añadirá después
                        "-y",
                        segment_output
                    ]
                    
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    
                    # Verificar que el segmento se creó correctamente
                    if os.path.exists(segment_output) and os.path.getsize(segment_output) > 0:
                        segments.append(segment_output)
                    else:
                        if log_progress:
                            console.log(f"[yellow]Advertencia: Segmento {i} no se generó correctamente, ignorando[/]")
                except subprocess.CalledProcessError as e:
                    if log_progress:
                        console.log(f"[yellow]Error al procesar segmento {i}, ignorando: {e}[/]")
                        # Mostrar salida de error de ffmpeg
                        if e.stderr:
                            console.log(f"[red]FFmpeg error: {e.stderr}[/]")
                
                # Actualizar progreso
                update_segment_progress(i + 1, total_segments)
        else:
            # Si no hay progreso externo, crear uno propio
            with Progress() as segment_progress:
                segment_task = segment_progress.add_task("[cyan]Procesando segmentos...", total=total_segments)
                
                for i, segment in enumerate(timeline):
                    speaker_id = segment["speaker_id"]
                    start_time = segment["start_time"]
                    end_time = segment["end_time"]
                    duration = end_time - start_time
                    
                    # Validar duración del segmento
                    if duration <= 0:
                        if log_progress:
                            console.log(f"[yellow]Advertencia: Segmento {i} tiene duración no positiva ({duration}s), ignorando[/]")
                        segment_progress.update(segment_task, advance=1)
                        continue
                    
                    if speaker_id not in video_paths:
                        if log_progress:
                            console.log(f"[yellow]Advertencia: No hay video para speaker {speaker_id}, usando video alternativo[/]")
                        # Usar el primer video disponible como fallback
                        video_path = next(iter(video_paths.values()))
                    else:
                        video_path = video_paths[speaker_id]
                    
                    # Verificar que el video exista
                    if not os.path.exists(video_path):
                        if log_progress:
                            console.log(f"[yellow]Advertencia: Video no encontrado: {video_path}, buscando alternativa[/]")
                        # Buscar otro video disponible
                        alternate_found = False
                        for alt_path in video_paths.values():
                            if os.path.exists(alt_path):
                                video_path = alt_path
                                alternate_found = True
                                if log_progress:
                                    console.log(f"[green]Video alternativo encontrado: {alt_path}[/]")
                                break
                        
                        if not alternate_found:
                            if log_progress:
                                console.log(f"[bold red]Error: No hay videos disponibles para el segmento {i}[/]")
                            segment_progress.update(segment_task, advance=1)
                            continue
                    
                    segment_output = os.path.join(temp_dir, f"segment_{i:04d}.mp4")
                    
                    try:
                        # Cortar segmento de video
                        cmd = [
                            "ffmpeg",
                            "-ss", str(start_time),
                            "-i", video_path,
                            "-t", str(duration),
                            *video_params,
                            "-an",  # sin audio, se añadirá después
                            "-y",
                            segment_output
                        ]
                        
                        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                        
                        # Verificar que el segmento se creó correctamente
                        if os.path.exists(segment_output) and os.path.getsize(segment_output) > 0:
                            segments.append(segment_output)
                        else:
                            if log_progress:
                                console.log(f"[yellow]Advertencia: Segmento {i} no se generó correctamente, ignorando[/]")
                    except subprocess.CalledProcessError as e:
                        if log_progress:
                            console.log(f"[yellow]Error al procesar segmento {i}, ignorando: {e}[/]")
                            # Mostrar salida de error de ffmpeg
                            if e.stderr:
                                console.log(f"[red]FFmpeg error: {e.stderr}[/]")
                    
                    # Actualizar progreso
                    segment_progress.update(segment_task, advance=1)
        
        # Verificar que tengamos segmentos para procesar
        if not segments:
            raise ValueError("No se pudo generar ningún segmento de video válido")
        
        # Crear archivo de lista para concat
        with open(segments_list_file, "w") as f:
            for segment in segments:
                f.write(f"file '{segment}'\n")
        
        if log_progress:
            console.log(f"Concatenando {len(segments)} segmentos y añadiendo audio...")
        
        try:
            # Concatenar todos los segmentos y añadir audio
            concat_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", segments_list_file,
                "-i", audio_path,
                "-map", "0:v",
                "-map", "1:a",
                *video_params,
                *audio_params,
                "-shortest",
                "-y",
                output_path
            ]
            
            concat_result = subprocess.run(concat_cmd, check=True, capture_output=True, text=True)
            
            # Verificar que el video final se creó correctamente
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise ValueError(f"El video final no se generó correctamente: {output_path}")
        except subprocess.CalledProcessError as e:
            if log_progress:
                console.log(f"[bold red]Error al concatenar segmentos: {e}[/]")
                # Mostrar salida de error de ffmpeg
                if e.stderr:
                    console.log(f"[red]FFmpeg error: {e.stderr}[/]")
            raise
        
        if progress and task_id:
            # Completar la otra mitad del progreso
            progress.update(task_id, advance=0.5)
        
        if log_progress:
            console.log(f"[bold green]Video compuesto exitosamente: {output_path}[/]")
            
            # Obtener información del video generado
            try:
                video_info = get_video_info(output_path)
                duration_sec = float(video_info.get("format", {}).get("duration", 0))
                file_size_mb = round(float(video_info.get("format", {}).get("size", 0)) / (1024 * 1024), 2)
                
                console.log(f"Duración: {format_time(duration_sec)}")
                console.log(f"Tamaño: {file_size_mb} MB")
            except Exception as e:
                console.log(f"[yellow]No se pudo obtener información del video: {e}[/]")
            
            if preview_mode:
                console.log(f"[bold yellow]Este es un preview de {preview_duration} minutos[/]")
        
        return output_path
    
    except Exception as e:
        console.log(f"[bold red]Error al componer video: {e}[/]")
        raise
    
    finally:
        # Limpiar archivos temporales
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            console.log(f"[yellow]Advertencia: No se pudieron eliminar archivos temporales: {e}[/]")

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

def format_time(seconds: float) -> str:
    """
    Formatea un tiempo en segundos a formato HH:MM:SS
    
    Args:
        seconds: Tiempo en segundos
        
    Returns:
        Tiempo formateado
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def process_camera_changes(
    speaker_segments: List[Dict],
    video_paths: Dict[str, str],
    audio_master_path: str,
    output_path: str,
    preview_mode: bool = False,
    preview_duration: int = 5,
    min_segment_duration: float = 1.0,
    transition_type: str = "cut",
    output_quality: str = "high",
    log_progress: bool = True,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None
) -> str:
    """
    Procesa cambios de cámara y genera video final
    
    Args:
        speaker_segments: Lista de diccionarios con segmentos y speaker_id
        video_paths: Diccionario de {speaker_id: video_path}
        audio_master_path: Ruta al audio maestro
        output_path: Ruta donde guardar el video final
        preview_mode: Si procesar solo los primeros N minutos
        preview_duration: Duración en minutos del preview
        min_segment_duration: Duración mínima de un segmento en segundos
        transition_type: Tipo de transición
        output_quality: Calidad de salida
        log_progress: Si mostrar logs del progreso
        progress: Objeto Progress de rich para actualizar barra general
        task_id: ID de la tarea en el objeto Progress
        
    Returns:
        Ruta al video final
    """
    if log_progress:
        console.log("Iniciando procesamiento de cambios de cámara...")
        if preview_mode:
            console.log(f"[yellow]Modo preview activo: {preview_duration} minutos[/]")
    
    # Validaciones iniciales
    if not speaker_segments:
        raise ValueError("No se proporcionaron segmentos de speaker")
    
    if not video_paths:
        raise ValueError("No se proporcionaron rutas de video")
    
    if not os.path.exists(audio_master_path):
        raise ValueError(f"El archivo de audio maestro no existe: {audio_master_path}")
    
    # Verificar que los segmentos tengan la estructura correcta
    for i, segment in enumerate(speaker_segments):
        if not isinstance(segment, dict):
            raise ValueError(f"Segmento {i} no es un diccionario: {segment}")
        
        if "speaker_id" not in segment:
            raise ValueError(f"Segmento {i} no tiene 'speaker_id': {segment}")
        
        if "start_time" not in segment:
            raise ValueError(f"Segmento {i} no tiene 'start_time': {segment}")
        
        if "end_time" not in segment:
            raise ValueError(f"Segmento {i} no tiene 'end_time': {segment}")
        
        # Convertir a float si son strings (pueden venir así de algunos analizadores)
        if isinstance(segment["start_time"], str):
            try:
                segment["start_time"] = float(segment["start_time"])
            except ValueError:
                raise ValueError(f"No se pudo convertir 'start_time' a float en segmento {i}: {segment}")
        
        if isinstance(segment["end_time"], str):
            try:
                segment["end_time"] = float(segment["end_time"])
            except ValueError:
                raise ValueError(f"No se pudo convertir 'end_time' a float en segmento {i}: {segment}")
    
    # Ordenar segmentos por tiempo de inicio
    speaker_segments.sort(key=lambda x: x["start_time"])
    
    # Verificar y corregir solapamientos
    corrected_segments = []
    for i, segment in enumerate(speaker_segments):
        # Ignorar segmentos con duración negativa o cero
        if segment["end_time"] <= segment["start_time"]:
            if log_progress:
                console.log(f"[yellow]Advertencia: Segmento {i} con duración no positiva, ignorando: {segment}[/]")
            continue
        
        # Si es el primer segmento, añadirlo directamente
        if not corrected_segments:
            corrected_segments.append(segment.copy())
            continue
        
        # Verificar solapamiento con el segmento anterior
        prev_segment = corrected_segments[-1]
        if segment["start_time"] < prev_segment["end_time"]:
            # Si es el mismo speaker, extender el segmento anterior
            if segment["speaker_id"] == prev_segment["speaker_id"]:
                prev_segment["end_time"] = max(prev_segment["end_time"], segment["end_time"])
            else:
                # Si son speakers diferentes, usar punto medio o preferir el nuevo
                midpoint = (segment["start_time"] + prev_segment["end_time"]) / 2
                prev_segment["end_time"] = midpoint
                segment_copy = segment.copy()
                segment_copy["start_time"] = midpoint
                corrected_segments.append(segment_copy)
        else:
            # No hay solapamiento, añadir normalmente
            corrected_segments.append(segment.copy())
    
    if log_progress:
        if len(corrected_segments) != len(speaker_segments):
            console.log(f"[yellow]Se corrigieron solapamientos: {len(speaker_segments)} -> {len(corrected_segments)} segmentos[/]")
    
    # Usar los segmentos corregidos
    speaker_segments = corrected_segments
    
    # Si no hay segmentos después de correcciones, mostrar error
    if not speaker_segments:
        raise ValueError("No hay segmentos válidos después de corregir solapamientos y duraciones negativas")
    
    # Filtrar segmentos muy cortos
    filtered_segments = []
    current_segment = None
    
    for segment in speaker_segments:
        if current_segment is None:
            current_segment = segment.copy()
        elif segment["speaker_id"] == current_segment["speaker_id"]:
            # Extender segmento actual
            current_segment["end_time"] = segment["end_time"]
        elif (segment["end_time"] - current_segment["start_time"]) < min_segment_duration:
            # Segmento demasiado corto, mantener speaker actual
            current_segment["end_time"] = segment["end_time"]
        else:
            # Añadir segmento actual y empezar nuevo
            filtered_segments.append(current_segment)
            current_segment = segment.copy()
    
    # Añadir último segmento
    if current_segment:
        filtered_segments.append(current_segment)
    
    if log_progress:
        original_count = len(speaker_segments)
        filtered_count = len(filtered_segments)
        console.log(f"Segmentos originales: {original_count}, después de filtrar segmentos cortos: {filtered_count}")
    
    # En modo preview, asegurarse de que solo procesamos los segmentos dentro de la duración del preview
    if preview_mode:
        max_time = preview_duration * 60  # convertir a segundos
        preview_segments = [seg for seg in filtered_segments if seg["start_time"] < max_time]
        
        # Ajustar el último segmento si sobrepasa la duración del preview
        if preview_segments and preview_segments[-1]["end_time"] > max_time:
            preview_segments[-1]["end_time"] = max_time
            
        filtered_segments = preview_segments
        
        if log_progress:
            console.log(f"Segmentos limitados para preview: {len(filtered_segments)} segmentos dentro de {preview_duration} minutos")
    
    # Si no hay segmentos después de filtrar, crear un segmento por defecto
    if not filtered_segments:
        if log_progress:
            console.log("[yellow]Advertencia: No hay segmentos después de filtrar, creando segmento por defecto[/]")
        
        # Usar el primer speaker disponible
        default_speaker_id = next(iter(video_paths.keys())) if video_paths else "speaker1"
        
        # Duración predeterminada
        max_duration = preview_duration * 60 if preview_mode else 60  # 1 minuto por defecto si no es preview
        
        filtered_segments = [{
            "speaker_id": default_speaker_id,
            "start_time": 0.0,
            "end_time": float(max_duration)
        }]
    
    # Ajustar nombre de archivo para preview
    if preview_mode:
        base, ext = os.path.splitext(output_path)
        if not ext:
            # Si no hay extensión, añadir .mp4 por defecto
            ext = ".mp4"
        output_path = f"{base}_preview{ext}"
        
        # Verificar que el nombre del archivo no comience con un punto (archivos ocultos en macOS)
        output_filename = os.path.basename(output_path)
        if output_filename.startswith("."):
            # Sustituir el nombre por un valor predeterminado
            output_dir = os.path.dirname(output_path)
            output_path = os.path.join(output_dir, f"preview_video{ext}")
    
    # Usar el objeto Progress proporcionado o crear uno nuevo si no se proporciona
    if progress is not None and task_id is not None:
        # Actualizar el progreso existente
        progress.update(task_id, description="[green]Generando video final...")
        
        # Crear video con progress existente
        output_path = compose_video_from_timeline(
            timeline=filtered_segments,
            video_paths=video_paths,
            audio_path=audio_master_path,
            output_path=output_path,
            preview_mode=preview_mode,
            preview_duration=preview_duration,
            transition_type=transition_type,
            output_quality=output_quality,
            progress=progress,
            task_id=task_id,
            log_progress=log_progress
        )
        
        # Actualizar al completar
        progress.update(task_id, completed=100, description="[green]Video generado exitosamente")
    else:
        # Crear una nueva barra de progreso si no se proporciona una
        with Progress() as new_progress:
            new_task = new_progress.add_task("[green]Generando video final...", total=1.0)
            
            output_path = compose_video_from_timeline(
                timeline=filtered_segments,
                video_paths=video_paths,
                audio_path=audio_master_path,
                output_path=output_path,
                preview_mode=preview_mode,
                preview_duration=preview_duration,
                transition_type=transition_type,
                output_quality=output_quality,
                progress=new_progress,
                task_id=new_task,
                log_progress=log_progress
            )
    
    return output_path 