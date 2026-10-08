import pymupdf


def extract_pages_from_pdf(file_path: str) -> list[tuple[int, str]]:
    """Return [(page_number, text), ...] so answers can cite page numbers."""
    pages = []
    document = pymupdf.open(file_path)
    try:
        for index, page in enumerate(document, start=1):
            text = page.get_text()
            if text.strip():
                pages.append((index, text))
    finally:
        document.close()
    return pages


def extract_text_from_pdf(file_path: str) -> str:
    """Extract all text from a PDF (kept for backwards compatibility)."""
    return "\n".join(text for _, text in extract_pages_from_pdf(file_path))