const express  = require('express');
const multer   = require('multer');
const fs       = require('fs');
const path     = require('path');
const pdfParse = require('pdf-parse');
const Epub     = require('epub2').default;

const app  = express();
const port = 3000;

const upload = multer({ dest: path.join(__dirname, 'uploads') });

function countWords(text) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function stripHtml(str) {
  return str.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

app.get('/health', (req, res) => res.json({ status: 'ok' }));

app.post('/convert', upload.single('file'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

  const ext = path.extname(req.file.originalname || '').toLowerCase();

  try {
    let text = '';
    let fileType = 'txt';

    if (ext === '.pdf') {
      fileType = 'pdf';
      const dataBuffer = fs.readFileSync(req.file.path);
      const result = await pdfParse(dataBuffer);
      text = (result.text || '').trim();
      if (!text) return res.status(400).json({ error: 'PDF has no extractable text' });

    } else if (ext === '.epub') {
      fileType = 'epub';
      const epub = await Epub.createAsync(req.file.path);
      const chapters = await Promise.all(
        epub.flow.map(chapter =>
          new Promise(resolve => {
            epub.getChapterAsync(chapter.id)
              .then(data => resolve(stripHtml(data || '')))
              .catch(() => resolve(''));
          })
        )
      );
      text = chapters.filter(Boolean).join(' ').trim();
      if (!text) return res.status(400).json({ error: 'EPUB has no extractable text' });

    } else {
      fileType = 'txt';
      text = fs.readFileSync(req.file.path, 'utf8').trim();
      if (!text) return res.status(400).json({ error: 'File is empty' });
    }

    res.json({
      text,
      wordCount: countWords(text),
      fileType,
      originalName: req.file.originalname
    });

  } catch (err) {
    console.error('Conversion error:', err);
    res.status(500).json({ error: 'Failed to convert: ' + (err.message || 'unknown') });
  } finally {
    fs.unlink(req.file.path, () => {});
  }
});

app.listen(port, () => console.log(`OrbReader backend listening on http://localhost:${port}`));
