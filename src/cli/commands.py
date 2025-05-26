import os
import click
from rich.console import Console
from rich.progress import Progress
from InquirerPy import inquirer
from InquirerPy.validator import PathValidator
from InquirerPy.base.control import Choice

from src.audio.analyzer import validate_audio_file, analyze_audio_file
from src.audio.extractor import extract_audio_from_video
from src.audio.synchronizer import (
    find_offset_between_audios, 
    create_audio_fingerprint, 
    calculate_drift, 
    sync_audio_with_windows,
    correct_offset_puntuales,
    generate_final_sync_timeline
)
from src.detection.vad import detect_voice_activity, auto_threshold_vad
from src.video.processor import VideoProcessor
from src.video.composer import VideoComposer
from src.utils.validation import validate_video_file

console = Console()

@click.command(name="process")
@click.option("--preview", is_flag=True, help="Ejecutar en modo prueba (solo 5 minutos)")
@click.option("--duration", type=int, default=300, help="Duración en segundos para el modo prueba")
def process_command(preview, duration):
    """Procesar videos y audios para generar video multicámara automático."""
    # Selección de archivos con InquirerPy
    files = select_input_files()
    
    if not all(files.values()):
        console.print("[bold red]Proceso cancelado: no se seleccionaron todos los archivos requeridos.[/]")
        return
    
    # Selección de parámetros
    params = select_processing_parameters(preview, duration)
    
    # Mostrar resumen
    show_summary(files, params)
    
    # Confirmar procesamiento
    if not inquirer.confirm(
        message="¿Iniciar procesamiento con estos parámetros?",
        default=True
    ).execute():
        console.print("[yellow]Proceso cancelado por el usuario.[/]")
        return
    
    # Iniciar procesamiento
    with Progress() as progress:
        main_task = progress.add_task("[cyan]Procesando...", total=100)
        
        # Fase 1: Validar archivos de audio
        progress.update(main_task, advance=5, description="[cyan]Validando archivos de audio...")
        
        # Validar audio speaker 1
        audio1_valid, audio1_info = validate_audio_file(files["audio1"])
        if not audio1_valid:
            console.print(f"[bold red]Error: El archivo de audio del Speaker 1 no es válido.[/]")
            return
        
        # Validar audio speaker 2
        audio2_valid, audio2_info = validate_audio_file(files["audio2"])
        if not audio2_valid:
            console.print(f"[bold red]Error: El archivo de audio del Speaker 2 no es válido.[/]")
            return
        
        # Fase 2: Extraer audio de videos si es necesario
        progress.update(main_task, advance=5, description="[cyan]Extrayendo audio de videos...")
        
        # Extraer audio de video speaker 1
        video1_audio_task = progress.add_task("[green]Extrayendo audio de video 1...", total=100)
        video1_audio = extract_audio_from_video(
            files["video1"],
            mono=True,
            progress=progress,
            task_id=video1_audio_task
        )
        
        # Extraer audio de video speaker 2
        video2_audio_task = progress.add_task("[green]Extrayendo audio de video 2...", total=100)
        video2_audio = extract_audio_from_video(
            files["video2"],
            mono=True,
            progress=progress,
            task_id=video2_audio_task
        )
        
        # Fase 3: Crear fingerprints de audio
        progress.update(main_task, advance=5, description="[cyan]Creando fingerprints de audio...")
        
        # Fingerprint para audio speaker 1
        fingerprint1_task = progress.add_task("[green]Creando fingerprint audio 1...", total=100)
        try:
            fingerprint1 = create_audio_fingerprint(
                files["audio1"],
                progress=progress
            )
            progress.update(fingerprint1_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error al crear fingerprint para audio 1: {str(e)}[/]")
            return
        
        # Fingerprint para audio speaker 2
        fingerprint2_task = progress.add_task("[green]Creando fingerprint audio 2...", total=100)
        try:
            fingerprint2 = create_audio_fingerprint(
                files["audio2"],
                progress=progress
            )
            progress.update(fingerprint2_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error al crear fingerprint para audio 2: {str(e)}[/]")
            return
        
        # Fase 4: Encontrar offset entre audios y videos
        progress.update(main_task, advance=10, description="[cyan]Calculando sincronización inicial...")
        
        # Offset entre audio y video del speaker 1
        offset1_task = progress.add_task("[green]Calculando offset video 1...", total=100)
        try:
            offset1_result = find_offset_between_audios(
                files["audio1"],
                video1_audio,
                progress=progress
            )
            progress.update(offset1_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error al calcular offset para speaker 1: {str(e)}[/]")
            return
        
        # Offset entre audio y video del speaker 2
        offset2_task = progress.add_task("[green]Calculando offset video 2...", total=100)
        try:
            offset2_result = find_offset_between_audios(
                files["audio2"],
                video2_audio,
                progress=progress
            )
            progress.update(offset2_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error al calcular offset para speaker 2: {str(e)}[/]")
            return
        
        # Fase 5: Detectar y corregir drift temporal
        progress.update(main_task, advance=10, description="[cyan]Analizando drift temporal...")
        
        # Drift para speaker 1
        drift1_task = progress.add_task("[green]Calculando drift video 1...", total=100)
        try:
            drift1_result = calculate_drift(
                files["audio1"],
                video1_audio,
                offset1_result["offset_seconds"],
                window_size_seconds=30.0,
                step_size_seconds=15.0,
                progress=progress
            )
            progress.update(drift1_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error al calcular drift para speaker 1: {str(e)}[/]")
            drift1_result = None
        
        # Drift para speaker 2
        drift2_task = progress.add_task("[green]Calculando drift video 2...", total=100)
        try:
            drift2_result = calculate_drift(
                files["audio2"],
                video2_audio,
                offset2_result["offset_seconds"],
                window_size_seconds=30.0,
                step_size_seconds=15.0,
                progress=progress
            )
            progress.update(drift2_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error al calcular drift para speaker 2: {str(e)}[/]")
            drift2_result = None
        
        # Fase 6: Sincronización con ventanas deslizantes
        progress.update(main_task, advance=10, description="[cyan]Realizando sincronización fina...")
        
        # Ventanas para speaker 1
        window1_task = progress.add_task("[green]Sincronización fina video 1...", total=100)
        try:
            window1_result = sync_audio_with_windows(
                files["audio1"],
                video1_audio,
                window_size_seconds=20.0,
                overlap_seconds=5.0,
                max_offset_seconds=2.0,
                progress=progress
            )
            
            # Corregir desfases puntuales
            window1_result["sync_map"] = correct_offset_puntuales(
                window1_result["sync_map"],
                smoothing_window=5
            )
            
            progress.update(window1_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error en sincronización fina para speaker 1: {str(e)}[/]")
            window1_result = None
        
        # Ventanas para speaker 2
        window2_task = progress.add_task("[green]Sincronización fina video 2...", total=100)
        try:
            window2_result = sync_audio_with_windows(
                files["audio2"],
                video2_audio,
                window_size_seconds=20.0,
                overlap_seconds=5.0,
                max_offset_seconds=2.0,
                progress=progress
            )
            
            # Corregir desfases puntuales
            window2_result["sync_map"] = correct_offset_puntuales(
                window2_result["sync_map"],
                smoothing_window=5
            )
            
            progress.update(window2_task, completed=100)
        except Exception as e:
            console.print(f"[bold red]Error en sincronización fina para speaker 2: {str(e)}[/]")
            window2_result = None
        
        # Fase 7: Generar timeline final sincronizado
        progress.update(main_task, advance=5, description="[cyan]Generando timeline sincronizado...")
        
        # Timeline para speaker 1
        timeline1_task = progress.add_task("[green]Generando timeline video 1...", total=100)
        try:
            timeline1_result = generate_final_sync_timeline(
                files["audio1"],
                video1_audio,
                offset1_result,
                drift1_result,
                window1_result,
                sync_interval=0.5,  # Un punto cada 0.5 segundos
                progress=progress
            )
            progress.update(timeline1_task, completed=100)
            
            # Guardar timeline1 como JSON intermedio
            import json
            timeline1_json_path = os.path.join(params["output_dir"], "timeline1.json")
            with open(timeline1_json_path, 'w') as f:
                json.dump(timeline1_result, f)
            console.print(f"[green]Timeline 1 guardado en: {timeline1_json_path}[/]")
            
        except Exception as e:
            console.print(f"[bold red]Error al generar timeline para speaker 1: {str(e)}[/]")
            timeline1_result = None
        
        # Timeline para speaker 2
        timeline2_task = progress.add_task("[green]Generando timeline video 2...", total=100)
        try:
            timeline2_result = generate_final_sync_timeline(
                files["audio2"],
                video2_audio,
                offset2_result,
                drift2_result,
                window2_result,
                sync_interval=0.5,  # Un punto cada 0.5 segundos
                progress=progress
            )
            progress.update(timeline2_task, completed=100)
            
            # Guardar timeline2 como JSON intermedio
            import json
            timeline2_json_path = os.path.join(params["output_dir"], "timeline2.json")
            with open(timeline2_json_path, 'w') as f:
                json.dump(timeline2_result, f)
            console.print(f"[green]Timeline 2 guardado en: {timeline2_json_path}[/]")
            
        except Exception as e:
            console.print(f"[bold red]Error al generar timeline para speaker 2: {str(e)}[/]")
            timeline2_result = None
        
        # Fase 8: Detección de actividad vocal (VAD)
        progress.update(main_task, advance=10, description="[cyan]Detectando actividad vocal...")
        
        # VAD para speaker 1
        vad1_task = progress.add_task("[green]Detectando voz speaker 1...", total=100)
        try:
            # Primero calibrar automáticamente
            vad1_calibration = auto_threshold_vad(
                files["audio1"],
                progress=progress
            )
            
            # Usar el umbral óptimo encontrado
            vad1_result = detect_voice_activity(
                files["audio1"],
                threshold=vad1_calibration["best_threshold"],
                progress=progress
            )
            progress.update(vad1_task, completed=100)
            
            # Guardar resultados de VAD1 como JSON intermedio
            vad1_json_path = os.path.join(params["output_dir"], "vad1_result.json")
            with open(vad1_json_path, 'w') as f:
                json.dump(vad1_result, f)
            console.print(f"[green]Resultados VAD 1 guardados en: {vad1_json_path}[/]")
            
        except Exception as e:
            console.print(f"[bold red]Error en VAD para speaker 1: {str(e)}[/]")
            return
        
        # VAD para speaker 2
        vad2_task = progress.add_task("[green]Detectando voz speaker 2...", total=100)
        try:
            # Primero calibrar automáticamente
            vad2_calibration = auto_threshold_vad(
                files["audio2"],
                progress=progress
            )
            
            # Usar el umbral óptimo encontrado
            vad2_result = detect_voice_activity(
                files["audio2"],
                threshold=vad2_calibration["best_threshold"],
                progress=progress
            )
            progress.update(vad2_task, completed=100)
            
            # Guardar resultados de VAD2 como JSON intermedio
            vad2_json_path = os.path.join(params["output_dir"], "vad2_result.json")
            with open(vad2_json_path, 'w') as f:
                json.dump(vad2_result, f)
            console.print(f"[green]Resultados VAD 2 guardados en: {vad2_json_path}[/]")
            
        except Exception as e:
            console.print(f"[bold red]Error en VAD para speaker 2: {str(e)}[/]")
            return
        
        # Fase 9: Generar video final
        progress.update(main_task, advance=10, description="[cyan]Generando video final...")
        
        # Mapear timeline a formato esperado por VideoComposer
        speaker_timeline = []
        
        # Combinar los segmentos de VAD con la información de timeline
        for segment in vad1_result["segments"]:
            # Los segmentos ya son de voz, no hace falta verificar is_speech
            # Convertir tiempo de audio a tiempo de video usando el timeline
            start_idx = min(int(segment["start"] / timeline1_result["sync_interval"]), len(timeline1_result["timeline"])-1)
            end_idx = min(int(segment["end"] / timeline1_result["sync_interval"]), len(timeline1_result["timeline"])-1)
            
            video_start_raw = timeline1_result["timeline"][start_idx]
            video_end_raw = timeline1_result["timeline"][end_idx]
            
            # Extraer el valor de tiempo target_time si es un diccionario
            if isinstance(video_start_raw, dict) and 'target_time' in video_start_raw:
                video_start = video_start_raw['target_time']
            else:
                video_start = video_start_raw
                
            if isinstance(video_end_raw, dict) and 'target_time' in video_end_raw:
                video_end = video_end_raw['target_time']
            else:
                video_end = video_end_raw
            
            # Asegurarnos de que los valores sean numéricos
            if isinstance(video_start, (int, float)) and isinstance(video_end, (int, float)):
                speaker_timeline.append(("speaker1", video_start, video_end))
            else:
                console.print(f"[yellow]Advertencia: Valores no numéricos en timeline: {video_start_raw}, {video_end_raw}[/]")
        
        for segment in vad2_result["segments"]:
            # Los segmentos ya son de voz, no hace falta verificar is_speech
            # Convertir tiempo de audio a tiempo de video usando el timeline
            start_idx = min(int(segment["start"] / timeline2_result["sync_interval"]), len(timeline2_result["timeline"])-1)
            end_idx = min(int(segment["end"] / timeline2_result["sync_interval"]), len(timeline2_result["timeline"])-1)
            
            video_start_raw = timeline2_result["timeline"][start_idx]
            video_end_raw = timeline2_result["timeline"][end_idx]
            
            # Extraer el valor de tiempo target_time si es un diccionario
            if isinstance(video_start_raw, dict) and 'target_time' in video_start_raw:
                video_start = video_start_raw['target_time']
            else:
                video_start = video_start_raw
                
            if isinstance(video_end_raw, dict) and 'target_time' in video_end_raw:
                video_end = video_end_raw['target_time']
            else:
                video_end = video_end_raw
            
            # Asegurarnos de que los valores sean numéricos
            if isinstance(video_start, (int, float)) and isinstance(video_end, (int, float)):
                speaker_timeline.append(("speaker2", video_start, video_end))
            else:
                console.print(f"[yellow]Advertencia: Valores no numéricos en timeline: {video_start_raw}, {video_end_raw}[/]")
        
        # Verificar la estructura antes de ordenar
        is_valid_structure = all(
            isinstance(item, tuple) and len(item) == 3 and 
            isinstance(item[0], str) and 
            isinstance(item[1], (int, float)) and 
            isinstance(item[2], (int, float))
            for item in speaker_timeline
        )
        
        if not is_valid_structure:
            console.print("[bold red]Error: El timeline generado no tiene la estructura esperada (speaker_id, start_time, end_time).[/]")
            console.print("[yellow]Se guardarán los datos sin ordenar.[/]")
            
            # Guardar speaker_timeline intermedio para diagnóstico
            raw_timeline_path = os.path.join(params["output_dir"], "raw_speaker_timeline_error.json")
            with open(raw_timeline_path, 'w') as f:
                json.dump(speaker_timeline, f, default=str)
            console.print(f"[green]Timeline raw con error guardado en: {raw_timeline_path}[/]")
            return
        
        # Ordenar por tiempo de inicio
        try:
            speaker_timeline.sort(key=lambda x: x[1])
            console.print(f"[green]Timeline ordenado correctamente: {len(speaker_timeline)} segmentos[/]")
        except Exception as e:
            console.print(f"[bold red]Error al ordenar timeline: {str(e)}[/]")
            console.print("[yellow]Se guardarán los datos sin ordenar.[/]")
            
            # Guardar speaker_timeline intermedio para diagnóstico
            raw_timeline_path = os.path.join(params["output_dir"], "raw_speaker_timeline_error.json")
            with open(raw_timeline_path, 'w') as f:
                json.dump(speaker_timeline, f, default=str)
            console.print(f"[green]Timeline raw con error guardado en: {raw_timeline_path}[/]")
            return
        
        # Guardar speaker_timeline intermedio antes de procesar el video
        raw_timeline_path = os.path.join(params["output_dir"], "raw_speaker_timeline.json")
        with open(raw_timeline_path, 'w') as f:
            json.dump(speaker_timeline, f)
        console.print(f"[green]Timeline raw de speaker activo guardado en: {raw_timeline_path}[/]")
        
        # Crear video final
        video_task = progress.add_task("[green]Generando video final...", total=100)
        
        try:
            # Crear mapeo de speaker_id a rutas de archivos
            video_paths = {
                "speaker1": files["video1"],
                "speaker2": files["video2"]
            }
            
            audio_paths = {
                "speaker1": files["audio1"],
                "speaker2": files["audio2"]
            }
            
            # Si ambos audios tienen aproximadamente la misma duración, usar el del speaker1 como maestro
            audio1_info = audio1_valid[1] if isinstance(audio1_valid, tuple) else None
            audio2_info = audio2_valid[1] if isinstance(audio2_valid, tuple) else None
            
            master_audio = None
            if audio1_info and audio2_info and abs(audio1_info.get("duration", 0) - audio2_info.get("duration", 0)) < 5:
                master_audio = files["audio1"]
            
            # Crear compositor de video
            composer = VideoComposer(
                video_paths=video_paths,
                audio_paths=audio_paths,
                master_audio_path=master_audio,
                output_dir=params["output_dir"],
                preview_mode=params["preview_mode"],
                preview_duration=params["preview_duration"],
                output_quality=params["output_quality"],
                transition_type=params["transition_type"]
            )
            
            # Generar video
            result_path = composer.generate_video(
                speaker_timeline=speaker_timeline,
                output_filename=params["output_filename"],
                progress=progress
            )
            
            progress.update(video_task, completed=100)
            
        except Exception as e:
            console.print(f"[bold red]Error al generar video final: {str(e)}[/]")
            return
        
        # Completar barra principal
        progress.update(main_task, completed=100, description="[green]Procesamiento completado")
    
    # Mostrar resultados
    console.print("\n[bold green]¡Procesamiento completado con éxito![/]")
    
    # Mostrar información de sincronización
    console.print("\n[bold cyan]Resultados de sincronización inicial:[/]")
    console.print(f"- Offset video 1: [green]{offset1_result['offset_seconds']:.3f} segundos[/] (confianza: {offset1_result['confidence_score']:.4f})")
    console.print(f"- Offset video 2: [green]{offset2_result['offset_seconds']:.3f} segundos[/] (confianza: {offset2_result['confidence_score']:.4f})")
    
    # Mostrar información de drift
    console.print("\n[bold cyan]Resultados de drift temporal:[/]")
    if drift1_result:
        console.print(f"- Drift video 1: [green]{drift1_result['drift_rate']:.6f} seg/seg[/] ({drift1_result['num_windows']} ventanas analizadas)")
    else:
        console.print("- Drift video 1: [yellow]No disponible[/]")
        
    if drift2_result:
        console.print(f"- Drift video 2: [green]{drift2_result['drift_rate']:.6f} seg/seg[/] ({drift2_result['num_windows']} ventanas analizadas)")
    else:
        console.print("- Drift video 2: [yellow]No disponible[/]")
    
    # Mostrar información de sincronización fina
    console.print("\n[bold cyan]Resultados de sincronización fina:[/]")
    if window1_result:
        console.print(f"- Video 1: [green]{window1_result['num_windows']} puntos de sincronización[/] (offset promedio: {window1_result['average_offset']:.3f}s)")
    else:
        console.print("- Video 1: [yellow]No disponible[/]")
        
    if window2_result:
        console.print(f"- Video 2: [green]{window2_result['num_windows']} puntos de sincronización[/] (offset promedio: {window2_result['average_offset']:.3f}s)")
    else:
        console.print("- Video 2: [yellow]No disponible[/]")
    
    # Mostrar información de timeline final
    console.print("\n[bold cyan]Resultados de timeline:[/]")
    if timeline1_result:
        console.print(f"- Timeline video 1: [green]{timeline1_result['num_points']} puntos[/] (intervalo: {timeline1_result['sync_interval']:.1f}s)")
    else:
        console.print("- Timeline video 1: [yellow]No disponible[/]")
        
    if timeline2_result:
        console.print(f"- Timeline video 2: [green]{timeline2_result['num_points']} puntos[/] (intervalo: {timeline2_result['sync_interval']:.1f}s)")
    else:
        console.print("- Timeline video 2: [yellow]No disponible[/]")
    
    # Mostrar información de VAD
    console.print("\n[bold cyan]Resultados de detección de voz:[/]")
    console.print(f"- Speaker 1: [green]{vad1_result['num_segments']} segmentos[/] ({vad1_result['speech_percentage']:.1f}% de voz)")
    console.print(f"- Speaker 2: [green]{vad2_result['num_segments']} segmentos[/] ({vad2_result['speech_percentage']:.1f}% de voz)")
    
    console.print("\n[bold cyan]Resultados de generación de video:[/]")
    console.print(f"- Timeline generado: [green]{len(speaker_timeline)} segmentos[/]")
    console.print(f"- Modo: [green]{'Preview (5 min)' if params['preview_mode'] else 'Completo'}[/]")
    console.print(f"- Calidad: [green]{params['output_quality']}[/]")
    console.print(f"- Transiciones: [green]{params['transition_type']}[/]")
    
    console.print(f"\nVideo final guardado en: [cyan]{result_path}[/]")
    console.print(f"Timeline guardado en: [cyan]{timeline1_json_path}[/]")
    console.print(f"Timeline guardado en: [cyan]{timeline2_json_path}[/]")
    
    console.print("\n[bold green]¡Procesamiento completado con éxito![/]")

@click.command(name="generate")
@click.option("--speaker1-video", type=click.Path(exists=True), help="Ruta al video del speaker 1")
@click.option("--speaker2-video", type=click.Path(exists=True), help="Ruta al video del speaker 2")
@click.option("--speaker1-audio", type=click.Path(exists=True), help="Ruta al audio mono del speaker 1")
@click.option("--speaker2-audio", type=click.Path(exists=True), help="Ruta al audio mono del speaker 2")
@click.option("--master-audio", type=click.Path(exists=True), help="Ruta al audio maestro (opcional)")
@click.option("--timeline", type=click.Path(exists=True), help="Ruta al archivo JSON de timeline de speaker activo")
@click.option("--output", type=click.Path(), help="Ruta para guardar el video final")
@click.option("--transition", type=click.Choice(["instantáneo", "suave", "muy suave"]), default="suave", help="Tipo de transición entre cámaras")
@click.option("--quality", type=click.Choice(["low", "medium", "high"]), default="medium", help="Calidad del video final")
@click.option("--preview", is_flag=True, help="Generar solo un preview de 5 minutos")
@click.option("--preview-duration", type=int, default=300, help="Duración en segundos para el preview")
def generate_command(speaker1_video, speaker2_video, speaker1_audio, speaker2_audio, 
                     master_audio, timeline, output, transition, quality, preview, preview_duration):
    """Generar video final a partir de los videos sincronizados y el timeline de speaker activo."""
    import json
    
    console = Console()
    
    # Si no se especifican todos los parámetros, usar modo interactivo
    if not all([speaker1_video, speaker2_video, speaker1_audio, speaker2_audio, timeline]):
        console.print("[yellow]Algunos parámetros no fueron especificados. Iniciando modo interactivo...[/]")
        
        # Selección de archivos con InquirerPy
        files = {}
        
        files["video1"] = inquirer.filepath(
            message="Seleccionar video del Speaker 1:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["video2"] = inquirer.filepath(
            message="Seleccionar video del Speaker 2:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["audio1"] = inquirer.filepath(
            message="Seleccionar audio mono del Speaker 1:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["audio2"] = inquirer.filepath(
            message="Seleccionar audio mono del Speaker 2:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["master_audio"] = inquirer.filepath(
            message="Seleccionar audio maestro (opcional, Enter para omitir):",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result) if result else None,
            default=None
        ).execute()
        
        files["timeline"] = inquirer.filepath(
            message="Seleccionar archivo JSON de timeline de speaker activo:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        # Asignar valores
        speaker1_video = files["video1"]
        speaker2_video = files["video2"]
        speaker1_audio = files["audio1"]
        speaker2_audio = files["audio2"]
        master_audio = files["master_audio"]
        timeline = files["timeline"]
        
        # Selección de parámetros
        params = select_processing_parameters(preview, preview_duration)
        
        transition = params["transition_type"]
        quality = params["output_quality"]
        output = params["output_file"]
    else:
        # Usar valores de parámetros
        if not output:
            output = os.path.join(os.getcwd(), "output", "podcast_multicam.mp4")
    
    # Validar archivos
    for file_path, file_desc in [
        (speaker1_video, "Video Speaker 1"),
        (speaker2_video, "Video Speaker 2"),
        (speaker1_audio, "Audio Speaker 1"),
        (speaker2_audio, "Audio Speaker 2"),
        (timeline, "Timeline JSON")
    ]:
        is_valid, _ = validate_video_file(file_path) if "Video" in file_desc else (os.path.isfile(file_path), {})
        if not is_valid:
            console.print(f"[bold red]Error: El archivo {file_desc} no es válido o no existe.[/]")
            return
    
    # Si existe audio maestro, validar
    if master_audio:
        is_valid, _ = validate_audio_file(master_audio)
        if not is_valid:
            console.print(f"[bold red]Error: El archivo de audio maestro no es válido.[/]")
            return
    
    # Cargar timeline desde archivo JSON
    try:
        with open(timeline, 'r') as f:
            speaker_timeline = json.load(f)
    except Exception as e:
        console.print(f"[bold red]Error al cargar el archivo de timeline: {str(e)}[/]")
        return
    
    # Crear mapeo de speaker_id a rutas de archivos
    video_paths = {
        "speaker1": speaker1_video,
        "speaker2": speaker2_video
    }
    
    audio_paths = {
        "speaker1": speaker1_audio,
        "speaker2": speaker2_audio
    }
    
    # Generar video final
    with Progress() as progress:
        main_task = progress.add_task("[cyan]Generando video final...", total=100)
        
        # Crear compositor de video
        output_dir = os.path.dirname(output)
        output_filename = os.path.basename(output)
        
        composer = VideoComposer(
            video_paths=video_paths,
            audio_paths=audio_paths,
            master_audio_path=master_audio,
            output_dir=output_dir,
            preview_mode=preview,
            preview_duration=preview_duration,
            output_quality=quality,
            transition_type=transition
        )
        
        try:
            # Generar video
            result_path = composer.generate_video(
                speaker_timeline=speaker_timeline,
                output_filename=output_filename,
                progress=progress
            )
            
            progress.update(main_task, completed=100)
            
            # Mostrar resultado
            console.print("\n[bold green]¡Video generado con éxito![/]")
            console.print(f"Video guardado en: [cyan]{result_path}[/]")
            
        except Exception as e:
            progress.update(main_task, completed=0, description="[red]Error en generación de video")
            console.print(f"[bold red]Error al generar el video: {str(e)}[/]")
            return

@click.command(name="quick-test")
@click.option("--speaker1-video", type=click.Path(exists=True), help="Ruta al video del speaker 1")
@click.option("--speaker2-video", type=click.Path(exists=True), help="Ruta al video del speaker 2")
@click.option("--output", type=click.Path(), help="Ruta para guardar el video de prueba")
@click.option("--duration", type=int, default=30, help="Duración en segundos de cada segmento")
def quick_test_command(speaker1_video, speaker2_video, output, duration):
    """Ejecuta una prueba rápida y simple uniendo fragmentos de los videos."""
    console = Console()
    
    # Si no se especifican todos los parámetros, usar modo interactivo
    if not all([speaker1_video, speaker2_video]):
        console.print("[yellow]Algunos parámetros no fueron especificados. Iniciando modo interactivo...[/]")
        
        # Selección de archivos con InquirerPy
        files = {}
        
        files["video1"] = inquirer.filepath(
            message="Seleccionar video del Speaker 1:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["video2"] = inquirer.filepath(
            message="Seleccionar video del Speaker 2:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        # Asignar valores
        speaker1_video = files["video1"]
        speaker2_video = files["video2"]
    
    # Si no se especifica salida, usar valor por defecto
    if not output:
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        output = os.path.join(output_dir, "quick_test.mp4")
    
    # Validar archivos
    for file_path, file_desc in [
        (speaker1_video, "Video Speaker 1"),
        (speaker2_video, "Video Speaker 2")
    ]:
        is_valid, _ = validate_video_file(file_path)
        if not is_valid:
            console.print(f"[bold red]Error: El archivo {file_desc} no es válido o no existe.[/]")
            return
    
    # Crear mapeo de speaker_id a rutas de archivos
    video_paths = {
        "speaker1": speaker1_video,
        "speaker2": speaker2_video
    }
    
    audio_paths = {}  # No necesitamos audios específicos para esta prueba
    
    # Ejecutar prueba rápida
    with Progress() as progress:
        main_task = progress.add_task("[cyan]Ejecutando prueba rápida...", total=100)
        
        # Crear procesador de video
        processor = VideoProcessor(
            video_paths=video_paths,
            audio_paths=audio_paths,
            output_quality="low"  # Usamos calidad baja para mayor velocidad
        )
        
        try:
            # Generar video de prueba
            progress.update(main_task, advance=10, description="[cyan]Generando video de prueba...")
            result_path = processor.quick_test(output, duration=duration)
            
            progress.update(main_task, completed=100)
            
            # Mostrar resultado
            console.print("\n[bold green]¡Prueba rápida completada con éxito![/]")
            console.print(f"Video guardado en: [cyan]{result_path}[/]")
            
        except Exception as e:
            progress.update(main_task, completed=0, description="[red]Error en prueba rápida")
            console.print(f"[bold red]Error al generar el video de prueba: {str(e)}[/]")
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/]")
            return

@click.command(name="simple-test")
@click.option("--speaker1-video", type=click.Path(exists=True), help="Ruta al video del speaker 1")
@click.option("--speaker2-video", type=click.Path(exists=True), help="Ruta al video del speaker 2")
@click.option("--timeline", type=click.Path(exists=True), help="Ruta al archivo JSON de timeline simple")
@click.option("--output", type=click.Path(), help="Ruta para guardar el video de prueba")
def simple_test_command(speaker1_video, speaker2_video, timeline, output):
    """Ejecuta una prueba con un timeline sencillo para verificar el procesamiento básico."""
    console = Console()
    import json
    
    # Si no se especifican todos los parámetros, usar modo interactivo
    if not all([speaker1_video, speaker2_video, timeline]):
        console.print("[yellow]Algunos parámetros no fueron especificados. Iniciando modo interactivo...[/]")
        
        # Selección de archivos con InquirerPy
        files = {}
        
        files["video1"] = inquirer.filepath(
            message="Seleccionar video del Speaker 1:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["video2"] = inquirer.filepath(
            message="Seleccionar video del Speaker 2:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["timeline"] = inquirer.filepath(
            message="Seleccionar archivo JSON de timeline simple:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        # Asignar valores
        speaker1_video = files["video1"]
        speaker2_video = files["video2"]
        timeline = files["timeline"]
    
    # Si no se especifica salida, usar valor por defecto
    if not output:
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        output = os.path.join(output_dir, "simple_test.mp4")
    
    # Validar archivos
    for file_path, file_desc in [
        (speaker1_video, "Video Speaker 1"),
        (speaker2_video, "Video Speaker 2"),
        (timeline, "Timeline JSON")
    ]:
        is_valid, _ = validate_video_file(file_path) if "Video" in file_desc else (os.path.isfile(file_path), {})
        if not is_valid:
            console.print(f"[bold red]Error: El archivo {file_desc} no es válido o no existe.[/]")
            return
    
    # Cargar timeline desde archivo JSON
    try:
        with open(timeline, 'r') as f:
            speaker_timeline = json.load(f)
        console.print(f"[green]Timeline cargado: {len(speaker_timeline)} segmentos[/]")
    except Exception as e:
        console.print(f"[bold red]Error al cargar el archivo de timeline: {str(e)}[/]")
        return
    
    # Crear mapeo de speaker_id a rutas de archivos
    video_paths = {
        "speaker1": speaker1_video,
        "speaker2": speaker2_video
    }
    
    audio_paths = {}  # No necesitamos audios específicos para esta prueba
    
    # Ejecutar prueba simple
    with Progress() as progress:
        main_task = progress.add_task("[cyan]Ejecutando prueba simple...", total=100)
        
        # Crear procesador de video
        processor = VideoProcessor(
            video_paths=video_paths,
            audio_paths=audio_paths,
            output_quality="low",  # Usamos calidad baja para mayor velocidad
            preview_duration=300   # Limitar a 5 minutos para prueba
        )
        
        try:
            # Cargar videos
            progress.update(main_task, advance=10, description="[cyan]Cargando videos...")
            processor.load_videos(progress=progress, task_id=main_task)
            
            # Procesar timeline
            progress.update(main_task, advance=10, description="[cyan]Procesando timeline...")
            result_path = processor.process_active_speaker_timeline(
                speaker_timeline=speaker_timeline,
                transition_type="cut",  # Usar cortes directos para simplicidad
                min_segment_duration=2.0,
                output_path=output,
                progress=progress,
                task_id=main_task
            )
            
            progress.update(main_task, completed=100)
            
            # Mostrar resultado
            console.print("\n[bold green]¡Prueba simple completada con éxito![/]")
            console.print(f"Video guardado en: [cyan]{result_path}[/]")
            
        except Exception as e:
            progress.update(main_task, completed=0, description="[red]Error en prueba simple")
            console.print(f"[bold red]Error al generar el video de prueba: {str(e)}[/]")
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/]")
            return

@click.command(name="ultra-simple-test")
@click.option("--speaker1-video", type=click.Path(exists=True), help="Ruta al video del speaker 1")
@click.option("--speaker2-video", type=click.Path(exists=True), help="Ruta al video del speaker 2")
@click.option("--timeline", type=click.Path(exists=True), help="Ruta al archivo JSON de timeline ultra simple")
@click.option("--output", type=click.Path(), help="Ruta para guardar el video de prueba")
@click.option("--transition", type=click.Choice(["cut", "crossfade", "fade"]), default="cut", 
              help="Tipo de transición entre clips")
def ultra_simple_test_command(speaker1_video, speaker2_video, timeline, output, transition):
    """Ejecuta una prueba ultra simplificada que concatena segmentos directamente sin efectos."""
    console = Console()
    import json
    
    # Si no se especifican todos los parámetros, usar modo interactivo
    if not all([speaker1_video, speaker2_video, timeline]):
        console.print("[yellow]Algunos parámetros no fueron especificados. Iniciando modo interactivo...[/]")
        
        # Selección de archivos con InquirerPy
        files = {}
        
        files["video1"] = inquirer.filepath(
            message="Seleccionar video del Speaker 1:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["video2"] = inquirer.filepath(
            message="Seleccionar video del Speaker 2:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["timeline"] = inquirer.filepath(
            message="Seleccionar archivo JSON de timeline ultra simple:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        # Asignar valores
        speaker1_video = files["video1"]
        speaker2_video = files["video2"]
        timeline = files["timeline"]
        
        # Seleccionar tipo de transición
        transition = inquirer.select(
            message="Seleccionar tipo de transición:",
            choices=[
                Choice(value="cut", name="Corte directo"),
                Choice(value="crossfade", name="Crossfade"),
                Choice(value="fade", name="Fade con negro")
            ],
            default="cut"
        ).execute()
    
    # Si no se especifica salida, usar valor por defecto
    if not output:
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        output = os.path.join(output_dir, f"ultra_simple_{transition}.mp4")
    
    # Validar archivos
    for file_path, file_desc in [
        (speaker1_video, "Video Speaker 1"),
        (speaker2_video, "Video Speaker 2"),
        (timeline, "Timeline JSON")
    ]:
        is_valid, _ = validate_video_file(file_path) if "Video" in file_desc else (os.path.isfile(file_path), {})
        if not is_valid:
            console.print(f"[bold red]Error: El archivo {file_desc} no es válido o no existe.[/]")
            return
    
    # Cargar timeline desde archivo JSON
    try:
        with open(timeline, 'r') as f:
            speaker_timeline = json.load(f)
        console.print(f"[green]Timeline cargado: {len(speaker_timeline)} segmentos[/]")
    except Exception as e:
        console.print(f"[bold red]Error al cargar el archivo de timeline: {str(e)}[/]")
        return
    
    # Crear mapeo de speaker_id a rutas de archivos
    video_paths = {
        "speaker1": speaker1_video,
        "speaker2": speaker2_video
    }
    
    audio_paths = {}  # No necesitamos audios específicos para esta prueba
    
    # Ejecutar prueba ultra simple
    with Progress() as progress:
        main_task = progress.add_task("[cyan]Ejecutando prueba ultra simple...", total=100)
        
        # Crear procesador de video
        processor = VideoProcessor(
            video_paths=video_paths,
            audio_paths=audio_paths,
            output_quality="low"  # Usamos calidad baja para mayor velocidad
        )
        
        try:
            # Actualizar progreso
            progress.update(main_task, advance=10, description=f"[cyan]Procesando timeline con transición '{transition}'...")
            
            # Ejecutar prueba ultra simple
            result_path = processor.ultra_simple_test(
                timeline=speaker_timeline,
                output_path=output,
                transition_type=transition
            )
            
            progress.update(main_task, completed=100)
            
            # Mostrar resultado
            if result_path:
                console.print("\n[bold green]¡Prueba ultra simple completada con éxito![/]")
                console.print(f"Video guardado en: [cyan]{result_path}[/]")
            else:
                console.print("\n[bold red]La prueba ultra simple no generó un video.[/]")
            
        except Exception as e:
            progress.update(main_task, completed=0, description="[red]Error en prueba ultra simple")
            console.print(f"[bold red]Error al generar el video de prueba: {str(e)}[/]")
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/]")
            return

@click.command(name="resume")
@click.option("--speaker1-video", type=click.Path(exists=True), help="Ruta al video del speaker 1")
@click.option("--speaker2-video", type=click.Path(exists=True), help="Ruta al video del speaker 2")
@click.option("--speaker-timeline", type=click.Path(exists=True), help="Ruta al archivo JSON de timeline generado")
@click.option("--output", type=click.Path(), help="Ruta para guardar el video final")
@click.option("--transition", type=click.Choice(["instantáneo", "suave", "muy suave"]), default="suave", help="Tipo de transición entre cámaras")
@click.option("--quality", type=click.Choice(["low", "medium", "high"]), default="medium", help="Calidad del video final")
@click.option("--preview", is_flag=True, help="Generar solo un preview de 5 minutos")
@click.option("--preview-duration", type=int, default=300, help="Duración en segundos para el preview")
def resume_command(speaker1_video, speaker2_video, speaker_timeline, output, transition, quality, preview, preview_duration):
    """Continuar el proceso desde un timeline guardado sin realizar todo el análisis de nuevo."""
    import json
    
    console = Console()
    
    # Si no se especifican todos los parámetros, usar modo interactivo
    if not all([speaker1_video, speaker2_video, speaker_timeline]):
        console.print("[yellow]Algunos parámetros no fueron especificados. Iniciando modo interactivo...[/]")
        
        # Selección de archivos con InquirerPy
        files = {}
        
        files["video1"] = inquirer.filepath(
            message="Seleccionar video del Speaker 1:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["video2"] = inquirer.filepath(
            message="Seleccionar video del Speaker 2:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        files["timeline"] = inquirer.filepath(
            message="Seleccionar archivo JSON de timeline guardado:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
        
        # Asignar valores
        speaker1_video = files["video1"]
        speaker2_video = files["video2"]
        speaker_timeline = files["timeline"]
        
        # Selección de parámetros
        params = select_processing_parameters(preview, preview_duration)
        
        transition = params["transition_type"]
        quality = params["output_quality"]
        output = params["output_file"]
    else:
        # Usar valores de parámetros
        if not output:
            output_dir = os.path.join(os.getcwd(), "output")
            os.makedirs(output_dir, exist_ok=True)
            output = os.path.join(output_dir, "podcast_multicam.mp4")
    
    # Validar archivos
    for file_path, file_desc in [
        (speaker1_video, "Video Speaker 1"),
        (speaker2_video, "Video Speaker 2"),
        (speaker_timeline, "Timeline JSON")
    ]:
        is_valid, _ = validate_video_file(file_path) if "Video" in file_desc else (os.path.isfile(file_path), {})
        if not is_valid:
            console.print(f"[bold red]Error: El archivo {file_desc} no es válido o no existe.[/]")
            return
    
    # Cargar timeline desde archivo JSON
    try:
        with open(speaker_timeline, 'r') as f:
            timeline_data = json.load(f)
        
        # Verificar si el timeline es un formato raw o procesado
        if isinstance(timeline_data, list):
            # Es un timeline procesado en formato [(speaker_id, start, end), ...]
            speaker_timeline_data = timeline_data
        else:
            console.print("[bold yellow]El formato del timeline no es el esperado. Debe ser una lista de tuplas (speaker_id, start_time, end_time).[/]")
            return
            
        console.print(f"[green]Timeline cargado: {len(speaker_timeline_data)} segmentos[/]")
    except Exception as e:
        console.print(f"[bold red]Error al cargar el archivo de timeline: {str(e)}[/]")
        return
    
    # Crear mapeo de speaker_id a rutas de archivos
    video_paths = {
        "speaker1": speaker1_video,
        "speaker2": speaker2_video
    }
    
    # Generar video final
    with Progress() as progress:
        main_task = progress.add_task("[cyan]Generando video final...", total=100)
        
        # Crear compositor de video
        output_dir = os.path.dirname(output)
        output_filename = os.path.basename(output)
        
        composer = VideoComposer(
            video_paths=video_paths,
            audio_paths={},  # No necesitamos audio separado para este comando
            master_audio_path=None,
            output_dir=output_dir,
            preview_mode=preview,
            preview_duration=preview_duration,
            output_quality=quality,
            transition_type=transition
        )
        
        try:
            # Generar video
            result_path = composer.generate_video(
                speaker_timeline=speaker_timeline_data,
                output_filename=output_filename,
                progress=progress
            )
            
            progress.update(main_task, completed=100)
            
            # Mostrar resultado
            console.print("\n[bold green]¡Video generado con éxito desde timeline guardado![/]")
            console.print(f"Video guardado en: [cyan]{result_path}[/]")
            
        except Exception as e:
            progress.update(main_task, completed=0, description="[red]Error en generación de video")
            console.print(f"[bold red]Error al generar el video: {str(e)}[/]")
            return

@click.command(name="inspect-timeline")
@click.option("--timeline", type=click.Path(exists=True), help="Ruta al archivo JSON de timeline a inspeccionar")
def inspect_timeline_command(timeline):
    """Inspecciona y valida un archivo de timeline para diagnóstico."""
    import json
    import pprint
    
    console = Console()
    
    # Si no se especifica timeline, usar modo interactivo
    if not timeline:
        timeline = inquirer.filepath(
            message="Seleccionar archivo JSON de timeline para inspeccionar:",
            validate=PathValidator(is_file=True, message="Debe ser un archivo existente"),
            filter=lambda result: os.path.abspath(result)
        ).execute()
    
    try:
        # Cargar timeline
        with open(timeline, 'r') as f:
            timeline_data = json.load(f)
        
        # Analizar tipo de datos
        console.print(f"[cyan]Archivo cargado: [bold]{timeline}[/][/]")
        console.print(f"[cyan]Tipo de datos: [bold]{type(timeline_data).__name__}[/][/]")
        
        if isinstance(timeline_data, list):
            console.print(f"[cyan]Número de elementos: [bold]{len(timeline_data)}[/][/]")
            
            # Muestra los primeros elementos
            console.print("\n[cyan]Primeros 5 elementos:[/]")
            for i, item in enumerate(timeline_data[:5]):
                console.print(f"[green]Elemento {i}: {type(item).__name__}[/]")
                if isinstance(item, (list, tuple)):
                    formatted = pprint.pformat(item)
                    console.print(f"  [white]{formatted}[/]")
                else:
                    console.print(f"  [white]{item}[/]")
            
            # Verifica la estructura si parece un timeline de speaker
            if len(timeline_data) > 0 and isinstance(timeline_data[0], (list, tuple)) and len(timeline_data[0]) == 3:
                # Verifica que la estructura sea consistente
                has_correct_structure = all(
                    isinstance(item, (list, tuple)) and len(item) == 3 and
                    isinstance(item[0], str) and
                    isinstance(item[1], (int, float)) and
                    isinstance(item[2], (int, float))
                    for item in timeline_data
                )
                
                if has_correct_structure:
                    console.print("\n[bold green]✓ El timeline tiene la estructura correcta (speaker_id, start_time, end_time)[/]")
                    
                    # Estadísticas sobre el timeline
                    durations = [(item[2] - item[1]) for item in timeline_data]
                    avg_duration = sum(durations) / len(durations) if durations else 0
                    total_duration = timeline_data[-1][2] if timeline_data else 0
                    
                    console.print(f"\n[cyan]Estadísticas del timeline:[/]")
                    console.print(f"- Duración total: [green]{total_duration:.2f} segundos[/]")
                    console.print(f"- Duración promedio de segmentos: [green]{avg_duration:.2f} segundos[/]")
                    console.print(f"- Segmento más corto: [green]{min(durations):.2f} segundos[/]")
                    console.print(f"- Segmento más largo: [green]{max(durations):.2f} segundos[/]")
                    
                    # Conteo por speaker
                    speaker_counts = {}
                    for item in timeline_data:
                        speaker_id = item[0]
                        speaker_counts[speaker_id] = speaker_counts.get(speaker_id, 0) + 1
                    
                    console.print("\n[cyan]Distribución por speaker:[/]")
                    for speaker_id, count in speaker_counts.items():
                        percentage = (count / len(timeline_data)) * 100
                        console.print(f"- {speaker_id}: [green]{count} segmentos[/] ({percentage:.1f}%)")
                else:
                    console.print("\n[bold red]✗ El timeline no tiene la estructura esperada[/]")
                    
                    # Identificar elementos problemáticos
                    for i, item in enumerate(timeline_data):
                        if not (isinstance(item, (list, tuple)) and len(item) == 3):
                            console.print(f"  Elemento {i}: formato incorrecto - {type(item).__name__}, longitud: {len(item) if hasattr(item, '__len__') else 'N/A'}")
                        elif not isinstance(item[0], str):
                            console.print(f"  Elemento {i}: speaker_id no es string - {type(item[0]).__name__}")
                        elif not isinstance(item[1], (int, float)):
                            console.print(f"  Elemento {i}: start_time no es numérico - {type(item[1]).__name__}")
                        elif not isinstance(item[2], (int, float)):
                            console.print(f"  Elemento {i}: end_time no es numérico - {type(item[2]).__name__}")
            else:
                console.print("\n[yellow]No parece ser un timeline de speaker activo[/]")
        elif isinstance(timeline_data, dict):
            # Probablemente sea un resultado de otro proceso
            console.print(f"[cyan]Estructura de diccionario con [bold]{len(timeline_data)}[/] claves[/]")
            console.print("\n[cyan]Claves presentes:[/]")
            for key in timeline_data.keys():
                value = timeline_data[key]
                value_type = type(value).__name__
                if isinstance(value, list):
                    console.print(f"- [green]{key}[/]: lista con {len(value)} elementos")
                else:
                    console.print(f"- [green]{key}[/]: {value_type}")
                    
            # Si es un resultado de VAD, mostrar info específica
            if "segments" in timeline_data and "speech_percentage" in timeline_data:
                console.print("\n[cyan]Parece ser un resultado de detección de voz (VAD)[/]")
                console.print(f"- Archivo: [green]{timeline_data.get('file', 'No especificado')}[/]")
                console.print(f"- Duración total: [green]{timeline_data.get('total_duration', 0):.2f} segundos[/]")
                console.print(f"- Porcentaje de voz: [green]{timeline_data.get('speech_percentage', 0):.1f}%[/]")
                console.print(f"- Número de segmentos: [green]{timeline_data.get('num_segments', 0)}[/]")
                
                # Mostrar primeros segmentos
                segments = timeline_data.get("segments", [])
                console.print("\n[cyan]Primeros 5 segmentos de voz:[/]")
                for i, segment in enumerate(segments[:5]):
                    start = segment.get("start", 0)
                    end = segment.get("end", 0)
                    duration = segment.get("duration", end - start)
                    console.print(f"- Segmento {i}: [green]{start:.2f}s - {end:.2f}s[/] (duración: {duration:.2f}s)")
            
            # Si es un resultado de timeline de sincronización
            elif "timeline" in timeline_data and "sync_interval" in timeline_data:
                console.print("\n[cyan]Parece ser un timeline de sincronización[/]")
                console.print(f"- Intervalo de sincronización: [green]{timeline_data.get('sync_interval', 0):.2f} segundos[/]")
                console.print(f"- Número de puntos: [green]{timeline_data.get('num_points', 0)}[/]")
                
                # Mostrar primeros puntos del timeline
                timeline_points = timeline_data.get("timeline", [])
                console.print("\n[cyan]Primeros 10 puntos del timeline:[/]")
                for i, point in enumerate(timeline_points[:10]):
                    console.print(f"- Punto {i} ({i * timeline_data.get('sync_interval', 0):.2f}s): [green]{point}[/]")
        else:
            console.print(f"\n[bold red]Formato de archivo no reconocido: {type(timeline_data).__name__}[/]")
        
    except Exception as e:
        console.print(f"[bold red]Error al inspeccionar timeline: {str(e)}[/]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/]")

def select_input_files():
    """Permite al usuario seleccionar los archivos de entrada usando InquirerPy."""
    files = {}
    
    # Video Speaker 1
    files["video1"] = inquirer.filepath(
        message="Selecciona el video del Speaker 1:",
        only_files=True,
        validate=PathValidator(is_file=True, message="Debes seleccionar un archivo válido"),
        transformer=lambda result: os.path.abspath(result),
    ).execute()
    
    # Video Speaker 2
    files["video2"] = inquirer.filepath(
        message="Selecciona el video del Speaker 2:",
        only_files=True,
        validate=PathValidator(is_file=True, message="Debes seleccionar un archivo válido"),
        transformer=lambda result: os.path.abspath(result),
    ).execute()
    
    # Audio Speaker 1
    files["audio1"] = inquirer.filepath(
        message="Selecciona el audio MONO del Speaker 1:",
        only_files=True,
        validate=PathValidator(is_file=True, message="Debes seleccionar un archivo válido"),
        transformer=lambda result: os.path.abspath(result),
    ).execute()
    
    # Audio Speaker 2
    files["audio2"] = inquirer.filepath(
        message="Selecciona el audio MONO del Speaker 2:",
        only_files=True,
        validate=PathValidator(is_file=True, message="Debes seleccionar un archivo válido"),
        transformer=lambda result: os.path.abspath(result),
    ).execute()
    
    return files

def select_processing_parameters(test=False, duration=300):
    """Seleccionar parámetros de procesamiento."""
    params = {}
    
    # Tipo de transición
    params["transition_type"] = inquirer.select(
        message="Seleccionar tipo de transición entre cámaras:",
        choices=[
            Choice(value="instantáneo", name="Instantáneo (corte directo)"),
            Choice(value="suave", name="Suave (crossfade 0.5s)"),
            Choice(value="muy suave", name="Muy suave (fade 1s)")
        ],
        default="suave"
    ).execute()
    
    # Duración mínima de segmento
    params["min_segment_duration"] = inquirer.number(
        message="Duración mínima de cada segmento de cámara (segundos):",
        min_allowed=1.0,
        max_allowed=10.0,
        default=2.0,
        float_allowed=True
    ).execute()
    
    # Calidad de salida
    params["output_quality"] = inquirer.select(
        message="Calidad del video final:",
        choices=[
            Choice(value="low", name="Baja (más rápido)"),
            Choice(value="medium", name="Media (equilibrado)"),
            Choice(value="high", name="Alta (más lento)")
        ],
        default="medium"
    ).execute()
    
    # Directorio de salida
    default_output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(default_output_dir, exist_ok=True)
    
    params["output_dir"] = inquirer.text(
        message="Directorio para guardar el video final:",
        default=default_output_dir,
        validate=PathValidator(is_dir=True, message="El directorio debe existir o ser creado"),
        filter=lambda result: os.path.abspath(result)
    ).execute()
    
    # Crear directorio si no existe
    if not os.path.exists(params["output_dir"]):
        os.makedirs(params["output_dir"])
    
    # Nombre del archivo de salida
    params["output_filename"] = inquirer.text(
        message="Nombre del archivo de salida:",
        default="podcast_multicam.mp4"
    ).execute()
    
    # Ruta completa del archivo de salida
    params["output_file"] = os.path.join(params["output_dir"], params["output_filename"])
    
    # Modo preview
    params["preview_mode"] = test
    params["preview_duration"] = duration if test else None
    
    return params

def try_convert_to_int(val):
    """Intenta convertir un valor a entero."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return val

def show_summary(files, params):
    """Muestra un resumen de los archivos y parámetros seleccionados."""
    console.print("\n[bold cyan]Resumen de configuración:[/]")
    
    # Archivos
    console.print("\n[bold]Archivos seleccionados:[/]")
    console.print(f"- Video Speaker 1: [green]{files['video1']}[/]")
    console.print(f"- Video Speaker 2: [green]{files['video2']}[/]")
    console.print(f"- Audio Speaker 1: [green]{files['audio1']}[/]")
    console.print(f"- Audio Speaker 2: [green]{files['audio2']}[/]")
    
    # Parámetros
    console.print("\n[bold]Parámetros de procesamiento:[/]")
    
    if params["preview_mode"]:
        console.print(f"- Modo de prueba: [yellow]Activado[/] ({params['preview_duration']} segundos)")
    else:
        console.print("- Modo de prueba: [green]Desactivado[/] (procesamiento completo)")
    
    # Tipo de transición
    transition_names = {
        "instantáneo": "Instantáneo (corte directo)",
        "suave": "Suave (crossfade 0.5s)",
        "muy suave": "Muy suave (fade 1s)"
    }
    console.print(f"- Transición: [green]{transition_names[params['transition_type']]}[/]")
    
    # Calidad de salida
    quality_names = {
        "low": "Baja (más rápido)",
        "medium": "Media (equilibrado)",
        "high": "Alta (más lento)"
    }
    console.print(f"- Calidad: [green]{quality_names[params['output_quality']]}[/]")
    
    # Archivo de salida
    console.print(f"\n- Archivo de salida: [cyan]{params['output_file']}[/]")
    console.print("") 