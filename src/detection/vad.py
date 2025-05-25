"""
Módulo para detección de actividad vocal (Voice Activity Detection - VAD).
Implementa funciones para detectar segmentos de voz en pistas de audio.
"""

import os
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
import librosa
from rich.progress import Progress
from scipy import signal

from src.audio.analyzer import load_audio

logger = logging.getLogger(__name__)

def detect_voice_activity(
    audio_path: str,
    threshold: float = 0.025,
    min_silence_duration: float = 0.3,
    min_speech_duration: float = 0.25,
    window_size: float = 0.02,
    hop_length: float = 0.01,
    smooth_window: int = 5,
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Detecta segmentos de voz en un archivo de audio usando energía y características.
    
    Args:
        audio_path: Ruta al archivo de audio
        threshold: Umbral de energía para considerar voz
        min_silence_duration: Duración mínima del silencio (segundos)
        min_speech_duration: Duración mínima del habla (segundos)
        window_size: Tamaño de la ventana de análisis (segundos)
        hop_length: Salto entre ventanas (segundos)
        smooth_window: Tamaño de la ventana para suavizado
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con segmentos de voz y metadatos
    """
    if progress:
        task = progress.add_task(f"[cyan]Detectando voz en {os.path.basename(audio_path)}", total=100)
        progress.update(task, advance=10)
        
    try:
        # Cargar audio
        y, sr = load_audio(audio_path, mono=True)
        
        if progress:
            progress.update(task, advance=20, description=f"[cyan]Calculando características...")
        
        # Convertir parámetros de tiempo a muestras
        window_samples = int(window_size * sr)
        hop_samples = int(hop_length * sr)
        min_silence_samples = int(min_silence_duration * sr)
        min_speech_samples = int(min_speech_duration * sr)
        
        # Calcular energía RMS en ventanas cortas
        rms = librosa.feature.rms(y=y, frame_length=window_samples, hop_length=hop_samples)[0]
        
        # Suavizar la señal RMS para reducir falsos positivos/negativos
        if smooth_window > 0:
            # Usar convolución con una ventana para suavizar
            smooth_kernel = np.ones(smooth_window) / smooth_window
            rms = np.convolve(rms, smooth_kernel, mode='same')
        
        # Convertir a array binario (1 = voz, 0 = silencio)
        speech_frames = rms > threshold
        
        if progress:
            progress.update(task, advance=20, description=f"[cyan]Procesando segmentos...")
        
        # Convertir a segmentos (inicio, fin)
        segments = []
        in_speech = False
        speech_start = 0
        
        for i, is_speech in enumerate(speech_frames):
            # Cambio de silencio a voz
            if is_speech and not in_speech:
                in_speech = True
                speech_start = i * hop_samples
            
            # Cambio de voz a silencio
            elif not is_speech and in_speech:
                in_speech = False
                speech_end = i * hop_samples
                
                # Solo guardar si supera la duración mínima
                if speech_end - speech_start >= min_speech_samples:
                    segments.append((speech_start, speech_end))
        
        # Añadir último segmento si termina con voz
        if in_speech:
            speech_end = len(speech_frames) * hop_samples
            if speech_end - speech_start >= min_speech_samples:
                segments.append((speech_start, speech_end))
        
        # Unir segmentos cercanos (separados por menos del silencio mínimo)
        if segments:
            merged_segments = [segments[0]]
            
            for curr_start, curr_end in segments[1:]:
                prev_start, prev_end = merged_segments[-1]
                
                # Si la separación es menor que el silencio mínimo, unir
                if curr_start - prev_end < min_silence_samples:
                    # Actualizar el final del segmento anterior
                    merged_segments[-1] = (prev_start, curr_end)
                else:
                    # Añadir como nuevo segmento
                    merged_segments.append((curr_start, curr_end))
            
            segments = merged_segments
        
        # Convertir a segundos para el resultado final
        speech_segments = []
        for start, end in segments:
            speech_segments.append({
                "start": start / sr,
                "end": end / sr,
                "duration": (end - start) / sr
            })
        
        # Calcular estadísticas de voz
        total_duration = len(y) / sr
        speech_duration = sum(segment["duration"] for segment in speech_segments)
        speech_percentage = (speech_duration / total_duration) * 100 if total_duration > 0 else 0
        
        result = {
            "file": audio_path,
            "sample_rate": sr,
            "total_duration": total_duration,
            "speech_duration": speech_duration,
            "speech_percentage": speech_percentage,
            "num_segments": len(speech_segments),
            "segments": speech_segments,
            "threshold_used": threshold
        }
        
        if progress:
            progress.update(task, completed=100, 
                          description=f"[green]Voz detectada: {len(speech_segments)} segmentos ({speech_percentage:.1f}%)")
        
        logger.info(f"VAD completado para {audio_path}: {len(speech_segments)} segmentos, {speech_percentage:.1f}% de voz")
        return result
        
    except Exception as e:
        logger.error(f"Error en VAD para {audio_path}: {str(e)}")
        if progress:
            progress.update(task, completed=100, description=f"[red]Error en VAD")
        raise

def auto_threshold_vad(
    audio_path: str,
    test_thresholds: List[float] = None,
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Encuentra automáticamente el mejor umbral para VAD basado en la distribución de energía.
    
    Args:
        audio_path: Ruta al archivo de audio
        test_thresholds: Lista de umbrales a probar (opcional)
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con el mejor umbral y resultados
    """
    if progress:
        task = progress.add_task(f"[cyan]Calibrando VAD para {os.path.basename(audio_path)}", total=100)
        progress.update(task, advance=10)
    
    try:
        # Cargar audio
        y, sr = load_audio(audio_path, mono=True)
        
        if progress:
            progress.update(task, advance=20, description=f"[cyan]Analizando distribución de energía...")
        
        # Calcular RMS a lo largo del tiempo
        frame_length = int(0.025 * sr)  # 25ms
        hop_length = int(0.010 * sr)    # 10ms
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        
        # Si no se proporcionan umbrales, generarlos automáticamente
        if test_thresholds is None:
            # Analizar distribución de energía para sugerir umbrales
            # Generar 5 umbrales basados en percentiles
            rms_sorted = np.sort(rms)
            test_thresholds = [
                float(np.percentile(rms, 10)),  # Muy sensible
                float(np.percentile(rms, 20)),  # Sensible
                float(np.percentile(rms, 30)),  # Moderado
                float(np.percentile(rms, 40)),  # Menos sensible
                float(np.percentile(rms, 50))   # Poco sensible
            ]
        
        if progress:
            progress.update(task, advance=20, description=f"[cyan]Probando umbrales...")
        
        # Probar cada umbral
        results = []
        
        for i, threshold in enumerate(test_thresholds):
            if progress:
                progress.update(task, description=f"[cyan]Probando umbral {i+1}/{len(test_thresholds)}: {threshold:.5f}")
            
            # Ejecutar VAD con este umbral
            vad_result = detect_voice_activity(
                audio_path=audio_path,
                threshold=threshold,
                progress=None  # Sin progreso individual
            )
            
            # Añadir a resultados
            results.append({
                "threshold": threshold,
                "speech_percentage": vad_result["speech_percentage"],
                "num_segments": vad_result["num_segments"],
                "segments": vad_result["segments"]
            })
        
        if progress:
            progress.update(task, advance=40, description=f"[cyan]Seleccionando mejor umbral...")
        
        # Elegir el mejor umbral
        # Criterio: preferimos un porcentaje de voz razonable (30-70%) con menos segmentos fragmentados
        best_result = None
        best_score = -float('inf')
        
        for result in results:
            # Penalizar muchos segmentos pequeños y porcentaje fuera del rango ideal
            speech_pct = result["speech_percentage"]
            num_segments = result["num_segments"]
            
            # Función de puntuación que favorece 30-70% de voz y menos segmentos
            score = 0
            
            # Bonus por estar en rango ideal
            if 30 <= speech_pct <= 70:
                score += 100 - abs(50 - speech_pct)  # Máximo en 50%
            else:
                score -= abs(50 - speech_pct) * 2  # Penalización por estar fuera del rango
            
            # Penalizar muchos segmentos pequeños
            if num_segments > 0:
                avg_segment_duration = result["speech_percentage"] / num_segments
                # Favorecemos segmentos más largos (al menos 1-2 segundos en promedio)
                if avg_segment_duration < 1:
                    score -= (1 - avg_segment_duration) * 50
            
            if best_result is None or score > best_score:
                best_result = result
                best_score = score
        
        if progress:
            progress.update(task, completed=100, 
                          description=f"[green]Umbral óptimo: {best_result['threshold']:.5f}")
        
        logger.info(f"Umbral VAD óptimo para {audio_path}: {best_result['threshold']:.5f} "
                   f"({best_result['speech_percentage']:.1f}% voz, {best_result['num_segments']} segmentos)")
                   
        return {
            "file": audio_path,
            "best_threshold": best_result["threshold"],
            "best_speech_percentage": best_result["speech_percentage"],
            "best_num_segments": best_result["num_segments"],
            "all_results": results
        }
        
    except Exception as e:
        logger.error(f"Error en auto-calibración VAD para {audio_path}: {str(e)}")
        if progress:
            progress.update(task, completed=100, description=f"[red]Error en calibración VAD")
        raise

def get_voice_timestamps(
    vad_result: Dict[str, Any],
    format_type: str = "seconds"
) -> List[Dict[str, Any]]:
    """
    Extrae timestamps de voz en diferentes formatos para uso en edición.
    
    Args:
        vad_result: Resultado de la función detect_voice_activity
        format_type: Tipo de formato ('seconds', 'frames', 'timecode')
        
    Returns:
        Lista de timestamps en el formato solicitado
    """
    if "segments" not in vad_result:
        raise ValueError("El resultado VAD no contiene segmentos de voz")
    
    segments = vad_result["segments"]
    sample_rate = vad_result.get("sample_rate", 44100)
    fps = 30  # Frames por segundo para formato timecode
    
    result = []
    
    for segment in segments:
        start_sec = segment["start"]
        end_sec = segment["end"]
        
        if format_type == "seconds":
            formatted_segment = {
                "start": start_sec,
                "end": end_sec,
                "duration": end_sec - start_sec
            }
        elif format_type == "frames":
            # Convertir a frames (para edición de video)
            start_frame = int(start_sec * fps)
            end_frame = int(end_sec * fps)
            formatted_segment = {
                "start_frame": start_frame,
                "end_frame": end_frame,
                "duration_frames": end_frame - start_frame
            }
        elif format_type == "timecode":
            # Convertir a timecode HH:MM:SS.ms
            start_tc = format_timecode(start_sec)
            end_tc = format_timecode(end_sec)
            formatted_segment = {
                "start_tc": start_tc,
                "end_tc": end_tc,
                "duration_seconds": end_sec - start_sec
            }
        else:
            raise ValueError(f"Formato desconocido: {format_type}")
            
        result.append(formatted_segment)
    
    return result

def format_timecode(seconds: float) -> str:
    """
    Formatea segundos a timecode HH:MM:SS.ms.
    
    Args:
        seconds: Tiempo en segundos
        
    Returns:
        String con formato de timecode
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}" 