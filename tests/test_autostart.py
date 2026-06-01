from unittest.mock import patch
import winreg
import app.autostart as autostart


def test_is_enabled_returns_true_when_key_exists():
    with patch("winreg.OpenKey"), patch("winreg.QueryValueEx"), patch("winreg.CloseKey"):
        assert autostart.is_enabled() is True


def test_is_enabled_returns_false_when_key_missing():
    with patch("winreg.OpenKey", side_effect=FileNotFoundError):
        assert autostart.is_enabled() is False


def test_enable_writes_registry_value(tmp_path):
    patched_vbs = str(tmp_path / "start.vbs")
    with patch.object(autostart, "VBS_PATH", patched_vbs), \
         patch("winreg.OpenKey"), \
         patch("winreg.SetValueEx") as mock_set, \
         patch("winreg.CloseKey"):
        autostart.enable()
    mock_set.assert_called_once()
    _, args, _ = mock_set.mock_calls[0]
    assert args[1] == autostart.APP_NAME
    assert args[3] == winreg.REG_SZ
    assert patched_vbs in args[4]


def test_enable_writes_vbs_file(tmp_path):
    vbs = tmp_path / "start.vbs"
    with patch.object(autostart, "VBS_PATH", str(vbs)), \
         patch("winreg.OpenKey"), patch("winreg.SetValueEx"), patch("winreg.CloseKey"):
        autostart.enable()
    assert vbs.exists()
    content = vbs.read_text(encoding="utf-8")
    assert "app.main" in content
    assert "WScript.Shell" in content


def test_disable_removes_registry_value():
    with patch("winreg.OpenKey"), \
         patch("winreg.DeleteValue") as mock_del, \
         patch("winreg.CloseKey"):
        autostart.disable()
    mock_del.assert_called_once()
    _, args, _ = mock_del.mock_calls[0]
    assert args[1] == autostart.APP_NAME


def test_disable_is_silent_when_key_missing():
    with patch("winreg.OpenKey", side_effect=FileNotFoundError):
        autostart.disable()  # must not raise


def test_get_launch_cmd_references_vbs_and_wscript():
    cmd = autostart._get_launch_cmd()
    assert "wscript.exe" in cmd.lower()
    assert autostart.VBS_PATH in cmd
