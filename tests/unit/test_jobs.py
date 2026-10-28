import time

import pytest

from evergreen import jobrun, jobs, project
from evergreen import manifest as mf
from evergreen.errors import EvergreenError


def new(tmp_path):
    return project.create("Los patitos", mf.Format.rhyme, mf.Language.es, tmp_path)


def wait(v, timeout=60):
    end = time.time() + timeout
    while jobs.is_running(v) and time.time() < end:
        time.sleep(0.1)


def test_background_run_executes_logs_and_releases_the_lock(tmp_path):
    v = new(tmp_path)
    jobs.start(v)
    with pytest.raises(EvergreenError, match="ya se está ejecutando"):
        jobs.start(v)
    wait(v)
    assert not jobs.is_running(v) and not (v / jobrun.LOCK).exists()
    log = jobs.read_log(v)
    assert (
        "script: " in log
    )  # sin clave, la primera etapa queda esperando el paso manual
    assert mf.load(v / "manifest.yaml").stages["script"].status != mf.Status.pending


def test_stale_lock_from_a_dead_process_is_cleaned(tmp_path):
    v = new(tmp_path)
    (v / jobrun.LOCK).write_text("999999")
    assert not jobs.is_running(v) and not (v / jobrun.LOCK).exists()
    (v / jobrun.LOCK).write_text("basura")
    assert not jobs.is_running(v)
    assert jobs.read_log(v) == ""


def test_main_reports_errors_and_always_unlocks(tmp_path, capsys):
    v = tmp_path / "no-existe"
    v.mkdir()
    assert jobrun.main(v) == 1 and "Error" in capsys.readouterr().out
    assert not (v / jobrun.LOCK).exists()


def test_pid_reused_by_another_process_is_not_a_running_job(tmp_path):
    import os

    v = new(tmp_path)
    (v / jobrun.LOCK).write_text(str(os.getpid()))  # vivo, pero es pytest, no jobrun
    assert not jobs.is_running(v) and not (v / jobrun.LOCK).exists()
