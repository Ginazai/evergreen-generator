# Tareas: gui

- [x] G0 Núcleo: `StageState.stale`, `runner.reopen(video, etapa)` (archiva a `archive/<fecha>/`, marca posteriores `stale`), mapa de dependencias, `evergreen reopen`. Tests.
- [x] G1 `settings.env`: leer/escribir/enmascarar claves; la CLI lo carga al iniciar. Tests.
- [x] G2 Servicios de edición (`gui/edit.py`): brief/título, guion, cast, voices, style; validan con los modelos, guardan atómico, marcan `stale`. Tests.
- [x] G3 Regenerar un elemento (imagen o escena de voz): archiva solo ese archivo y reabre la etapa. Tests.
- [x] G4 Ejecución en subproceso con bloqueo y registro (`gui/jobs.py`). Tests.
- [x] G5 Pantallas Streamlit (Videos, Video, Editar, Ajustes) con AppTest + captura.
- [x] G6 Docker (servicio `gui`, puerto 8501, extra `streamlit`), README, `docs/verificacion-gui.md`, tarball.
