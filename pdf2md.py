"""Komandna linija: pdf2md fajl.pdf [folder ...] [-o izlaz] [--pismo auto|latinica|cirilica] [--brzo] [--ocr] [--slike]"""
import argparse
import sys
import time

import core


def main():
    ap = argparse.ArgumentParser(prog="pdf2md", description="Lokalna konverzija PDF -> Markdown (offline).")
    ap.add_argument("ulaz", nargs="+", help="PDF fajlovi ili folderi (rekurzivno)")
    ap.add_argument("-o", "--izlaz", help="izlazni folder (podrazumijevano: pored PDF-a)")
    ap.add_argument("--pismo", choices=["auto", "latinica", "cirilica"], default="auto",
                    help="pismo za OCR skeniranih strana (podrazumijevano: automatski)")
    ap.add_argument("--brzo", action="store_true", help="brzi režim bez OCR-a i analize tabela")
    ap.add_argument("--ocr", action="store_true", help="prisilni OCR cijelih strana (loš tekstualni sloj)")
    ap.add_argument("--slike", action="store_true", help="izvuci slike u folder ime_slike/ (podrazumijevano: [slika])")
    args = ap.parse_args()

    pdfs = core.collect_pdfs(args.ulaz)
    if not pdfs:
        print("Nije pronađen nijedan PDF.")
        return 1

    failed = 0
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf} ...", flush=True)
        t = time.time()
        try:
            md, script = core.convert(
                pdf,
                args.izlaz,
                mode="brzo" if args.brzo else "kvalitetno",
                script=args.pismo,
                force_ocr=args.ocr,
                images=args.slike,
            )
            print(f"    -> {md} ({time.time() - t:.1f} s{', ' + script if script else ''})")
        except Exception as e:
            failed += 1
            print(f"    GREŠKA: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
