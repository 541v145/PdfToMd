"""Prozor za PDF -> Markdown. Pokretanje: gui.py [fajl.pdf ...] (sa fajlovima odmah kreće konverzija).

Radi kao jedna instanca: ako je prozor već otvoren, novi poziv (npr. desni klik na
više PDF-ova) samo mu preda fajlove preko 127.0.0.1 i završi.
"""
import json
import os
import queue
import socket
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# pythonw nema konzolu; biblioteke koje pišu u stdout/stderr bi pukle
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

APP_DIR = Path(__file__).resolve().parent
SETTINGS = APP_DIR / "settings.json"
PORT = 47653

SCRIPTS = {"Automatski": "auto", "Latinica": "latinica", "Ćirilica": "cirilica"}
STATUS_ICON = {"ceka": "…", "radi": "▶", "ok": "✓", "greska": "✗"}


def send_to_running(files):
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1) as s:
            s.sendall(json.dumps(files).encode("utf-8"))
        return True
    except OSError:
        return False


def claim_single_instance():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        srv.bind(("127.0.0.1", PORT))
        srv.listen()
        return srv
    except OSError:
        srv.close()
        return None


class App:
    def __init__(self, root, server, initial_files):
        self.root = root
        self.items = []  # dict(path, status, msg)
        self.events = queue.Queue()
        self.worker = None
        self.last_output = None
        self.core = None

        root.title("PDF → Markdown (lokalno)")
        root.geometry("820x620")
        root.minsize(640, 480)
        self._build()
        self._load_settings()

        if server:
            threading.Thread(target=self._serve, args=(server,), daemon=True).start()
        root.after(150, self._poll)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        if initial_files:
            self.add_files(initial_files, autostart=True)

    # ---------- UI ----------
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="Dodaj PDF…", command=self._pick_files).pack(side="left")
        ttk.Button(top, text="Dodaj folder…", command=self._pick_folder).pack(side="left", padx=4)
        ttk.Button(top, text="Ukloni označene", command=self._remove_selected).pack(side="left")
        ttk.Button(top, text="Očisti završene", command=self._clear_done).pack(side="left", padx=4)

        lf = ttk.Frame(self.root)
        lf.pack(fill="both", expand=True, **pad)
        self.listbox = tk.Listbox(lf, selectmode="extended", activestyle="none", font=("Segoe UI", 10))
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.hint = tk.Label(self.listbox, text="Prevuci PDF fajlove ili foldere ovdje", fg="#888", bg="white",
                             font=("Segoe UI", 12))
        self.hint.place(relx=0.5, rely=0.5, anchor="center")

        try:
            from tkinterdnd2 import DND_FILES

            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", lambda e: self.add_files(self.root.tk.splitlist(e.data)))
        except Exception:
            self.hint.configure(text="Dodaj PDF fajlove dugmetom iznad")

        opt = ttk.LabelFrame(self.root, text="Opcije")
        opt.pack(fill="x", **pad)
        self.mode = tk.StringVar(value="kvalitetno")
        ttk.Radiobutton(opt, text="Kvalitetno (raspored, tabele, OCR skenova)", value="kvalitetno",
                        variable=self.mode).grid(row=0, column=0, columnspan=2, sticky="w", padx=6)
        ttk.Radiobutton(opt, text="Brzo (samo digitalni PDF, bez OCR-a)", value="brzo",
                        variable=self.mode).grid(row=0, column=2, columnspan=2, sticky="w", padx=6)

        ttk.Label(opt, text="Pismo skenova:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.script = tk.StringVar(value="Automatski")
        ttk.Combobox(opt, textvariable=self.script, values=list(SCRIPTS), state="readonly", width=12).grid(
            row=1, column=1, sticky="w")
        self.force_ocr = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="OCR cijele strane (loš tekstualni sloj)", variable=self.force_ocr).grid(
            row=1, column=2, sticky="w", padx=6)
        self.images = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Izvuci slike (troši tokene)", variable=self.images).grid(row=1, column=3, sticky="w", padx=6)

        self.out_mode = tk.StringVar(value="pored")
        ttk.Radiobutton(opt, text="Snimi pored PDF-a", value="pored", variable=self.out_mode).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        of = ttk.Frame(opt)
        of.grid(row=2, column=2, columnspan=2, sticky="we", padx=6)
        ttk.Radiobutton(of, text="U folder:", value="folder", variable=self.out_mode).pack(side="left")
        self.out_dir = tk.StringVar()
        ttk.Entry(of, textvariable=self.out_dir, width=34).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(of, text="…", width=3, command=self._pick_out_dir).pack(side="left")
        opt.columnconfigure(3, weight=1)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        self.start_btn = ttk.Button(bottom, text="Pretvori", command=self.start)
        self.start_btn.pack(side="left")
        ttk.Button(bottom, text="Otvori izlazni folder", command=self._open_output).pack(side="left", padx=6)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=6)
        self.status = tk.StringVar(value="Spremno. Sve se obrađuje lokalno, bez interneta.")
        ttk.Label(self.root, textvariable=self.status, foreground="#444").pack(fill="x", padx=8, pady=(0, 8))

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for it in self.items:
            line = f"{STATUS_ICON[it['status']]}  {it['path'].name}"
            if it["msg"]:
                line += f"   — {it['msg']}"
            self.listbox.insert("end", line)
            if it["status"] == "greska":
                self.listbox.itemconfig("end", fg="#b00020")
            elif it["status"] == "ok":
                self.listbox.itemconfig("end", fg="#1b7a2e")
        if self.items:
            self.hint.place_forget()
        else:
            self.hint.place(relx=0.5, rely=0.5, anchor="center")

    # ---------- dodavanje ----------
    def add_files(self, paths, autostart=False):
        from core import collect_pdfs  # lagan import; teški modeli se učitavaju tek pri konverziji

        known = {str(it["path"]).lower() for it in self.items if it["status"] in ("ceka", "radi")}
        added = 0
        for p in collect_pdfs(paths):
            if str(p).lower() not in known:
                self.items.append({"path": p, "status": "ceka", "msg": ""})
                added += 1
        self._refresh_list()
        if added and (autostart or self.worker):
            self.start()

    def _pick_files(self):
        files = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        if files:
            self.add_files(files)

    def _pick_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.add_files([d])

    def _pick_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.out_dir.set(d)
            self.out_mode.set("folder")

    def _remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            if self.items[i]["status"] != "radi":
                del self.items[i]
        self._refresh_list()

    def _clear_done(self):
        self.items = [it for it in self.items if it["status"] in ("ceka", "radi")]
        self._refresh_list()

    # ---------- konverzija ----------
    def start(self):
        if self.worker and self.worker.is_alive():
            self._update_progress()
            return
        if not any(it["status"] == "ceka" for it in self.items):
            self.status.set("Nema fajlova na čekanju.")
            return
        if self.out_mode.get() == "folder" and not self.out_dir.get().strip():
            messagebox.showwarning("Izlazni folder", "Izaberi izlazni folder ili 'Snimi pored PDF-a'.")
            return
        self._save_settings()
        opts = {
            "out_dir": self.out_dir.get().strip() if self.out_mode.get() == "folder" else None,
            "mode": self.mode.get(),
            "script": SCRIPTS[self.script.get()],
            "force_ocr": self.force_ocr.get(),
            "images": self.images.get(),
        }
        self.start_btn.state(["disabled"])
        self.worker = threading.Thread(target=self._work, args=(opts,), daemon=True)
        self.worker.start()

    def _work(self, opts):
        if self.core is None:
            self.events.put(("status", "Učitavam biblioteke…"))
            import core

            self.core = core
        while True:
            idx = next((i for i, it in enumerate(self.items) if it["status"] == "ceka"), None)
            if idx is None:
                break
            it = self.items[idx]
            it["status"] = "radi"
            self.events.put(("refresh", None))
            self.events.put(("status", f"Obrađujem {it['path'].name} … (prvi fajl traje duže zbog učitavanja modela)"
                             if self.last_output is None else f"Obrađujem {it['path'].name} …"))
            t = time.time()
            try:
                md, script = self.core.convert(it["path"], **opts)
                it["status"], it["msg"] = "ok", f"{time.time() - t:.0f} s" + (f", {script}" if script else "")
                self.last_output = md
            except Exception as e:
                it["status"], it["msg"] = "greska", str(e)[:200]
            self.events.put(("refresh", None))
        self.events.put(("done", None))

    def _update_progress(self):
        total = len(self.items)
        done = sum(it["status"] in ("ok", "greska") for it in self.items)
        self.progress.configure(maximum=max(total, 1), value=done)

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "refresh":
                    self._refresh_list()
                    self._update_progress()
                elif kind == "status":
                    self.status.set(data)
                elif kind == "done":
                    self.worker = None
                    self.start_btn.state(["!disabled"])
                    ok = sum(it["status"] == "ok" for it in self.items)
                    err = sum(it["status"] == "greska" for it in self.items)
                    self.status.set(f"Gotovo: {ok} uspješno" + (f", {err} sa greškom" if err else "") + ".")
                    if any(it["status"] == "ceka" for it in self.items):
                        self.start()
                elif kind == "external":
                    self.root.deiconify()
                    self.root.lift()
                    self.root.attributes("-topmost", True)
                    self.root.after(300, lambda: self.root.attributes("-topmost", False))
                    if data:
                        self.add_files(data, autostart=True)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _serve(self, srv):
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    buf = b""
                    while chunk := conn.recv(65536):
                        buf += chunk
                self.events.put(("external", json.loads(buf.decode("utf-8") or "[]")))
            except Exception:
                continue

    def _open_output(self):
        if self.last_output:
            os.startfile(Path(self.last_output).parent)
        elif self.out_mode.get() == "folder" and self.out_dir.get():
            os.startfile(self.out_dir.get())
        else:
            self.status.set("Još nema izlaza.")

    # ---------- podešavanja ----------
    def _load_settings(self):
        try:
            s = json.loads(SETTINGS.read_text(encoding="utf-8-sig"))
        except Exception:
            return
        for var, key in ((self.mode, "mode"), (self.script, "script"), (self.out_mode, "out_mode"),
                         (self.out_dir, "out_dir"), (self.force_ocr, "force_ocr"), (self.images, "images")):
            if key in s:
                var.set(s[key])

    def _save_settings(self):
        s = {"mode": self.mode.get(), "script": self.script.get(), "out_mode": self.out_mode.get(),
             "out_dir": self.out_dir.get(), "force_ocr": self.force_ocr.get(), "images": self.images.get()}
        try:
            SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Konverzija u toku", "Konverzija još traje. Zatvoriti ipak?"):
                return
        self._save_settings()
        self.root.destroy()
        os._exit(0)


def main():
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    server = claim_single_instance()
    if server is None:
        for _ in range(20):
            if send_to_running(files):
                return
            time.sleep(0.25)

    try:
        from tkinterdnd2 import TkinterDnD

        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    App(root, server, files)
    root.mainloop()


if __name__ == "__main__":
    main()
