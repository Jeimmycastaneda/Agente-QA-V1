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
# is_valid_prompt_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["qa_base.md", "custom-prompt.md", "prompt_v2.md", "A1_-.md"],
)
def test_is_valid_prompt_name_accepts_valid_names(name):
    assert prompts.is_valid_prompt_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "qa_base.txt",
        "../qa_base.md",
        "../../etc/passwd.md",
        "sub/dir.md",
        "qa base.md",
        "qa_base.MD",
        None,
    ],
)
def test_is_valid_prompt_name_rejects_invalid_names(name):
    assert not prompts.is_valid_prompt_name(name)


# ---------------------------------------------------------------------------
# list_prompts
# ---------------------------------------------------------------------------


def test_list_prompts_empty_directory():
    assert prompts.list_prompts() == []


def test_list_prompts_returns_sorted_md_files(tmp_path):
    (tmp_path / "b_prompt.md").write_text("b", encoding="utf-8")
    (tmp_path / "a_prompt.md").write_text("a", encoding="utf-8")
    (tmp_path / "not_a_prompt.txt").write_text("x", encoding="utf-8")
    assert prompts.list_prompts() == ["a_prompt.md", "b_prompt.md"]


def test_list_prompts_missing_directory_returns_empty(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist"
    monkeypatch.setattr(prompts, "PROMPTS_DIR", missing)
    assert prompts.list_prompts() == []


# ---------------------------------------------------------------------------
# load_prompt / cache
# ---------------------------------------------------------------------------


def test_load_prompt_reads_file_content(tmp_path):
    (tmp_path / "qa_base.md").write_text("  Contenido del prompt.  ", encoding="utf-8")
    assert prompts.load_prompt("qa_base.md") == "Contenido del prompt."


def test_load_prompt_missing_file_returns_fallback():
    assert prompts.load_prompt("missing.md") == prompts._FALLBACK_PROMPT


def test_load_prompt_empty_file_returns_fallback(tmp_path):
    (tmp_path / "empty.md").write_text("   ", encoding="utf-8")
    assert prompts.load_prompt("empty.md") == prompts._FALLBACK_PROMPT


def test_load_prompt_is_cached(tmp_path):
    (tmp_path / "cached.md").write_text("version 1", encoding="utf-8")
    assert prompts.load_prompt("cached.md") == "version 1"

    # Overwriting the file on disk should not change the cached value.
    (tmp_path / "cached.md").write_text("version 2", encoding="utf-8")
    assert prompts.load_prompt("cached.md") == "version 1"


def test_clear_prompt_cache_forces_reread(tmp_path):
    (tmp_path / "cached.md").write_text("version 1", encoding="utf-8")
    assert prompts.load_prompt("cached.md") == "version 1"

    (tmp_path / "cached.md").write_text("version 2", encoding="utf-8")
    prompts.clear_prompt_cache()
    assert prompts.load_prompt("cached.md") == "version 2"


# ---------------------------------------------------------------------------
# save_prompt
# ---------------------------------------------------------------------------


def test_save_prompt_writes_file(tmp_path):
    prompts.save_prompt("new_prompt.md", "contenido nuevo")
    assert (tmp_path / "new_prompt.md").read_text(encoding="utf-8") == "contenido nuevo"


def test_save_prompt_invalidates_cache(tmp_path):
    (tmp_path / "qa_base.md").write_text("old", encoding="utf-8")
    assert prompts.load_prompt("qa_base.md") == "old"

    prompts.save_prompt("qa_base.md", "new")
    assert prompts.load_prompt("qa_base.md") == "new"


def test_save_prompt_rejects_invalid_name(tmp_path):
    with pytest.raises(ValueError):
        prompts.save_prompt("../escape.md", "malicious")


def test_save_prompt_creates_missing_directory(tmp_path, monkeypatch):
    missing = tmp_path / "nested"
    monkeypatch.setattr(prompts, "PROMPTS_DIR", missing)
    prompts.save_prompt("qa_base.md", "content")
    assert (missing / "qa_base.md").read_text(encoding="utf-8") == "content"


# ---------------------------------------------------------------------------
# prompt_path / traversal guard
# ---------------------------------------------------------------------------


def test_prompt_path_rejects_traversal():
    with pytest.raises(ValueError):
        prompts.prompt_path("../../etc/passwd.md")


def test_prompt_path_returns_path_inside_prompts_dir(tmp_path):
    assert prompts.prompt_path("qa_base.md") == tmp_path / "qa_base.md"
