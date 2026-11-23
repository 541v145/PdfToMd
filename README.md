# PDF → Markdown (lokalno)

Konverzija PDF-a u Markdown potpuno na ovom računaru. PDF-ovi se nikad ne šalju nikome.
Internet treba samo jednom, za preuzimanje modela (`setup_models.bat`); u radu je Hugging Face
prisilno u offline režimu i modeli se učitavaju iz `models/`.

## Korištenje

- **Prozor:** Start meni → *PDF u Markdown*, ili `PdfToMd.bat`. Prevuci PDF-ove ili foldere u listu → *Pretvori*.
- **Desni klik:** na PDF (ili više njih) → *Pretvori u Markdown* (Windows 11: *Show more options*).
  Ako je prozor već otvoren, fajlovi se dodaju u njega.
- **Komandna linija:**
  ```
  pdf2md.bat fajl.pdf folder\ [-o izlaz] [--pismo auto|latinica|cirilica] [--brzo] [--ocr] [--slike]
  ```

Izlaz: `ime.md`, pored PDF-a ili u izabranom folderu. Slike su po defaultu samo `[slika]` (štedi tokene);
sa `--slike` / *Izvuci slike* idu u `ime_slike/` sa relativnim linkovima.
Tekst koji je u PDF-u unutar grafike (kote na crtežu, "30 Years") ulazi u .md.

## Režimi

- **Kvalitetno** (Docling): raspored, naslovi, tabele; OCR (EasyOCR) samo za skenirane dijelove
  i strane sa pokvarenim tekstualnim slojem. Pismo skenova se automatski prepoznaje
  (latinica/ćirilica); EasyOCR ne može oba u istom prolazu, pa se bira po dokumentu.
- **Brzo** (PyMuPDF): samo tekstualni sloj, sekunde po fajlu, bez OCR-a.
- **OCR cijele strane**: kad digitalni PDF ima besmislen tekst (loši fontovi).

Na CPU-u: ~20–40 s po strani skena, prvi fajl duže (učitavanje modela).

## Instalacija ispočetka

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install docling easyocr pymupdf tkinterdnd2
setup_models.bat
powershell -ExecutionPolicy Bypass -File install_menu.ps1      (-Uninstall za uklanjanje)
```
Napomena: od pymupdf 2.x je `pymupdf4llm` dio paketa (`from pymupdf import pymupdf4llm`).
