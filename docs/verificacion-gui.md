# Verificación de la GUI (en tu PC)

1. `docker compose build` y `docker compose up gui`; abre http://localhost:8501.
2. Ajustes: pega tu clave de Gemini y de Cloudflare, guarda; recarga la página: debe verse `••••1234`, no la clave. Comprueba que aparece `settings.env` en tu carpeta de proyectos.
3. Crea un video, pulsa *Ejecutar / continuar*; cierra la pestaña, vuelve a abrirla: el registro y el estado deben seguir ahí.
4. Edita una línea del guion en *Editar* y guarda: las etapas posteriores deben salir "desactualizadas". Prueba *Mantener* y *Rehacer*; revisa que lo anterior quedó en `stages/<etapa>/archive/`.
5. En una etapa de imágenes lista, elige una clave y *Regenerar este*; luego *Ejecutar*: solo debe generarse esa imagen.
6. Edita `style.yaml` con un valor inválido: debe rechazarlo explicando el motivo sin guardar.
7. Anota lo que se vea incómodo (textos, orden de botones): el diseño visual se afina con tu uso.
