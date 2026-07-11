from __future__ import annotations


PAPER = "#F4F1E8"
PAPER_RAISED = "#FCFBF7"
INK = "#17211D"
MUTED = "#52615A"
DEEP_GREEN = "#173F35"
GREEN = "#28624F"
PALE_GREEN = "#DDE9E1"
BORDER = "#AAB8B0"
def apply_operator_theme(root, ttk_module) -> None:
    root.configure(background=PAPER)
    root.option_add("*Font", ("Aptos", 10))
    style = ttk_module.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=PAPER)
    style.configure("TLabel", background=PAPER, foreground=INK, font=("Aptos", 10))
    style.configure("TLabelframe", background=PAPER, bordercolor=BORDER)
    style.configure(
        "TLabelframe.Label",
        background=PAPER,
        foreground=DEEP_GREEN,
        font=("Aptos Display", 10, "bold"),
    )
    style.configure("Header.TFrame", background=DEEP_GREEN)
    style.configure(
        "HeaderTitle.TLabel",
        background=DEEP_GREEN,
        foreground="white",
        font=("Aptos Display", 15, "bold"),
    )
    style.configure(
        "HeaderStatus.TLabel",
        background=DEEP_GREEN,
        foreground="white",
        font=("Aptos", 10, "bold"),
    )
    style.configure(
        "Selection.TLabel",
        background=PALE_GREEN,
        foreground=DEEP_GREEN,
        font=("Aptos", 10, "bold"),
        padding=(10, 7),
    )
    style.configure("TButton", padding=(8, 5), font=("Aptos", 9))
    style.map(
        "TButton",
        background=[("active", PALE_GREEN), ("pressed", GREEN)],
        foreground=[("pressed", "white")],
    )
    style.configure("Treeview", background=PAPER_RAISED, fieldbackground=PAPER_RAISED)
    style.configure("Treeview.Heading", font=("Aptos", 9, "bold"))
    style.configure("TEntry", fieldbackground=PAPER_RAISED)
    style.configure("TSpinbox", fieldbackground=PAPER_RAISED)
