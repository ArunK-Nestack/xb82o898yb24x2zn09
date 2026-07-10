from pathlib import Path
from pypdf import PdfReader


ASSIGNMENT_PDF_MAP = {
    "webhook": "webhook.pdf",
    "rate-limiter": "rate-limiter.pdf",
    "standard-vectorization": "standard-vectorization.pdf",
    "langchain-vectorization": "langchain-vectorization.pdf",
    "robust-otp": "robust-otp.pdf",
    "data-extractor": "data-extractor.pdf",
}


def load_assignment_pdf(assessment_type: str) -> dict:
    file_name = ASSIGNMENT_PDF_MAP.get(assessment_type)

    if not file_name:
        return {
            "found": False,
            "assessmentType": assessment_type,
            "fileName": None,
            "filePath": None,
            "pageCount": 0,
            "pages": [],
            "combinedText": "",
            "message": f"No assignment PDF mapped for assessment type: {assessment_type}",
        }

    pdf_path = Path.cwd() / "assignments" / file_name

    if not pdf_path.exists():
        return {
            "found": False,
            "assessmentType": assessment_type,
            "fileName": file_name,
            "filePath": str(pdf_path),
            "pageCount": 0,
            "pages": [],
            "combinedText": "",
            "message": f"Assignment PDF not found: {pdf_path}",
        }

    reader = PdfReader(str(pdf_path))
    pages = []

    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""

        pages.append({
            "pageNumber": index + 1,
            "text": text.strip(),
        })

    combined_text = "\n\n".join(
        f"PAGE {page['pageNumber']}:\n{page['text']}"
        for page in pages
    )

    return {
        "found": True,
        "assessmentType": assessment_type,
        "fileName": file_name,
        "filePath": str(pdf_path),
        "pageCount": len(pages),
        "pages": pages,
        "combinedText": combined_text,
        "message": f"Assignment PDF loaded: {file_name}",
    }