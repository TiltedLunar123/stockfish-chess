"""First-run install dialog: detect CPU, pick a build, download Stockfish."""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .installer import (
    available_builds, detect_cpu, detect_os, install_stockfish,
    recommend_build,
)
from .theme import (
    ACCENT, ACCENT_HOVER, BG, BTN_BG, BTN_BORDER, BTN_HOVER, CARD_BG,
    DIVIDER, FONT_BODY, FONT_HEADER, FONT_HINT, FONT_LABEL, PANEL_BG,
    TEXT_DIM, TEXT_FAINT, TEXT_FG,
)


class InstallDialog(tk.Toplevel):
    """Modal install dialog. Calls on_done(installed_path_str) on success."""

    def __init__(self, parent, target_dir, on_done, first_run=True):
        super().__init__(parent)
        self.target_dir = Path(target_dir)
        self.on_done = on_done
        self.first_run = first_run
        self._installing = False
        self._installed_path = None

        self.title("Install Stockfish")
        self.configure(bg=PANEL_BG, padx=24, pady=20)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Detect first; show error if completely broken
        try:
            self.os_id = detect_os()
            self.cpu = detect_cpu()
        except Exception as e:
            messagebox.showerror("Detection failed", str(e), parent=self)
            self.destroy()
            return

        self._build_ui()

        # Center the dialog on the parent window
        self.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.winfo_reqwidth()
            h = self.winfo_reqheight()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda _e: self._on_close())

    # ---------------- layout ----------------

    def _build_ui(self):
        title = ("Welcome! Let's install Stockfish"
                 if self.first_run else "Install another Stockfish build")
        tk.Label(self, text=title, bg=PANEL_BG, fg=TEXT_FG,
                 font=(FONT_HEADER[0], 15, "bold")
                 ).pack(anchor="w")

        subtitle = ("Stockfish is the chess engine that does the thinking. "
                    "Pick a build optimised for your CPU."
                    if self.first_run else
                    "Download an additional Stockfish build. You can switch "
                    "between installed engines in the Engine section.")
        tk.Label(self, text=subtitle, bg=PANEL_BG, fg=TEXT_DIM,
                 font=FONT_BODY, wraplength=460, justify="left",
                 ).pack(anchor="w", pady=(4, 16))

        # System info card
        card = tk.Frame(self, bg=CARD_BG, padx=16, pady=12)
        card.pack(fill="x", pady=(0, 16))

        self._info_row(card, "Operating system",
                       self.os_id.replace("-", " ").title())
        self._info_row(card, "Processor", self.cpu["name"])
        flags_pretty = self._format_flags()
        self._info_row(card, "Detected", flags_pretty or "no advanced flags")

        # Recommended slug
        self.recommended_slug, rec_label = recommend_build(
            self.os_id, self.cpu["flags"])
        tk.Frame(card, bg=DIVIDER, height=1).pack(fill="x", pady=(8, 8))
        self._info_row(card, "Recommended",
                       f"{self.recommended_slug}  ({rec_label})",
                       value_color=ACCENT)

        # Build picker
        tk.Label(self, text="Build to install", bg=PANEL_BG, fg=TEXT_FG,
                 font=FONT_LABEL, anchor="w"
                 ).pack(anchor="w", pady=(0, 4))

        builds = available_builds(self.os_id)
        labels = [f"{slug}  ·  {label}" for slug, label, _ in builds]
        slugs = [slug for slug, _, _ in builds]
        self._slug_for_label = dict(zip(labels, slugs))
        default_label = next(
            (lbl for lbl, slug in zip(labels, slugs)
             if slug == self.recommended_slug),
            labels[0],
        )
        self.build_var = tk.StringVar(value=default_label)
        ttk.Combobox(self, textvariable=self.build_var, values=labels,
                     state="readonly", width=46
                     ).pack(fill="x", pady=(0, 6))
        tk.Label(self,
                 text="Pick a build your CPU does NOT support and the engine "
                      "will fail to start. \"Generic x86-64\" is the safest "
                      "fallback.",
                 bg=PANEL_BG, fg=TEXT_FAINT, font=FONT_HINT,
                 wraplength=460, justify="left"
                 ).pack(anchor="w", pady=(0, 16))

        # Action buttons
        btn_row = tk.Frame(self, bg=PANEL_BG)
        btn_row.pack(fill="x")
        self.install_btn = self._button(btn_row, "Install", self._start_install,
                                        primary=True)
        self.install_btn.pack(side="left", padx=(0, 8))
        self._button(btn_row, "Use existing file…",
                     self._pick_existing).pack(side="left")
        if not self.first_run:
            self._button(btn_row, "Cancel",
                         self._on_close).pack(side="right")

        # Status + progress
        self.status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status_var, bg=PANEL_BG, fg=TEXT_DIM,
                 font=FONT_BODY, anchor="w", wraplength=460
                 ).pack(anchor="w", pady=(16, 4), fill="x")
        self.progress_var = tk.IntVar(value=0)
        ttk.Progressbar(self, variable=self.progress_var, maximum=100,
                        length=460).pack(fill="x")

    # ---------------- helpers ----------------

    def _info_row(self, parent, label, value, value_color=TEXT_FG):
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(anchor="w", fill="x", pady=1)
        tk.Label(row, text=f"{label}:", bg=CARD_BG, fg=TEXT_DIM,
                 font=FONT_BODY, width=16, anchor="w"
                 ).pack(side="left")
        tk.Label(row, text=value, bg=CARD_BG, fg=value_color,
                 font=FONT_BODY, anchor="w"
                 ).pack(side="left")

    def _format_flags(self):
        interesting = ("avx512vnni", "avx512f", "avx_vnni", "avxvnni",
                       "bmi2", "avx2", "sse4_1", "popcnt")
        present = [f for f in interesting if f in self.cpu["flags"]]
        return ", ".join(present)

    def _button(self, parent, text, cmd, primary=False):
        fg = "white" if primary else TEXT_FG
        bg = ACCENT if primary else BTN_BG
        hover = ACCENT_HOVER if primary else BTN_HOVER
        wrap = tk.Frame(parent, bg=BTN_BORDER, padx=1, pady=1)
        b = tk.Button(wrap, text=text, command=cmd, bg=bg, fg=fg,
                      relief="flat", font=FONT_LABEL, padx=18, pady=8,
                      borderwidth=0, activebackground=hover,
                      activeforeground=fg, cursor="hand2")
        b.pack()
        b.bind("<Enter>", lambda _e: b.configure(bg=hover))
        b.bind("<Leave>", lambda _e: b.configure(bg=bg))
        wrap.button = b
        return wrap

    # ---------------- install flow ----------------

    def _start_install(self):
        if self._installing:
            return
        label = self.build_var.get()
        slug = self._slug_for_label.get(label, self.recommended_slug)
        self._installing = True
        self.install_btn.button.configure(state="disabled")
        self.status_var.set(f"Starting install of '{slug}'…")
        self.progress_var.set(0)

        def thread_main():
            try:
                path = install_stockfish(
                    self.target_dir, slug, os_id=self.os_id,
                    on_progress=self._on_progress,
                    on_status=self._on_status,
                )
                self.after(0, lambda p=path: self._finish(str(p)))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._fail(err))

        threading.Thread(target=thread_main, daemon=True).start()

    def _on_progress(self, downloaded, total):
        if total:
            pct = downloaded * 100 // total
            self.after(0, lambda p=pct: self.progress_var.set(p))
            mb_done = downloaded / 1024 / 1024
            mb_total = total / 1024 / 1024
            self.after(0, lambda d=mb_done, t=mb_total:
                       self.status_var.set(f"Downloading… {d:.1f} / {t:.1f} MB"))

    def _on_status(self, msg):
        self.after(0, lambda m=msg: self.status_var.set(m))

    def _finish(self, path):
        self._installing = False
        self._installed_path = path
        self.status_var.set("Installed successfully.")
        self.progress_var.set(100)
        if self.on_done:
            try:
                self.on_done(path)
            except Exception:
                pass
        self.destroy()

    def _fail(self, err):
        self._installing = False
        self.install_btn.button.configure(state="normal")
        self.status_var.set(f"Failed: {err[:100]}")
        self.progress_var.set(0)

    def _pick_existing(self):
        path = filedialog.askopenfilename(
            title="Locate Stockfish executable",
            filetypes=[("Executables", "*.exe"), ("All files", "*.*")],
            parent=self,
        )
        if not path:
            return
        if self.on_done:
            self.on_done(path)
        self.destroy()

    def _on_close(self):
        if self._installing:
            if not messagebox.askyesno(
                "Cancel install?",
                "A download is in progress. Cancel and close?",
                parent=self,
            ):
                return
        self.destroy()
