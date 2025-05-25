import os
import click
from rich.console import Console
from rich.progress import Progress
from InquirerPy import inquirer
from InquirerPy.validator import PathValidator
from InquirerPy.base.control import Choice

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
    
    # Simulación de procesamiento
    with Progress() as progress:
        task = progress.add_task("[cyan]Procesando...", total=100)
        
        # Aquí se llamaría al procesamiento real
        for i in range(101):
            # Simular trabajo
            progress.update(task, completed=i)
            # Aquí iría el procesamiento real
    
    console.print("[bold green]¡Procesamiento completado con éxito![/]")
    console.print(f"Video final guardado en: [cyan]{params['output_file']}[/]")

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
            validate=lambda val: val >= 30 and val <= 1800,
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