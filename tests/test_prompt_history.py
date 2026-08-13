import pytest

from agente_qa import prompts


@pytest.fixture(autouse=True)
def isolated_prompts_dir(tmp_path, monkeypatch):
    """Redirect PROMPTS_DIR to a scratch directory and reset the cache so
    tests never touch the real prompts/ directory or leak state."""
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    prompts.clear_prompt_cache()
    yield
    prompts.clear_prompt_cache()


# ---------------------------------------------------------------------------
# save_prompt snapshotting
# ---------------------------------------------------------------------------


def test_save_prompt_does_not_snapshot_on_first_save(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    assert prompts.list_prompt_versions("qa_base.md") == []


def test_save_prompt_snapshots_previous_content(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    prompts.save_prompt("qa_base.md", "v2")

    versions = prompts.list_prompt_versions("qa_base.md")
    assert len(versions) == 1
    assert prompts.read_prompt_version("qa_base.md", versions[0]) == "v1"
    assert prompts.load_prompt("qa_base.md") == "v2"


def test_save_prompt_history_lives_under_history_dir(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    prompts.save_prompt("qa_base.md", "v2")

    history_dir = tmp_path / ".history"
    assert history_dir.is_dir()
    snapshots = list(history_dir.glob("qa_base.*.md"))
    assert len(snapshots) == 1


def test_history_dir_is_excluded_from_list_prompts(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    prompts.save_prompt("qa_base.md", "v2")
    assert prompts.list_prompts() == ["qa_base.md"]


def test_list_prompt_versions_newest_first(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    prompts.save_prompt("qa_base.md", "v2")
    prompts.save_prompt("qa_base.md", "v3")

    versions = prompts.list_prompt_versions("qa_base.md")
    assert versions == sorted(versions, reverse=True)
    assert len(versions) == 2


def test_prune_history_keeps_only_max_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "MAX_VERSIONS", 2)

    for i in range(5):
        prompts.save_prompt("qa_base.md", f"v{i}")

    versions = prompts.list_prompt_versions("qa_base.md")
    assert len(versions) == 2


# ---------------------------------------------------------------------------
# restore_prompt_version
# ---------------------------------------------------------------------------


def test_restore_prompt_version_restores_content(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    prompts.save_prompt("qa_base.md", "v2")
    versions = prompts.list_prompt_versions("qa_base.md")

    prompts.restore_prompt_version("qa_base.md", versions[0])
    assert prompts.load_prompt("qa_base.md") == "v1"


def test_restore_prompt_version_snapshots_replaced_content(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    prompts.save_prompt("qa_base.md", "v2")
    v1_version = prompts.list_prompt_versions("qa_base.md")[0]

    prompts.restore_prompt_version("qa_base.md", v1_version)

    # v2 (the content that was active before the restore) must now be
    # preserved in the history too.
    versions = prompts.list_prompt_versions("qa_base.md")
    assert len(versions) == 2
    contents = {prompts.read_prompt_version("qa_base.md", v) for v in versions}
    assert contents == {"v1", "v2"}


# ---------------------------------------------------------------------------
# Security: version parameter must never allow path traversal.
#
# is_valid_prompt_name / _VALID_VERSION are security controls, not
# ergonomics — this test is the required verification from the roadmap
# plan (Fase 6, "Restricción crítica sobre la guardia de path-traversal").
# ---------------------------------------------------------------------------


TRAVERSAL_VERSIONS = [
    "../../etc/passwd",
    "../../../etc/passwd",
    "..%2F..%2Fetc%2Fpasswd",
    "20240101T000000/../../../etc/passwd",
    "20240101T000000.md",
    "20240101T00000",  # too short
    "2024010100000000",  # missing the literal 'T'
    "",
    None,
    "20240101T000000; rm -rf /",
    "/etc/passwd",
]


@pytest.mark.parametrize("version", TRAVERSAL_VERSIONS)
def test_read_prompt_version_rejects_path_traversal(tmp_path, version):
    prompts.save_prompt("qa_base.md", "v1")
    prompts.save_prompt("qa_base.md", "v2")  # creates one real, valid snapshot

    with pytest.raises(ValueError):
        prompts.read_prompt_version("qa_base.md", version)

    # No file must ever be created or read outside prompts/.history/ as a
    # result of a malicious version string: the history dir must only
    # ever contain the legitimately created, well-formed snapshot file(s).
    history_dir = tmp_path / ".history"
    for f in history_dir.glob("*"):
        assert prompts._VALID_VERSION.fullmatch(
            f.name[len("qa_base."):-3]
        ), f"unexpected file created in history dir: {f}"


@pytest.mark.parametrize("version", TRAVERSAL_VERSIONS)
def test_restore_prompt_version_rejects_path_traversal(tmp_path, version):
    prompts.save_prompt("qa_base.md", "v1")

    with pytest.raises(ValueError):
        prompts.restore_prompt_version("qa_base.md", version)

    # The active prompt must be untouched by a rejected restore attempt.
    assert prompts.load_prompt("qa_base.md") == "v1"


@pytest.mark.parametrize(
    "name",
    ["../qa_base.md", "../../etc/passwd.md", "sub/dir.md", "qa base.md", ""],
)
def test_list_prompt_versions_rejects_invalid_name(tmp_path, name):
    with pytest.raises(ValueError):
        prompts.list_prompt_versions(name)


def test_read_prompt_version_missing_version_raises(tmp_path):
    prompts.save_prompt("qa_base.md", "v1")
    with pytest.raises(ValueError):
        prompts.read_prompt_version("qa_base.md", "20240101T000000")
