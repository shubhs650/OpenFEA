"""Word text/package boundaries; actual rendering and editing run in test-reports."""

import io
import zipfile

import pytest

from worker.reports.docx import valid_text, validate_docx


@pytest.mark.parametrize(
    "text", ["σxx ≤ 1.2 MPa · Évaluation & <review> μm", "Title\nline\ttab", ""]
)
def test_word_preserves_supported_xml_characters(text: str) -> None:
    valid_text(text)


@pytest.mark.parametrize("text", ["bad\x00text", "bad\x01", "bad\ud800", "bad\ufffe"])
def test_word_refuses_characters_that_would_be_silently_lost(text: str) -> None:
    with pytest.raises(ValueError, match="character"):
        valid_text(text)


@pytest.mark.parametrize("fault", ["traversal", "external", "macro", "count", "missing"])
def test_word_package_refuses_unsafe_outputs(fault: str) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if fault != "missing":
            archive.writestr("word/document.xml", "<document/>")
        if fault == "traversal":
            archive.writestr("../escape", "invalid")
        elif fault == "external":
            archive.writestr(
                "word/_rels/document.xml.rels",
                '<Relationships><Relationship TargetMode="External" Target="https://invalid.example"/></Relationships>',
            )
        elif fault == "macro":
            archive.writestr("word/vbaProject.bin", b"invalid")
        elif fault == "count":
            for i in range(64):
                archive.writestr(f"many-{i}", "invalid")
    with pytest.raises(ValueError):
        validate_docx(buffer.getvalue())
