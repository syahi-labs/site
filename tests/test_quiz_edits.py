# tests/test_quiz_edits.py
#
# Her answers of 2026-10-10 (quiz in chat), items not pinned elsewhere. The parity and page tests carry the rest
# (about/profiles in test_launch_pages and test_site, Spotify in test_b23_pages and test_schema, katha clip, home and
# Signet edits in test_parity and test_signet_page).
import re

import pytest

from tests.test_b23_pages import REPO, built, dist, main_of, register, visible  # noqa: F401  (fixtures)


def test_about_has_no_find_her_on_line(dist):
    text = visible(main_of(built(dist, "about.html")))
    assert "Find her on" not in text and "x.com" not in built(dist, "about.html")


def test_services_whole_office_starts_with_a_free_call_then_the_assessment(dist):
    text = visible(main_of(built(dist, "services.html")))
    assert "We start with free call" not in text
    assert "We start with a free call, then the assessment." in text and "We start with the assessment." not in text


def test_named_builds_examples_sit_under_a_for_example_lead_in(dist):
    main = main_of(built(dist, "services.html"))
    assert re.search(r'<p class="builds-lead">For example:</p>\s*<ul class="builds">', main)
    assert main.count("For example:") == 1


def test_the_home_colophon_is_the_two_sentences_and_the_sign_off(dist):
    main = main_of(built(dist, "index.html"))
    (colophon,) = re.findall(r'<section class="colophon">(.*?)</section>', main, re.S)
    paragraphs = [visible(p) for p in re.findall(r"<p>(.*?)</p>", colophon, re.S)]
    assert paragraphs[0] == ("Ink is how intent becomes record. Every piece of work that reaches you has a person's yes "
                             "behind it, and a dated record that shows it.")
    assert paragraphs[1].startswith("Surabhi Pradhan signs everything that leaves here, eleven years into AI, ML and analytics.")
    assert "same loop" not in colophon and "next decade" not in colophon


def test_the_home_card_iv_goes_to_the_plates(dist):
    main = main_of(built(dist, "index.html"))
    assert re.search(r'<a class="card" id="papermachine" href="/paper-machine">', main) and "see the plates" in main
    assert "watch on YouTube" not in main


def test_the_listener_blurb_and_hyphen(dist, register):
    html = (dist.parent / "katha.syahi.sh" / "index.html").read_text(encoding="utf-8")
    text = visible(main_of(html))
    assert ("Kabir Mehra's startup is sinking. His great-grandfather left him a ledger with one account still open, "
            "from 1947.") in text
    assert "Indian-language audiobooks" in text and "Indian Language" not in text


def test_the_publisher_page_has_the_clip_near_the_pitch(dist, register):
    main = main_of(built(dist, "katha.html"))
    assert main.index("Who it's for") < main.index("Hear the quality") < main.index("<audio") < main.index("The ask")
    assert register.get("katha-sample-length").text in visible(main)


def test_paper_machine_links_both_playlists_after_the_plates(dist, register):
    main = main_of(built(dist, "paper-machine.html"))
    a, b = register.get("pm-playlist-agents-url").text, register.get("pm-playlist-core-url").text
    assert (a, b) == ("https://www.youtube.com/playlist?list=PLAxWjMEpGWxI", "https://www.youtube.com/playlist?list=PLE-Rl7inR4Z4")
    assert f'<a href="{a}">' in main and f'<a href="{b}">' in main
    assert ("More on the channel: The Control Room: AI Agents and Core AI Concepts, Simply Explained.") in visible(main).replace(" .", ".")
    assert main.index("</ol>") < main.index("More on the channel") < main.index("New plates land")
