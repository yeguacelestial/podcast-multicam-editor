#!/usr/bin/env python3
"""
Script optimizado para cambio automático de cámaras basado en detección de voz
Ultra-optimizado para MacBook Air M1 con ffmpeg
"""

import subprocess
import numpy as np
import argparse
import os
import sys
import tempfile
import json
import re

def check_dependencies():
    """Verifica que ffmpeg esté instalado"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ffmpeg no está instalado o no está en el PATH")
        print("Instala con: brew install ffmpeg")
        sys.exit(1)

def get_audio_energy_fast(video_path, segment_duration=0.5):
    """
    Obtiene la energía de audio de forma ultra-rápida usando volumedetect
    Usa segmentos más largos para mayor eficiencia
    """
    print(f"Analizando audio de {os.path.basename(video_path)}...")
    
    # Comando optimizado para análisis rápido
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-af', f'silencedetect=noise=-30dB:duration=0.1,volumedetect',
        '-f', 'null',
        '-'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parsear información de volumen y silencios
    stderr_lines = result.stderr.split('\n')
    
    # Obtener duración total
    duration = 0
    for line in stderr_lines:
        if 'Duration:' in line:
            time_match = re.search(r'Duration: ([0-9:\.]+)', line)
            if time_match:
                time_str = time_match.group(1)
                h, m, s = time_str.split(':')
                duration = int(h) * 3600 + int(m) * 60 + float(s)
                break
    
    # Obtener nivel de volumen promedio
    volume_db = -60  # Valor por defecto muy bajo
    for line in stderr_lines:
        if 'mean_volume:' in line:
            vol_match = re.search(r'mean_volume: ([-\d\.]+) dB', line)
            if vol_match:
                volume_db = float(vol_match.group(1))
                break
    
    # Detectar silencios para crear timeline básica
    silence_periods = []
    for line in stderr_lines:
        if 'silence_start:' in line:
            start_match = re.search(r'silence_start: ([\d\.]+)', line)
            if start_match:
                silence_start = float(start_match.group(1))
        elif 'silence_end:' in line:
            end_match = re.search(r'silence_end: ([\d\.]+)', line)
            if end_match:
                silence_end = float(end_match.group(1))
                silence_periods.append((silence_start, silence_end))
    
    return duration, volume_db, silence_periods

def create_simple_timeline(duration1, vol1, silence1, duration2, vol2, silence2, min_segment=2.0):
    """
    Crea una timeline simplificada basada en análisis de silencios
    Mucho más eficiente que análisis granular
    """
    total_duration = min(duration1, duration2)
    
    # Crear timeline con segmentos más largos para eficiencia
    segments = []
    current_time = 0
    
    # Si un video tiene mucho más volumen, favorecerlo
    primary_speaker = 1 if vol1 > vol2 + 3 else 2  # 3dB de diferencia
    current_speaker = primary_speaker
    
    # Crear segmentos basados en silencios
    all_events = []
    
    # Agregar eventos de silencio del video 1
    for start, end in silence1:
        if start < total_duration:
            all_events.append((start, 'silence_start_1'))
            all_events.append((min(end, total_duration), 'silence_end_1'))
    
    # Agregar eventos de silencio del video 2
    for start, end in silence2:
        if start < total_duration:
            all_events.append((start, 'silence_start_2'))
            all_events.append((min(end, total_duration), 'silence_end_2'))
    
    # Ordenar eventos por tiempo
    all_events.sort()
    
    # Estado de actividad (True = hablando, False = silencio)
    speaker1_active = True
    speaker2_active = True
    
    for time, event in all_events:
        # Determinar nuevo speaker antes del cambio de estado
        if speaker1_active and not speaker2_active:
            new_speaker = 1
        elif speaker2_active and not speaker1_active:
            new_speaker = 2
        else:
            new_speaker = primary_speaker  # Default cuando ambos hablan o ambos callan
        
        # Si hay cambio de speaker y el segmento es suficientemente largo
        if new_speaker != current_speaker and time - current_time >= min_segment:
            segments.append((current_time, time, current_speaker))
            current_speaker = new_speaker
            current_time = time
        
        # Actualizar estado de actividad
        if event == 'silence_start_1':
            speaker1_active = False
        elif event == 'silence_end_1':
            speaker1_active = True
        elif event == 'silence_start_2':
            speaker2_active = False
        elif event == 'silence_end_2':
            speaker2_active = True
    
    # Agregar segmento final
    if current_time < total_duration:
        segments.append((current_time, total_duration, current_speaker))
    
    # Si no hay suficientes cambios, crear segmentos alternos simples
    if len(segments) <= 2:
        segments = []
        segment_duration = total_duration / 4  # 4 segmentos
        for i in range(4):
            start = i * segment_duration
            end = min((i + 1) * segment_duration, total_duration)
            speaker = 1 if i % 2 == 0 else 2
            segments.append((start, end, speaker))
    
    return segments

def create_ffmpeg_concat_file(segments, video1_path, video2_path):
    """
    Crea archivos de concatenación para ffmpeg (método más eficiente)
    """
    # Crear archivo temporal para la lista de concatenación
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        concat_file = f.name
        
        for start, end, speaker in segments:
            video_path = video1_path if speaker == 1 else video2_path
            duration = end - start
            
            # Escribir entrada para concat
            f.write(f"file '{os.path.abspath(video_path)}'\n")
            f.write(f"inpoint {start:.2f}\n")
            f.write(f"outpoint {end:.2f}\n")
    
    return concat_file

def create_preview_clips(video1_path, video2_path, preview_duration):
    """
    Crea clips temporales de los primeros N segundos para análisis rápido
    """
    temp_video1 = tempfile.NamedTemporaryFile(suffix='_preview1.mp4', delete=False).name
    temp_video2 = tempfile.NamedTemporaryFile(suffix='_preview2.mp4', delete=False).name
    
    print(f"🎬 Extrayendo primeros {preview_duration}s de cada video...")
    
    # Extraer preview del video 1
    cmd1 = [
        'ffmpeg',
        '-i', video1_path,
        '-t', str(preview_duration),
        '-c', 'copy',  # Copia sin recodificar (ultra rápido)
        '-avoid_negative_ts', 'make_zero',
        '-y',
        temp_video1
    ]
    
    # Extraer preview del video 2
    cmd2 = [
        'ffmpeg',
        '-i', video2_path,
        '-t', str(preview_duration),
        '-c', 'copy',  # Copia sin recodificar (ultra rápido)
        '-avoid_negative_ts', 'make_zero',
        '-y',
        temp_video2
    ]
    
    # Ejecutar ambos comandos
    result1 = subprocess.run(cmd1, capture_output=True, text=True)
    result2 = subprocess.run(cmd2, capture_output=True, text=True)
    
    if result1.returncode != 0 or result2.returncode != 0:
        print(f"❌ Error creando clips de preview")
        print(f"Error video1: {result1.stderr}")
        print(f"Error video2: {result2.stderr}")
        return None, None
    
    print(f"✅ Clips de preview creados")
    return temp_video1, temp_video2

def process_videos_fast(video1_path, video2_path, output_path, preview_duration=None):
    """
    Procesamiento ultra-optimizado usando concat demuxer de ffmpeg
    """
    print("🚀 Iniciando procesamiento optimizado...")
    
    # Si es preview, crear clips temporales primero
    temp_files = []
    work_video1 = video1_path
    work_video2 = video2_path
    
    if preview_duration:
        work_video1, work_video2 = create_preview_clips(video1_path, video2_path, preview_duration)
        if work_video1 is None or work_video2 is None:
            return False
        temp_files.extend([work_video1, work_video2])
    
    try:
        # Analizar los videos de trabajo (completos o clips de preview)
        duration1, vol1, silence1 = get_audio_energy_fast(work_video1)
        duration2, vol2, silence2 = get_audio_energy_fast(work_video2)
    
        print(f"📊 Video 1: {duration1:.1f}s, {vol1:.1f}dB, {len(silence1)} silencios")
        print(f"📊 Video 2: {duration2:.1f}s, {vol2:.1f}dB, {len(silence2)} silencios")
        
        # Para preview, no necesitamos recortar más (ya está recortado)
        # Para procesamiento completo, usar toda la duración
        work_duration = min(duration1, duration2)
        
        # Crear timeline simplificada
        segments = create_simple_timeline(duration1, vol1, silence1, duration2, vol2, silence2)
        
        print(f"🎬 Generando {len(segments)} segmentos...")
        for i, (start, end, speaker) in enumerate(segments):
            print(f"  Segmento {i+1}: {start:.1f}s-{end:.1f}s -> Cámara {speaker}")
        
        # Método ultra-rápido: usar filter_complex 
        filter_parts = []
        
        # Preparar inputs de VIDEO para cada segmento (solo video, no audio)
        for i, (start, end, speaker) in enumerate(segments):
            input_idx = 0 if speaker == 1 else 1
            duration = end - start
            
            # Solo trim del video, NO del audio
            filter_parts.append(f"[{input_idx}:v]trim=start={start:.2f}:duration={duration:.2f},setpts=PTS-STARTPTS[v{i}];")
        
        # Concatenar todos los segmentos de VIDEO
        n_segments = len(segments)
        video_concat = "".join([f"[v{i}]" for i in range(n_segments)])
        filter_parts.append(f"{video_concat}concat=n={n_segments}:v=1:a=0[outv];")
        
        # AUDIO: Mezclar ambas pistas completas durante toda la duración
        work_duration = min(duration1, duration2)
        filter_parts.append(f"[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=0[outa]")
        
        complex_filter = "".join(filter_parts)
        
        # Comando ffmpeg ultra-optimizado para M1 usando los videos de trabajo
        cmd = [
            'ffmpeg',
            '-i', work_video1,
            '-i', work_video2,
            '-filter_complex', complex_filter,
            '-map', '[outv]',
            '-map', '[outa]',
            # Configuración optimizada para M1
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Máxima velocidad
            '-crf', '25',  # Balance velocidad/calidad
            '-tune', 'fastdecode',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',  # Optimización para reproducción rápida
            '-threads', '0',  # Usar todos los cores disponibles
            '-y',
            output_path
        ]
        
        print("⚡ Generando video final...")
        print(f"🔧 Comando: ffmpeg con {len(segments)} segmentos")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Error en ffmpeg: {result.stderr}")
            return False
        
        print(f"✅ Video generado exitosamente: {output_path}")
        return True
    
    finally:
        # Limpiar archivos temporales
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    print(f"🧹 Limpiado: {os.path.basename(temp_file)}")
            except Exception as e:
                print(f"⚠️  No se pudo limpiar {temp_file}: {e}")

def main():
    parser = argparse.ArgumentParser(description='Cambio automático de cámaras ultra-optimizado')
    parser.add_argument('video1', help='Primer video (persona 1)')
    parser.add_argument('video2', help='Segundo video (persona 2)')
    parser.add_argument('-o', '--output', default='output_switched.mp4', help='Archivo de salida')
    parser.add_argument('-p', '--preview', type=int, help='Duración del preview en segundos')
    parser.add_argument('--min-segment', type=float, default=2.0, help='Duración mínima de segmento en segundos')
    
    args = parser.parse_args()
    
    # Verificar dependencias
    check_dependencies()
    
    # Verificar que los archivos existan
    if not os.path.exists(args.video1):
        print(f"❌ Error: {args.video1} no existe")
        sys.exit(1)
    
    if not os.path.exists(args.video2):
        print(f"❌ Error: {args.video2} no existe")
        sys.exit(1)
    
    # Procesar videos con optimización máxima
    success = process_videos_fast(
        args.video1, 
        args.video2, 
        args.output, 
        preview_duration=args.preview
    )
    
    if success:
        print(f"\n🎉 Proceso completado!")
        print(f"📹 Video generado: {args.output}")
    else:
        print("\n💥 Error durante el procesamiento")
        sys.exit(1)

if __name__ == "__main__":
    main()