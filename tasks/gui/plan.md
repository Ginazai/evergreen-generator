# Plan: gui

Spec: `SPEC-gui.md` (decisiones cerradas 2026-10-24).

## Orden y dependencias
```
G0 núcleo: stale + reopen + archivo ──┬─> G3 regenerar elemento suelto ─┐
G1 settings.env (claves) ─────────────┤                                 │
G2 servicios de edición (validan+stale)┴─> G4 ejecución en subproceso ───┴─> G5 pantallas Streamlit ─> G6 Docker y docs
```
Todo hasta G4 es Python puro y testeable sin navegador; G5 es solo presentación (AppTest).

## Riesgos
- Streamlit no se puede ver aquí con un navegador real del usuario: se prueba con `AppTest` y una captura con Playwright; el ajuste visual fino queda para tu verificación.
- Subproceso de larga duración dentro del contenedor: si el contenedor se detiene, la etapa queda `running` y el runner ya la reanuda.
- Claves en `settings.env` en texto plano (aceptado por el usuario).
- Regenerar un elemento de voz: Gemini TTS agrupa por petición (≤2 voces); regenerar "una escena" puede repetir una petición completa (1 de 10 diarias).

## Qué cambia en otros módulos
Solo el núcleo: campo aditivo `StageState.stale`, `runner.reopen`, `evergreen reopen`, y carga de `settings.env` al iniciar la CLI.
