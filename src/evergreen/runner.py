from collections.abc import Mapping
from pathlib import Path

from evergreen import manifest as mf
from evergreen import registry
from evergreen.adapters.base import Adapter, Done, StageContext
from evergreen.adapters.manual import ManualAdapter
from evergreen.errors import EvergreenError


def run(video_dir: Path, adapters: Mapping[str, Adapter] | None = None) -> mf.Manifest:
    """Ejecuta las etapas en orden hasta terminar o hasta que una se detenga.

    Reanudable: las etapas `done` se saltan; `running` (proceso interrumpido) y
    `failed` se vuelven a ejecutar. Cada cambio de estado se guarda antes de seguir.
    """
    adapters = registry.ADAPTERS if adapters is None else adapters
    path = video_dir / "manifest.yaml"
    manifest = mf.load(path)

    for name, state in manifest.stages.items():
        if state.status == mf.Status.done:
            continue
        if state.status == mf.Status.awaiting_approval:
            return manifest  # espera `evergreen approve`
        # Sin adaptador registrado, la etapa se hace a mano.
        adapter = adapters.get(name) or ManualAdapter(registry.MANUAL_FILES[name])

        state.status, state.error, state.adapter = mf.Status.running, None, adapter.name
        mf.save(manifest, path)
        stage_dir = video_dir / "stages" / name
        stage_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = adapter.run(StageContext(name, stage_dir, video_dir, manifest))
        except Exception as e:  # noqa: BLE001 - un adaptador puede fallar con cualquier error; KeyboardInterrupt no entra y deja `running` para reanudar
            state.status, state.error = mf.Status.failed, f"{type(e).__name__}: {e}"
            mf.save(manifest, path)
            return manifest

        if isinstance(result, Done):
            gated = name in manifest.review_gates
            state.status = mf.Status.awaiting_approval if gated else mf.Status.done
            state.outputs = [
                p.relative_to(video_dir).as_posix() for p in result.outputs
            ]
            mf.save(manifest, path)
            if gated:
                return manifest
            continue
        state.status = mf.Status.awaiting_manual
        mf.save(manifest, path)
        return manifest
    return manifest


def approve(video_dir: Path, stage: str) -> None:
    path = video_dir / "manifest.yaml"
    manifest = mf.load(path)
    state = manifest.stages.get(stage)
    if state is None:
        raise EvergreenError(f"El video no tiene la etapa '{stage}'.")
    if state.status != mf.Status.awaiting_approval:
        raise EvergreenError(f"La etapa '{stage}' no está esperando aprobación.")
    state.status = mf.Status.done
    mf.save(manifest, path)
