"""
Módulo para sincronización de pistas de audio y creación de fingerprints.
Implementa funciones para encontrar el offset entre pistas de audio y video.
"""

import os
import logging
import numpy as np
from typing import Tuple, Dict, Optional, Any, List
import librosa
from scipy import signal
from rich.progress import Progress
from pathlib import Path

from src.audio.analyzer import load_audio

logger = logging.getLogger(__name__)

def create_audio_fingerprint(
    audio_path: str, 
    sr: Optional[int] = None,
    n_fft: int = 2048,
    hop_length: int = 512,
    n_mels: int = 128,
    progress: Optional[Progress] = None
) -> np.ndarray:
    """
    Crea una huella digital (fingerprint) de un archivo de audio.
    Utiliza MFCCs (Mel-Frequency Cepstral Coefficients) para la representación.
    
    Args:
        audio_path: Ruta al archivo de audio
        sr: Frecuencia de muestreo (si None, se usa la del archivo)
        n_fft: Tamaño de la ventana FFT
        hop_length: Tamaño del salto entre ventanas
        n_mels: Número de bandas mel
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Array numpy con la huella digital del audio
    """
    if progress:
        task = progress.add_task(f"[cyan]Creando fingerprint: {Path(audio_path).name}", total=100)
        progress.update(task, advance=10)
        
    try:
        # Cargar audio como mono
        y, sr = load_audio(audio_path, mono=True)
        
        if progress:
            progress.update(task, advance=30, description=f"[cyan]Calculando características: {Path(audio_path).name}")
        
        # Calcular mel-spectrograma
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=n_fft, 
                                          hop_length=hop_length, n_mels=n_mels)
        
        # Convertir a decibelios
        log_S = librosa.power_to_db(S, ref=np.max)
        
        # Calcular MFCCs
        mfcc = librosa.feature.mfcc(S=log_S, n_mfcc=20)
        
        # Delta y delta-delta para capturar dinámica
        mfcc_delta = librosa.feature.delta(mfcc)
        mfcc_delta2 = librosa.feature.delta(mfcc, order=2)
        
        # Combinar características
        fingerprint = np.vstack([mfcc, mfcc_delta, mfcc_delta2])
        
        if progress:
            progress.update(task, completed=100, description=f"[green]Fingerprint completado: {Path(audio_path).name}")
            
        return fingerprint
        
    except Exception as e:
        logger.error(f"Error al crear fingerprint para {audio_path}: {str(e)}")
        if progress:
            progress.update(task, completed=100, description=f"[red]Error en fingerprint: {Path(audio_path).name}")
        raise

def find_offset_between_audios(
    reference_audio: str,
    target_audio: str,
    max_offset_seconds: float = 60.0,
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Encuentra el offset entre dos archivos de audio usando correlación cruzada.
    
    Args:
        reference_audio: Ruta al archivo de audio de referencia
        target_audio: Ruta al archivo de audio a sincronizar
        max_offset_seconds: Máximo offset a buscar (en segundos)
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con información del offset encontrado
    """
    if progress:
        task = progress.add_task("[cyan]Calculando offset entre audios...", total=100)
        progress.update(task, advance=10)
    
    try:
        # Cargar audios
        logger.info(f"Calculando offset entre {reference_audio} y {target_audio}")
        
        if progress:
            progress.update(task, advance=10, description="[cyan]Cargando audios...")
            
        y_ref, sr_ref = load_audio(reference_audio, mono=True)
        y_target, sr_target = load_audio(target_audio, mono=True)
        
        # Asegurar que ambos tienen el mismo sample rate
        if sr_ref != sr_target:
            logger.info(f"Resampleando audio target de {sr_target}Hz a {sr_ref}Hz")
            y_target = librosa.resample(y_target, orig_sr=sr_target, target_sr=sr_ref)
            sr_target = sr_ref
        
        if progress:
            progress.update(task, advance=20, description="[cyan]Calculando correlación...")
        
        # Calcular máximo offset en muestras
        max_offset_samples = int(max_offset_seconds * sr_ref)
        
        # Recortar si es necesario para correlación eficiente
        y_ref_segment = y_ref[:min(len(y_ref), 30 * sr_ref)]  # 30 segundos máximo
        y_target_segment = y_target[:min(len(y_target), 30 * sr_ref + max_offset_samples)]
        
        # Calcular correlación cruzada
        correlation = signal.correlate(y_target_segment, y_ref_segment, mode='valid', method='fft')
        
        # Encontrar el índice del máximo de correlación
        max_corr_idx = np.argmax(correlation)
        
        # Convertir a segundos
        offset_seconds = max_corr_idx / sr_ref
        
        if progress:
            progress.update(task, advance=40, description="[cyan]Verificando calidad del offset...")
        
        # Calcular score de confianza (correlación normalizada)
        max_corr_value = correlation[max_corr_idx]
        # Normalizar por la energía de las señales
        ref_energy = np.sqrt(np.sum(y_ref_segment**2))
        target_energy = np.sqrt(np.sum(y_target_segment**2))
        confidence_score = max_corr_value / (ref_energy * target_energy)
        
        result = {
            "offset_seconds": float(offset_seconds),
            "offset_samples": int(max_corr_idx),
            "confidence_score": float(confidence_score),
            "sample_rate": sr_ref,
            "reference_audio": reference_audio,
            "target_audio": target_audio
        }
        
        logger.info(f"Offset encontrado: {offset_seconds:.3f} segundos (confianza: {confidence_score:.4f})")
        
        if progress:
            progress.update(task, completed=100, description=f"[green]Offset encontrado: {offset_seconds:.3f}s")
            
        return result
        
    except Exception as e:
        logger.error(f"Error al calcular offset: {str(e)}")
        if progress:
            progress.update(task, completed=100, description="[red]Error al calcular offset")
        raise

def compare_fingerprints(
    fingerprint1: np.ndarray,
    fingerprint2: np.ndarray,
    max_offset: int = 100
) -> Dict[str, Any]:
    """
    Compara dos fingerprints de audio para encontrar el mejor match.
    
    Args:
        fingerprint1: Primer fingerprint
        fingerprint2: Segundo fingerprint
        max_offset: Máximo offset a buscar (en frames)
        
    Returns:
        Diccionario con información del match
    """
    try:
        # Asegurar que ambos fingerprints tengan la misma forma en la dimensión de características
        if fingerprint1.shape[0] != fingerprint2.shape[0]:
            raise ValueError("Los fingerprints deben tener el mismo número de características")
        
        # Calcular distancias DTW (Dynamic Time Warping) entre fingerprints
        # Esto es computacionalmente costoso pero preciso para audio
        distance, path = librosa.sequence.dtw(fingerprint1, fingerprint2, 
                                             subseq=True, metric='cosine')
        
        # El inicio y fin del mejor path nos da el match
        start_idx = path[0][0]
        end_idx = path[-1][0]
        
        # Calcular score (menor distancia = mejor match)
        match_score = 1.0 / (1.0 + distance[-1, -1])
        
        return {
            "start_frame": int(start_idx),
            "end_frame": int(end_idx),
            "match_score": float(match_score),
            "path": path
        }
        
    except Exception as e:
        logger.error(f"Error al comparar fingerprints: {str(e)}")
        raise

def calculate_drift(
    reference_audio: str,
    target_audio: str,
    initial_offset_seconds: float,
    window_size_seconds: float = 30.0,
    step_size_seconds: float = 15.0,
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Calcula el drift entre dos audios a lo largo del tiempo.
    
    Args:
        reference_audio: Ruta al archivo de audio de referencia
        target_audio: Ruta al archivo de audio a sincronizar
        initial_offset_seconds: Offset inicial entre los audios
        window_size_seconds: Tamaño de la ventana de análisis
        step_size_seconds: Salto entre ventanas consecutivas
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con información del drift
    """
    if progress:
        task = progress.add_task("[cyan]Calculando drift temporal...", total=100)
        progress.update(task, advance=10)
    
    try:
        # Cargar audios
        logger.info(f"Calculando drift entre {reference_audio} y {target_audio}")
        
        y_ref, sr_ref = load_audio(reference_audio, mono=True)
        y_target, sr_target = load_audio(target_audio, mono=True)
        
        # Asegurar mismo sample rate
        if sr_ref != sr_target:
            y_target = librosa.resample(y_target, orig_sr=sr_target, target_sr=sr_ref)
            sr_target = sr_ref
            
        # Convertir parámetros de tiempo a muestras
        window_samples = int(window_size_seconds * sr_ref)
        step_samples = int(step_size_seconds * sr_ref)
        initial_offset_samples = int(initial_offset_seconds * sr_ref)
        
        # Aplicar offset inicial al audio target
        y_target_shifted = y_target[initial_offset_samples:] if initial_offset_samples > 0 else y_target
        
        # Determinar el número de ventanas
        min_length = min(len(y_ref), len(y_target_shifted))
        num_windows = max(1, (min_length - window_samples) // step_samples)
        
        if progress:
            progress.update(task, advance=10, 
                          description=f"[cyan]Analizando {num_windows} ventanas temporales...")
        
        # Lista para almacenar offsets por ventana
        offsets = []
        timestamps = []
        
        # Analizar cada ventana
        for i in range(num_windows):
            if progress and i % max(1, num_windows // 10) == 0:
                progress.update(task, advance=5, 
                              description=f"[cyan]Ventana {i+1}/{num_windows}...")
            
            # Índices de inicio y fin para esta ventana
            start_idx = i * step_samples
            end_idx = start_idx + window_samples
            
            # Extraer segmentos
            y_ref_segment = y_ref[start_idx:end_idx]
            y_target_segment = y_target_shifted[start_idx:end_idx]
            
            # Calcular correlación cruzada para este segmento
            # Limitar búsqueda a 1 segundo en cada dirección para eficiencia
            max_lag_samples = int(1.0 * sr_ref)
            
            # Calcular correlación
            correlation = signal.correlate(
                y_target_segment, 
                y_ref_segment, 
                mode='same', 
                method='fft'
            )
            
            # Encontrar el índice del máximo de correlación
            center_idx = len(correlation) // 2
            max_corr_idx = np.argmax(correlation[center_idx - max_lag_samples:center_idx + max_lag_samples])
            max_corr_idx = max_corr_idx + center_idx - max_lag_samples
            
            # Calcular offset en muestras (diferencia desde el centro)
            local_offset_samples = max_corr_idx - center_idx
            local_offset_seconds = local_offset_samples / sr_ref
            
            # Almacenar resultados
            timestamp = start_idx / sr_ref
            offsets.append(local_offset_seconds)
            timestamps.append(timestamp)
        
        if progress:
            progress.update(task, advance=15, description="[cyan]Analizando tendencia de drift...")
        
        # Analizar tendencia del drift
        if len(offsets) > 1:
            # Ajustar una línea recta a los offsets para ver la tendencia
            timestamps_array = np.array(timestamps)
            offsets_array = np.array(offsets)
            
            # Usar regresión lineal para estimar tendencia
            if len(timestamps_array) > 1:
                slope, intercept = np.polyfit(timestamps_array, offsets_array, 1)
                drift_rate = slope  # segundos de drift por segundo de audio
            else:
                slope, intercept, drift_rate = 0, offsets_array[0], 0
        else:
            slope, intercept, drift_rate = 0, offsets[0] if offsets else 0, 0
        
        # Crear resultado
        result = {
            "reference_audio": reference_audio,
            "target_audio": target_audio,
            "initial_offset": initial_offset_seconds,
            "timestamps": timestamps,
            "offsets": offsets,
            "drift_rate": float(drift_rate),
            "drift_intercept": float(intercept),
            "drift_slope": float(slope),
            "num_windows": num_windows
        }
        
        logger.info(f"Drift calculado: {drift_rate:.6f} seg/seg (tasa), {num_windows} ventanas")
        
        if progress:
            progress.update(task, completed=100, 
                          description=f"[green]Drift calculado: {drift_rate:.6f} seg/seg")
        
        return result
        
    except Exception as e:
        logger.error(f"Error al calcular drift: {str(e)}")
        if progress:
            progress.update(task, completed=100, description="[red]Error al calcular drift")
        raise

def create_sync_timeline(
    reference_audio: str,
    target_audio: str,
    initial_offset: float,
    drift_rate: float = 0.0,
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Crea un timeline sincronizado entre dos archivos de audio.
    
    Args:
        reference_audio: Ruta al archivo de audio de referencia
        target_audio: Ruta al archivo de audio a sincronizar
        initial_offset: Offset inicial entre los audios (segundos)
        drift_rate: Tasa de drift (segundos/segundo)
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con información del timeline
    """
    if progress:
        task = progress.add_task("[cyan]Creando timeline sincronizado...", total=100)
        progress.update(task, advance=20)
    
    try:
        # Cargar información básica de los audios
        y_ref, sr_ref = load_audio(reference_audio, mono=True, normalize=False)
        y_target, sr_target = load_audio(target_audio, mono=True, normalize=False)
        
        # Duración de los audios
        ref_duration = len(y_ref) / sr_ref
        target_duration = len(y_target) / sr_target
        
        if progress:
            progress.update(task, advance=20, 
                          description=f"[cyan]Generando puntos de sincronización...")
        
        # Crear puntos de sincronización cada 10 segundos
        sync_interval = 10.0  # segundos
        sync_points = []
        
        current_time = 0.0
        while current_time < ref_duration:
            # Calcular offset en este punto, considerando drift
            point_offset = initial_offset + (drift_rate * current_time)
            
            # Tiempo correspondiente en el target
            target_time = current_time + point_offset
            
            # Solo incluir si está dentro de los límites del target
            if 0 <= target_time < target_duration:
                sync_points.append({
                    "reference_time": current_time,
                    "target_time": target_time,
                    "offset": point_offset
                })
            
            current_time += sync_interval
        
        # Crear resultado
        result = {
            "reference_audio": reference_audio,
            "target_audio": target_audio,
            "initial_offset": initial_offset,
            "drift_rate": drift_rate,
            "reference_duration": ref_duration,
            "target_duration": target_duration,
            "sync_points": sync_points,
            "num_sync_points": len(sync_points)
        }
        
        logger.info(f"Timeline creado: {len(sync_points)} puntos de sincronización")
        
        if progress:
            progress.update(task, completed=100, 
                          description=f"[green]Timeline creado: {len(sync_points)} puntos")
        
        return result
        
    except Exception as e:
        logger.error(f"Error al crear timeline: {str(e)}")
        if progress:
            progress.update(task, completed=100, description="[red]Error al crear timeline")
        raise

def sync_audio_with_windows(
    reference_audio: str,
    target_audio: str,
    window_size_seconds: float = 30.0,
    overlap_seconds: float = 5.0,
    max_offset_seconds: float = 2.0,
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Sincroniza dos audios utilizando ventanas deslizantes para corregir desfases puntuales.
    
    Args:
        reference_audio: Ruta al archivo de audio de referencia
        target_audio: Ruta al archivo de audio a sincronizar
        window_size_seconds: Tamaño de la ventana de análisis
        overlap_seconds: Superposición entre ventanas consecutivas
        max_offset_seconds: Máximo offset a buscar en cada ventana
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con información de la sincronización
    """
    if progress:
        task = progress.add_task("[cyan]Sincronizando con ventanas deslizantes...", total=100)
        progress.update(task, advance=10)
    
    try:
        # Cargar audios
        logger.info(f"Sincronizando con ventanas: {reference_audio} y {target_audio}")
        
        y_ref, sr_ref = load_audio(reference_audio, mono=True)
        y_target, sr_target = load_audio(target_audio, mono=True)
        
        # Asegurar mismo sample rate
        if sr_ref != sr_target:
            y_target = librosa.resample(y_target, orig_sr=sr_target, target_sr=sr_ref)
            sr_target = sr_ref
        
        # Convertir parámetros de tiempo a muestras
        window_samples = int(window_size_seconds * sr_ref)
        overlap_samples = int(overlap_seconds * sr_ref)
        step_samples = window_samples - overlap_samples
        max_offset_samples = int(max_offset_seconds * sr_ref)
        
        # Calcular número de ventanas
        ref_length = len(y_ref)
        num_windows = max(1, (ref_length - overlap_samples) // step_samples)
        
        if progress:
            progress.update(task, advance=10, 
                          description=f"[cyan]Procesando {num_windows} ventanas...")
        
        # Lista para almacenar offsets por ventana
        window_offsets = []
        window_positions = []
        
        # Procesar cada ventana
        for i in range(num_windows):
            if progress and i % max(1, num_windows // 10) == 0:
                progress.update(task, advance=5, 
                              description=f"[cyan]Ventana {i+1}/{num_windows}...")
            
            # Índices de esta ventana en el audio de referencia
            start_idx = i * step_samples
            end_idx = min(start_idx + window_samples, ref_length)
            
            # Extraer segmento de referencia
            y_ref_segment = y_ref[start_idx:end_idx]
            
            # Verificar que el segmento de referencia no esté vacío
            if len(y_ref_segment) < window_samples * 0.5:  # Al menos 50% de la ventana
                continue
            
            # Rango de búsqueda en el target (considerando posible offset)
            target_start = max(0, start_idx - max_offset_samples)
            target_end = min(len(y_target), end_idx + max_offset_samples)
            
            # Extraer segmento target ampliado para búsqueda
            y_target_segment = y_target[target_start:target_end]
            
            # Verificar que el segmento target no esté vacío y sea suficientemente grande
            if len(y_target_segment) <= len(y_ref_segment):
                continue
            
            # Calcular correlación cruzada
            try:
                correlation = signal.correlate(y_target_segment, y_ref_segment, mode='valid', method='fft')
                
                # Verificar que la correlación no esté vacía
                if len(correlation) == 0:
                    continue
                
                # Encontrar el mejor match
                max_corr_idx = np.argmax(correlation)
                
                # Calcular offset real en muestras
                offset_samples = target_start + max_corr_idx - start_idx
                offset_seconds = offset_samples / sr_ref
                
                # Almacenar resultados
                window_offsets.append(offset_seconds)
                window_positions.append(start_idx / sr_ref)
            except Exception as e:
                logger.warning(f"Error en ventana {i}: {str(e)}")
                continue
        
        if progress:
            progress.update(task, advance=15, description="[cyan]Generando mapa de sincronización...")
        
        # Verificar que se encontraron puntos de sincronización
        if not window_offsets or not window_positions:
            logger.warning("No se encontraron puntos de sincronización válidos")
            return {
                "reference_audio": reference_audio,
                "target_audio": target_audio,
                "window_size": window_size_seconds,
                "overlap": overlap_seconds,
                "num_windows": 0,
                "sync_map": [],
                "average_offset": 0.0,
                "std_offset": 0.0,
                "window_positions": [],
                "window_offsets": []
            }
        
        # Crear mapa de sincronización
        sync_map = []
        for i, (position, offset) in enumerate(zip(window_positions, window_offsets)):
            sync_map.append({
                "reference_time": position,
                "offset": offset,
                "target_time": position + offset,
                "window_index": i
            })
        
        # Calcular estadísticas
        avg_offset = np.mean(window_offsets) if window_offsets else 0
        std_offset = np.std(window_offsets) if len(window_offsets) > 1 else 0
        
        result = {
            "reference_audio": reference_audio,
            "target_audio": target_audio,
            "window_size": window_size_seconds,
            "overlap": overlap_seconds,
            "num_windows": len(window_offsets),  # Número real de ventanas procesadas
            "sync_map": sync_map,
            "average_offset": float(avg_offset),
            "std_offset": float(std_offset),
            "window_positions": window_positions,
            "window_offsets": window_offsets
        }
        
        logger.info(f"Sincronización con ventanas completada: {len(sync_map)} ventanas, offset promedio {avg_offset:.3f}s")
        
        if progress:
            progress.update(task, completed=100, 
                          description=f"[green]Sincronización completada: offset promedio {avg_offset:.3f}s")
        
        return result
        
    except Exception as e:
        logger.error(f"Error en sincronización con ventanas: {str(e)}")
        if progress:
            progress.update(task, completed=100, description="[red]Error en sincronización")
        raise

def correct_offset_puntuales(
    sync_map: List[Dict[str, float]],
    smoothing_window: int = 3
) -> List[Dict[str, float]]:
    """
    Corrige desfases puntuales en un mapa de sincronización aplicando suavizado.
    
    Args:
        sync_map: Lista de puntos de sincronización con offsets
        smoothing_window: Tamaño de la ventana para suavizado
        
    Returns:
        Lista de puntos de sincronización corregidos
    """
    try:
        # Verificar que el mapa no esté vacío
        if not sync_map or len(sync_map) < 2:
            logger.warning("Mapa de sincronización vacío o demasiado pequeño para corregir")
            return sync_map
        
        # Extraer offsets y tiempos
        offsets = [point.get("offset", 0.0) for point in sync_map]
        times = [point.get("reference_time", 0.0) for point in sync_map]
        
        # Verificar que hay datos suficientes para el suavizado
        if len(offsets) < smoothing_window:
            logger.warning(f"No hay suficientes puntos para usar ventana de suavizado {smoothing_window}, reduciendo tamaño")
            smoothing_window = max(1, len(offsets) - 1)
        
        # Detectar outliers (desfases puntuales)
        # Usar diferencia con promedio local
        smoothed_offsets = offsets.copy()
        
        for i in range(len(offsets)):
            # Definir ventana local
            start_idx = max(0, i - smoothing_window // 2)
            end_idx = min(len(offsets), i + smoothing_window // 2 + 1)
            
            # Calcular promedio local excluyendo el punto actual
            local_offsets = offsets[start_idx:i] + offsets[i+1:end_idx]
            if local_offsets:
                local_avg = sum(local_offsets) / len(local_offsets)
                
                # Si la diferencia es grande, suavizar
                if abs(offsets[i] - local_avg) > 0.1:  # 100ms de umbral
                    smoothed_offsets[i] = local_avg
        
        # Crear nuevo mapa de sincronización
        corrected_map = []
        for i, point in enumerate(sync_map):
            corrected_point = point.copy()
            corrected_point["offset"] = smoothed_offsets[i]
            corrected_point["target_time"] = point.get("reference_time", 0.0) + smoothed_offsets[i]
            corrected_point["is_corrected"] = smoothed_offsets[i] != offsets[i]
            corrected_map.append(corrected_point)
        
        # Contar correcciones
        num_corrected = sum(1 for point in corrected_map if point.get("is_corrected", False))
        logger.info(f"Corrección de desfases puntuales: {num_corrected} puntos corregidos de {len(corrected_map)}")
        
        return corrected_map
        
    except Exception as e:
        logger.error(f"Error al corregir desfases puntuales: {str(e)}")
        # En caso de error, devolver el mapa original sin cambios
        return sync_map

def generate_final_sync_timeline(
    reference_audio: str,
    target_audio: str,
    initial_sync_result: Dict[str, Any],
    drift_result: Dict[str, Any] = None,
    window_sync_result: Dict[str, Any] = None,
    sync_interval: float = 1.0,
    progress: Optional[Progress] = None
) -> Dict[str, Any]:
    """
    Genera un timeline final sincronizado combinando offset inicial, drift y ventanas.
    
    Args:
        reference_audio: Ruta al archivo de audio de referencia
        target_audio: Ruta al archivo de audio a sincronizar
        initial_sync_result: Resultado de la sincronización inicial
        drift_result: Resultado del cálculo de drift (opcional)
        window_sync_result: Resultado de la sincronización por ventanas (opcional)
        sync_interval: Intervalo entre puntos de sincronización (segundos)
        progress: Objeto Progress para mostrar progreso
        
    Returns:
        Diccionario con timeline final sincronizado
    """
    if progress:
        task = progress.add_task("[cyan]Generando timeline final...", total=100)
        progress.update(task, advance=10)
    
    try:
        # Obtener información básica de los audios
        y_ref, sr_ref = load_audio(reference_audio, mono=True, normalize=False)
        reference_duration = len(y_ref) / sr_ref
        
        if progress:
            progress.update(task, advance=20, description="[cyan]Combinando resultados de sincronización...")
        
        # Verificar y obtener offset inicial
        if not initial_sync_result or "offset_seconds" not in initial_sync_result:
            logger.warning("No hay resultado de sincronización inicial válido, usando offset 0")
            initial_offset = 0.0
        else:
            initial_offset = initial_sync_result.get("offset_seconds", 0.0)
        
        # Obtener tasa de drift si está disponible
        drift_rate = 0.0
        if drift_result and "drift_rate" in drift_result:
            drift_rate = drift_result.get("drift_rate", 0.0)
            logger.info(f"Usando drift rate de {drift_rate:.6f} seg/seg")
        else:
            logger.info("No hay información de drift, asumiendo drift rate 0")
        
        # Crear timeline base con puntos a intervalos regulares
        timeline = []
        current_time = 0.0
        
        # Verificar que window_sync_result sea válido
        has_valid_window_sync = (
            window_sync_result and 
            "sync_map" in window_sync_result and 
            window_sync_result["sync_map"]
        )
        
        if has_valid_window_sync:
            logger.info(f"Usando {len(window_sync_result['sync_map'])} puntos de sincronización fina")
        else:
            logger.info("No hay puntos de sincronización fina disponibles")
        
        # Construir el timeline
        while current_time <= reference_duration:
            # Calcular offset base (inicial + drift)
            base_offset = initial_offset + (drift_rate * current_time)
            
            # Buscar si hay corrección de ventana deslizante en este punto
            window_correction = 0.0
            if has_valid_window_sync:
                try:
                    # Encontrar el punto de sincronización más cercano
                    sync_map = window_sync_result["sync_map"]
                    
                    # Convertir a arrays para cálculos vectorizados
                    window_times = np.array([point.get("reference_time", 0.0) for point in sync_map])
                    window_offsets = np.array([point.get("offset", 0.0) for point in sync_map])
                    
                    if len(window_times) > 0:
                        # Encontrar índice del tiempo más cercano
                        idx = np.argmin(np.abs(window_times - current_time))
                        
                        # Si está suficientemente cerca, usar esa corrección
                        if abs(window_times[idx] - current_time) < 5.0:  # 5 segundos de umbral
                            window_correction = window_offsets[idx] - base_offset
                except Exception as e:
                    logger.warning(f"Error al aplicar corrección de ventana: {str(e)}")
            
            # Offset final combinado
            final_offset = base_offset + window_correction
            
            # Añadir punto al timeline
            timeline.append({
                "reference_time": current_time,
                "target_time": current_time + final_offset,
                "offset": final_offset,
                "base_offset": base_offset,
                "window_correction": window_correction
            })
            
            current_time += sync_interval
        
        # Resultados
        result = {
            "reference_audio": reference_audio,
            "target_audio": target_audio,
            "reference_duration": reference_duration,
            "initial_offset": initial_offset,
            "drift_rate": drift_rate,
            "timeline": timeline,
            "num_points": len(timeline),
            "sync_interval": sync_interval
        }
        
        logger.info(f"Timeline final generado: {len(timeline)} puntos, intervalo {sync_interval}s")
        
        if progress:
            progress.update(task, completed=100, 
                          description=f"[green]Timeline final: {len(timeline)} puntos")
        
        return result
        
    except Exception as e:
        logger.error(f"Error al generar timeline final: {str(e)}")
        if progress:
            progress.update(task, completed=100, description="[red]Error al generar timeline")
        raise 