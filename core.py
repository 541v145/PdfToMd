"""Lokalna konverzija PDF -> Markdown. Ništa se ne šalje na internet.

Modeli se preuzimaju jednom (setup_models.py) u folder models/, a u radu je
Hugging Face hub prisilno u offline režimu.
"""
import os
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
MODELS_DIR = APP_DIR / "models"
EASYOCR_DIR = MODELS_DIR / "EasyOcr"

# Mora prije importa docling/transformers/huggingface_hub
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import logging  # noqa: E402
import warnings  # noqa: E402

warnings.filterwarnings("ignore")
logging.getLogger("docling").setLevel(logging.ERROR)

# EasyOCR: ćirilica se može kombinovati samo sa engleskim, latinica sa ostalim latiničnim
OCR_LANGS = {
    "latinica": ["rs_latin", "en"],
    "cirilica": ["rs_cyrillic", "en"],
}

_converters = {}
_readers = {}


def _reader(script):
    if script not in _readers:
        import easyocr

        _readers[script] = easyocr.Reader(
            OCR_LANGS[script], gpu=False, model_storage_directory=str(EASYOCR_DIR), download_enabled=False, verbose=False
        )
    return _readers[script]


def detect_script(pdf):
    """Vraća "latinica" ili "cirilica" za OCR skeniranih strana.

    Ćirilični model (rs_cyrillic + en) čita oba pisma, pa se na srednjoj trećini prve
    skenirane strane gleda udio ćiriličnih slova u rezultatu. Ako sve strane imaju
    tekstualni sloj, OCR skoro nije potreban i pismo nije bitno.
    """
    import numpy as np
    import pymupdf

    with pymupdf.open(pdf) as doc:
        page = next((p for p in doc if len(p.get_text().strip()) < 50), None)
        if page is None:
            return "latinica"
        r = page.rect
        clip = pymupdf.Rect(r.x0, r.y0 + r.height / 3, r.x1, r.y0 + 2 * r.height / 3)
        pix = page.get_pixmap(dpi=120, colorspace=pymupdf.csGRAY, clip=clip)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)

    text = "".join(_reader("cirilica").readtext(img, detail=0))
    letters = [c for c in text if c.isalpha()]
    cyr = sum("Ѐ" <= c <= "ӿ" for c in letters)
    return "cirilica" if letters and cyr / len(letters) > 0.4 else "latinica"


def models_ready():
    return MODELS_DIR.is_dir() and EASYOCR_DIR.is_dir() and any(EASYOCR_DIR.glob("*.pth"))


def _docling_converter(script, force_ocr, images):
    key = (script, force_ocr, images)
    if key in _converters:
        return _converters[key]

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, OcrMode, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions(artifacts_path=str(MODELS_DIR))
    opts.enable_remote_services = False
    opts.do_picture_classification = False
    # OCR se primjenjuje samo na dijelove strane bez tekstualnog sloja (skenovi, slike),
    # osim ako je force_ocr uključen. Strane sa pokvarenim tekstualnim slojem
    # (česta pojava kod CAD PDF-ova) automatski idu kroz OCR.
    opts.do_ocr = True
    opts.ocr_options = EasyOcrOptions(
        lang=OCR_LANGS[script],
        mode=OcrMode.FULL_PAGE if force_ocr else OcrMode.DEFAULT,
        replace_broken_text_layer=True,
        model_storage_directory=str(EASYOCR_DIR),
        download_enabled=False,
    )
    opts.do_table_structure = True
    opts.table_structure_options.do_cell_matching = True
    opts.generate_picture_images = images
    opts.images_scale = 2.0

    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    _converters[key] = conv
    return conv


def output_paths(pdf, out_dir=None):
    pdf = Path(pdf)
    target = Path(out_dir) if out_dir else pdf.parent
    return target / f"{pdf.stem}.md", target / f"{pdf.stem}_slike"


def convert(pdf, out_dir=None, mode="kvalitetno", script="auto", force_ocr=False, images=False):
    """Pretvara jedan PDF i vraća (putanja do .md, korišteno pismo ili None u brzom režimu)."""
    pdf = Path(pdf)
    md_path, img_dir = output_paths(pdf, out_dir)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "brzo":
        from pymupdf import pymupdf4llm  # od pymupdf 2.x je 4llm dio paketa

        kwargs = {}
        if images:
            img_dir.mkdir(exist_ok=True)
            kwargs = {"write_images": True, "image_path": str(img_dir)}
        md = pymupdf4llm.to_markdown(str(pdf), **kwargs)
        md_path.write_text(md, encoding="utf-8")
        if images and not any(img_dir.iterdir()):
            img_dir.rmdir()
        return md_path, None

    if not models_ready():
        raise RuntimeError("Modeli nisu preuzeti. Pokreni setup_models.bat (jednom, uz internet).")

    from docling_core.types.doc import ImageRefMode

    if script == "auto":
        script = detect_script(pdf)
    result = _docling_converter(script, force_ocr, images).convert(pdf)
    md_opts = {
        "compact_tables": True,  # bez poravnanja kolona razmacima (kod tabela i do 2/3 fajla = bačeni tokeni)
        "traverse_pictures": True,  # tekst koji je Docling svrstao u sliku (kote na crtežima, "30 Years" u grafici)
        "escape_html": False,  # & umjesto &amp;
        "image_placeholder": "[slika]",
    }
    if images:
        # Relativan artifacts_dir -> relativni linkovi u .md (folder se može premještati)
        result.document.save_as_markdown(md_path, artifacts_dir=Path(img_dir.name),
                                          image_mode=ImageRefMode.REFERENCED, **md_opts)
        if img_dir.is_dir() and not any(img_dir.iterdir()):
            img_dir.rmdir()
    else:
        result.document.save_as_markdown(md_path, image_mode=ImageRefMode.PLACEHOLDER, **md_opts)
    md_path.write_text(cleanup(md_path.read_text(encoding="utf-8")), encoding="utf-8")
    return md_path, script


_LOWER = "a-zčćšžđа-яђјљњћџ"


def cleanup(md):
    """Sitne popravke PDF artefakata u tekstu."""
    md = re.sub(rf"([{_LOWER}])- ([{_LOWER}])", r"\1\2", md)  # "Inclu- ding" -> "Including"
    md = md.replace("ˣ", "×")
    md = re.sub(r"(?<=/)(c?m) ([23])\b", lambda m: m[1] + "²³"[int(m[2]) - 2], md)  # "W/m 2" -> "W/m²"
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md


def collect_pdfs(paths):
    """Fajlovi i folderi (rekurzivno) -> lista PDF-ova bez duplikata."""
    seen, out = set(), []
    for p in map(Path, paths):
        items = sorted(p.rglob("*.pdf")) if p.is_dir() else [p]
        for f in items:
            if f.suffix.lower() == ".pdf" and f.is_file():
                key = str(f.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(f)
    return out
