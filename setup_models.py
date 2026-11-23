"""Jednokratno preuzimanje modela u models/ (jedini korak koji koristi internet).

Preuzimaju se samo modeli (layout, tabele, OCR). PDF-ovi se nikad ne šalju nikome.
"""
import os
from pathlib import Path

from core import EASYOCR_DIR, MODELS_DIR, OCR_LANGS

# core uključuje offline režim; samo za preuzimanje ga gasimo (prije importa huggingface_hub)
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"


def main():
    from docling.utils.model_downloader import download_models

    print(f"Preuzimam Docling modele u {MODELS_DIR} ...")
    download_models(
        output_dir=Path(MODELS_DIR),
        progress=True,
        with_code_formula=False,
        with_picture_classifier=False,
        with_rapidocr=False,
    )

    import easyocr

    EASYOCR_DIR.mkdir(parents=True, exist_ok=True)
    for script, langs in OCR_LANGS.items():
        print(f"Preuzimam EasyOCR model: {script} {langs} ...")
        easyocr.Reader(langs, gpu=False, model_storage_directory=str(EASYOCR_DIR), download_enabled=True, verbose=False)

    print("\nGotovo. Aplikacija od sada radi potpuno offline.")


if __name__ == "__main__":
    main()
