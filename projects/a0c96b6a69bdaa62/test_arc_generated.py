import pathlib, subprocess

def test_application_artifacts():
    assert pathlib.Path("index.html").is_file()
    assert pathlib.Path("app.js").is_file()
    assert pathlib.Path("test_app.js").is_file()
    assert "node:test" in pathlib.Path("test_app.js").read_text()
    for path in pathlib.Path(".").rglob("*.js"):
        subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, text=True)
    result = subprocess.run(["node", "--test", "test_app.js"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# tests 0" not in result.stdout, "No JavaScript tests ran"
