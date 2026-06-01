from app.i18n import get_strings, TRANSLATIONS


def test_get_strings_en():
    s = get_strings("en")
    assert s["btn_start_recording"] == "Start recording"
    assert s["status_done"] == "Done"
    assert s["jobs_empty_title"] == "No recordings yet"


def test_get_strings_cs():
    s = get_strings("cs")
    assert s["btn_start_recording"] == "Spustit nahrávání"
    assert s["status_done"] == "Hotovo"
    assert s["jobs_empty_title"] == "Zatím žádné záznamy"


def test_get_strings_unknown_falls_back_to_en():
    s = get_strings("fr")
    assert s["btn_start_recording"] == "Start recording"
    assert s["nav_settings"] == "Settings"


def test_both_langs_have_identical_keys():
    en_keys = set(TRANSLATIONS["en"].keys())
    cs_keys = set(TRANSLATIONS["cs"].keys())
    assert en_keys == cs_keys, f"Key mismatch: {en_keys.symmetric_difference(cs_keys)}"


def test_get_strings_returns_dict():
    s = get_strings("en")
    assert isinstance(s, dict)
    assert len(s) > 50


def test_msg_update_available_has_version_placeholder():
    for lang in ("en", "cs"):
        assert "{version}" in TRANSLATIONS[lang]["msg_update_available"]


def test_msg_update_available_substitution():
    s = get_strings("en")
    result = s["msg_update_available"].replace("{version}", "1.2.3")
    assert "1.2.3" in result
    assert "{version}" not in result
