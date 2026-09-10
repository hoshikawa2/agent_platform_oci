from pathlib import Path
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]


def _local_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [
        target for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", text)
        if not target.startswith(("http://", "https://", "#", "mailto:"))
    ]


def test_main_readmes_have_no_broken_local_links():
    for name in ("README.md", "README_en.md"):
        readme = ROOT / name
        for target in _local_links(readme):
            relative = unquote(target.split("#", 1)[0])
            assert not relative or (readme.parent / relative).exists(), (name, target)


def test_every_feature_guide_is_listed_in_corresponding_main_readme():
    pairs = (("pt-BR", "README.md"), ("en", "README_en.md"))
    for language, readme_name in pairs:
        readme = (ROOT / readme_name).read_text(encoding="utf-8")
        guides = sorted((ROOT / "docs" / "features" / language).glob("[0-9][0-9]_*.md"))
        assert guides
        for guide in guides:
            expected = f"docs/features/{language}/{guide.name}"
            assert expected in readme, (readme_name, expected)


def test_portuguese_and_english_feature_catalogs_are_symmetric():
    pt = {path.name for path in (ROOT / "docs" / "features" / "pt-BR").glob("*.md")}
    en = {path.name for path in (ROOT / "docs" / "features" / "en").glob("*.md")}
    assert pt == en
