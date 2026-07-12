from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import humalike
from humalike import AsyncHumalikeClient, HumalikeClient

ROOT = Path(__file__).parents[1]
API_REFERENCE = ROOT / "docs" / "API_REFERENCE.md"
MARKDOWN_FILES = (
    sorted(ROOT.glob("*.md"))
    + sorted((ROOT / "docs").glob("*.md"))
    + [ROOT / "examples" / "README.md"]
)


def _public_callables(cls: type[object]) -> set[str]:
    return {
        name for name in dir(cls) if not name.startswith("_") and callable(getattr(cls, name, None))
    }


def test_api_reference_mentions_every_public_client_method() -> None:
    reference = API_REFERENCE.read_text(encoding="utf-8")
    methods = _public_callables(HumalikeClient) | _public_callables(AsyncHumalikeClient)
    missing = sorted(
        name for name in methods if f"{name}(" not in reference and f"`{name}`" not in reference
    )
    assert missing == []


def test_release_docs_mention_every_public_export() -> None:
    documentation = "\n".join(path.read_text(encoding="utf-8") for path in MARKDOWN_FILES)
    missing = sorted(name for name in humalike.__all__ if name not in documentation)
    assert missing == []


def test_local_markdown_links_resolve() -> None:
    missing: list[str] = []
    for document in MARKDOWN_FILES:
        text = document.read_text(encoding="utf-8")
        for raw_target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith(("#", "mailto:")):
                continue
            resolved = document.parent / unquote(target)
            if not resolved.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {raw_target}")
    assert missing == []


def test_release_markdown_has_balanced_code_fences() -> None:
    unbalanced = [
        str(path.relative_to(ROOT))
        for path in MARKDOWN_FILES
        if path.read_text(encoding="utf-8").count("```") % 2
    ]
    assert unbalanced == []


def test_api_reference_keeps_safety_contract_discoverable() -> None:
    reference = API_REFERENCE.read_text(encoding="utf-8")
    required_terms = {
        "408",
        "429",
        "502",
        "503",
        "504",
        "Retry-After",
        "retry=True",
        "OperationTimeoutError",
        "UpstreamError",
        "TurnTakingStream",
        "recv(timeout",
        "total=False",
    }
    assert {term for term in required_terms if term not in reference} == set()
