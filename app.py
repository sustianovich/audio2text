"""Tk desktop interface. Run with python app.py."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

from pathlib import Path
import os
import sys

# Windowed executables do not provide stdout/stderr; libraries expect streams.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Some Windows virtual environments fail to locate the base install's Tcl/Tk.
if sys.platform == "win32" and not getattr(sys, "frozen", False):
    for variable, directory, marker in (
        ("TCL_LIBRARY", "tcl8.6", "init.tcl"),
        ("TK_LIBRARY", "tk8.6", "tk.tcl"),
    ):
        library = Path(sys.base_prefix) / "tcl" / directory
        if (library / marker).is_file():
            os.environ.setdefault(variable, str(library))

from paths import ROOT
from transcription import discover
from settings import DEFAULTS, LANGUAGES, SENSITIVITY, load_settings, save_settings
from jobs import run_job


def resolve_folder(value):
    """Resolve relative UI paths against the project, independent of launch directory."""
    if not str(value).strip():
        raise ValueError("Selecciona una carpeta. / Select a folder.")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def display_folder(value):
    path = resolve_folder(value)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Audio a texto")
        self.geometry("920x740")
        self.minsize(820, 700)
        (ROOT / "input_audio").mkdir(parents=True, exist_ok=True)
        (ROOT / "output_text").mkdir(parents=True, exist_ok=True)
        self.events = queue.Queue()
        self.busy = False
        self.cancelled = threading.Event()
        self.closing = False
        self.files = []
        self.input_dir = tk.StringVar(value="input_audio")
        self.output_dir = tk.StringVar(value="output_text")
        self.language = tk.StringVar(value="Español")
        self.model = tk.StringVar(value="small")
        self.timestamps = tk.BooleanVar(value=False)
        self.speakers = tk.BooleanVar(value=False)
        self.speaker_count = tk.StringVar(value="0")
        self.speaker_sensitivity = tk.StringVar(value="Normal")
        self.warnings = []
        self.word_output = tk.BooleanVar(value=True)
        self.md_output = tk.BooleanVar(value=True)
        self.srt_output = tk.BooleanVar(value=False)
        for key, value in load_settings().items():
            getattr(self, key).set(value)
        self.status = tk.StringVar(value="Listo / Ready")
        body = ttk.Frame(self, padding=22)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(4, weight=1)
        ttk.Label(body, text="Audio a texto", font=("Segoe UI", 23, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(body, text="Transcripción local · Word (.docx) + Markdown (.md)").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 18)
        )
        self.controls = []
        for row, label, variable in (
            (2, "Entrada / Input", self.input_dir),
            (3, "Salida / Output", self.output_dir),
        ):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10))
            entry = ttk.Entry(body, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            button = ttk.Button(
                body, text="Elegir / Browse", command=lambda v=variable: self.browse(v)
            )
            button.grid(row=row, column=2, padx=(8, 0))
            self.controls.extend([entry, button])
        box = ttk.LabelFrame(body, text="Archivos / Files — selecciona uno o varios", padding=8)
        box.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=15)
        self.listbox = tk.Listbox(
            box, selectmode=tk.EXTENDED, exportselection=False, font=("Segoe UI", 10), height=8
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)
        settings = ttk.Frame(body)
        settings.grid(row=5, column=0, columnspan=3, sticky="ew")
        for label, variable, values in (
            ("Idioma / Language", self.language, list(LANGUAGES)),
            ("Modelo / Model", self.model, ["tiny", "base", "small", "medium", "large-v3"]),
        ):
            ttk.Label(settings, text=label).pack(side="left", padx=(0, 6))
            widget = ttk.Combobox(
                settings, textvariable=variable, values=values, state="readonly", width=12
            )
            widget.pack(side="left", padx=(0, 15))
            self.controls.append(widget)
        output_options = ttk.Frame(body)
        output_options.grid(row=6, column=0, columnspan=3, sticky="w", pady=10)
        for label, variable in (
            ("Word (.docx)", self.word_output),
            ("Markdown (.md)", self.md_output),
            ("Subtítulos (.srt)", self.srt_output),
            ("Marcas de tiempo / Timestamps", self.timestamps),
        ):
            check = ttk.Checkbutton(output_options, text=label, variable=variable)
            check.pack(side="left", padx=(0, 16))
            self.controls.append(check)
        speaker_options = ttk.Frame(body)
        speaker_options.grid(row=7, column=0, columnspan=3, sticky="w", pady=(0, 10))
        speaker_check = ttk.Checkbutton(
            speaker_options, text="Identificar voces / Speaker labels", variable=self.speakers
        )
        speaker_check.pack(side="left", padx=(0, 16))
        ttk.Label(speaker_options, text="Voces / Speakers (0 = auto):").pack(side="left")
        count = ttk.Spinbox(
            speaker_options, from_=0, to=20, textvariable=self.speaker_count, width=4
        )
        count.pack(side="left", padx=6)
        ttk.Label(speaker_options, text="Separación / Split:").pack(side="left", padx=(10, 0))
        sensitivity = ttk.Combobox(
            speaker_options,
            textvariable=self.speaker_sensitivity,
            values=list(SENSITIVITY),
            state="readonly",
            width=20,
        )
        sensitivity.pack(side="left", padx=6)
        self.controls.extend([speaker_check, count, sensitivity])
        ttk.Label(
            body,
            text="small: equilibrio de calidad y velocidad. Modelos mayores: más lentos.\n"
            "Primera ejecución: descarga del modelo por Internet. Después funciona sin conexión.",
            wraplength=800,
        ).grid(row=8, column=0, columnspan=3, sticky="w")
        buttons = ttk.Frame(body)
        buttons.grid(row=9, column=0, columnspan=3, sticky="ew", pady=14)
        for label, command in (
            ("Actualizar / Refresh", self.refresh),
            ("Seleccionar todos / Select all", lambda: self.listbox.selection_set(0, tk.END)),
            ("Transcribir / Transcribe", self.start),
        ):
            button = ttk.Button(buttons, text=label, command=command)
            button.pack(side="left", padx=(0, 8))
            self.controls.append(button)
        self.cancel_button = ttk.Button(
            buttons, text="Cancelar / Cancel", command=self.cancel, state="disabled"
        )
        self.cancel_button.pack(side="left")
        self.progress = ttk.Progressbar(body, maximum=100)
        self.progress.grid(row=10, column=0, columnspan=3, sticky="ew")
        ttk.Label(body, textvariable=self.status, wraplength=800).grid(
            row=11, column=0, columnspan=3, sticky="w", pady=8
        )
        ttk.Button(body, text="Abrir salida / Open output folder", command=self.open_output).grid(
            row=12, column=0, columnspan=3, sticky="w"
        )
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.after(100, self.poll)

    def open_output(self):
        try:
            path = resolve_folder(self.output_dir.get())
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Salida / Output", str(exc))

    def browse(self, variable):
        try:
            initial = resolve_folder(variable.get())
        except ValueError:
            initial = ROOT
        path = filedialog.askdirectory(initialdir=str(initial), mustexist=True)
        if path:
            variable.set(display_folder(path))
            if variable is self.input_dir:
                self.refresh()

    def refresh(self):
        try:
            self.files = discover(resolve_folder(self.input_dir.get()))
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
        formats = tuple(
            fmt
            for fmt, enabled in (
                ("md", self.md_output.get()),
                ("docx", self.word_output.get()),
                ("srt", self.srt_output.get()),
            )
            if enabled
        )
        if not formats:
            messagebox.showerror("Formato / Format", "Selecciona un formato: Word, Markdown o SRT.")
            return
        try:
            input_path = resolve_folder(self.input_dir.get())
            output_path = resolve_folder(self.output_dir.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror("Carpeta / Folder", str(exc))
            return
        # Refresh if a folder was typed manually before starting.
        if self.files and self.files[0].parent != input_path:
            self.refresh()
            return
        selected = [self.files[i] for i in self.listbox.curselection()]
        if not selected:
            messagebox.showinfo(
                "Archivos / Files", "Selecciona archivos. / Select files (Refresh)."
            )
            return
        if not self.output_dir.get().strip():
            messagebox.showerror("Salida / Output", "Elige una carpeta de salida.")
            return
        try:
            count = int(self.speaker_count.get()) if self.speakers.get() else 0
            if not 0 <= count <= 20:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Voces / Speakers",
                "Elige 0 (auto) o 1-20 voces. / Choose 0 (auto) or 1-20 speakers.",
            )
            return
        self.persist_settings()
        self.cancelled.clear()
        self.warnings = []
        self.busy = True
        self.cancel_button.configure(state="normal")
        for widget in self.controls:
            widget.configure(state="disabled")
        self.listbox.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.status.set(
            "Cargando modelo / Loading model… La primera descarga puede tardar varios minutos."
        )
        job = {
            "files": [str(path) for path in selected],
            "output": str(output_path),
            "language": LANGUAGES[self.language.get()],
            "model": self.model.get(),
            "timestamps": self.timestamps.get(),
            "formats": formats,
            "speakers": self.speakers.get(),
            "speaker_count": count,
            "speaker_threshold": SENSITIVITY[self.speaker_sensitivity.get()],
        }
        threading.Thread(
            target=run_job,
            args=(job, self.cancelled, lambda kind, value: self.events.put((kind, value))),
            daemon=True,
        ).start()

    def cancel(self):
        if self.busy:
            self.cancelled.set()
            self.cancel_button.configure(state="disabled")
            self.status.set("Cancelando / Cancelling... Los archivos guardados se conservan.")

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    if not self.cancelled.is_set():
                        self.status.set(value)
                elif kind == "warning":
                    self.warnings.append(value)
                elif kind == "progress":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=value)
                elif kind == "done":
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.busy = False
                    self.cancel_button.configure(state="disabled")
                    for widget in self.controls:
                        widget.configure(
                            state="readonly" if isinstance(widget, ttk.Combobox) else "normal"
                        )
                    self.listbox.configure(state="normal")
                    completed, errors, formats, cancelled = value
                    format_label = " + ".join(
                        {"docx": "Word", "md": "Markdown", "srt": "SRT"}[fmt] for fmt in formats
                    )
                    self.status.set(
                        f"Completados / Completed: {completed}. Errores / Errors: {len(errors)}."
                    )
                    if self.closing:
                        self.destroy()
                        return
                    if cancelled:
                        self.status.set(f"Cancelado / Cancelled. Guardados / Saved: {completed}.")
                        if errors:
                            messagebox.showerror("Errores / Errors", "\n\n".join(errors))
                    elif errors:
                        messagebox.showerror("Resultado / Result", "\n\n".join(errors))
                    else:
                        self.progress["value"] = 100
                        message = f"{completed} archivo(s): {format_label}\n{self.output_dir.get()}"
                        if self.warnings:
                            message += "\n\nAvisos / Warnings:\n" + "\n".join(self.warnings)
                        messagebox.showinfo("Completado / Complete", message)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def persist_settings(self):
        try:
            save_settings({key: getattr(self, key).get() for key in DEFAULTS})
        except OSError as exc:
            messagebox.showwarning("Configuración / Settings", str(exc))

    def close(self):
        self.persist_settings()
        if self.busy:
            if messagebox.askyesno(
                "Salir / Quit", "¿Cancelar y cerrar? / Cancel transcription and close?"
            ):
                self.closing = True
                self.cancel()
            return
        self.destroy()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from self_test import run

        job_path = (
            Path(sys.argv[sys.argv.index("--integration-job") + 1])
            if "--integration-job" in sys.argv
            else None
        )
        run(Path(sys.argv[sys.argv.index("--self-test") + 1]), job_path)
    else:
        App().mainloop()
