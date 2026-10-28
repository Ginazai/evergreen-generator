"""Etapa `assembly`: junta imágenes/clips, voz o canción y música en `final.mp4`."""

import json

from evergreen.adapters.base import Done, StageContext, StageResult
from evergreen.assembly import render, timing
from evergreen.assembly.ffmpeg import probe_seconds, require_ffmpeg
from evergreen.assembly.inputs import load_inputs
from evergreen.errors import EvergreenError

SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920)}


class AssemblyAdapter:
    name = "ffmpeg"

    def __init__(self, sizes: dict[str, tuple[int, int]] | None = None) -> None:
        self._sizes = sizes or SIZES  # inyectable: los tests rinden en miniatura

    def run(self, ctx: StageContext) -> StageResult:
        require_ffmpeg()
        i = load_inputs(ctx.video_dir, ctx.manifest)
        size = self._sizes[i.aspect]
        work = ctx.stage_dir / "work"
        work.mkdir(parents=True, exist_ok=True)

        if i.song:
            total = probe_seconds(i.song)
            spans = timing.rhyme_spans(i.script, total)
            voice = None
        else:
            if i.scene_seconds_files:
                per_scene = {
                    s: sum(probe_seconds(f) for f in fs)
                    for s, fs in i.scene_seconds_files.items()
                }
                voice = render.concat(i.voice_files, work / "voice.wav")
            else:
                voice = i.voice_files[0]
                per_scene = timing.scene_seconds_from_total(
                    i.script, probe_seconds(voice)
                )
            missing = [s.id for s in i.script.body.scenes if s.id not in per_scene]
            if missing:
                raise EvergreenError(
                    f"La voz no tiene audio para la escena {missing[0]}."
                )
            spans = timing.long_spans(i.script, per_scene)
            total = sum(per_scene.values())

        groups: dict[str, list[timing.ShotSpan]] = {}
        for span in spans:  # rhyme: un solo grupo (sin negro entre secciones)
            groups.setdefault("all" if i.song else span.scene_id, []).append(span)

        scene_files, n = [], 0
        for gid, shots in groups.items():
            durations = [max(s.seconds, timing.MIN_SHOT) for s in shots]
            t = min(render.TRANSITION, *(d / 2 for d in durations))
            segs = []
            for k, (span, d) in enumerate(zip(shots, durations, strict=True)):
                if span.key not in i.frames:
                    raise EvergreenError(
                        f"Falta la imagen {span.key} (etapa de imágenes)."
                    )
                extra = t if k < len(shots) - 1 else 0
                segs.append(
                    render.segment(
                        i.frames[span.key],
                        d + extra,
                        render.DIRECTIONS[n % 4],
                        size,
                        work,
                    )
                )
                n += 1
            scene_files.append(render.scene(segs, durations, work / f"scene-{gid}.mp4"))

        video = render.concat(scene_files, work / "video.mp4")
        total = sum(
            sum(max(s.seconds, timing.MIN_SHOT) for s in g) for g in groups.values()
        )
        audio = render.mix_audio(voice, i.music, i.song, total, work / "audio.m4a")
        final = render.mux(video, audio, ctx.stage_dir / "final.mp4")
        info = ctx.stage_dir / "assembly.json"
        info.write_text(
            json.dumps(
                {"seconds": round(total, 2), "aspect": i.aspect, "size": list(size),
                 "shots": [{"key": s.key, "seconds": round(s.seconds, 2),
                            "clip": bool(i.frames[s.key].clip)} for s in spans]},
                indent=2,
            ),
            encoding="utf-8",
        )  # fmt: skip
        return Done([final, info])
