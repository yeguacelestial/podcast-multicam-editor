# Podcast Multicam Editor

Herramienta de edición automática de podcasts multicámara que sincroniza videos de iPhone con audios mono de alta calidad y genera cambios automáticos de cámara basados en detección de speaker activo.

## Descripción

Podcast Multicam Editor automatiza el proceso de edición de podcasts que utilizan múltiples cámaras. El sistema toma como entrada:

- Videos de los participantes (iPhone u otras cámaras)
- Audios mono de alta calidad de cada participante (grabados por separado)

Y produce un video final con:

- Perfecta sincronización entre todas las fuentes
- Cambios automáticos de cámara basados en quién está hablando
- Corrección de drift temporal progresivo
- Subtítulos automáticos (opcional)
- Transcripción completa (opcional)

## Características Principales

- **Sincronización precisa**: Utiliza correlación cruzada, ventanas deslizantes y corrección de drift para una sincronización perfecta.
- **Detección de speaker activo**: Identifica automáticamente quién está hablando en cada momento.
- **Cambios automáticos de cámara**: Genera un timeline de edición basado en los speakers activos.
- **Interface de usuario intuitiva**: CLI interactivo con selección visual de archivos y opciones.
- **Transcripción automática**: Genera subtítulos y transcripciones completas usando Whisper.

## Instalación

### Requisitos previos

- Python 3.11+
- FFmpeg

### Crear entorno conda

```bash
# Clonar el repositorio
git clone https://github.com/yeguacelestial/podcast-multicam-editor.git
cd podcast-multicam-editor

# Crear entorno conda a partir del archivo environment.yml
conda env create -f environment.yml

# Activar el entorno
conda activate podcast-editor
```

## Uso

```bash
# Activar el entorno
conda activate podcast-editor

# Ejecutar la aplicación
python main.py
```

El CLI interactivo te guiará a través del proceso para seleccionar:

1. Videos de cada speaker
2. Audios mono de cada speaker
3. Opciones de procesamiento y edición
4. Ubicación del archivo final

## Módulos Implementados

### Sincronización de Audio/Video

El módulo de sincronización implementa un sistema de tres niveles para garantizar una perfecta sincronización:

1. **Sincronización inicial**: Encuentra el offset básico entre pistas de audio usando correlación cruzada.
2. **Detección y corrección de drift**: Identifica desviaciones progresivas en la sincronización a lo largo del tiempo.
3. **Ventanas deslizantes**: Corrige desfases puntuales dividiendo el audio en segmentos y sincronizando cada uno.

Estas tres capas se combinan para generar un timeline de sincronización altamente preciso que mantiene el audio y video perfectamente alineados incluso en grabaciones largas.

### Pruebas de Sincronización

Se incluye un script de prueba para verificar la precisión de la sincronización:

```bash
# Ejemplo básico
python tests/test_sync.py --reference audio_speaker1.wav --target video_speaker1.mp4 --extract

# Prueba completa
python tests/test_sync.py --reference audio_speaker1.wav --target video_speaker1.mp4 --extract --drift --windows --timeline --all
```

## Estado del Proyecto

- ✅ **Fase 1**: Setup y Configuración Inicial
- ✅ **Fase 2**: Análisis y Procesamiento de Audio con Whisper
- ✅ **Fase 3**: Sincronización de Audio/Video
- ⏳ **Fase 4**: Detección de Speaker Activo (en progreso)
- ⏳ **Fase 5**: Generación de Video Final (pendiente)
- ⏳ **Fase 6**: Optimización y Features Avanzadas (pendiente)

## Licencia

Este proyecto está bajo la Licencia MIT.
