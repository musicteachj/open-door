import stat
from pathlib import Path

import pytest

from app.core.encryption import load_key_provider
from scripts.make_keyring import main


def test_it_writes_a_loadable_keyring_with_a_random_key_readable_only_by_its_owner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / ".keys" / "keyring"

    assert main([str(path)]) == 0

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    keys = load_key_provider(keyring=None, keyring_file=str(path))
    assert len(keys.key_ids) == 1
    assert not keys.uses_test_key
    # The output names the file and never the key.
    assert path.read_text().split(":", 1)[1].strip() not in capsys.readouterr().out


def test_two_keyrings_differ(tmp_path: Path) -> None:
    main([str(tmp_path / "a")])
    main([str(tmp_path / "b")])
    assert (tmp_path / "a").read_text() != (tmp_path / "b").read_text()


def test_it_never_overwrites_an_existing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "keyring"
    path.write_text("keep:me")
    path.chmod(0o644)

    assert main([str(path)]) == 0

    assert path.read_text() == "keep:me"
    assert stat.S_IMODE(path.stat().st_mode) == 0o644  # untouched, not fixed up either
    assert "already exists" in capsys.readouterr().out


def test_it_does_not_follow_a_symlink_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("keep:me")
    link = tmp_path / "keyring"
    link.symlink_to(target)

    assert main([str(link)]) == 0

    assert target.read_text() == "keep:me"


def test_the_default_path_is_the_one_the_settings_default_to() -> None:
    from app.core.config import Settings
    from app.core.encryption import DEFAULT_KEYRING_PATH

    default = Settings.model_fields["encryption_keyring_file"].default
    assert default.get_secret_value() == DEFAULT_KEYRING_PATH == ".keys/keyring"


def test_it_writes_the_keyring_file_the_settings_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The API reads ENCRYPTION_KEYRING_FILE, so `make keyring` writes that file, not the default.
    from app.core import encryption

    monkeypatch.setattr(encryption, "_API_DIR", tmp_path / "api")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:5433/db")
    monkeypatch.setenv("ENCRYPTION_KEYRING_FILE", "custom/ring")
    monkeypatch.delenv("ENCRYPTION_KEYRING", raising=False)

    assert main([]) == 0

    assert (tmp_path / "api" / "custom" / "ring").is_file()
    assert not (tmp_path / "api" / ".keys").exists()


def test_the_default_path_is_under_apps_api_whatever_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core import encryption

    api_dir = tmp_path / "api"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(encryption, "_API_DIR", api_dir)
    monkeypatch.chdir(elsewhere)

    assert main([]) == 0

    assert (api_dir / ".keys" / "keyring").is_file()
    assert not (elsewhere / ".keys").exists()
