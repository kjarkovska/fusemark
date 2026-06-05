from app.tray import icon_for_state


# ------------------------------------------------------------------
# icon_for_state() — precedence logic
# ------------------------------------------------------------------

def test_idle_when_neither():
    assert icon_for_state(recording=False, transcribing=False) == "idle"


def test_recording_when_recording_only():
    assert icon_for_state(recording=True, transcribing=False) == "recording"


def test_transcribing_when_transcribing_only():
    assert icon_for_state(recording=False, transcribing=True) == "transcribing"


def test_recording_takes_precedence_over_transcribing():
    assert icon_for_state(recording=True, transcribing=True) == "recording"
