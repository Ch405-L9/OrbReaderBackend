import os
import re
import random
import base64
from collections import Counter
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from tempfile import NamedTemporaryFile

from converter import convert

app = FastAPI(title="BADGR Text Conversion Service")

MAX_FILE_BYTES  = 100 * 1024 * 1024  # 100 MB — documents (Pro tier uploads)
MAX_IMAGE_BYTES =   5 * 1024 * 1024  #   5 MB — images

DOCUMENT_EXTENSIONS = {"pdf", "epub", "mobi", "azw3", "docx", "csv", "txt"}
IMAGE_EXTENSIONS     = {"png", "jpg", "jpeg", "webp"}


_STOP_WORDS = {
    'the','a','an','is','it','in','on','at','to','for','of','and','or','but',
    'with','as','by','from','that','this','was','are','were','be','been','has',
    'have','had','he','she','they','we','i','you','his','her','their','its',
    'not','so','do','did','if','up','out','about','than','then','there','what',
    'which','who','whom','when','where','how','all','each','both','more','also',
    'been','could','would','should','will','can','may','might','just','one','two',
}

MAX_SUMMARIZE_WORDS = 4000


def count_words(text: str) -> int:
    return len(text.split())


def _extractive_summary(text: str, max_sentences: int = 6) -> tuple[str, list[str]]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if len(s.split()) >= 6]
    if not sentences:
        return text[:500], []
    if len(sentences) <= max_sentences:
        return " ".join(sentences), sentences[:3]

    words = re.findall(r'\b[a-z]+\b', text.lower())
    freq = Counter(w for w in words if w not in _STOP_WORDS)

    def score(sent: str) -> float:
        sw = re.findall(r'\b[a-z]+\b', sent.lower())
        return sum(freq.get(w, 0) for w in sw) / max(len(sw), 1)

    scored = sorted(enumerate(sentences), key=lambda x: score(x[1]), reverse=True)
    top_idx = sorted(i for i, _ in scored[:max_sentences])
    top = [sentences[i] for i in top_idx]
    key_points = [sentences[i] for i in sorted(i for i, _ in scored[:3])]
    return " ".join(top), key_points


_QUESTION_TEMPLATES = [
    "Which of the following is stated in the text?",
    "According to the passage, which statement is true?",
    "Which of the following appears in the reading?",
]

MAX_QUIZ_WORDS = 4000


def _generate_quiz(text: str, num_questions: int = 3) -> list[dict]:
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.split()) >= 8]
    if len(sentences) < num_questions * 4:
        return []

    def informativeness(sent: str) -> int:
        score = 0
        if re.search(r'\b[A-Z][a-z]+\b', sent): score += 2
        if re.search(r'\b\d+\b', sent):          score += 2
        if len(sent.split()) > 12:               score += 1
        return score

    scored = sorted(enumerate(sentences), key=lambda x: informativeness(x[1]), reverse=True)
    questions = []
    used: set[int] = set()

    for qi, (idx, correct) in enumerate(scored):
        if len(questions) >= num_questions:
            break
        used.add(idx)
        distractors = [s for j, s in enumerate(sentences)
                       if j not in used and abs(j - idx) > 1][:3]
        if len(distractors) < 3:
            continue
        options = [correct[:220]] + [d[:220] for d in distractors]
        random.shuffle(options)
        questions.append({
            "question": _QUESTION_TEMPLATES[qi % len(_QUESTION_TEMPLATES)],
            "options":  options,
            "answerIndex": options.index(correct[:220]),
        })
        used.update(j for j, s in enumerate(sentences) if s in distractors)

    return questions


class SummarizeRequest(BaseModel):
    text: str
    max_sentences: int = 6


class QuizRequest(BaseModel):
    text: str
    num_questions: int = 3


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/summarize")
async def summarize_endpoint(req: SummarizeRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    words = text.split()
    if len(words) > MAX_SUMMARIZE_WORDS:
        text = " ".join(words[:MAX_SUMMARIZE_WORDS])
    summary, key_points = _extractive_summary(text, max_sentences=req.max_sentences)
    return JSONResponse(content={
        "summary": summary,
        "keyPoints": key_points,
        "wordCount": len(words),
    })


@app.post("/quiz")
async def quiz_endpoint(req: QuizRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    words = text.split()
    if len(words) > MAX_QUIZ_WORDS:
        text = " ".join(words[:MAX_QUIZ_WORDS])
    questions = _generate_quiz(text, num_questions=min(req.num_questions, 5))
    if not questions:
        raise HTTPException(status_code=422, detail="Not enough text to generate quiz questions.")
    return JSONResponse(content={"questions": questions})


@app.post("/convert")
async def convert_endpoint(
    file: UploadFile = File(...),
    ocr_fallback: bool = Form(False),
):
    filename = file.filename or "upload.bin"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Reject bad types before reading any bytes — no point buffering them.
    if ext in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Images are not text documents. Use POST /upload-image for covers and profile photos."
        )

    if ext not in DOCUMENT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    # Stream upload directly to a temp file in 64 KB chunks so a 100 MB document
    # never fully occupies RAM (Render free tier: 512 MB). Size is checked
    # incrementally — the upload aborts the moment the limit is exceeded.
    tmp_path = None
    try:
        suffix = f".{ext}" if ext else ".bin"
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            received = 0
            chunk_size = 64 * 1024  # 64 KB
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum is {MAX_FILE_BYTES // (1024 * 1024)} MB."
                    )
                tmp.write(chunk)

        text = convert(tmp_path, use_ocr=ocr_fallback)

    except HTTPException:
        raise  # don't let the broad Exception handler swallow 413/400
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


@app.post("/upload-image")
async def upload_image_endpoint(
    file: UploadFile = File(...),
    purpose: str = Form("cover"),
):
    """
    Accepts a cover or profile image. Returns it base64-encoded so the
    Android client can store it locally via CoverExtractor.fromUserPick()
    without needing server-side storage at this stage.
    purpose: "cover" | "profile"
    """
    filename = file.filename or "image.bin"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: .{ext}. Allowed: png, jpg, jpeg, webp"
        )

    content = await file.read()

    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large. Maximum is 5 MB.")

    mime = f"image/{'jpeg' if ext == 'jpg' else ext}"
    encoded = base64.b64encode(content).decode("utf-8")

    return JSONResponse(content={
        "imageBase64": encoded,
        "mimeType": mime,
        "sizeBytes": len(content),
        "purpose": purpose,
        "error": None,
    })
