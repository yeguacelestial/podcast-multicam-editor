# Plan de Acción: Podcast Multicam Editor (Actualizado)

## Resumen del Proyecto
Automatizar la edición de podcasts multicámara utilizando un CLI interactivo en Python, sincronizando videos de iPhone con audios mono de alta calidad (uno por speaker) y generando cambios automáticos de cámara basados en detección de speaker activo.

## Arquitectura del Sistema

### Tecnologías Principales
- **Python 3.11+** con conda environment
- **FFmpeg** para procesamiento de audio/video de bajo nivel
- **MoviePy** para edición y composición de video
- **Librosa** para análisis de audio y sincronización
- **Whisper** para transcripción, detección de actividad vocal e identificación de speakers
- **Click** para CLI base
- **InquirerPy** para selección interactiva de archivos y parámetros
- **Rich** para visualización mejorada (progreso, logs, etc.)
- **NumPy/SciPy** para análisis de señales

### Flujo del Proceso Interactivo
1. **Inicio del CLI**: Banner de bienvenida "CULTURAMA podcast editor" y menú interactivo.
2. **Selección de archivos**: Navegador de archivos profesional con InquirerPy, permitiendo navegación completa y validación de archivos. El usuario debe seleccionar:
   - Video del Speaker 1
   - Video del Speaker 2
   - Audio mono del Speaker 1
   - Audio mono del Speaker 2
3. **Parámetros de procesamiento**: Selección de suavidad del cambio de cámara (opciones: instantáneo, suave, muy suave), duración de preview, calidad de salida, y ubicación del archivo final.
4. **Confirmación de configuración**: Resumen visual de todos los archivos y parámetros seleccionados con confirmación.
5. **Procesamiento y feedback**: Barra de progreso con Rich y logs detallados durante el proceso.
6. **Entrega de resultados**: Mensaje de éxito y ruta del video final generado.

---

## FASE 1: Setup y Configuración Inicial
**Objetivo:** Establecer el entorno de desarrollo y estructura básica del proyecto

### Tareas:
- [x] **1.1** Crear entorno conda `podcast-editor`
- [x] **1.2** Instalar dependencias principales (ffmpeg, librosa, moviepy, click, InquirerPy, Rich, Whisper)
- [x] **1.3** Crear estructura de carpetas del proyecto
- [x] **1.4** Implementar CLI base con Click e InquirerPy
- [x] **1.5** Crear utilities para validación de archivos de entrada
- [x] **1.6** Implementar logging y configuración

### Entregables:
- ✅ Entorno conda funcional
- ✅ CLI interactivo profesional con selección visual de archivos y parámetros
- ✅ Estructura de proyecto organizada
- ✅ Sistema de validación de archivos y logging

### Testing:
```bash
python main.py
# El CLI muestra el banner CULTURAMA y guía interactivamente por todo el proceso
```

---

## FASE 2: Análisis y Procesamiento de Audio con Whisper
**Objetivo:** Procesar y analizar los audios mono de cada speaker utilizando Whisper para simplificar el proceso

### Tareas:
- [x] **2.1** Validar y cargar los archivos de audio mono de cada speaker
- [x] **2.2** Extraer audio de videos de iPhone (si es necesario) usando FFmpeg
- [x] **2.3** Implementar transcripción y detección de actividad vocal con Whisper
- [x] **2.4** Utilizar Whisper para identificación automática de speakers
- [x] **2.5** Crear sistema de análisis de segmentación temporal para cada speaker

### Entregables:
- ✅ Función de validación y carga de audios mono
- ✅ Extractor de audio de videos (opcional)
- ✅ Sistema de transcripción y detección de speaker con Whisper
- ✅ Segmentación temporal precisa por speaker
- ✅ Generación de subtítulos y archivos de transcripción

### Archivos Implementados:
- `src/transcription/whisper_transcriber.py`: Módulo para transcripción de audio y detección de speakers
- `src/transcription/subtitle_generator.py`: Módulo para generación de subtítulos y transcripciones

### Testing:
- Seleccionar archivos desde el CLI y verificar la identificación correcta de speakers y segmentos de voz

---

## FASE 3: Sincronización de Audio/Video
**Objetivo:** Sincronizar videos con los audios mono usando cross-correlation

### Tareas:
- [ ] **3.1** Implementar cross-correlation para encontrar offset inicial
- [ ] **3.2** Detectar y corregir drift temporal progresivo
- [ ] **3.3** Crear sistema de ventanas deslizantes para re-sincronización
- [ ] **3.4** Implementar corrección de desfases puntuales
- [ ] **3.5** Generar timeline sincronizado

### Entregables:
- ✅ Algoritmo de sincronización robusto
- ✅ Sistema de corrección de drift
- ✅ Timeline sincronizado de audio/video

### Testing:
- Opción de preview de 5 minutos desde el CLI para validar sincronización

---

## FASE 4: Detección de Speaker Activo
**Objetivo:** Identificar quién está hablando en cada momento para cambios de cámara

### Tareas:
- [x] **4.1** Utilizar resultados de Whisper para identificación precisa de speaker activo
- [ ] **4.2** Analizar energía por pista para refinar la detección de Whisper
- [ ] **4.3** Implementar filtros para evitar cambios muy rápidos
- [ ] **4.4** Crear sistema de transiciones suaves (ajustable por usuario) con MoviePy
- [ ] **4.5** Manejar casos de overlap de speakers

### Entregables:
- ✅ Sistema de detección de speaker confiable
- ✅ Timeline de cambios de cámara
- ✅ Configuración de sensibilidad ajustable desde el CLI

### Testing:
- Selección de sensibilidad de cambio de cámara desde el CLI y verificación de resultados

---

## FASE 5: Generación de Video Final
**Objetivo:** Componer el video final con cambios automáticos de cámara

### Tareas:
- [ ] **5.1** Implementar sistema de cortes de video basado en timeline con MoviePy
- [ ] **5.2** Sincronizar audio maestro con video resultante
- [ ] **5.3** Manejar casos de video faltante (mostrar cámara disponible)
- [ ] **5.4** Optimizar renderizado para videos largos (1-2 horas) con procesamiento por chunks
- [ ] **5.5** Agregar metadatos y configuraciones de calidad usando FFmpeg

### Entregables:
- ✅ Video final sincronizado
- ✅ Sistema optimizado para archivos grandes
- ✅ Configuraciones de calidad ajustables desde el CLI

### Testing:
- Proceso completo desde el CLI, con feedback y barra de progreso

---

## FASE 6: Optimización y Features Avanzadas
**Objetivo:** Pulir el sistema y agregar características adicionales

### Tareas:
- [ ] **6.1** Implementar preview de 5 minutos para testing rápido
- [ ] **6.2** Optimizar rendimiento para archivos grandes
- [ ] **6.3** Agregar configuraciones avanzadas (sensibilidad, transiciones)
- [ ] **6.4** Implementar resumenes y reportes de procesamiento
- [x] **6.5** Generar subtítulos automáticos utilizando transcripciones de Whisper
- [x] **6.6** Agregar opción para exportar transcripción completa del podcast
- [ ] **6.7** Crear documentación completa de uso

### Entregables:
- ✅ Sistema completo optimizado
- ✅ Funcionalidad de subtitulado automático
- ✅ Exportación de transcripciones
- ✅ Documentación de usuario
- ✅ Configuraciones avanzadas

### Testing:
- Pruebas de preview y procesamiento completo desde el CLI
- Verificación de calidad de subtítulos y transcripciones

---

## Estructura Final del Proyecto

```
podcast-multicam-editor/
├── environment.yml
├── main.py
├── src/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── commands.py
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   ├── synchronizer.py
│   │   └── analyzer.py
│   ├── video/
│   │   ├── __init__.py
│   │   ├── processor.py
│   │   └── composer.py
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── vad.py
│   │   └── speaker.py
│   ├── transcription/
│   │   ├── __init__.py
│   │   ├── whisper_transcriber.py
│   │   └── subtitle_generator.py
│   └── utils/
│       ├── __init__.py
│       ├── validation.py
│       └── logging.py
├── tests/
├── configs/
├── docs/
└── README.md
```

## Comandos CLI Finales

El usuario solo ejecuta:
```bash
python main.py
```
Y el sistema muestra un banner "CULTURAMA podcast editor" y lo guía paso a paso con una interfaz visual para seleccionar archivos, parámetros y procesar el video.

## Consideraciones de Rendimiento

1. **Procesamiento por chunks** para archivos grandes
2. **Multithreading** para operaciones paralelas
3. **Caching** de resultados intermedios
4. **Optimización de memoria** para videos largos
5. **Progress tracking** detallado para el usuario con Rich
6. **Selección de modelo de Whisper** según recursos disponibles (tiny, base, small, medium)

## Métricas de Éxito

- [ ] Sincronización precisa (< 100ms de error)
- [ ] Detección de speaker > 95% precisión
- [ ] Procesamiento eficiente (< 2x tiempo real para video final)
- [ ] Sistema robusto ante variaciones de duración
- [ ] Interface intuitiva y fácil de usar
- [ ] Transcripción con > 90% de precisión

## Módulos implementados

### Módulo de transcripción

El módulo de transcripción implementado con Whisper ofrece las siguientes funcionalidades:

1. **Transcripción de audio**: Convierte audio en texto con alta precisión.
2. **Detección de speakers**: Identifica quién está hablando en cada momento.
3. **Segmentación temporal**: Genera líneas de tiempo precisas para cada intervención.
4. **Generación de subtítulos**: Crea archivos SRT y VTT para uso en reproductores.
5. **Exportación de transcripciones**: Genera archivos de texto plano con la transcripción completa.

El módulo se ha diseñado con las siguientes ventajas:

- **Escalabilidad**: Soporta diferentes tamaños de modelos de Whisper según los recursos disponibles.
- **Multilingüe**: Funciona con cualquier idioma soportado por Whisper.
- **Barra de progreso**: Proporciona feedback visual al usuario durante el procesamiento.
- **Manejo de errores**: Sistema robusto con gestión de excepciones y logging detallado.
- **Resolución de solapamientos**: Algoritmo para manejar cuando dos speakers hablan simultáneamente. 