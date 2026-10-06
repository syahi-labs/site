# tests/test_parity_helpers.py
#
# The one text-parity comparison every ported page uses (tests/parity_helpers.py), tested on its own
# so a page test passing means the page matches, not that the helper is lenient.
import pytest

from parity_helpers import apply_allowed, link_values, words


def page(body: str) -> str:
    return f"<html><head><title>T</title></head><body>{body}</body></html>"


def test_inline_elements_are_transparent():
    markup = page('<p>by <span data-claim="x">day 30</span>, you pay <b>nothing</b>. <a href="/a">Read</a>.</p>')
    assert words(markup, "body") == "by day 30, you pay nothing. Read."


def test_a_time_or_small_inside_a_line_adds_no_space():
    assert words(page('<p>Last updated <time datetime="2026-09-10">10 September 2026</time></p>'), "body") == "Last updated 10 September 2026"
    assert words(page("<p>₹1,499 a month<small>GST included</small></p>"), "body") == "₹1,499 a monthGST included"


@pytest.mark.parametrize("markup", [
    "<p>one</p><p>two</p>", "<div>one</div><div>two</div>", "<ul><li>one</li><li>two</li></ul>",
    "<dl><div><dt>one</dt><dd>two</dd></div></dl>", "<h2>one</h2><h3>two</h3>", "one<br>two",
    "<section>one</section><section>two</section>", "<figure>one</figure><figcaption>two</figcaption>",
])
def test_block_elements_are_breaks_even_with_no_whitespace_between_them(markup):
    assert words(page(markup), "body") == "one two"


def test_a_tag_it_does_not_know_counts_as_a_block():
    assert words(page("<p>one</p><made-up>two</made-up>three"), "body") == "one two three"


def test_script_style_svg_head_and_the_olds_footer_nav_canvas_are_not_text():
    markup = ("<html><head><title>Title</title><style>.a{}</style></head><body>"
              "<script>var x = 1</script><svg><text>glyph</text></svg><nav>menu</nav><canvas>c</canvas>"
              "<noscript>n</noscript><p>kept</p><footer>foot</footer></body></html>")
    assert words(markup, "body") == "kept"


def test_whitespace_and_non_breaking_spaces_collapse():
    assert words(page("<p>a \n\n  b&nbsp;&middot;&nbsp;c</p>"), "body") == "a b · c"


def test_main_scope_reads_only_main():
    markup = page("<header>strip</header><main><h1>Head</h1><p>Body</p></main><footer>foot</footer>")
    assert words(markup, "main") == "Head Body"
    assert words(markup, "body") == "strip Head Body"


def test_main_scope_ends_at_the_closing_tag():
    assert words(page("<p>before</p><main>inside</main><p>after</p>"), "main") == "inside"


def test_a_page_with_no_main_has_no_main_text():
    assert words(page("<p>no main here</p>"), "main") == ""


# ---- allowed differences ----

def diffs(tmp_path, text: str):
    path = tmp_path / "allowed.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_an_allowed_diff_is_removed_once_as_a_whole_run(tmp_path):
    path = diffs(tmp_path, "p.html:\n  - {text: \"ENTRY P-01\", reason: strip}\n")
    assert apply_allowed("ENTRY P-01 Privacy ENTRY P-01", "p.html", path) == "Privacy ENTRY P-01"


def test_an_allowed_diff_must_be_a_whole_run_of_words(tmp_path):
    path = diffs(tmp_path, "p.html:\n  - {text: \"01\", reason: marker}\n")
    with pytest.raises(AssertionError, match="not in the old page"):
        apply_allowed("Call 0123 now", "p.html", path)


def test_a_stale_allowed_diff_fails(tmp_path):
    path = diffs(tmp_path, "p.html:\n  - {text: \"gone\", reason: was a strip}\n")
    with pytest.raises(AssertionError, match="gone"):
        apply_allowed("the page no longer says it", "p.html", path)


def test_an_allowed_diff_without_a_reason_fails(tmp_path):
    path = diffs(tmp_path, "p.html:\n  - {text: \"strip\", reason: \"  \"}\n")
    with pytest.raises(AssertionError, match="no reason"):
        apply_allowed("strip text", "p.html", path)
    path = diffs(tmp_path, "p.html:\n  - {text: \"strip\"}\n")
    with pytest.raises(AssertionError, match="no reason"):
        apply_allowed("strip text", "p.html", path)


def test_a_snapshot_with_no_entries_is_only_whitespace_normalised(tmp_path):
    path = diffs(tmp_path, "other.html:\n  - {text: \"x\", reason: r}\n")
    assert apply_allowed("a   b", "p.html", path) == "a b"
    assert apply_allowed("a   b", "p.html", diffs(tmp_path, "")) == "a b"


# ---- links ----

def test_link_values_are_in_document_order_and_include_src():
    markup = '<a href="/a">x</a><img src="/i.webp"><link href="/s.css"><a href="mailto:hello@syahi.example">m</a>'
    assert link_values(markup) == ["/a", "/i.webp", "/s.css", "mailto:hello@syahi.example"]
