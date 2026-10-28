from evergreen import manifest as mf
from evergreen.adapters.base import Done, NeedsManual


class Fake:
    """Adaptador ficticio: cuenta llamadas y puede fallar, interrumpirse o pedir paso manual."""

    def __init__(self, fail=0, manual=False, interrupt_once=False):
        self.name = "fake"
        self.calls = 0
        self.fail = fail
        self.manual = manual
        self.interrupt_once = interrupt_once
        self.seen = {}

    def run(self, ctx):
        self.calls += 1
        # Lo que el disco decía justo antes de ejecutar esta etapa.
        self.seen = {
            n: s.status
            for n, s in mf.load(ctx.video_dir / "manifest.yaml").stages.items()
        }
        if self.interrupt_once and self.calls == 1:
            raise KeyboardInterrupt
        if self.calls <= self.fail:
            raise RuntimeError("boom")
        if self.manual:
            return NeedsManual(ctx.stage_dir / "MANUAL.md", ["x"])
        out = ctx.stage_dir / "out.txt"
        out.write_text(ctx.stage, encoding="utf-8")
        return Done([out])
