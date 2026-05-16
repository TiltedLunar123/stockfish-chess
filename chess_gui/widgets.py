"""Light, reusable widgets: link-style labels, bordered buttons, radios, checks."""

import tkinter as tk

from .theme import (
    ACCENT, ACCENT_HOVER, BG, BTN_BG, BTN_BORDER, BTN_HOVER, CARD_BG,
    FONT_BODY, FONT_BODY_BOLD, FONT_HEADER, FONT_LABEL, FONT_LINK,
    FONT_LINK_SMALL, LINK, LINK_HOVER, PANEL_BG, TEXT_DIM, TEXT_FG,
)


def header(parent, text):
    return tk.Label(
        parent, text=text, bg=PANEL_BG, fg=TEXT_FG, font=FONT_HEADER, anchor="w",
    )


def link(parent, text, command, small=False, color=ACCENT, hover=ACCENT_HOVER):
    font = FONT_LINK_SMALL if small else FONT_LINK
    lbl = tk.Label(
        parent, text=text, bg=PANEL_BG, fg=color, font=font, cursor="hand2",
    )
    lbl.bind("<Enter>", lambda _e: lbl.configure(fg=hover))
    lbl.bind("<Leave>", lambda _e: lbl.configure(fg=color))
    lbl.bind("<Button-1>", lambda _e: command())
    return lbl


def styled_button(parent, text, command):
    """White button with thin gray border, matches reference 'Calculate Next Move'."""
    wrap = tk.Frame(parent, bg=BTN_BORDER, padx=1, pady=1)
    btn = tk.Button(
        wrap, text=text, command=command, bg=BTN_BG, fg=TEXT_FG,
        relief="flat", font=FONT_BODY_BOLD, padx=14, pady=8, borderwidth=0,
        activebackground=BTN_HOVER, activeforeground=TEXT_FG, cursor="hand2",
    )
    btn.pack(fill="x")
    btn.bind("<Enter>", lambda _e: btn.configure(bg=BTN_HOVER))
    btn.bind("<Leave>", lambda _e: btn.configure(bg=BTN_BG))
    wrap.button = btn
    return wrap


class Radio(tk.Frame):
    """Radio button group rendered with native ttk feel but our colors."""

    def __init__(self, parent, var, options, command=None):
        super().__init__(parent, bg=PANEL_BG)
        self.var = var
        self.command = command
        self.buttons = []
        for label, value in options:
            rb = tk.Radiobutton(
                self, text=label, variable=var, value=value,
                command=self._on_change, bg=PANEL_BG, fg=TEXT_FG,
                activebackground=PANEL_BG, activeforeground=TEXT_FG,
                selectcolor=CARD_BG, font=FONT_BODY, anchor="w",
                borderwidth=0, highlightthickness=0, cursor="hand2",
                padx=2, pady=2,
            )
            rb.pack(anchor="w", fill="x")
            self.buttons.append(rb)

    def _on_change(self):
        if self.command:
            self.command(self.var.get())


class Check(tk.Checkbutton):
    def __init__(self, parent, text, var, command=None):
        super().__init__(
            parent, text=text, variable=var, command=command,
            bg=PANEL_BG, fg=TEXT_FG, activebackground=PANEL_BG,
            activeforeground=TEXT_FG, selectcolor=CARD_BG,
            font=FONT_BODY, anchor="w", borderwidth=0,
            highlightthickness=0, cursor="hand2", padx=2, pady=1,
        )


def divider(parent):
    from .theme import DIVIDER
    return tk.Frame(parent, bg=DIVIDER, height=1)
