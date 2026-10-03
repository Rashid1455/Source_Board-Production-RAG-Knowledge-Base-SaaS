from io import BytesIO
from pathlib import Path
from pypdf import PdfReader

ALLOWED = {'.pdf','.txt','.md','.csv'}


def extract(name: str, content: bytes) -> list[str]:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError('Supported files: PDF, TXT, Markdown, CSV.')
    if suffix == '.pdf':
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted: raise ValueError('Upload an unlocked PDF.')
            if len(reader.pages)>300: raise ValueError('PDFs are limited to 300 pages.')
            pages=[]
            total=0
            for page in reader.pages:
                text=page.extract_text() or ''
                total+=len(text)
                if total>2_000_000: raise ValueError('Extracted text exceeds 2 million characters.')
                pages.append(text)
        except ValueError:
            raise
        except Exception as error:
            raise ValueError('Unable to parse PDF. Upload a valid text-based PDF.') from error
    else:
        try: pages=[content.decode('utf-8-sig')]
        except UnicodeDecodeError: raise ValueError('Use UTF-8 encoded text files.')
    if sum(map(len,pages))>2_000_000: raise ValueError('Extracted text exceeds 2 million characters.')
    if not any(p.strip() for p in pages): raise ValueError('No readable text found. Scanned PDFs need OCR.')
    return pages


def chunk_pages(pages: list[str]) -> list[dict]:
    chunks=[]
    for page,text in enumerate(pages,1):
        text=' '.join(text.split())
        for start in range(0,len(text),1200):
            passage=text[start:start+1500]
            if passage: chunks.append({'page':page,'text':passage,'ordinal':len(chunks)})
            if start+1500>=len(text): break
    return chunks
