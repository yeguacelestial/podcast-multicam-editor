#!/usr/bin/env python
import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.cli.commands import (
    process_command, 
    generate_command, 
    quick_test_command, 
    simple_test_command,
    ultra_simple_test_command,
    resume_command,
    inspect_timeline_command
)

console = Console()

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """CULTURAMA Podcast Multicam Editor - Automatización de edición de podcasts."""
    # Mostrar banner solo si se ejecuta sin subcomando
    if ctx.invoked_subcommand is None:
        show_welcome_banner()
        # Si no hay subcomando, ejecutar el comando de procesamiento por defecto
        ctx.invoke(process_command)

def show_welcome_banner():
    """Muestra un banner de bienvenida con estilo."""
    title = Text("CULTURAMA", style="bold cyan")
    title.append(" podcast editor", style="bold white")
    
    description = Text("\nAutomatización de edición de podcast multicámara")
    description.append("\nSincronización de video y cambios automáticos basados en detección de audio")
    
    panel = Panel(
        Text.assemble(title, "\n", description),
        border_style="cyan",
        expand=False,
        padding=(1, 2)
    )
    
    console.print(panel)
    console.print("\n")

# Registrar los comandos disponibles
cli.add_command(process_command)
cli.add_command(generate_command)
cli.add_command(quick_test_command)
cli.add_command(simple_test_command)
cli.add_command(ultra_simple_test_command)
cli.add_command(resume_command)
cli.add_command(inspect_timeline_command)

if __name__ == "__main__":
    cli() 