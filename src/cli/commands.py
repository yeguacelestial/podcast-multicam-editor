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
@click.option("--preview", is_flag=True, help="Ejecutar en modo preview (procesa solo los primeros N minutos)")
@click.option("--preview-duration", type=int, default=5, help="Duración en minutos para el modo preview")
def process_command(preview, preview_duration):
    """Procesar videos y audios para generar video multicámara automático."""
    # Selección de archivos con InquirerPy
    files = select_input_files()
    
    if not all(files.values()):
        console.print("[bold red]Proceso cancelado: no se seleccionaron todos los archivos requeridos.[/]")
        return
    
    # Selección de parámetros
    params = select_processing_parameters(preview, preview_duration)
    
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
            
        # Cortar archivos si estamos en modo preview (mover al inicio para procesar solo el fragmento)
        if params["preview_mode"]:
            from src.video.processor import cut_video_for_preview
            
            console.log(f"[cyan]Modo preview activado: procesando solo los primeros {params['preview_duration']} minutos[/]")
            preview_task = progress.add_task("[green]Preparando archivos para preview...", total=4)
            
            # Cortar videos para preview
            video1_preview = cut_video_for_preview(
                files["video1"],
                f"{os.path.splitext(files['video1'])[0]}_preview.mp4",
                duration_minutes=params["preview_duration"],
                log_progress=True
            )
            progress.update(preview_task, advance=1)
            
            video2_preview = cut_video_for_preview(
                files["video2"],
                f"{os.path.splitext(files['video2'])[0]}_preview.mp4",
                duration_minutes=params["preview_duration"],
                log_progress=True
            )
            progress.update(preview_task, advance=1)
            
            # Actualizar rutas de video
            files["video1"] = video1_preview
            files["video2"] = video2_preview
            
            # Cortar audios para preview
            audio1_preview = cut_video_for_preview(
                files["audio1"],
                f"{os.path.splitext(files['audio1'])[0]}_preview.wav",
                duration_minutes=params["preview_duration"],
                log_progress=True
            )
            progress.update(preview_task, advance=1)
            
            audio2_preview = cut_video_for_preview(
                files["audio2"],
                f"{os.path.splitext(files['audio2'])[0]}_preview.wav",
                duration_minutes=params["preview_duration"],
                log_progress=True
            )
            progress.update(preview_task, advance=1)
            
            # Actualizar rutas de audio
            files["audio1"] = audio1_preview
            files["audio2"] = audio2_preview
            
            console.log(f"[cyan]Archivos preparados para preview de {params['preview_duration']} minutos[/]")
        
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
        
        # Fase 8: Procesar segmentos de speaker para generar cambios de cámara
        progress.update(main_task, advance=10, description="[cyan]Procesando cambios de cámara...")
        
        from src.video.processor import (
            normalize_audio, 
            mix_audio_tracks
        )
        from src.video.composer import process_camera_changes
        
        # Preparar audio maestro según la selección del usuario
        audio_master_task = progress.add_task("[green]Preparando audio maestro...", total=100)
        
        try:
            # Crear audio maestro
            import tempfile
            temp_dir = tempfile.mkdtemp()
            
            if params["audio_mix"] == "speaker1":
                # Usar audio del Speaker 1 normalizado
                audio_master_path = os.path.join(temp_dir, "audio_master.wav")
                console.log(f"[cyan]Normalizando audio del Speaker 1...[/]")
                normalize_audio(
                    files["audio1"],
                    audio_master_path,
                    target_level=-23.0,
                    log_progress=True
                )
            elif params["audio_mix"] == "speaker2":
                # Usar audio del Speaker 2 normalizado
                audio_master_path = os.path.join(temp_dir, "audio_master.wav")
                console.log(f"[cyan]Normalizando audio del Speaker 2...[/]")
                normalize_audio(
                    files["audio2"],
                    audio_master_path,
                    target_level=-23.0,
                    log_progress=True
                )
            else:
                # Mezclar ambos audios con los volúmenes seleccionados
                audio_master_path = os.path.join(temp_dir, "audio_master.wav")
                console.log(f"[cyan]Mezclando audios (Speaker 1: {params['speaker1_volume']}, Speaker 2: {params['speaker2_volume']})...[/]")
                mix_audio_tracks(
                    [files["audio1"], files["audio2"]],
                    audio_master_path,
                    volumes=[params["speaker1_volume"], params["speaker2_volume"]],
                    normalize_output=True,
                    log_progress=True
                )
            
            # Verificar que el archivo se creó correctamente
            if not os.path.exists(audio_master_path):
                raise ValueError(f"El archivo de audio maestro no se generó correctamente: {audio_master_path}")
            
            file_size = os.path.getsize(audio_master_path)
            console.log(f"[green]Audio maestro generado: {audio_master_path} ({file_size/1024/1024:.2f} MB)[/]")
            
            progress.update(audio_master_task, completed=100)
        except Exception as e:
            progress.update(audio_master_task, completed=0, description="[bold red]Error en audio maestro")
            console.print(f"\n[bold red]Error al preparar audio maestro: {str(e)}[/]")
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/]")
            
            # Información de diagnóstico específica para audio
            console.print("\n[bold yellow]Información de diagnóstico de audio:[/]")
            console.print(f"- Audio Speaker 1: {files['audio1']} (existe: {os.path.exists(files['audio1'])})")
            console.print(f"- Audio Speaker 2: {files['audio2']} (existe: {os.path.exists(files['audio2'])})")
            console.print(f"- Modo de mezcla: {params['audio_mix']}")
            
            if params['audio_mix'] == 'mix':
                console.print(f"- Volumen Speaker 1: {params['speaker1_volume']}")
                console.print(f"- Volumen Speaker 2: {params['speaker2_volume']}")
            
            console.print(f"- Directorio temporal: {temp_dir} (existe: {os.path.exists(temp_dir)})")
            
            # Comprobar permisos del directorio temporal
            try:
                test_file = os.path.join(temp_dir, "test.txt")
                with open(test_file, 'w') as f:
                    f.write("test")
                console.print(f"- Permisos de escritura en directorio temporal: Sí")
                os.remove(test_file)
            except Exception as perm_error:
                console.print(f"- Permisos de escritura en directorio temporal: No ({str(perm_error)})")
            
            # Comprobar espacio disponible
            try:
                import shutil
                total, used, free = shutil.disk_usage(temp_dir)
                console.print(f"- Espacio disponible: {free/1024/1024/1024:.2f} GB")
            except:
                console.print("- No se pudo determinar el espacio disponible")
            
            # No continuar con el resto del código
            return
        
        # Generar video final con cambios de cámara
        video_task = progress.add_task("[green]Generando video final...", total=100)
        
        # Crear diccionario de videos por speaker
        video_paths = {
            "speaker1": files["video1"],
            "speaker2": files["video2"]
        }
        
        try:
            # Crear lista de segmentos
            console.log("[cyan]Preparando segmentos para cambios de cámara...[/]")
            all_segments = []
            
            # Añadir segmentos del speaker 1
            for segment in vad1_result["segments"]:
                all_segments.append({
                    "speaker_id": "speaker1",
                    "start_time": segment["start"],
                    "end_time": segment["end"]
                })
            
            # Añadir segmentos del speaker 2
            for segment in vad2_result["segments"]:
                all_segments.append({
                    "speaker_id": "speaker2",
                    "start_time": segment["start"],
                    "end_time": segment["end"]
                })
            
            # Ordenar todos los segmentos por tiempo de inicio
            all_segments.sort(key=lambda x: x["start_time"])
            
            # Verificar que los segmentos sean válidos
            if not all_segments:
                raise ValueError("No se generaron segmentos para los cambios de cámara")
            
            # Eliminar segmentos con duración no positiva
            valid_segments = [seg for seg in all_segments if seg["end_time"] > seg["start_time"]]
            
            if len(valid_segments) != len(all_segments):
                console.log(f"[yellow]Advertencia: Se eliminaron {len(all_segments) - len(valid_segments)} segmentos con duración no positiva[/]")
                all_segments = valid_segments
            
            if not all_segments:
                raise ValueError("Todos los segmentos tenían duración no positiva")
            
            # Mostrar estadísticas de segmentos
            speaker1_count = sum(1 for seg in all_segments if seg["speaker_id"] == "speaker1")
            speaker2_count = sum(1 for seg in all_segments if seg["speaker_id"] == "speaker2")
            
            console.log(f"[green]Segmentos preparados: {len(all_segments)} total (Speaker 1: {speaker1_count}, Speaker 2: {speaker2_count})[/]")
            
            # Verificar que los videos existan
            for speaker_id, video_path in video_paths.items():
                if not os.path.exists(video_path):
                    raise ValueError(f"El video para {speaker_id} no existe: {video_path}")
            
            console.log(f"[green]Videos verificados: todos los archivos existen[/]")
        
        except Exception as e:
            progress.update(video_task, completed=0, description="[bold red]Error en segmentos")
            console.print(f"\n[bold red]Error al preparar segmentos: {str(e)}[/]")
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/]")
            
            # Información de diagnóstico
            console.print("\n[bold yellow]Información de diagnóstico de segmentos:[/]")
            console.print(f"- VAD Speaker 1: {vad1_result['num_segments']} segmentos")
            console.print(f"- VAD Speaker 2: {vad2_result['num_segments']} segmentos")
            
            if all_segments:
                console.print(f"- Total segmentos combinados: {len(all_segments)}")
                console.print(f"- Primer segmento: {all_segments[0]}")
                console.print(f"- Último segmento: {all_segments[-1]}")
            else:
                console.print("- No hay segmentos combinados")
            
            # Salir del procesamiento
            return
        
        try:
            # Procesar cambios de cámara y generar video final
            console.log("[cyan]Generando video final con cambios de cámara...[/]")
            final_video_path = process_camera_changes(
                speaker_segments=all_segments,
                video_paths=video_paths,
                audio_master_path=audio_master_path,
                output_path=params["output_file"],
                preview_mode=params["preview_mode"],
                preview_duration=params["preview_duration"],
                min_segment_duration=1.0,  # Mínimo 1 segundo por plano
                transition_type=params["transition_type"],
                output_quality=params["output_quality"],
                log_progress=True,
                progress=progress,
                task_id=video_task
            )
            
            progress.update(video_task, completed=100)
            progress.update(main_task, completed=100, description="[bold green]¡Procesamiento completado!")
            
            # Mostrar resumen final
            console.print("\n[bold green]¡Procesamiento completado exitosamente![/]")
            console.print(f"Video final guardado en: [cyan]{final_video_path}[/]")
            
            # Si estamos en modo preview, recordar al usuario
            if params["preview_mode"]:
                console.print(f"[bold yellow]NOTA: Este es un preview de {params['preview_duration']} minutos.[/]")
                console.print("Para procesar el video completo, ejecuta de nuevo sin la opción --preview.")
            
            # Mostrar resultados
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
            
            console.print(f"\nVideo final guardado en: [cyan]{final_video_path}[/]")
            
        except Exception as e:
            progress.update(video_task, completed=0, description="[bold red]Error")
            progress.update(main_task, completed=0, description="[bold red]Error en el procesamiento")
            console.print(f"\n[bold red]Error al generar el video final: {str(e)}[/]")
            import traceback
            console.print(f"[red]{traceback.format_exc()}[/]")
            
            # Mostrar información adicional de diagnóstico
            console.print("\n[bold yellow]Información de diagnóstico:[/]")
            console.print(f"- Número total de segmentos: {len(all_segments)}")
            if all_segments:
                console.print(f"- Primer segmento: {all_segments[0]}")
                console.print(f"- Último segmento: {all_segments[-1]}")
            console.print(f"- Rutas de video: {video_paths}")
            console.print(f"- Audio maestro: {audio_master_path}")
            console.print(f"- Modo preview: {params['preview_mode']}")
            console.print(f"- Duración preview: {params['preview_duration']} minutos")
            console.print(f"- Transición: {params['transition_type']}")
            console.print(f"- Calidad: {params['output_quality']}")
            
            # No continuar con el resto del código
            return
            
        finally:
            # Limpiar archivos temporales
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass
    
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

def select_processing_parameters(preview_mode, preview_duration):
    """Permite al usuario seleccionar los parámetros de procesamiento."""
    params = {}
    
    # Modo preview
    params["preview_mode"] = preview_mode or inquirer.confirm(
        message="¿Ejecutar en modo preview? (solo procesará los primeros minutos)",
        default=False
    ).execute()
    
    # Duración de preview
    if params["preview_mode"] and not preview_mode:
        params["preview_duration"] = inquirer.number(
            message="Duración del preview (minutos):",
            min_allowed=1,
            max_allowed=30,
            default=preview_duration,
            transformer=try_convert_to_int
        ).execute()
    else:
        params["preview_duration"] = preview_duration
    
    # Tipo de transición
    params["transition_type"] = inquirer.select(
        message="Selecciona el tipo de transición entre cámaras:",
        choices=[
            Choice(value="cut", name="Corte directo (instantáneo)"),
            Choice(value="dissolve", name="Fundido suave (0.5 segundos)"),
            Choice(value="fade", name="Fundido lento (1 segundo)")
        ],
        default="cut"
    ).execute()
    
    # Calidad de salida
    params["output_quality"] = inquirer.select(
        message="Selecciona la calidad del video final:",
        choices=[
            Choice(value="high", name="Alta (1080p, mejor calidad)"),
            Choice(value="medium", name="Media (720p, calidad estándar)"),
            Choice(value="low", name="Baja (480p, procesamiento más rápido)")
        ],
        default="high"
    ).execute()
    
    # Mezcla de audio
    params["audio_mix"] = inquirer.select(
        message="Selecciona el tipo de audio para el video final:",
        choices=[
            Choice(value="speaker1", name="Usar audio del Speaker 1"),
            Choice(value="speaker2", name="Usar audio del Speaker 2"),
            Choice(value="mix", name="Mezclar ambos audios (normalizado)")
        ],
        default="mix"
    ).execute()
    
    # Si se eligió mezclar, preguntar por volúmenes
    if params["audio_mix"] == "mix":
        params["speaker1_volume"] = inquirer.number(
            message="Volumen para Speaker 1 (0.0-2.0):",
            min_allowed=0.0,
            max_allowed=2.0,
            default=1.0,
            float_allowed=True
        ).execute()
        
        params["speaker2_volume"] = inquirer.number(
            message="Volumen para Speaker 2 (0.0-2.0):",
            min_allowed=0.0,
            max_allowed=2.0,
            default=1.0,
            float_allowed=True
        ).execute()
    
    # Archivo de salida
    output_dir = inquirer.filepath(
        message="Selecciona la ubicación del video final:",
        only_directories=True,
        default=".",
        transformer=lambda result: os.path.abspath(result)
    ).execute()
    
    output_filename = "podcast_final.mp4"
    params["output_file"] = os.path.join(output_dir, output_filename)
    
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
    
    if params["preview_mode"]:
        console.print(f"- Modo preview: [yellow]Activado[/] (primeros {params['preview_duration']} minutos)")
    else:
        console.print("- Modo preview: [green]Desactivado[/] (procesamiento completo)")
    
    # Tipo de transición
    transition_names = {
        "cut": "Corte directo (instantáneo)",
        "dissolve": "Fundido suave (0.5 segundos)",
        "fade": "Fundido lento (1 segundo)"
    }
    console.print(f"- Transición: [green]{transition_names[params['transition_type']]}[/]")
    
    # Calidad de salida
    quality_names = {
        "high": "Alta (1080p, mejor calidad)",
        "medium": "Media (720p, calidad estándar)",
        "low": "Baja (480p, procesamiento más rápido)"
    }
    console.print(f"- Calidad: [green]{quality_names[params['output_quality']]}[/]")
    
    # Audio
    if params["audio_mix"] == "speaker1":
        console.print("- Audio: [green]Speaker 1[/]")
    elif params["audio_mix"] == "speaker2":
        console.print("- Audio: [green]Speaker 2[/]")
    else:
        console.print(f"- Audio: [green]Mezcla (Speaker 1: {params['speaker1_volume']}, Speaker 2: {params['speaker2_volume']})[/]")
    
    # Subtítulos y transcripción
    console.print(f"- Subtítulos: [green]{'Activados' if params['add_subtitles'] else 'Desactivados'}[/]")
    console.print(f"- Transcripción: [green]{'Activada' if params['export_transcript'] else 'Desactivada'}[/]")
    
    # Archivo de salida
    console.print(f"\n- Archivo de salida: [cyan]{params['output_file']}[/]")
    console.print("") 