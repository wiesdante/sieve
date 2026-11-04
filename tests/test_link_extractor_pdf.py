import pytest

from sieve.core.link_extractor import EMAILS, LINK, ExtractOptions

pymupdf = pytest.importorskip("pymupdf")

from sieve.core.link_extractor import extract_from_pdfs  # noqa: E402


def make_pdf(path, pages):
    doc = pymupdf.open()
    for text, links in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
        for i, uri in enumerate(links):
            rect = pymupdf.Rect(72, 100 + i * 20, 300, 115 + i * 20)
            page.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": uri})
    doc.save(str(path))
    doc.close()


def test_pdf_combines_clickable_and_text_links(tmp_path):
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, [
        ("Contact: www.acme.example or mail info@acme.example", ["https://hidden.example/offer"]),
        ("Again https://hidden.example/offer and shop.io", ["mailto:x@y.z"]),
    ])
    result = extract_from_pdfs([pdf])
    assert result.lines == [
        "https://hidden.example/offer",
        "https://www.acme.example",
        "https://shop.io",
    ]
    assert result.links[0].kind == LINK and result.links[0].page == 1
    assert result.links[2].page == 2
    assert (result.files, result.pages, result.errors) == (1, 2, [])


def test_wrapped_text_link_is_dropped_in_favour_of_clickable_link(tmp_path):
    pdf = tmp_path / "wrapped.pdf"
    make_pdf(pdf, [("https://example.com/very/long", ["https://example.com/very/long/address?q=1"])])
    assert extract_from_pdfs([pdf]).lines == ["https://example.com/very/long/address?q=1"]


def test_bad_files_are_reported_and_others_still_processed(tmp_path):
    good = tmp_path / "good.pdf"
    make_pdf(good, [("site.com", [])])
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    result = extract_from_pdfs([bad, good])
    assert result.lines == ["https://site.com"]
    assert result.errors and result.errors[0][0] == "bad.pdf"


def test_pdf_email_mode_uses_mailto_and_text(tmp_path):
    pdf = tmp_path / "contacts.pdf"
    make_pdf(pdf, [
        ("Sales: sales@acme.example, site www.acme.example", ["mailto:ceo@acme.example?subject=Hi"]),
        ("Again SALES@acme.example and jobs@acme.example", []),
    ])
    result = extract_from_pdfs([pdf], ExtractOptions(mode=EMAILS))
    assert result.lines == ["ceo@acme.example", "sales@acme.example", "jobs@acme.example"]
    assert result.links[0].kind == LINK
