from deploy.linux.service import render_service


def test_systemd_service_rendering(tmp_path):
    template = (tmp_path / "jarvis.service")
    template.write_text("WorkingDirectory=@PROJECT_DIR@\nExecStart=@PYTHON@ @PROJECT_DIR@/main.py --background\n")
    rendered = render_service(template.read_text(), tmp_path / "project", tmp_path / "venv/bin/python")
    assert "@PROJECT_DIR@" not in rendered
    assert "--background" in rendered
