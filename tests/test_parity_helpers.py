# tests/test_parity_helpers.py
#
# The one text-parity comparison every ported page uses (tests/parity_helpers.py), tested on its own
# so a page test passing means the page matches, not that the helper is lenient.
import pytest

from parity_helpers import PARITY, LinkMove, LINK_MOVES, apply_allowed, apply_link_moves, link_values, moves_used, words


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


# ---- link moves: a page that moved into the one site is linked at its new home, and nothing else changes ----

MOVES = (
    LinkMove("https://shop.example", "/shop", "the shop moved into the one site", host=True),
    LinkMove("https://blog.example/", "/blog", "only the blog's front page moved"),
    LinkMove("art/a.webp", "/assets/img/a.webp", "the same file, in the shared assets"),
)


def test_a_link_move_replaces_an_exact_value_and_leaves_every_other_value_alone():
    values = ["https://blog.example/", "https://blog.example/post", "art/a.webp", "art/b.webp", "mailto:hi@syahi.example"]
    assert apply_link_moves(values, MOVES) == ["/blog", "https://blog.example/post", "/assets/img/a.webp", "art/b.webp",
                                               "mailto:hi@syahi.example"]


def test_a_host_move_takes_any_path_on_that_host_and_only_that_host():
    values = ["https://shop.example", "https://shop.example/", "https://shop.example/cart?x=1#top", "https://shop.example.other.example/",
              "https://notshop.example/", "http://shop.example/", "/shop"]
    assert apply_link_moves(values, MOVES) == ["/shop", "/shop", "/shop", "https://shop.example.other.example/",
                                               "https://notshop.example/", "http://shop.example/", "/shop"]


def test_the_order_and_the_length_of_the_links_never_change():
    values = ["a", "art/a.webp", "b", "https://shop.example/x", "a"]
    assert len(apply_link_moves(values, MOVES)) == len(values)
    assert apply_link_moves([], MOVES) == []


def test_moves_used_names_each_move_that_matched_at_least_once():
    values = ["https://shop.example/a", "https://shop.example/b", "x"]
    assert moves_used(values, MOVES) == [MOVES[0]]
    assert moves_used(["x"], MOVES) == []


def test_every_real_move_has_a_reason_and_goes_to_a_path_on_this_site():
    assert LINK_MOVES
    for move in LINK_MOVES:
        assert move.reason.strip() and len(move.reason.split()) >= 4, move
        assert move.new.startswith("/") and not move.new.startswith("//"), move
        assert chr(0x2014) not in move.old + move.new + move.reason
    assert len({move.old for move in LINK_MOVES}) == len(LINK_MOVES)       # one entry per old value


def test_the_real_moves_are_the_controllers_ruling_and_the_art_that_moved_to_assets():
    by_old = {move.old: move for move in LINK_MOVES}
    assert (by_old["https://signet.syahi.sh"].new, by_old["https://signet.syahi.sh"].host) == ("/signet", True)
    assert (by_old["https://services.syahi.sh"].new, by_old["https://services.syahi.sh"].host) == ("/services/quote", True)
    assert (by_old["https://katha.syahi.sh/"].new, by_old["https://katha.syahi.sh/"].host) == ("/katha", False)
    for name in ("inkpot", "loom", "gramophone", "cube"):
        assert by_old[f"art/{name}.webp"].new == f"/assets/img/{name}.webp"
    assert by_old["https://syahi.sh/art/gramophone.webp"].new == "/assets/img/gramophone.webp"
    # Task 9c: Signet's own footer linked the main site by its full address; the site's pages are linked by path
    for path in ("contact", "privacy", "terms", "refund"):
        assert (by_old[f"https://syahi.sh/{path}"].new, by_old[f"https://syahi.sh/{path}"].host) == (f"/{path}", False)
    assert (by_old["https://syahi.sh/"].new, by_old["https://syahi.sh/"].host) == ("/", False)
    assert len(by_old) == 13


def test_no_real_move_is_stale_each_one_is_used_by_a_snapshot():
    # A move whose old value is in no snapshot is dead weight, and a place a link could change unseen.
    seen = []
    for snapshot in sorted(PARITY.glob("*.html")):
        seen += link_values(snapshot.read_text(encoding="utf-8"))
    for move in LINK_MOVES:
        assert move in moves_used(seen, LINK_MOVES), f"{move.old} is in no snapshot: remove the move"
