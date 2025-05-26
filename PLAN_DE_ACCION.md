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
- [x] **3.1** Implementar cross-correlation para encontrar offset inicial
- [x] **3.2** Detectar y corregir drift temporal progresivo
- [x] **3.3** Crear sistema de ventanas deslizantes para re-sincronización
- [x] **3.4** Implementar corrección de desfases puntuales
- [x] **3.5** Generar timeline sincronizado

### Entregables:
- ✅ Algoritmo de sincronización robusto
- ✅ Sistema de corrección de drift
- ✅ Timeline sincronizado de audio/video

### Archivos Implementados:
- `src/audio/synchronizer.py`: Módulo principal de sincronización con funciones para offset inicial, drift y timeline
- `tests/test_sync.py`: Script de prueba para verificar funciones de sincronización

### Testing:
```bash
# Ejecutar pruebas de sincronización
python tests/test_sync.py --reference audio_speaker1.wav --target video_speaker1.mp4 --all
```

---

## FASE 4: Detección de Speaker Activo
**Objetivo:** Identificar quién está hablando en cada momento para cambios de cámara

### Tareas:
- [x] **4.1** Utilizar resultados de Whisper para identificación precisa de speaker activo
- [x] **4.2** Analizar energía por pista para refinar la detección de Whisper
- [x] **4.3** Implementar filtros para evitar cambios muy rápidos
- [x] **4.4** Crear sistema de transiciones suaves (ajustable por usuario) con MoviePy
- [x] **4.5** Manejar casos de overlap de speakers

### Entregables:
- ✅ Sistema de detección de speaker confiable
- ✅ Timeline de cambios de cámara
- ✅ Configuración de sensibilidad ajustable desde el CLI

### Archivos Implementados:
- `src/detection/speaker.py`: Módulo para detección de speaker activo, análisis de energía y manejo de solapamientos
- `src/detection/vad.py`: Módulo para detección de actividad vocal

### Testing:
- Selección de sensibilidad de cambio de cámara desde el CLI y verificación de resultados

---

## FASE 5: Generación de Video Final
**Objetivo:** Componer el video final con cambios automáticos de cámara

### Tareas:
- [x] **5.1** Implementar sistema de cortes de video basado en timeline con MoviePy
- [x] **5.2** Sincronizar audio maestro con video resultante
- [x] **5.3** Manejar casos de video faltante (mostrar cámara disponible)
- [x] **5.4** Optimizar renderizado para videos largos (1-2 horas) con procesamiento por chunks
- [x] **5.5** Agregar metadatos y configuraciones de calidad usando FFmpeg
- [x] **5.6** Implementar modo preview para renderizar solo los primeros 5 minutos
- [x] **5.7** Añadir logs detallados y barras de progreso para cada fase del proceso

### Entregables:
- ✅ Video final sincronizado
- ✅ Sistema optimizado para archivos grandes
- ✅ Configuraciones de calidad ajustables desde el CLI
- ✅ Opción de preview rápido (5 minutos) para pruebas
- ✅ Sistema completo de logs y barras de progreso

### Archivos Implementados:
- `src/video/processor.py`: Módulo para procesar clips de video, implementar transiciones y optimizar rendimiento
- `src/video/composer.py`: Módulo de alto nivel para orquestar el proceso de generación de video final

### Testing:
```bash
# Modo completo
python main.py

# Modo preview (solo procesa 5 minutos)
python main.py --preview
```

---

## FASE 6: Optimización y Features Avanzadas
**Objetivo:** Pulir el sistema y agregar características adicionales

### Tareas:
- [x] **6.1** Implementar preview de 5 minutos para testing rápido
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
│   └── test_sync.py
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
   - División automática del timeline en segmentos de 5 minutos
   - Procesamiento independiente de cada chunk para optimizar memoria
   - Concatenación eficiente con FFmpeg directo (sin recodificar)

2. **Enfoque híbrido FFmpeg/MoviePy**
   - MoviePy para la lógica de alto nivel (cortes, composición, transiciones)
   - FFmpeg como backend para operaciones de bajo nivel y codificación final
   - Optimización de comandos FFmpeg para máxima eficiencia

3. **Multithreading** para operaciones paralelas
   - Procesamiento paralelo de chunks cuando sea posible
   - Configuración de threads para codificación de video

4. **Modo Preview**
   - Opción para renderizar solo los primeros 5 minutos
   - Ideal para pruebas rápidas sin esperar el procesamiento completo
   - Conserva todas las características del video final

5. **Niveles de Calidad Configurables**
   - Opciones de calidad baja, media y alta
   - Presets de FFmpeg optimizados para cada nivel
   - Balance entre velocidad de procesamiento y calidad final

6. **Progress Tracking**
   - Barras de progreso detalladas para cada fase del proceso
   - Logs completos con timestamps para diagnóstico
   - Estimación de tiempo restante durante el procesamiento

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

### Módulo de sincronización

El módulo de sincronización implementa un sistema de tres niveles para garantizar una perfecta sincronización entre las fuentes de audio y video:

1. **Sincronización inicial**: Detecta el offset básico entre pistas utilizando correlación cruzada en el dominio del tiempo, con funciones optimizadas para procesar archivos grandes.

2. **Corrección de drift temporal**: Detecta y corrige desviaciones progresivas en la sincronización que pueden ocurrir debido a diferencias en tasas de muestreo o reloj entre dispositivos. Usa un enfoque de ventanas deslizantes para calcular la tasa de drift.

3. **Sincronización fina por segmentos**: Divide el audio en ventanas con solapamiento y calcula sincronización local para cada segmento, permitiendo corregir desfases puntuales.

4. **Corrección de outliers**: Identifica y corrige desfases anómalos mediante suavizado adaptativo, evitando saltos bruscos en la sincronización.

5. **Timeline unificado**: Genera un timeline preciso que combina offset inicial, corrección de drift y ajustes por segmentos para cada punto del audio.

El módulo incluye herramientas de prueba y visualización para verificar la calidad de la sincronización en cada etapa del proceso. 

### Módulo de detección de speaker activo

El módulo de detección de speaker activo implementa un sistema multi-nivel para identificar con precisión qué speaker está hablando en cada momento:

1. **Análisis de energía por pista**: Analiza la energía de cada pista de audio para determinar quién está hablando con mayor intensidad en cada segmento.

2. **Refinamiento de detección Whisper**: Utiliza los resultados de Whisper como base y los refina mediante análisis de energía para resolver ambigüedades y mejorar la precisión.

3. **Filtrado de cambios rápidos**: Elimina cambios de cámara demasiado cortos para evitar una edición frenética, agrupando segmentos y asignándolos al speaker dominante.

4. **Manejo de solapamientos**: Detecta y gestiona casos donde dos speakers hablan simultáneamente, decidiendo entre mostrar al speaker dominante o crear segmentos especiales de overlap.

5. **Generación de timeline de cámara**: Crea un timeline preciso de cambios de cámara con transiciones configurables (instantáneas, suaves, muy suaves) según las preferencias del usuario.

El sistema incluye parámetros ajustables para:
- Duración mínima de cada plano (evitando cortes muy rápidos)
- Nivel de suavidad de las transiciones (desde cortes directos hasta transiciones lentas)
- Umbral de sensibilidad para detección de overlaps
- Ratio de energía para decidir el speaker dominante

El resultado es un sistema de detección robusto que proporciona cambios de cámara naturales y profesionales, siguiendo el flujo de la conversación. 