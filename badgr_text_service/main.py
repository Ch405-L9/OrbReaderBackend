from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import PlainTextResponse
from tempfile import NamedTemporaryFile
import shutil

from converter import convert

app = FastAPI(title="BADGR Text Conversion Service")

@app.post("/convert", response_class=PlainTextResponse)
async def convert_endpoint(
    file: UploadFile = File(...),
    ocr_fallback: bool = Form(False),
):
    try:
        suffix = "." + file.filename.split(".")[-1] if "." in file.filename else ""
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to save uploaded file")

    try:
        text = convert(tmp_path, use_ocr=ocr_fallback)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Conversion failed")
    finally:
        try:
            import os
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    return text
