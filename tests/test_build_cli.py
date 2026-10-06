import subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

def run(*args):
    return subprocess.run([sys.executable, str(REPO / "build.py"), *args],
                          capture_output=True, text=True)

def test_bad_content_exits_1_and_names_file(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "broken.html").write_text("<p>no front matter</p>", encoding="utf-8")
    r = run("--root", str(tmp_path), "--out", str(tmp_path / "dist"))
    assert r.returncode == 1
    assert "broken.html" in (r.stdout + r.stderr)

def test_good_content_exits_0(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "index.html").write_text(
        "---\ntitle: Home\ndescription: d\nupdated: 2026-10-06\napproved: 2026-10-06\nlayout: page\n---\n<p>x</p>\n",
        encoding="utf-8")
    r = run("--root", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr

def test_missing_content_dir_exits_1(tmp_path):
    r = run("--root", str(tmp_path))
    assert r.returncode == 1
