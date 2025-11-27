# MotionManga

MotionManga es una herramienta CLI que transforma tus videos en un cómic manga utilizando la potencia de los modelos Gemini 3 de Google.

## Características

*   **Optimización Automática de Video:** Redimensiona videos grandes (>10MB) para una carga eficiente.
*   **Generación de Historia Multimodal:** Crea una narrativa coherente basada en tus videos usando `gemini-3-pro-preview`.
*   **Ilustración con IA:** Genera páginas de manga visualmente impactantes usando `gemini-3-pro-image-preview`.

## Requisitos Previos

*   Python 3.10+
*   [uv](https://github.com/astral-sh/uv) (Gestor de paquetes recomendado)
*   Una API Key de Google GenAI con acceso a los modelos Gemini 3.

## Instalación

1.  **Clonar el repositorio (o descargar los archivos):**
    Asegúrate de tener `main.py`, `story.md` y `comic.md` en tu directorio de trabajo.

2.  **Inicializar y descargar dependencias:**
    ```bash
    uv init
    uv add google-genai python-dotenv typer rich imageio-ffmpeg
    ```

3.  **Configurar Variables de Entorno:**
    Crea un archivo `.env` en la raíz del proyecto y añade tu API Key:
    ```env
    GOOGLE_API_KEY=tu_api_key_aqui
    ```

## Uso

Ejecuta el script pasando hasta 3 archivos de video como argumentos:

```bash
uv run main.py video1.mp4 video2.mp4 video3.mp4
```

### Archivos de Configuración

*   **`story.md`**: Contiene el prompt del sistema y el contexto para la generación de la historia. Puedes editarlo para cambiar el tono o el estilo narrativo.
*   **`comic.md`**: Contiene el prompt de estilo para la generación de imágenes. Ajusta esto para cambiar el estilo artístico del manga.

## Salida

El script generará los siguientes archivos en el directorio `output/`:

*   **`story.txt`**: El guion de tu manga, dividido por páginas.
*   **`page_1.png`, `page_2.png`, ...**: Las imágenes generadas para cada página de la historia.

## Notas

*   Los videos mayores a 10MB serán redimensionados automáticamente a 720p de altura para optimizar el uso de la API.
*   Asegúrate de que tus videos sean claros y relevantes para obtener los mejores resultados en la historia.
