# ViralClips AI

Aplicación web personal para convertir enlaces de videos en clips verticales con subtítulos.

## Despliegue recomendado: Hugging Face Spaces

1. Crea una cuenta en Hugging Face.
2. Crea un Space nuevo y selecciona **Gradio** como SDK.
3. Sube `app.py`, `requirements.txt` y `README.md`.
4. En la configuración del Space, elige hardware CPU. El primer inicio puede tardar porque descarga el modelo de transcripción.
5. Abre la dirección del Space desde tu iPad.

## Importante sobre privacidad

Si el Space queda **público**, cualquier persona que tenga el enlace podrá abrirlo y usarlo. No tener contraseña no permite garantizar que sea solo tuyo. Para uso realmente privado, el alojamiento debe permitir acceso privado/autenticación; eso puede requerir una cuenta o plan de pago.

## Qué hace el prototipo

- Recibe un enlace compatible con yt-dlp.
- Transcribe el audio con faster-whisper.
- Puntúa ventanas de conversación mediante heurísticas sencillas.
- Exporta clips MP4 verticales 9:16 con subtítulos incrustados.

No es un detector perfecto de viralidad ni garantiza que todos los enlaces de YouTube funcionen. El proveedor puede limitar descargas; no intenta saltarse restricciones de acceso. Utiliza únicamente videos que sean tuyos o que tengas permiso de procesar y reutilizar.

## Límites

El plan gratuito de alojamiento puede dormir cuando no se usa, limitar CPU/tiempo y no ser adecuado para videos largos. Para una versión de producción conviene añadir almacenamiento persistente, cola de trabajos y un motor de selección semántica más avanzado.
