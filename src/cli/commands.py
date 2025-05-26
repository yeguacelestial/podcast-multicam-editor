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

console = Console()

@click.command(name="process")
@click.option("--test", is_flag=True, help="Ejecutar en modo prueba (solo 5 minutos)")
@click.option("--duration", type=int, default=300, help="Duración en segundos para el modo prueba")
def process_command(test, duration):
    """Procesar videos y audios para generar video multicámara automático."""
    # Selección de archivos con InquirerPy
    files = select_input_files()
    
    if not all(files.values()):
        console.print("[bold red]Proceso cancelado: no se seleccionaron todos los archivos requeridos.[/]")
        return
    
    # Selección de parámetros
    params = select_processing_parameters(test, duration)
    
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
        except Exception as e:
            console.print(f"[bold red]Error en VAD para speaker 2: {str(e)}[/]")
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
    
    console.print(f"\nVideo final guardado en: [cyan]{params['output_file']}[/]")

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

def select_processing_parameters(test_mode, test_duration):
    """Permite al usuario seleccionar los parámetros de procesamiento."""
    params = {}
    
    # Modo de prueba
    params["test_mode"] = test_mode or inquirer.confirm(
        message="¿Ejecutar en modo prueba? (solo procesará 5 minutos)",
        default=False
    ).execute()
    
    # Duración de prueba
    if params["test_mode"] and not test_mode:
        params["test_duration"] = inquirer.number(
            message="Duración de la prueba (segundos):",
            min_allowed=10,
            max_allowed=3600,
            default=test_duration,
            transformer=try_convert_to_int
        ).execute()
    else:
        params["test_duration"] = test_duration
    
    # Tipo de transición
    params["transition_type"] = inquirer.select(
        message="Selecciona el tipo de transición entre cámaras:",
        choices=[
            Choice(value="cut", name="Corte directo (instantáneo)"),
            Choice(value="dissolve", name="Fundido suave (0.5 segundos)"),
            Choice(value="fade", name="Fundido lento (1 segundo)")
        ],
        default="dissolve"
    ).execute()
    
    # Calidad de salida
    params["output_quality"] = inquirer.select(
        message="Selecciona la calidad del video final:",
        choices=[
            Choice(value="high", name="Alta (1080p, 30fps)"),
            Choice(value="medium", name="Media (720p, 30fps)"),
            Choice(value="low", name="Baja (480p, 30fps)")
        ],
        default="high"
    ).execute()
    
    # Archivo de salida
    params["output_file"] = inquirer.filepath(
        message="Selecciona la ubicación del video final:",
        only_directories=True,
        default=".",
        transformer=lambda result: os.path.join(os.path.abspath(result), "podcast_final.mp4")
    ).execute()
    
    # Añadir subtítulos
    params["add_subtitles"] = inquirer.confirm(
        message="¿Añadir subtítulos automáticos al video?",
        default=True
    ).execute()
    
    # Exportar transcripción
    params["export_transcript"] = inquirer.confirm(
        message="¿Exportar transcripción completa?",
        default=True
    ).execute()
    
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
    
    if params["test_mode"]:
        console.print(f"- Modo de prueba: [yellow]Activado[/] ({params['test_duration']} segundos)")
    else:
        console.print("- Modo de prueba: [green]Desactivado[/] (procesamiento completo)")
    
    # Tipo de transición
    transition_names = {
        "cut": "Corte directo (instantáneo)",
        "dissolve": "Fundido suave (0.5 segundos)",
        "fade": "Fundido lento (1 segundo)"
    }
    console.print(f"- Transición: [green]{transition_names[params['transition_type']]}[/]")
    
    # Calidad de salida
    quality_names = {
        "high": "Alta (1080p, 30fps)",
        "medium": "Media (720p, 30fps)",
        "low": "Baja (480p, 30fps)"
    }
    console.print(f"- Calidad: [green]{quality_names[params['output_quality']]}[/]")
    
    # Subtítulos y transcripción
    console.print(f"- Subtítulos: [green]{'Activados' if params['add_subtitles'] else 'Desactivados'}[/]")
    console.print(f"- Transcripción: [green]{'Activada' if params['export_transcript'] else 'Desactivada'}[/]")
    
    # Archivo de salida
    console.print(f"\n- Archivo de salida: [cyan]{params['output_file']}[/]")
    console.print("") 