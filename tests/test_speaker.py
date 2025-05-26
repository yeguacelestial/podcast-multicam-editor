#!/usr/bin/env python
"""
Script de prueba para el módulo de detección de speaker activo.
Permite verificar la funcionalidad de análisis de energía, refinamiento de detección,
filtrado de cambios rápidos y generación de timeline de cámara.
"""

import os
import sys
import argparse
import json
import logging
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.progress import Progress
import numpy as np
import matplotlib.pyplot as plt

# Añadir la carpeta raíz al path para importar módulos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.detection.speaker import (
    analyze_energy_by_track,
    refine_whisper_segments,
    filter_rapid_changes,
    handle_speaker_overlap,
    generate_camera_changes,
    save_speaker_timeline
)
from src.audio.analyzer import load_audio
from src.transcription.whisper_transcriber import transcribe_audio

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('test_speaker')

def plot_energy_profiles(energy_profiles: Dict[str, Dict[str, Any]], output_path: Optional[str] = None):
    """
    Visualiza los perfiles de energía de cada pista de audio.
    
    Args:
        energy_profiles: Perfiles de energía
        output_path: Ruta donde guardar el gráfico (opcional)
    """
    plt.figure(figsize=(12, 6))
    
    for audio_path, profile in energy_profiles.items():
        times = profile["times"]
        rms = profile["rms"]
        
        # Normalizar para visualización
        rms_norm = rms / np.max(rms) if np.max(rms) > 0 else rms
        
        # Plotear energía
        plt.plot(times, rms_norm, label=os.path.basename(audio_path))
    
    plt.xlabel('Tiempo (s)')
    plt.ylabel('Energía (normalizada)')
    plt.title('Perfiles de energía por pista')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"Gráfico guardado en {output_path}")
    else:
        plt.show()

def visualize_speaker_segments(
    segments: List[Dict[str, Any]], 
    duration: float,
    output_path: Optional[str] = None
):
    """
    Visualiza los segmentos de speaker en una línea de tiempo.
    
    Args:
        segments: Lista de segmentos con speakers asignados
        duration: Duración total del audio (segundos)
        output_path: Ruta donde guardar el gráfico (opcional)
    """
    plt.figure(figsize=(15, 6))
    
    # Agrupar por speaker
    speakers = {}
    for segment in segments:
        speaker = segment["speaker"]
        if speaker not in speakers:
            speakers[speaker] = []
        
        speakers[speaker].append((segment["start"], segment["end"]))
    
    # Asignar colores a speakers
    colors = plt.cm.tab10.colors
    
    # Plotear segmentos por speaker
    for i, (speaker, time_ranges) in enumerate(speakers.items()):
        color = colors[i % len(colors)]
        
        for start, end in time_ranges:
            plt.barh(y=speaker, width=end-start, left=start, height=0.5, 
                   color=color, alpha=0.7, edgecolor='black', linewidth=0.5)
    
    plt.xlabel('Tiempo (s)')
    plt.ylabel('Speaker')
    plt.title('Segmentos de voz por speaker')
    plt.grid(True, alpha=0.3, axis='x')
    plt.xlim(0, duration)
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"Gráfico guardado en {output_path}")
    else:
        plt.show()

def visualize_camera_changes(
    camera_changes: List[Dict[str, Any]], 
    duration: float,
    output_path: Optional[str] = None
):
    """
    Visualiza los cambios de cámara en una línea de tiempo.
    
    Args:
        camera_changes: Lista de cambios de cámara
        duration: Duración total del audio (segundos)
        output_path: Ruta donde guardar el gráfico (opcional)
    """
    plt.figure(figsize=(15, 4))
    
    # Convertir a formato adecuado para visualización
    cameras = {}
    for i in range(len(camera_changes) - 1):
        camera = camera_changes[i]["camera"]
        start_time = camera_changes[i]["time"]
        end_time = camera_changes[i+1]["time"]
        
        if camera not in cameras:
            cameras[camera] = []
        
        cameras[camera].append((start_time, end_time))
    
    # Añadir el último segmento
    if camera_changes:
        last_camera = camera_changes[-1]["camera"]
        last_time = camera_changes[-1]["time"]
        
        if last_camera not in cameras:
            cameras[last_camera] = []
        
        cameras[last_camera].append((last_time, duration))
    
    # Asignar colores a cámaras
    colors = plt.cm.tab10.colors
    
    # Plotear segmentos por cámara
    for i, (camera, time_ranges) in enumerate(cameras.items()):
        color = colors[i % len(colors)]
        
        for start, end in time_ranges:
            plt.barh(y=camera, width=end-start, left=start, height=0.5, 
                   color=color, alpha=0.7, edgecolor='black', linewidth=0.5)
    
    # Añadir puntos para las transiciones
    for change in camera_changes:
        if change["transition"] == "dissolve":
            plt.plot(change["time"], change["camera"], 'o', color='red', 
                   markersize=8, alpha=0.7)
        else:
            plt.plot(change["time"], change["camera"], 's', color='black', 
                   markersize=6, alpha=0.7)
    
    plt.xlabel('Tiempo (s)')
    plt.ylabel('Cámara')
    plt.title('Timeline de cambios de cámara')
    plt.grid(True, alpha=0.3, axis='x')
    plt.xlim(0, duration)
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"Gráfico guardado en {output_path}")
    else:
        plt.show()

def main():
    parser = argparse.ArgumentParser(description='Prueba del módulo de detección de speaker activo')
    
    parser.add_argument('--audio1', required=True, help='Ruta al audio del speaker 1')
    parser.add_argument('--audio2', required=True, help='Ruta al audio del speaker 2')
    parser.add_argument('--model-size', default='base', choices=['tiny', 'base', 'small', 'medium'], 
                      help='Tamaño del modelo Whisper')
    parser.add_argument('--language', default='es', help='Idioma del audio')
    parser.add_argument('--min-duration', type=float, default=1.0, 
                      help='Duración mínima de cada plano (segundos)')
    parser.add_argument('--smoothness', default='normal', 
                      choices=['instant', 'normal', 'smooth', 'very_smooth'],
                      help='Nivel de suavidad de las transiciones')
    parser.add_argument('--output-dir', default='output', help='Directorio para guardar resultados')
    parser.add_argument('--visualize', action='store_true', help='Generar visualizaciones')
    
    args = parser.parse_args()
    
    # Crear directorio de salida si no existe
    os.makedirs(args.output_dir, exist_ok=True)
    
    console = Console()
    
    # Cargar audios para obtener duración
    y1, sr1 = load_audio(args.audio1, mono=True)
    duration1 = len(y1) / sr1
    
    y2, sr2 = load_audio(args.audio2, mono=True)
    duration2 = len(y2) / sr2
    
    total_duration = max(duration1, duration2)
    
    console.print(f"[bold green]Duración audio 1:[/] {duration1:.2f} segundos")
    console.print(f"[bold green]Duración audio 2:[/] {duration2:.2f} segundos")
    
    # Definir speaker-to-audio mapping
    speaker_to_audio_map = {
        "speaker1": args.audio1,
        "speaker2": args.audio2
    }
    
    # Paso 1: Analizar energía por pista
    with Progress() as progress:
        console.print("\n[bold]Paso 1: Analizando energía por pista[/]")
        energy_profiles = analyze_energy_by_track(
            [args.audio1, args.audio2],
            window_size=0.1,
            hop_length=0.05,
            progress=progress
        )
    
    if args.visualize:
        plot_energy_profiles(
            energy_profiles, 
            os.path.join(args.output_dir, 'energy_profiles.png')
        )
    
    # Paso 2: Transcribir audio con Whisper
    console.print("\n[bold]Paso 2: Transcribiendo audio con Whisper[/]")
    with Progress() as progress:
        # Transcribir audio con mayor volumen
        audio_path = args.audio1 if duration1 >= duration2 else args.audio2
        
        task_id = progress.add_task("[cyan]Transcribiendo audio...", total=100)
        transcription = transcribe_audio(
            audio_path,
            model_name=args.model_size,
            language=args.language,
            progress=progress,
            task_id=task_id
        )
    
    # Paso 3: Refinar segmentos con análisis de energía
    console.print("\n[bold]Paso 3: Refinando segmentos con análisis de energía[/]")
    with Progress() as progress:
        refined_segments = refine_whisper_segments(
            transcription["segments"],
            energy_profiles,
            speaker_to_audio_map,
            energy_threshold_ratio=1.5,
            progress=progress
        )
    
    # Paso 4: Filtrar cambios rápidos
    console.print("\n[bold]Paso 4: Filtrando cambios rápidos[/]")
    with Progress() as progress:
        filtered_segments = filter_rapid_changes(
            refined_segments,
            min_duration=args.min_duration,
            progress=progress
        )
    
    # Paso 5: Manejar casos de overlap
    console.print("\n[bold]Paso 5: Manejando casos de overlap[/]")
    with Progress() as progress:
        final_segments = handle_speaker_overlap(
            filtered_segments,
            energy_profiles,
            speaker_to_audio_map,
            overlap_threshold=0.5,
            energy_ratio_threshold=2.0,
            progress=progress
        )
    
    if args.visualize:
        visualize_speaker_segments(
            final_segments, 
            total_duration,
            os.path.join(args.output_dir, 'speaker_segments.png')
        )
    
    # Paso 6: Generar timeline de cámara
    console.print("\n[bold]Paso 6: Generando timeline de cámara[/]")
    with Progress() as progress:
        camera_changes = generate_camera_changes(
            final_segments,
            smoothness=args.smoothness,
            min_shot_duration=args.min_duration,
            progress=progress
        )
    
    if args.visualize:
        visualize_camera_changes(
            camera_changes, 
            total_duration,
            os.path.join(args.output_dir, 'camera_changes.png')
        )
    
    # Guardar resultados
    timeline_path = os.path.join(args.output_dir, 'speaker_timeline.json')
    save_speaker_timeline(final_segments, camera_changes, timeline_path)
    
    # Mostrar estadísticas
    total_segments = len(final_segments)
    total_camera_changes = len(camera_changes)
    speakers = set(segment["speaker"] for segment in final_segments)
    
    console.print("\n[bold green]Resultados:[/]")
    console.print(f"Total de segmentos: {total_segments}")
    console.print(f"Total de cambios de cámara: {total_camera_changes}")
    console.print(f"Speakers detectados: {', '.join(speakers)}")
    console.print(f"Timeline guardado en: {timeline_path}")
    
    if args.visualize:
        console.print("\nVisualizaciones guardadas en el directorio de salida.")

if __name__ == "__main__":
    main() 