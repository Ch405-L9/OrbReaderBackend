const express   = require("express");
const multer    = require("multer");
const fs        = require("fs");
const path      = require("path");
const pdfParse  = require("pdf-parse");

// epub2 usage per docs: const EPub = require("epub2").EPub;
const EPub      = require("epub2").EPub;

const app  = express();
const port = process.env.PORT || 3000;

// Store uploads in ./uploads
const upload = multer({ dest: path.join(__dirname, "uploads") });

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

// Simple word counter
function countWords(text) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

// Strip basic HTML tags and collapse whitespace
function stripHtml(html) {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Helper: extract text from EPUB using epub2
function extractEpubText(filePath) {
  return new Promise((resolve, reject) => {
    let epub;
    try {
      // imageWebRoot, chapterWebRoot can be null for our use case
      epub = new EPub(filePath, null, null);
    } catch (e) {
      return reject(e);
    }

    epub.on("error", err => reject(err));

    epub.on("end", () => {
      const ids = epub.flow.map(ch => ch.id);
      if (ids.length === 0) return resolve("");

      let remaining = ids.length;
      let fullText = "";

      ids.forEach(id => {
        epub.getChapter(id, (err, data) => {
          if (!err && data) {
            fullText += " " + stripHtml(data);
          }
          remaining -= 1;
          if (remaining === 0) {
            resolve(fullText.trim());
          }
        });
      });
    });

    epub.parse();
  });
}

// Main /convert endpoint
app.post("/convert", upload.single("file"), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No file uploaded" });
  }

  const originalName = req.file.originalname || "unknown";
  const ext = path.extname(originalName).toLowerCase();

  try {
    let text = "";
    let fileType = "txt";

    if (ext === ".pdf") {
      fileType = "pdf";

      const dataBuffer = fs.readFileSync(req.file.path);
      const result = await pdfParse(dataBuffer);
      const maybeText = (result.text || "").trim();

      if (!maybeText) {
        return res.status(400).json({
          error: "PDF has no extractable text (might be image-only or encrypted)"
        });
      }

      text = maybeText;
    } else if (ext === ".epub") {
      fileType = "epub";

      text = await extractEpubText(req.file.path);

      if (!text) {
        return res.status(400).json({
          error: "EPUB has no extractable text"
        });
      }
    } else {
      fileType = "txt";
      text = fs.readFileSync(req.file.path, "utf8").trim();
      if (!text) {
        return res.status(400).json({ error: "File is empty" });
      }
    }

    const wordCount = countWords(text);

    res.json({
      text,
      wordCount,
      fileType,
      originalName
    });
  } catch (err) {
    console.error("Conversion error:", err);
    res.status(500).json({
      error: "Failed to convert file: " + (err.message || "unknown error")
    });
  } finally {
    // Best-effort cleanup
    fs.unlink(req.file.path, () => {});
  }
});

// Start server
app.listen(port, () => {
  console.log(`OrbReader backend listening on http://localhost:${port}`);
});
