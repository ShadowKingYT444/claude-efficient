from claude_efficient.generators.tasks_md import TasksMdGenerator, TASKS_MD_TEMPLATE


def test_generate_returns_template(tmp_path):
    gen = TasksMdGenerator()
    result = gen.generate(tmp_path)
    assert result == TASKS_MD_TEMPLATE


def test_write_creates_file(tmp_path):
    gen = TasksMdGenerator()
    content = gen.generate(tmp_path)
    out = gen.write(tmp_path, content)
    assert out == tmp_path / "TASKS.md"
    assert out.exists()
    assert out.read_text(encoding="utf-8") == content


def test_update_reads_existing(tmp_path):
    existing = "# TASKS.md\n- [ ] MY_01: do something\n"
    (tmp_path / "TASKS.md").write_text(existing, encoding="utf-8")
    gen = TasksMdGenerator()
    result = gen.update(tmp_path)
    assert result == existing


def test_update_generates_when_missing(tmp_path):
    gen = TasksMdGenerator()
    result = gen.update(tmp_path)
    assert "TASKS.md" in result


def test_mark_completed(tmp_path):
    content = "# TASKS\n- [ ] FOO_01: build the thing\n- [ ] BAR_02: test it\n"
    (tmp_path / "TASKS.md").write_text(content, encoding="utf-8")
    gen = TasksMdGenerator()
    result = gen.update(tmp_path, completed=["FOO_01"])
    assert "- [x] FOO_01: build the thing" in result
    assert "- [ ] BAR_02: test it" in result


def test_mark_completed_case_insensitive(tmp_path):
    content = "- [ ] SPEC_01: Project Scaffold\n"
    (tmp_path / "TASKS.md").write_text(content, encoding="utf-8")
    gen = TasksMdGenerator()
    result = gen.update(tmp_path, completed=["spec_01"])
    assert "- [x] SPEC_01:" in result


def test_already_completed_unchanged(tmp_path):
    content = "- [x] DONE_01: already done\n"
    (tmp_path / "TASKS.md").write_text(content, encoding="utf-8")
    gen = TasksMdGenerator()
    result = gen.update(tmp_path, completed=["DONE_01"])
    assert result.count("[x]") == 1


def test_append_tasks(tmp_path):
    content = "# TASKS\n- [ ] OLD_01: existing\n"
    (tmp_path / "TASKS.md").write_text(content, encoding="utf-8")
    gen = TasksMdGenerator()
    result = gen.update(tmp_path, added=["- [ ] NEW_01: new task"])
    assert "- [ ] NEW_01: new task" in result
    assert "- [ ] OLD_01: existing" in result


def test_combined_completed_and_added(tmp_path):
    content = "# TASKS\n- [ ] A_01: alpha\n"
    (tmp_path / "TASKS.md").write_text(content, encoding="utf-8")
    gen = TasksMdGenerator()
    result = gen.update(tmp_path, completed=["A_01"], added=["- [ ] B_01: beta"])
    assert "- [x] A_01: alpha" in result
    assert "- [ ] B_01: beta" in result
