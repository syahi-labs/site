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

def test_good_content_exits_0(mini_root):
    # A build now needs the whole root (site.yaml, claims, templates, both hosts), so this uses the
    # mini fixture instead of a root holding one content file.
    r = run("--root", str(mini_root))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (mini_root / "dist" / "syahi.sh" / "index.html").is_file()
    assert (mini_root / "dist" / "katha.syahi.sh" / "index.html").is_file()

def test_missing_content_dir_exits_1(tmp_path):
    r = run("--root", str(tmp_path))
    assert r.returncode == 1

def test_a_problem_exits_1_and_is_printed(mini_root):
    sig = mini_root / "content" / "signet.html"
    sig.write_text(sig.read_text(encoding="utf-8").replace("claims: [", "claims: [org-name, ", 1), encoding="utf-8")
    r = run("--root", str(mini_root))
    assert r.returncode == 1
    assert "org-name" in r.stderr and "signet.html" in r.stderr

def test_release_exits_1_while_pages_are_pending(mini_root):
    assert run("--root", str(mini_root)).returncode == 0
    r = run("--root", str(mini_root), "--release")
    assert r.returncode == 1 and "pending" in r.stderr
