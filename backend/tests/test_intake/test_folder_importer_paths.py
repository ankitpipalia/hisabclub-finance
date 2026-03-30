from pathlib import Path

from app.engines.intake.folder_importer import _path_candidates, _resolve_folder_path


def test_windows_drive_path_generates_posix_candidates() -> None:
    candidates = _path_candidates(r"C:\Data\Statements")
    assert "/mnt/c/Data/Statements" in candidates
    assert "/c/Data/Statements" in candidates


def test_macos_users_path_generates_linux_home_candidates() -> None:
    candidates = _path_candidates("/Users/alice/Documents/FY24")
    assert "/home/alice/Documents/FY24" in candidates


def test_file_url_path_is_normalized() -> None:
    candidates = _path_candidates("file:///home/ankit/Documents/FY24-25-Ankit-details")
    assert "/home/ankit/Documents/FY24-25-Ankit-details" in candidates


def test_resolve_folder_path_uses_existing_candidate_from_home_mapping(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "Downloads" / "ABDM" / "Compressed" / "Ankit"
    target.mkdir(parents=True)

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    resolved = _resolve_folder_path("/Users/ankitpipalia/Downloads/ABDM/Compressed/Ankit")
    assert resolved == target.resolve()
