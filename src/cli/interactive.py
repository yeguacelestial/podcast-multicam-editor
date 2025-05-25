import questionary
import os
from typing import Optional
from questionary import Style

# Estilo personalizado para questionary
custom_style = Style([
    ("qmark", "fg:#00cfff bold"),
    ("question", "bold"),
    ("answer", "fg:#f4d35e bold"),
    ("pointer", "fg:#00cfff bold"),
    ("highlighted", "fg:#00cfff bold"),
    ("selected", "fg:#00cfff bold"),
    ("separator", "fg:#6c6c6c"),
    ("instruction", "fg:#b5b5b5"),
    ("text", "fg:#ffffff"),
    ("disabled", "fg:#858585 italic")
])

ICONS = {
    "dir": "📁",
    "file": "📄",
    "up": "⬆️",
    "home": "🏠",
    "root": "🗂️"
}

def seleccionar_archivo(mensaje: str, directorio_inicial: Optional[str] = None) -> str:
    """
    Permite al usuario navegar y seleccionar un archivo desde el CLI con iconos y colores.
    """
    if directorio_inicial is None:
        directorio_inicial = os.getcwd()
    current_dir = directorio_inicial
    while True:
        archivos = os.listdir(current_dir)
        archivos.sort()
        opciones = []
        # Opciones de navegación
        if current_dir != "/":
            opciones.append(questionary.Choice(f"{ICONS['up']}  Subir nivel", value=".."))
        opciones.append(questionary.Choice(f"{ICONS['root']}  Ir a raíz (/)", value="/"))
        opciones.append(questionary.Choice(f"{ICONS['home']}  Ir a home (~)", value=os.path.expanduser("~")))
        # Directorios
        for d in archivos:
            if os.path.isdir(os.path.join(current_dir, d)):
                opciones.append(questionary.Choice(f"{ICONS['dir']}  {d}", value=os.path.join(current_dir, d)))
        # Archivos
        for f in archivos:
            if os.path.isfile(os.path.join(current_dir, f)):
                opciones.append(questionary.Choice(f"{ICONS['file']}  {f}", value=os.path.join(current_dir, f)))
        seleccion = questionary.select(
            f"{mensaje}\nDirectorio actual: {current_dir}",
            choices=opciones,
            style=custom_style
        ).ask()
        if seleccion is None:
            return ""
        if seleccion == "..":
            current_dir = os.path.dirname(current_dir)
            continue
        if seleccion == "/":
            current_dir = "/"
            continue
        if seleccion == os.path.expanduser("~"):
            current_dir = os.path.expanduser("~")
            continue
        if os.path.isdir(seleccion):
            current_dir = seleccion
            continue
        return seleccion

def menu_principal():
    print("Bienvenido al Podcast Multicam Editor (CLI Interactivo)")
    questionary.print("\nEste asistente te guiará paso a paso para seleccionar tus archivos y parámetros de edición.\n", style="bold")
    video1 = seleccionar_archivo("Selecciona el video del Speaker 1:")
    video2 = seleccionar_archivo("Selecciona el video del Speaker 2:")
    audio1 = seleccionar_archivo("Selecciona el audio MONO del Speaker 1:")
    audio2 = seleccionar_archivo("Selecciona el audio MONO del Speaker 2:")
    questionary.print(f"\nArchivos seleccionados:\n- Video Speaker 1: {video1}\n- Video Speaker 2: {video2}\n- Audio Speaker 1 (mono): {audio1}\n- Audio Speaker 2 (mono): {audio2}\n", style="bold")
    # Aquí continuarían los siguientes pasos del flujo interactivo

if __name__ == "__main__":
    menu_principal() 