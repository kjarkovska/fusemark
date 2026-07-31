"""app/routes — Flask blueprints for FuseMark, grouped by concern.

Each leaf module does `from app import server` and reaches shared state via
`server.X` at call time (never `from app.server import X`) so tests that
monkeypatch attributes on the `app.server` module — `_recording_service`,
`_dl`, `_get_devices`, `Recorder`, `_time`, etc. — keep working unchanged.

register_blueprints() is called once, from the bottom of app/server.py,
*after* that module's globals (app, _recording_service, ...) already exist.
The leaf-module imports are deliberately deferred into this function rather
than done at package scope, since `from app import server` while
app/server.py is still executing only resolves via the sys.modules
fallback once server.py has reached its final statement.
"""


def register_blueprints(flask_app):
    from app.routes.pages import bp as pages_bp
    from app.routes.recording import bp as recording_bp
    from app.routes.jobs import bp as jobs_bp
    from app.routes.settings_api import bp as settings_api_bp
    from app.routes.llm_keys import bp as llm_keys_bp
    from app.routes.prompts_glossary import bp as prompts_glossary_bp
    from app.routes.updates import bp as updates_bp
    from app.routes.wizard import bp as wizard_bp

    for blueprint in (
        pages_bp,
        recording_bp,
        jobs_bp,
        settings_api_bp,
        llm_keys_bp,
        prompts_glossary_bp,
        updates_bp,
        wizard_bp,
    ):
        flask_app.register_blueprint(blueprint)
