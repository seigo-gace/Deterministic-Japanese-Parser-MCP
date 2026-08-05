from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PUBLIC_FILES = (
    "README.md",
    "LICENSE",
    "NOTICE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "VALIDATION.md",
    "CHANGELOG.md",
    "docs/README.md",
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/DISCUSSION_TEMPLATE/validation-campaigns.yml",
    ".github/DISCUSSION_TEMPLATE/validation-results.yml",
    ".github/DISCUSSION_TEMPLATE/japanese-language-review.yml",
    ".github/DISCUSSION_TEMPLATE/environment-validation.yml",
    ".github/DISCUSSION_TEMPLATE/evidence-review.yml",
)

REMOVED_PUBLIC_ISSUE_FORMS = (
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/question.yml",
)

PUBLIC_TEXT_FILES = tuple(
    ROOT / relative_path
    for relative_path in REQUIRED_PUBLIC_FILES
    if relative_path != "LICENSE"
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_required_public_repository_files_exist() -> None:
    missing = [path for path in REQUIRED_PUBLIC_FILES if not (ROOT / path).is_file()]
    assert not missing, f"missing required public repository files: {missing}"


def test_readme_has_bilingual_public_entrypoints() -> None:
    readme = _read("README.md")
    required_markers = (
        "## 日本語",
        "## English",
        "### Install",
        "### 検証",
        "### Scope and limitations",
        "### License",
        "非AI",
        "Non-AI",
        "Meaning Graph",
        "External Action Guard",
    )
    missing = [marker for marker in required_markers if marker not in readme]
    assert not missing, f"README is missing public entrypoints: {missing}"


def test_public_documents_do_not_reference_private_workspaces_or_local_paths() -> None:
    forbidden_fragments = (
        "app.notion.com",
        "notion.so/",
        "/home/",
        "/Users/",
        "C:\\Users\\",
        "PRIVATE_KEY=",
        "API_TOKEN=",
        "ACCESS_TOKEN=",
    )

    violations: list[str] = []
    for path in PUBLIC_TEXT_FILES:
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{path.relative_to(ROOT)} contains {fragment!r}")

    assert not violations, "public repository leakage detected: " + "; ".join(violations)


def test_issue_entrypoint_is_reserved_for_confirmed_bugs() -> None:
    config = _read(".github/ISSUE_TEMPLATE/config.yml")
    bug_form = _read(".github/ISSUE_TEMPLATE/bug_report.yml")

    assert "blank_issues_enabled: false" in config
    assert "/discussions" in config
    assert "confirmed" in bug_form.lower()
    assert "reproducible" in bug_form.lower()
    assert "not a question" in bug_form.lower()

    unexpected = [path for path in REMOVED_PUBLIC_ISSUE_FORMS if (ROOT / path).exists()]
    assert not unexpected, f"non-bug public issue forms must be removed: {unexpected}"


def test_bug_form_and_pull_request_template_cover_public_safety() -> None:
    combined = "\n".join(
        _read(path)
        for path in (
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/pull_request_template.md",
        )
    )

    required_terms = (
        "commit SHA",
        "private URL",
        "secret",
        "test",
        "license",
    )
    missing = [term for term in required_terms if term.lower() not in combined.lower()]
    assert not missing, f"public bug and pull request forms are missing safeguards: {missing}"


def test_discussion_forms_cover_validation_boundaries() -> None:
    discussion_paths = (
        ".github/DISCUSSION_TEMPLATE/validation-campaigns.yml",
        ".github/DISCUSSION_TEMPLATE/validation-results.yml",
        ".github/DISCUSSION_TEMPLATE/japanese-language-review.yml",
        ".github/DISCUSSION_TEMPLATE/environment-validation.yml",
        ".github/DISCUSSION_TEMPLATE/evidence-review.yml",
    )
    combined = "\n".join(_read(path) for path in discussion_paths)

    required_terms = (
        "validation",
        "reproduce",
        "secret",
        "license",
        "External Action",
        "runtime",
        "Discussion",
        "Bug Issue",
    )
    missing = [term for term in required_terms if term.lower() not in combined.lower()]
    assert not missing, f"discussion validation forms are missing boundaries: {missing}"

    for path in discussion_paths:
        content = _read(path)
        assert "body:" in content, f"discussion form missing body: {path}"
        assert "validations:" in content, f"discussion form missing required fields: {path}"


def test_public_documentation_index_links_core_contracts() -> None:
    index = _read("docs/README.md")
    required_links = (
        "../README.md",
        "../VALIDATION.md",
        "../SUPPORT.md",
        "../CONTRIBUTING.md",
        "../SECURITY.md",
        "../CHANGELOG.md",
        "OPEN_LEXICON_ACCURACY.md",
        "OPEN_DICTIONARY_SUPPLY_CHAIN.md",
        "PUBLIC_RELEASE_CHECKLIST.md",
    )
    missing = [link for link in required_links if link not in index]
    assert not missing, f"documentation index is incomplete: {missing}"
