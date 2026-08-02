import inspect

import app.main as main_module


def test_salvage_runs_before_recover_interrupted_jobs():
    """A crash-orphaned recording is only rescued if
    recording_service.salvage_interrupted_recordings() runs before
    queue.recover_interrupted_jobs() marks any still-'recording' job as an
    unrecoverable error — see app/queue.py's recover_interrupted_jobs()
    docstring. app/main.py's main() is otherwise untested (single-instance
    mutex, pywebview native window, tray thread — none of it mocks cleanly
    or is worth mocking just to prove call order), so this is a source-order
    guard rather than a behavioral test: it would catch someone silently
    reordering the two calls, not catch every way startup could misbehave.
    """
    source = inspect.getsource(main_module.main)
    salvage_pos = source.index("salvage_interrupted_recordings()")
    recover_pos = source.index("recover_interrupted_jobs()")
    assert salvage_pos < recover_pos, (
        "salvage_interrupted_recordings() must run before "
        "recover_interrupted_jobs() in app/main.py:main() — otherwise a "
        "crash-orphaned recording gets marked 'error' before salvage gets "
        "a chance to recover it."
    )
