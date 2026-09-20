"""Tk desktop interface. Run with python app.py."""
from pathlib import Path
import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Some Windows virtual environments fail to locate the base install's Tcl/Tk.
if sys.platform == "win32":
    for variable, directory, marker in (("TCL_LIBRARY", "tcl8.6", "init.tcl"),
                                         ("TK_LIBRARY", "tk8.6", "tk.tcl")):
        library = Path(sys.base_prefix) / "tcl" / directory
        if (library / marker).is_file():
            os.environ.setdefault(variable, str(library))

from transcription import ROOT, discover, export, load_model, transcribe


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Audio a texto")
        self.geometry("880x660")
        self.minsize(720, 580)
        (ROOT / "input_audio").mkdir(exist_ok=True)
        (ROOT / "output_text").mkdir(exist_ok=True)
        self.events = queue.Queue()
        self.busy = False
        self.files = []
        self.input_dir = tk.StringVar(value=str(ROOT / "input_audio"))
        self.output_dir = tk.StringVar(value=str(ROOT / "output_text"))
        self.language = tk.StringVar(value="Español")
        self.model = tk.StringVar(value="small")
        self.timestamps = tk.BooleanVar(value=False)
        self.word_output = tk.BooleanVar(value=True)
        self.md_output = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Listo / Ready")
        body = ttk.Frame(self, padding=22)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(4, weight=1)
        ttk.Label(body, text="Audio a texto", font=("Segoe UI", 23, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text="Transcripción local · Word (.docx) + Markdown (.md)").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 18))
        self.controls = []
        for row, label, variable in ((2, "Entrada / Input", self.input_dir),
                                     (3, "Salida / Output", self.output_dir)):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10))
            entry = ttk.Entry(body, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            button = ttk.Button(body, text="Elegir / Browse",
                                command=lambda v=variable: self.browse(v))
            button.grid(row=row, column=2, padx=(8, 0))
            self.controls.extend([entry, button])
        box = ttk.LabelFrame(body, text="Archivos / Files — selecciona uno o varios", padding=8)
        box.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=15)
        self.listbox = tk.Listbox(box, selectmode=tk.EXTENDED, exportselection=False,
                                  font=("Segoe UI", 10), height=8)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)
        settings = ttk.Frame(body)
        settings.grid(row=5, column=0, columnspan=3, sticky="ew")
        for label, variable, values in (("Idioma / Language", self.language, ["Español", "English"]),
                                       ("Modelo / Model", self.model, ["tiny", "base", "small", "medium", "large-v3"])):
            ttk.Label(settings, text=label).pack(side="left", padx=(0, 6))
            widget = ttk.Combobox(settings, textvariable=variable, values=values,
                                  state="readonly", width=12)
            widget.pack(side="left", padx=(0, 15))
            self.controls.append(widget)
        output_options = ttk.Frame(body)
        output_options.grid(row=6, column=0, columnspan=3, sticky="w", pady=10)
        for label, variable in (("Word (.docx)", self.word_output),
                                ("Markdown (.md)", self.md_output),
                                ("Marcas de tiempo / Timestamps", self.timestamps)):
            check = ttk.Checkbutton(output_options, text=label, variable=variable)
            check.pack(side="left", padx=(0, 16))
            self.controls.append(check)
        ttk.Label(body, text="small: equilibrio de calidad y velocidad. Modelos mayores: más lentos.\n"
                  "Primera ejecución: descarga del modelo por Internet. Después funciona sin conexión.",
                  wraplength=800).grid(row=7, column=0, columnspan=3, sticky="w")
        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=3, sticky="ew", pady=14)
        for label, command in (("Actualizar / Refresh", self.refresh),
                               ("Seleccionar todos / Select all", lambda: self.listbox.selection_set(0, tk.END)),
                               ("Transcribir / Transcribe", self.start)):
            button = ttk.Button(buttons, text=label, command=command)
            button.pack(side="left", padx=(0, 8))
            self.controls.append(button)
        self.progress = ttk.Progressbar(body, maximum=100)
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew")
        ttk.Label(body, textvariable=self.status, wraplength=800).grid(
            row=10, column=0, columnspan=3, sticky="w", pady=8)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.after(100, self.poll)

    def browse(self, variable):
        path = filedialog.askdirectory(initialdir=variable.get(), mustexist=True)
        if path:
            variable.set(path)
            if variable is self.input_dir:
                self.refresh()

    def refresh(self):
        try:
            self.files = discover(self.input_dir.get())
        except Exception as exc:
            messagebox.showerror("Carpeta / Folder", str(exc))
            return
        self.listbox.delete(0, tk.END)
        for path in self.files:
            self.listbox.insert(tk.END, path.name)
        self.listbox.selection_set(0, tk.END)
        self.status.set(f"{len(self.files)} archivos / files")

    def start(self):
        if self.busy:
            return
        formats = tuple(fmt for fmt, enabled in (("md", self.md_output.get()),
                                                 ("docx", self.word_output.get())) if enabled)
        if not formats:
            messagebox.showerror("Formato / Format",
                                 "Selecciona Word o Markdown. / Select Word or Markdown.")
            return
        # Refresh if a folder was typed manually before starting.
        if self.files and self.files[0].parent != Path(self.input_dir.get()).expanduser().resolve():
            self.refresh()
            return
        selected = [self.files[i] for i in self.listbox.curselection()]
        if not selected:
            messagebox.showinfo("Archivos / Files", "Selecciona archivos. / Select files (Refresh).")
            return
        if not self.output_dir.get().strip():
            messagebox.showerror("Salida / Output", "Elige una carpeta de salida.")
            return
        self.busy = True
        for widget in self.controls:
            widget.configure(state="disabled")
        self.listbox.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.status.set("Cargando modelo / Loading model… La primera descarga puede tardar varios minutos.")
        args = (selected, self.output_dir.get(), "es" if self.language.get() == "Español" else "en",
                self.model.get(), self.timestamps.get(), formats)
        threading.Thread(target=self.work, args=args, daemon=True).start()

    def work(self, files, output, language, model_name, timestamps, formats):
        errors = []
        completed = 0
        try:
            model = load_model(model_name)
            self.events.put(("loaded", None))
            for index, path in enumerate(files):
                self.events.put(("status", f"{index + 1}/{len(files)} — {path.name}"))
                try:
                    segments = transcribe(model, path, language,
                        lambda value, i=index: self.events.put(("progress", (i + value / 100) / len(files) * 100)))
                    export(path, output, segments, language, timestamps, formats=formats)
                    completed += 1
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
        except Exception as exc:
            errors.append(str(exc))
        finally:
            self.events.put(("done", (completed, errors, formats)))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "loaded":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                elif kind == "status":
                    self.status.set(value)
                elif kind == "progress":
                    self.progress["value"] = value
                elif kind == "done":
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.busy = False
                    for widget in self.controls:
                        widget.configure(state="readonly" if isinstance(widget, ttk.Combobox) else "normal")
                    self.listbox.configure(state="normal")
                    completed, errors, formats = value
                    format_label = " + ".join("Word" if fmt == "docx" else "Markdown" for fmt in formats)
                    self.status.set(f"Completados / Completed: {completed}. Errores / Errors: {len(errors)}.")
                    if errors:
                        messagebox.showerror("Resultado / Result", "\n\n".join(errors))
                    else:
                        self.progress["value"] = 100
                        messagebox.showinfo("Completado / Complete", f"{completed} archivo(s): {format_label}\n{self.output_dir.get()}")
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("Transcripción / Transcription", "Espera a que termine la transcripción antes de cerrar.")
            return
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
