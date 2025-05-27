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
import wave
from typing import Tuple
from tqdm import tqdm
import time

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

def extract_audio(input_path: str, output_path: str, duration: float = None) -> None:
    """
    Extrae el audio de un video o archivo de audio a un archivo WAV mono.
    Si duration está definido, recorta a los primeros N segundos.
    """
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-ac', '1',  # Mono
        '-ar', '16000',  # 16kHz para eficiencia
        '-vn',  # Sin video
        '-y',
    ]
    if duration:
        cmd += ['-t', str(duration)]
    cmd += [output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Error extrayendo audio: {result.stderr}")

def read_wav_mono(path: str) -> np.ndarray:
    """Lee un archivo WAV mono y lo retorna como un array de float32 normalizado."""
    with wave.open(path, 'rb') as wf:
        assert wf.getnchannels() == 1
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
        audio /= 32768.0
    return audio

def find_offset(ref: np.ndarray, target: np.ndarray, max_shift: int = 16000*5) -> int:
    """
    Calcula el offset óptimo (en muestras) para alinear target con ref usando correlación cruzada.
    max_shift limita el desfase máximo buscado (por defecto 5s a 16kHz).
    """
    if len(target) > len(ref):
        target = target[:len(ref)]
    if len(ref) > len(target):
        ref = ref[:len(target)]
    corr = np.correlate(ref, target, mode='full')
    mid = len(corr) // 2
    search_range = (mid - max_shift, mid + max_shift)
    best = np.argmax(corr[search_range[0]:search_range[1]])
    offset = best + search_range[0] - mid
    return offset

def process_videos_fast(video1_path, video2_path, ref_audio_path, output_path, preview_duration=None, batch_duration=60):
    """
    Procesamiento optimizado por batches de 1 minuto, tolerante a fallos y reanudable.
    """
    # Obtener duración total
    def get_duration(path):
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Error obteniendo duración: {result.stderr}")
        return float(result.stdout.strip())

    total_duration = min(get_duration(video1_path), get_duration(video2_path), get_duration(ref_audio_path))
    n_batches = int(np.ceil(total_duration / batch_duration))
    batches_dir = os.path.join('output', 'batches')
    os.makedirs(batches_dir, exist_ok=True)
    batch_files = []
    progreso = tqdm(total=n_batches, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]', desc='Batches procesados')
    tiempo_inicio = time.time()

    for batch_idx in range(n_batches):
        start = batch_idx * batch_duration
        end = min((batch_idx + 1) * batch_duration, total_duration)
        dur = end - start
        batch_name = f"batch_{batch_idx+1:04d}.mp4"
        batch_path = os.path.join(batches_dir, batch_name)
        batch_files.append(batch_path)
        if os.path.exists(batch_path):
            print(f"✅ Batch {batch_idx+1}/{n_batches} ya existe, saltando...")
            progreso.update(1)
            continue
        print(f"\n🚩 Procesando batch {batch_idx+1}/{n_batches} ({start:.1f}s - {end:.1f}s, duración {dur:.1f}s)")
        temp_files = []
        try:
            # Recortar videos y audio de referencia para el batch
            def cut_clip(input_path, suffix):
                temp_clip = tempfile.NamedTemporaryFile(suffix=suffix, delete=False).name
                temp_files.append(temp_clip)
                cmd = [
                    'ffmpeg', '-ss', str(start), '-t', str(dur),
                    '-i', input_path,
                    '-c', 'copy', '-avoid_negative_ts', 'make_zero', '-y', temp_clip
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"Error recortando clip: {result.stderr}")
                return temp_clip
            work_video1 = cut_clip(video1_path, f'_v1_b{batch_idx+1}.mp4')
            work_video2 = cut_clip(video2_path, f'_v2_b{batch_idx+1}.mp4')
            temp_audio_ref = tempfile.NamedTemporaryFile(suffix=f'_ref_b{batch_idx+1}.wav', delete=False).name
            temp_files.append(temp_audio_ref)
            cmd = [
                'ffmpeg', '-ss', str(start), '-t', str(dur),
                '-i', ref_audio_path,
                '-ac', '1', '-ar', '16000', '-vn', '-y', temp_audio_ref
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Error recortando audio de referencia: {result.stderr}")
            work_audio_ref = temp_audio_ref
            # Extracción de audios
            temp_audio1 = tempfile.NamedTemporaryFile(suffix=f'_v1_b{batch_idx+1}.wav', delete=False).name
            temp_audio2 = tempfile.NamedTemporaryFile(suffix=f'_v2_b{batch_idx+1}.wav', delete=False).name
            temp_files += [temp_audio1, temp_audio2]
            extract_audio(work_video1, temp_audio1, None)
            extract_audio(work_video2, temp_audio2, None)
            # Sincronización al inicio y final del batch
            audio1 = read_wav_mono(temp_audio1)
            audio2 = read_wav_mono(temp_audio2)
            audio_ref = read_wav_mono(work_audio_ref)
            sample_rate = 16000
            n_samples = int(min(10, dur) * sample_rate)
            offset1_ini = find_offset(audio_ref[:n_samples], audio1[:n_samples])
            offset2_ini = find_offset(audio_ref[:n_samples], audio2[:n_samples])
            # Si el batch es mayor a 30s, también sincronizar al final
            if dur > 30 and len(audio_ref) > n_samples*2:
                offset1_end = find_offset(audio_ref[-n_samples:], audio1[-n_samples:])
                offset2_end = find_offset(audio_ref[-n_samples:], audio2[-n_samples:])
                drift1 = (offset1_end - offset1_ini) / sample_rate
                drift2 = (offset2_end - offset2_ini) / sample_rate
            else:
                drift1 = drift2 = 0
            print(f"  Offsets: v1={offset1_ini/sample_rate:.3f}s, v2={offset2_ini/sample_rate:.3f}s | Drift: v1={drift1:.4f}s, v2={drift2:.4f}s")
            # Ajustar velocidad si hay drift
            def trim_and_stretch(input_path, offset_samples, drift, suffix):
                offset_sec = max(0, -offset_samples/sample_rate)
                temp_vid = tempfile.NamedTemporaryFile(suffix=suffix, delete=False).name
                temp_files.append(temp_vid)
                atempo = 1.0
                if abs(drift) > 0.01:
                    atempo = 1.0 + drift/dur
                # Recortar y ajustar velocidad solo del audio
                cmd = [
                    'ffmpeg', '-ss', f'{offset_sec:.3f}', '-t', str(dur),
                    '-i', input_path,
                    '-filter_complex', f"[0:v]setpts=PTS-STARTPTS[v];[0:a]atempo={atempo:.6f}[a]",
                    '-map', '[v]', '-map', '[a]',
                    '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-c:a', 'aac', '-b:a', '128k',
                    '-avoid_negative_ts', 'make_zero', '-y', temp_vid
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(f"Error sincronizando y ajustando velocidad: {result.stderr}")
                return temp_vid
            sync_video1 = trim_and_stretch(work_video1, offset1_ini, drift1, f'_sync1_b{batch_idx+1}.mp4')
            sync_video2 = trim_and_stretch(work_video2, offset2_ini, drift2, f'_sync2_b{batch_idx+1}.mp4')
            temp_files += [sync_video1, sync_video2]
            # Análisis de energía/silencios
            duration1, vol1, silence1 = get_audio_energy_fast(sync_video1)
            duration2, vol2, silence2 = get_audio_energy_fast(sync_video2)
            segments = create_simple_timeline(duration1, vol1, silence1, duration2, vol2, silence2)
            # Ensamblaje final del batch
            filter_parts = []
            for i, (start_s, end_s, speaker) in enumerate(segments):
                input_idx = 0 if speaker == 1 else 1
                seg_dur = end_s - start_s
                filter_parts.append(f"[{input_idx}:v]trim=start={start_s:.2f}:duration={seg_dur:.2f},setpts=PTS-STARTPTS[v{i}];")
            n_segments = len(segments)
            video_concat = "".join([f"[v{i}]" for i in range(n_segments)])
            filter_parts.append(f"{video_concat}concat=n={n_segments}:v=1:a=0[outv];")
            complex_filter = "".join(filter_parts)
            cmd = [
                'ffmpeg',
                '-i', sync_video1,
                '-i', sync_video2,
                '-i', work_audio_ref,
                '-filter_complex', complex_filter,
                '-map', '[outv]',
                '-map', '2:a',  # Audio de referencia
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '25',
                '-tune', 'fastdecode',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                '-threads', '0',
                '-y',
                batch_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"❌ Error en ffmpeg batch {batch_idx+1}: {result.stderr}")
                raise RuntimeError(f"Error en ffmpeg batch {batch_idx+1}")
            print(f"✅ Batch {batch_idx+1} generado: {batch_path}")
            progreso.update(1)
        except Exception as e:
            print(f"💥 Error en batch {batch_idx+1}: {e}")
            print(f"Deteniendo el procesamiento. Puedes reanudar luego.")
            break
        finally:
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                except Exception as e:
                    print(f"⚠️  No se pudo limpiar {temp_file}: {e}")
    progreso.close()
    # Concatenar todos los batches generados
    print("\n🔗 Concatenando todos los batches...")
    concat_list = os.path.join(batches_dir, 'concat_list.txt')
    with open(concat_list, 'w') as f:
        for batch_path in batch_files:
            if os.path.exists(batch_path):
                f.write(f"file '{os.path.abspath(batch_path)}'\n")
    cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_list,
        '-c', 'copy', '-y', output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Error concatenando batches: {result.stderr}")
        return False
    print(f"🎉 Video final generado: {output_path}")
    tiempo_total = time.time() - tiempo_inicio
    print(f"⏱️  Tiempo total transcurrido: {tiempo_total:.1f} segundos")
    return True

def main():
    parser = argparse.ArgumentParser(description='Cambio automático de cámaras ultra-optimizado')
    parser.add_argument('video1', help='Primer video (persona 1)')
    parser.add_argument('video2', help='Segundo video (persona 2)')
    parser.add_argument('audio_ref', help='Audio mezcla final de referencia')
    parser.add_argument('-o', '--output', default='output_switched.mp4', help='Archivo de salida')
    parser.add_argument('-p', '--preview', type=int, help='Duración del preview en segundos')
    parser.add_argument('--min-segment', type=float, default=2.0, help='Duración mínima de segmento en segundos')
    args = parser.parse_args()
    check_dependencies()
    if not os.path.exists(args.video1):
        print(f"❌ Error: {args.video1} no existe")
        sys.exit(1)
    if not os.path.exists(args.video2):
        print(f"❌ Error: {args.video2} no existe")
        sys.exit(1)
    if not os.path.exists(args.audio_ref):
        print(f"❌ Error: {args.audio_ref} no existe")
        sys.exit(1)
    success = process_videos_fast(
        args.video1,
        args.video2,
        args.audio_ref,
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