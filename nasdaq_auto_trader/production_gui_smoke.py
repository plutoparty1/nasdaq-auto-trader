from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path

from PIL import ImageGrab

from .production_gui import ProductionApp
from .production_gui_actions import ProductionFacade


def run_gui_smoke(service: ProductionFacade, output: Path) -> None:
    root = tk.Tk()
    app = ProductionApp(root, service)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = output.with_suffix(".json")

    def capture_main() -> None:
        root.lift()
        root.update_idletasks()
        bbox = (root.winfo_rootx(), root.winfo_rooty(),
                root.winfo_rootx() + root.winfo_width(),
                root.winfo_rooty() + root.winfo_height())
        ImageGrab.grab(bbox=bbox).save(output.with_suffix(".png"))
        metadata.write_text(json.dumps({
            "surface": "actual_tk_window", "status": app.status_var.get(),
            "buttons": [button.cget("text") for button in app._buttons],
            "preflight_calls": 0, "approval_calls": 0, "operating_start_calls": 0,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        app._show_review(service.review())
        _ = root.after(800, capture_review)

    def capture_review() -> None:
        window = app._review_window
        if window is not None:
            window.lift()
            window.update_idletasks()
            bbox = (window.winfo_rootx(), window.winfo_rooty(),
                    window.winfo_rootx() + window.winfo_width(),
                    window.winfo_rooty() + window.winfo_height())
            ImageGrab.grab(bbox=bbox).save(output.with_name(output.stem + "-review").with_suffix(".png"))
        _ = service.shutdown()
        app.closing = True
        app._executor.shutdown(wait=True)
        root.destroy()

    _ = root.after(800, capture_main)
    root.mainloop()
