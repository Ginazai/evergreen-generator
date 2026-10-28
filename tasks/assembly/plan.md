# Plan: assembly

Spec: `SPEC-assembly.md`. Decisiones cerradas 2026-10-23: sin subtítulos, una proporción por video, 1080p.

## Orden y dependencias
```
A1 timing (puro) ──┐
A2 inputs ─────────┤
A3 segmentos ──────┼─> A4 escenas y concatenación ─┐
A5 audio ──────────┴───────────────────────────────┴─> A6 AssemblyAdapter ─> A7 docs y verificación
```
A1, A2, A3 y A5 son independientes entre sí. A4 usa A3. A6 junta todo.

## Riesgos
- Tiempo de render (1080p con zoompan en CPU): se mide en la verificación real; si es excesivo, se baja la ampliación previa o se ofrece 720p.
- El reparto proporcional de tomas puede desfasar la imagen respecto al diálogo 1–2 s: es una aproximación declarada.
- Rendimiento de `xfade` con tomas largas: se limita a una cadena por escena.
- Clips de Flow de 8 s en tomas largas (mantener último cuadro) pueden verse estáticos: se evalúa con un clip real.

## Qué cambia respecto a otros módulos
Nada: `assembly` solo lee lo que producen las etapas anteriores (ver tabla de entradas en la spec).
