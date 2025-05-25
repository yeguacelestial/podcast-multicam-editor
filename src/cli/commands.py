import os
import click
from rich.console import Console
from rich.progress import Progress
from InquirerPy import inquirer
from InquirerPy.validator import PathValidator
from InquirerPy.base.control import Choice

from src.audio.analyzer import validate_audio_file, analyze_audio_file
from src.audio.extractor import extract_audio_from_video
from src.audio.synchronizer import find_offset_between_audios, create_audio_fingerprint
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
        progress.update(main_task, advance=10, description="[cyan]Creando fingerprints de audio...")
        
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
        progress.update(main_task, advance=15, description="[cyan]Calculando sincronización...")
        
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
        
        # Fase 5: Detección de actividad vocal (VAD)
        progress.update(main_task, advance=15, description="[cyan]Detectando actividad vocal...")
        
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
    console.print("\n[bold cyan]Resultados de sincronización:[/]")
    console.print(f"- Offset video 1: [green]{offset1_result['offset_seconds']:.3f} segundos[/] (confianza: {offset1_result['confidence_score']:.4f})")
    console.print(f"- Offset video 2: [green]{offset2_result['offset_seconds']:.3f} segundos[/] (confianza: {offset2_result['confidence_score']:.4f})")
    
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
            min_allowed=30,
            max_allowed=1800,
            default=300,
            validate=lambda val: try_convert_to_int(val) and 30 <= int(val) <= 1800,
        ).execute()
    else:
        params["test_duration"] = test_duration
    
    # Suavidad del cambio de cámara
    params["transition_smoothness"] = inquirer.select(
        message="Suavidad del cambio de cámara:",
        choices=[
            Choice("instantaneo", name="Instantáneo (sin transición)"),
            Choice("suave", name="Suave (0.5 segundos)"),
            Choice("muy_suave", name="Muy suave (1 segundo)")
        ],
        default="suave"
    ).execute()
    
    # Calidad de salida
    params["quality"] = inquirer.select(
        message="Calidad del video final:",
        choices=[
            Choice("baja", name="Baja (más rápido)"),
            Choice("media", name="Media (equilibrado)"),
            Choice("alta", name="Alta (mejor calidad)")
        ],
        default="media"
    ).execute()
    
    # Archivo de salida
    output_dir = inquirer.filepath(
        message="Directorio para guardar el video final:",
        only_directories=True,
        validate=PathValidator(is_dir=True, message="Debes seleccionar un directorio válido"),
    ).execute()
    
    output_filename = inquirer.text(
        message="Nombre del archivo de salida:",
        default="podcast_final.mp4",
        validate=lambda val: len(val) > 0 and val.endswith((".mp4", ".mov"))
    ).execute()
    
    params["output_file"] = os.path.join(output_dir, output_filename)
    
    return params

def try_convert_to_int(val):
    """Intenta convertir un valor a entero, retorna False si no es posible."""
    try:
        int(val)
        return True
    except (ValueError, TypeError):
        return False

def show_summary(files, params):
    """Muestra un resumen de los archivos y parámetros seleccionados."""
    console.print("\n[bold cyan]Resumen de configuración:[/]")
    
    console.print("\n[bold]Archivos seleccionados:[/]")
    console.print(f"- Video Speaker 1: [cyan]{files['video1']}[/]")
    console.print(f"- Video Speaker 2: [cyan]{files['video2']}[/]")
    console.print(f"- Audio Speaker 1: [cyan]{files['audio1']}[/]")
    console.print(f"- Audio Speaker 2: [cyan]{files['audio2']}[/]")
    
    console.print("\n[bold]Parámetros de procesamiento:[/]")
    console.print(f"- Modo prueba: [cyan]{'Sí' if params['test_mode'] else 'No'}[/]")
    if params["test_mode"]:
        console.print(f"- Duración prueba: [cyan]{params['test_duration']} segundos[/]")
    console.print(f"- Suavidad cambio: [cyan]{params['transition_smoothness']}[/]")
    console.print(f"- Calidad: [cyan]{params['quality']}[/]")
    console.print(f"- Archivo salida: [cyan]{params['output_file']}[/]")
    
    console.print() 