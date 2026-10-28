"""Render con ffmpeg: tomas con movimiento, escenas con fundidos, mezcla de audio y mux final."""

import hashlib
from pathlib import Path

from evergreen import fsutil
from evergreen.assembly.ffmpeg import run_ffmpeg
from evergreen.assembly.inputs import Frame

FPS = 25
TRANSITION = 0.5  # fundido cruzado entre tomas de una escena
DIP = 0.25  # entrada/salida a negro de cada escena
DIRECTIONS = ("in", "pan-right", "out", "pan-left")
ENCODE = [
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-crf",
    "20",
    "-preset",
    "veryfast",
    "-r",
    str(FPS),
    "-an",
]


def _zoompan(direction: str, frames: int, w: int, h: int) -> str:
    step = 0.12 / max(frames, 1)
    z, x, y = {
        "in": (f"1+{step}*on", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"),
        "out": (f"1.12-{step}*on", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"),
        "pan-right": ("1.12", f"(iw-iw/zoom)*on/{max(frames, 1)}", "ih/2-ih/zoom/2"),
        "pan-left": ("1.12", f"(iw-iw/zoom)*(1-on/{max(frames, 1)})", "ih/2-ih/zoom/2"),
    }[direction]
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={FPS}"


def _cover(w: int, h: int) -> str:
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def segment(
    frame: Frame, seconds: float, direction: str, size: tuple[int, int], work: Path
) -> Path:
    """Una toma de `seconds`. Con clip de Flow: se recorta y se congela el último cuadro si es corto."""
    w, h = size
    source = frame.clip or frame.image
    stat = source.stat()
    tag = f"{source.name}|{stat.st_size}|{stat.st_mtime_ns}|{seconds:.3f}|{direction}|{w}x{h}"
    out = work / f"seg-{hashlib.sha1(tag.encode()).hexdigest()[:16]}.mp4"
    if out.is_file():  # reanudable: la misma toma no se vuelve a renderizar
        return out
    frames = max(1, round(seconds * FPS))
    if frame.clip:
        vf = (
            f"{_cover(w, h)},fps={FPS},tpad=stop_mode=clone:stop_duration={seconds:.3f}"
        )
        args = ["-i", str(frame.clip), "-vf", vf, "-t", f"{seconds:.3f}"]
    else:
        vf = f"{_cover(w * 2, h * 2)},{_zoompan(direction, frames, w, h)}"
        args = ["-i", str(frame.image), "-vf", vf, "-frames:v", str(frames)]
    part = out.with_suffix(".part.mp4")
    run_ffmpeg([*args, *ENCODE, str(part)])
    fsutil.replace(part, out)
    return out


def scene(segments: list[Path], durations: list[float], out: Path) -> Path:
    """Une las tomas con fundido cruzado y pone entrada/salida a negro. Cada toma no final dura d+T."""
    n = len(segments)
    t = min(TRANSITION, *(d / 2 for d in durations))
    total = sum(durations)
    dip = min(DIP, total / 4)
    tail = f"fade=t=in:st=0:d={dip:.3f},fade=t=out:st={total - dip:.3f}:d={dip:.3f}"
    inputs = [x for s in segments for x in ("-i", str(s))]
    if n == 1:
        graph = f"[0:v]{tail}[v]"
    else:
        parts, prev, elapsed = [], "0:v", 0.0
        for i in range(1, n):
            elapsed += durations[i - 1]
            label = "x" if i < n - 1 else "xf"
            parts.append(
                f"[{prev}][{i}:v]xfade=transition=fade:duration={t:.3f}:offset={elapsed:.3f}[{label}]"
            )
            prev = label
        graph = ";".join(parts) + f";[xf]{tail}[v]"
    run_ffmpeg([*inputs, "-filter_complex", graph, "-map", "[v]", *ENCODE, str(out)])
    return out


def concat(files: list[Path], out: Path, copy: bool = True) -> Path:
    listing = out.with_suffix(".txt")
    listing.write_text(
        "".join(f"file '{f.resolve().as_posix()}'\n" for f in files), encoding="utf-8"
    )
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)]
    )
    return out


def mix_audio(
    voice: Path, music: Path | None, song: Path | None, seconds: float, out: Path
) -> Path:
    """Long: voz + música con ducking. Rhyme: solo la canción. Siempre -14 LUFS y cierre en fade."""
    fade = f"afade=t=out:st={max(seconds - 1.5, 0):.3f}:d=1.5"
    norm = "loudnorm=I=-14:TP=-1.5:LRA=11"
    stereo = "aresample=48000,aformat=channel_layouts=stereo"
    if song:
        args = ["-i", str(song), "-af", f"{stereo},{norm},{fade}"]
    else:
        graph = (
            f"[0:a]{stereo},asplit=2[v][sc];[1:a]{stereo},volume=0.35[m];"
            "[m][sc]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[duck];"
            f"[v][duck]amix=inputs=2:duration=first:normalize=0,{norm},{fade}[a]"
        )
        args = [
            "-i",
            str(voice),
            "-stream_loop",
            "-1",
            "-i",
            str(music),
            "-filter_complex",
            graph,
            "-map",
            "[a]",
        ]
    run_ffmpeg(
        [
            *args,
            "-t",
            f"{seconds:.3f}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            str(out),
        ]
    )
    return out


def mux(video: Path, audio: Path, out: Path) -> Path:
    part = out.with_name(out.name + ".part")
    run_ffmpeg(
        [
            "-i",
            str(video),
            "-i",
            str(audio),
            "-c",
            "copy",
            "-shortest",
            "-f",
            "mp4",
            str(part),
        ]
    )
    fsutil.replace(part, out)
    return out
