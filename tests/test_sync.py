"""
Script de prueba para las funcionalidades de sincronización de audio/video.
Permite probar las funciones de offset, drift y timeline.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from rich.console import Console
from rich.progress import Progress

# Asegurar que podemos importar desde src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.audio.analyzer import validate_audio_file
from src.audio.extractor import extract_audio_from_video
from src.audio.synchronizer import (
    find_offset_between_audios, 
    calculate_drift, 
    sync_audio_with_windows,
    correct_offset_puntuales,
    generate_final_sync_timeline
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_sync")

# Consola para output rico
console = Console()

def test_initial_sync(reference_audio, target_audio):
    """Prueba la sincronización inicial entre dos audios."""
    console.print(f"\n[bold cyan]Probando sincronización inicial[/]")
    console.print(f"Referencia: [green]{Path(reference_audio).name}[/]")
    console.print(f"Target: [green]{Path(target_audio).name}[/]")
    
    with Progress() as progress:
        try:
            # Calcular offset inicial
            result = find_offset_between_audios(
                reference_audio,
                target_audio,
                max_offset_seconds=60.0,
                progress=progress
            )
            
            # Mostrar resultados
            console.print("\n[bold green]Resultados:[/]")
            console.print(f"Offset: [green]{result['offset_seconds']:.3f} segundos[/]")
            console.print(f"Confianza: [green]{result['confidence_score']:.4f}[/]")
            
            return result
            
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/]")
            return None

def test_drift_calculation(reference_audio, target_audio, initial_offset):
    """Prueba el cálculo de drift entre dos audios."""
    console.print(f"\n[bold cyan]Probando cálculo de drift[/]")
    console.print(f"Referencia: [green]{Path(reference_audio).name}[/]")
    console.print(f"Target: [green]{Path(target_audio).name}[/]")
    console.print(f"Offset inicial: [green]{initial_offset:.3f} segundos[/]")
    
    with Progress() as progress:
        try:
            # Calcular drift
            result = calculate_drift(
                reference_audio,
                target_audio,
                initial_offset,
                window_size_seconds=30.0,
                step_size_seconds=15.0,
                progress=progress
            )
            
            # Mostrar resultados
            console.print("\n[bold green]Resultados:[/]")
            console.print(f"Drift rate: [green]{result['drift_rate']:.6f} seg/seg[/]")
            console.print(f"Ventanas analizadas: [green]{result['num_windows']}[/]")
            
            # Mostrar muestras de offsets
            if len(result['timestamps']) > 0:
                console.print("\n[bold]Muestras de offsets:[/]")
                
                num_samples = min(5, len(result['timestamps']))
                for i in range(num_samples):
                    idx = i * len(result['timestamps']) // num_samples
                    timestamp = result['timestamps'][idx]
                    offset = result['offsets'][idx]
                    console.print(f"- Tiempo {timestamp:.1f}s: Offset {offset:.3f}s")
            
            return result
            
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/]")
            return None

def test_window_sync(reference_audio, target_audio):
    """Prueba la sincronización con ventanas deslizantes."""
    console.print(f"\n[bold cyan]Probando sincronización con ventanas[/]")
    console.print(f"Referencia: [green]{Path(reference_audio).name}[/]")
    console.print(f"Target: [green]{Path(target_audio).name}[/]")
    
    with Progress() as progress:
        try:
            # Calcular sincronización por ventanas
            result = sync_audio_with_windows(
                reference_audio,
                target_audio,
                window_size_seconds=20.0,
                overlap_seconds=5.0,
                max_offset_seconds=2.0,
                progress=progress
            )
            
            # Aplicar corrección de desfases puntuales
            corrected_map = correct_offset_puntuales(
                result["sync_map"],
                smoothing_window=5
            )
            
            # Mostrar resultados
            console.print("\n[bold green]Resultados:[/]")
            console.print(f"Ventanas analizadas: [green]{result['num_windows']}[/]")
            console.print(f"Offset promedio: [green]{result['average_offset']:.3f} segundos[/]")
            console.print(f"Desviación estándar: [green]{result['std_offset']:.3f} segundos[/]")
            
            # Mostrar correcciones
            corrected_count = sum(1 for point in corrected_map if point.get("is_corrected", False))
            console.print(f"Puntos corregidos: [green]{corrected_count}[/] de {len(corrected_map)}")
            
            # Actualizar el resultado con el mapa corregido
            result["sync_map"] = corrected_map
            return result
            
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/]")
            return None

def test_timeline_generation(reference_audio, target_audio, initial_sync_result, drift_result=None, window_sync_result=None):
    """Prueba la generación del timeline final."""
    console.print(f"\n[bold cyan]Probando generación de timeline[/]")
    console.print(f"Referencia: [green]{Path(reference_audio).name}[/]")
    console.print(f"Target: [green]{Path(target_audio).name}[/]")
    
    with Progress() as progress:
        try:
            # Generar timeline
            result = generate_final_sync_timeline(
                reference_audio,
                target_audio,
                initial_sync_result,
                drift_result,
                window_sync_result,
                sync_interval=1.0,  # Un punto por segundo
                progress=progress
            )
            
            # Mostrar resultados
            console.print("\n[bold green]Resultados:[/]")
            console.print(f"Puntos generados: [green]{result['num_points']}[/]")
            console.print(f"Duración de referencia: [green]{result['reference_duration']:.1f} segundos[/]")
            console.print(f"Intervalo entre puntos: [green]{result['sync_interval']:.1f} segundos[/]")
            
            # Mostrar muestras del timeline
            if len(result['timeline']) > 0:
                console.print("\n[bold]Muestras del timeline:[/]")
                
                num_samples = min(5, len(result['timeline']))
                for i in range(num_samples):
                    idx = i * len(result['timeline']) // num_samples
                    point = result['timeline'][idx]
                    console.print(f"- Ref {point['reference_time']:.1f}s → Target {point['target_time']:.1f}s (offset: {point['offset']:.3f}s)")
            
            return result
            
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/]")
            return None

def test_extract_audio(video_path):
    """Extrae audio de un video para pruebas."""
    console.print(f"\n[bold cyan]Extrayendo audio de video[/]")
    console.print(f"Video: [green]{Path(video_path).name}[/]")
    
    with Progress() as progress:
        try:
            # Extraer audio
            task_id = progress.add_task("[green]Extrayendo audio...", total=100)
            
            output_path = os.path.join(
                os.path.dirname(video_path),
                f"{Path(video_path).stem}_test_audio.wav"
            )
            
            audio_path = extract_audio_from_video(
                video_path,
                output_path,
                mono=True,
                progress=progress,
                task_id=task_id
            )
            
            console.print(f"Audio extraído: [green]{Path(audio_path).name}[/]")
            return audio_path
            
        except Exception as e:
            console.print(f"[bold red]Error: {str(e)}[/]")
            return None

def main():
    """Función principal para ejecutar las pruebas."""
    parser = argparse.ArgumentParser(description="Prueba de sincronización de audio/video")
    parser.add_argument("--reference", "-r", help="Ruta al audio de referencia", required=True)
    parser.add_argument("--target", "-t", help="Ruta al audio o video a sincronizar", required=True)
    parser.add_argument("--extract", "-e", action="store_true", help="Extraer audio del target si es video")
    parser.add_argument("--drift", "-d", action="store_true", help="Probar cálculo de drift")
    parser.add_argument("--windows", "-w", action="store_true", help="Probar sincronización por ventanas")
    parser.add_argument("--timeline", "-l", action="store_true", help="Probar generación de timeline")
    parser.add_argument("--all", "-a", action="store_true", help="Ejecutar todas las pruebas")
    
    args = parser.parse_args()
    
    # Validar archivos
    if not os.path.isfile(args.reference):
        console.print(f"[bold red]Error: Archivo de referencia no encontrado: {args.reference}[/]")
        return
    
    if not os.path.isfile(args.target):
        console.print(f"[bold red]Error: Archivo target no encontrado: {args.target}[/]")
        return
    
    console.print("[bold cyan]Test de Sincronización Audio/Video[/]")
    
    # Extraer audio si es necesario
    target_audio = args.target
    if args.extract or args.all:
        console.print("\n[bold]Paso 1: Extracción de audio[/]")
        target_audio = test_extract_audio(args.target) or args.target
    
    # Ejecutar sincronización inicial
    console.print("\n[bold]Paso 2: Sincronización inicial[/]")
    initial_sync = test_initial_sync(args.reference, target_audio)
    
    if not initial_sync:
        console.print("[bold red]Error en sincronización inicial. Abortando pruebas.[/]")
        return
    
    # Calcular drift
    drift_result = None
    if args.drift or args.all:
        console.print("\n[bold]Paso 3: Cálculo de drift[/]")
        drift_result = test_drift_calculation(
            args.reference,
            target_audio,
            initial_sync["offset_seconds"]
        )
    
    # Sincronización por ventanas
    window_result = None
    if args.windows or args.all:
        console.print("\n[bold]Paso 4: Sincronización por ventanas[/]")
        window_result = test_window_sync(args.reference, target_audio)
    
    # Generar timeline
    if args.timeline or args.all:
        console.print("\n[bold]Paso 5: Generación de timeline[/]")
        timeline_result = test_timeline_generation(
            args.reference,
            target_audio,
            initial_sync,
            drift_result,
            window_result
        )
    
    console.print("\n[bold green]Pruebas completadas[/]")

if __name__ == "__main__":
    # Ejemplo de uso rápido si no se proporcionan argumentos
    if len(sys.argv) == 1:
        print("Uso rápido con archivos de ejemplo:")
        print("  python tests/test_sync.py --reference media/carlos_mono.mp3 --target media/carlos.mp4 --all")
        print("\nPara ver todas las opciones disponibles:")
        print("  python tests/test_sync.py --help")
        sys.exit(0)
        
    main() 