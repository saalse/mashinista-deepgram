"""Locked: the docs site's front page, docs/index.mdx, is the README.

Below its frontmatter it is the README word for word without the H1, with
two links rewritten for the site: the Nistka page becomes `/nistka`, and
LICENSE points at GitHub. The author credit stays at the bottom.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_front_page_is_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    body = readme.split("\n", 1)[1].lstrip("\n")
    body = body.replace("(docs/nistka.md)", "(/nistka)").replace(
        "(LICENSE)", "(https://github.com/saalse/mashinista-deepgram/blob/main/LICENSE)"
    )
    page = (ROOT / "docs/index.mdx").read_text(encoding="utf-8")
    assert page.split("---\n", 2)[2].lstrip("\n") == body
    assert "Made by [Alex Samson](" in page
