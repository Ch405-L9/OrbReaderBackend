import os
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from tempfile import NamedTemporaryFile

from converter import convert

app = FastAPI(title="BADGR Text Conversion Service")

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
# Added image extensions for OCR support
ALLOWED_EXTENSIONS = {"pdf", "epub", "mobi", "azw3", "docx", "csv", "txt", "png", "jpg", "jpeg", "webp"}


def count_words(text: str) -> int:
    return len(text.split())


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert_endpoint(
    file: UploadFile = File(...),
    ocr_fallback: bool = Form(False),
):
    # If the file extension is an image, we force ocr_fallback to True
    filename = file.filename or "upload.bin"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    is_image = ext in {"png", "jpg", "jpeg", "webp"}
    use_ocr = ocr_fallback or is_image

    content = await file.read()

    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum is 20 MB.")

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    tmp_path = None
    try:
        # Create a temporary file with the correct extension
        suffix = f".{ext}" if ext else ".bin"
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Pass the file to the converter
        text = convert(tmp_path, use_ocr=use_ocr)

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    if not text or not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from this file."
        )

    return JSONResponse(content={
        "text": text,
        "wordCount": count_words(text),
        "fileType": ext,
        "error": None,
    })
