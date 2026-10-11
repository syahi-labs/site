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

def test_warnings_are_printed_and_do_not_fail_the_build(mini_root):
    # the fixture's Services tab points at a pending page: a dev build says so and still exits 0
    r = run("--root", str(mini_root))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "warning:" in r.stderr and "/services" in r.stderr and "pending" in r.stderr
    assert "error:" not in r.stderr and "3 warning(s)" in r.stdout

def test_warnings_are_printed_beside_the_problems_of_a_failed_build(mini_root):
    sig = mini_root / "content" / "signet.html"
    sig.write_text(sig.read_text(encoding="utf-8").replace("<h1>", "<h1>We leverage ", 1), encoding="utf-8")
    r = run("--root", str(mini_root))
    assert r.returncode == 1
    assert "error:" in r.stderr and "buzzword" in r.stderr and "warning:" in r.stderr

def test_a_clean_build_with_no_warnings_says_nothing_of_them(mini_root):
    (mini_root / "site.yaml").write_text(
        (mini_root / "site.yaml").read_text(encoding="utf-8").replace("pending_pages: [/services]", "pending_pages: []")
        .replace("  - {label: Services, href: /services}\n", ""), encoding="utf-8")
    r = run("--root", str(mini_root))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "warning" not in (r.stdout + r.stderr)
