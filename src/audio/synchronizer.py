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
        
        if progress:
            progress.update(task, advance=10, description="[cyan]Analizando ventanas temporales...")
        
        # Convertir a muestras
        window_size_samples = int(window_size_seconds * sr_ref)
        step_size_samples = int(step_size_seconds * sr_ref)
        initial_offset_samples = int(initial_offset_seconds * sr_ref)
        
        # Calcular número de ventanas
        target_duration_samples = len(y_target)
        ref_duration_samples = len(y_ref)
        max_common_duration = min(target_duration_samples, ref_duration_samples + initial_offset_samples) - initial_offset_samples
        
        if max_common_duration <= 0:
            raise ValueError("No hay solapamiento entre los audios después del offset inicial")
        
        num_windows = max(1, int((max_common_duration - window_size_samples) / step_size_samples) + 1)
        
        # Lista para almacenar offsets por ventana
        window_offsets = []
        time_points = []
        
        # Procesar cada ventana
        for i in range(num_windows):
            if progress:
                progress.update(task, advance=50 / num_windows, 
                              description=f"[cyan]Analizando ventana {i+1}/{num_windows}...")
            
            # Calcular posición de inicio para cada ventana
            start_ref = i * step_size_samples
            start_target = i * step_size_samples + initial_offset_samples
            
            # Asegurar que no nos pasamos del límite
            if start_ref + window_size_samples > len(y_ref) or start_target + window_size_samples > len(y_target):
                break
            
            # Extraer ventanas
            window_ref = y_ref[start_ref:start_ref + window_size_samples]
            window_target = y_target[start_target:start_target + window_size_samples]
            
            # Calcular correlación para esta ventana
            correlation = signal.correlate(window_target, window_ref, mode='same', method='fft')
            max_corr_idx = np.argmax(correlation) - len(window_ref) // 2
            
            # Convertir a segundos
            window_offset = max_corr_idx / sr_ref
            time_point = (start_ref + window_size_samples/2) / sr_ref  # Punto medio de la ventana
            
            window_offsets.append(window_offset)
            time_points.append(time_point)
        
        if progress:
            progress.update(task, advance=20, description="[cyan]Calculando estadísticas de drift...")
        
        # Calcular drift global y estadísticas
        drift_stats = {
            "initial_offset": initial_offset_seconds,
            "window_offsets": window_offsets,
            "time_points": time_points,
            "mean_drift": float(np.mean(window_offsets)),
            "max_drift": float(np.max(window_offsets)),
            "min_drift": float(np.min(window_offsets)),
            "std_drift": float(np.std(window_offsets)),
            "num_windows": len(window_offsets)
        }
        
        if progress:
            progress.update(task, completed=100, 
                          description=f"[green]Drift calculado: {drift_stats['mean_drift']:.3f}s (±{drift_stats['std_drift']:.3f}s)")
        
        return drift_stats
        
    except Exception as e:
        logger.error(f"Error al calcular drift: {str(e)}")
        if progress:
            progress.update(task, completed=100, description="[red]Error al calcular drift")
        raise 