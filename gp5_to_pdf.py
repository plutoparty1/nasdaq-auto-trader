#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# ─── How to run ───
# 무료 MuseScore Studio 4 설치: https://musescore.org/en/download
# 실행: python gp5_to_pdf.py  (또는 uv run gp5_to_pdf.py)
# 추가 파이썬 패키지 설치는 필요하지 않습니다.
# v1.1 모바일(iOS·Android): https://plutoparty1.github.io/gp5-pdf-web/
# 휴대폰에서는 위 웹앱을 사용하세요. PC에서 열기: python gp5_to_pdf.py --web

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
import webbrowser
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import filedialog, messagebox, ttk
from typing import Final, TypeAlias, final

JSONValue: TypeAlias = "str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]"
WEB_APP_URL: Final = "https://plutoparty1.github.io/gp5-pdf-web/"


class ConversionError(ValueError):
    pass


def find_musescore() -> str:
    configured = os.environ.get("MUSESCORE_PATH", "")
    if configured and Path(configured).is_file():
        return configured
    for name in ("MuseScore4.exe", "mscore", "musescore4", "musescore"):
        found = shutil.which(name)
        if found:
            return found
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            for pattern in (
                "MuseScore*/bin/MuseScore4.exe",
                "Programs/MuseScore*/bin/MuseScore4.exe",
            ):
                for candidate in sorted(Path(root).glob(pattern), reverse=True):
                    if candidate.is_file():
                        return str(candidate)
    return ""


def parse_parts(
    raw: str,
    decode: Callable[[str], JSONValue] = json.loads,
) -> list[tuple[str, bytes]]:
    payload = decode(raw)
    error = "MuseScore가 올바른 악기별 PDF를 반환하지 않았습니다."
    if not isinstance(payload, dict):
        raise ConversionError(error)
    names, encoded = payload.get("parts"), payload.get("partsBin")
    if not isinstance(names, list) or not isinstance(encoded, list):
        raise ConversionError(error)
    if not names or len(names) != len(encoded):
        raise ConversionError("악기 파트를 찾지 못했거나 일부 파트 변환이 누락됐습니다.")
    parts: list[tuple[str, bytes]] = []
    for name, data in zip(names, encoded, strict=True):
        if not isinstance(name, str) or not isinstance(data, str):
            raise ConversionError(error)
        pdf = base64.b64decode(data, validate=True)
        if not pdf.startswith(b"%PDF-"):
            raise ConversionError(error)
        parts.append((name, pdf))
    return parts


def safe_name(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:60] or "악기"


def save_parts(source: Path, parts: list[tuple[str, bytes]]) -> list[Path]:
    saved: list[Path] = []
    for number, (name, pdf) in enumerate(parts, start=1):
        stem = f"{safe_name(source.stem)}_{number:02d}_{safe_name(name)}"
        target = source.parent / f"{stem}.pdf"
        suffix = 2
        while True:
            try:
                output = target.open("xb")
            except FileExistsError:
                target = source.parent / f"{stem} ({suffix}).pdf"
                suffix += 1
                continue
            try:
                with output:
                    _ = output.write(pdf)
            except OSError as exc:
                target.unlink(missing_ok=True)
                detail = f"{len(saved)}개 저장 후 실패했습니다.\n저장 위치: {target}\n{exc}"
                raise OSError(detail) from exc
            saved.append(target)
            break
    return saved


def convert_gp5(source: Path, musescore: Path) -> list[Path]:
    source, musescore = source.resolve(), musescore.resolve()
    if source.suffix.lower() != ".gp5" or not source.is_file():
        raise ConversionError("존재하는 .gp5 파일을 선택해 주세요.")
    if not musescore.is_file():
        raise ConversionError("MuseScore Studio 4의 실행 파일을 선택해 주세요.")
    with TemporaryDirectory(prefix="gp5_pdf_") as temporary:
        export = Path(temporary) / "parts.json"
        result = subprocess.run(
            [str(musescore), "--score-parts-pdf", str(source), "-o", str(export)],
            capture_output=True,
            timeout=300,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode != 0 or not export.is_file():
            detail = (result.stderr + result.stdout).decode("utf-8", errors="replace")[-1800:]
            raise ConversionError(f"MuseScore 변환 실패 (코드 {result.returncode}).\n{detail}")
        parts = parse_parts(export.read_text(encoding="utf-8-sig"))
    return save_parts(source, parts)


@final
class ConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.source = tk.StringVar()
        self.musescore = tk.StringVar(value=find_musescore())
        self.status = tk.StringVar(value="GP5 파일을 선택한 뒤 실행을 누르세요.")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.job: Future[list[Path]] | None = None
        root.title("GP5 → 악기별 PDF")
        root.minsize(700, 410)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        _ = frame.columnconfigure(0, weight=1)
        _ = frame.rowconfigure(7, weight=1)
        ttk.Label(frame, text="GP5 악기별 PDF 변환", font=("맑은 고딕", 16, "bold")).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 16),
        )
        ttk.Label(frame, text="선택한 GP5 파일").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.source, state="readonly").grid(row=2, column=0, sticky="ew")
        self.choose_button = ttk.Button(frame, text="GP5 선택", command=self.choose_source)
        self.choose_button.grid(row=2, column=1, padx=(10, 0))
        ttk.Label(frame, text="MuseScore Studio 4 실행 파일").grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(frame, textvariable=self.musescore, state="readonly").grid(row=4, column=0, sticky="ew")
        self.muse_button = ttk.Button(frame, text="MuseScore 선택", command=self.choose_musescore)
        self.muse_button.grid(row=4, column=1, padx=(10, 0))
        ttk.Label(frame, text="저장 위치: GP5와 같은 폴더 · 악기 트랙별 PDF · 기존 파일 보존").grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(16, 8),
        )
        self.run_button = ttk.Button(frame, text="실행", command=self.start)
        self.run_button.grid(row=6, column=1, sticky="e")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=6, column=0, sticky="ew", padx=(0, 10))
        self.results = tk.Text(frame, height=6, wrap="word", state="disabled")
        self.results.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(12, 8))
        ttk.Label(frame, textvariable=self.status, wraplength=650).grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="w",
        )
        root.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Button(
            frame,
            text="모바일·웹 버전 열기 (iOS·Android 지원)",
            command=lambda: webbrowser.open(WEB_APP_URL),
        ).grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
        )
        _ = root.after(150, self.choose_source)

    def choose_source(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="GP5 파일 선택",
            filetypes=[("Guitar Pro 5", "*.gp5")],
        )
        if selected:
            self.source.set(selected)

    def choose_musescore(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="MuseScore4.exe 선택",
            filetypes=[("실행 파일", "*.exe")],
        )
        if selected:
            self.musescore.set(selected)

    def start(self) -> None:
        if self.job is not None:
            return
        if not self.source.get():
            _ = messagebox.showwarning("파일 선택", "먼저 GP5 파일을 선택해 주세요.", parent=self.root)
            return
        if not self.musescore.get():
            _ = messagebox.showwarning(
                "MuseScore 필요",
                "무료 MuseScore Studio 4를 설치한 뒤\nMuseScore 선택 버튼으로 bin/MuseScore4.exe를 지정해 주세요.",
                parent=self.root,
            )
            return
        for button in (self.choose_button, self.muse_button, self.run_button):
            _ = button.state(["disabled"])
        self.status.set("악기별 PDF를 만드는 중입니다. 악보가 길면 몇 분 걸릴 수 있습니다.")
        self.progress.start(12)
        _ = self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        _ = self.results.configure(state="disabled")
        self.job = self.executor.submit(convert_gp5, Path(self.source.get()), Path(self.musescore.get()))
        _ = self.root.after(150, self.poll)

    def poll(self) -> None:
        if self.job is None:
            return
        if not self.job.done():
            _ = self.root.after(150, self.poll)
            return
        self.progress.stop()
        for button in (self.choose_button, self.muse_button, self.run_button):
            _ = button.state(["!disabled"])
        try:
            files = self.job.result()
            _ = self.results.configure(state="normal")
            self.results.insert("end", "\n".join(str(path) for path in files))
            _ = self.results.configure(state="disabled")
            self.status.set(f"완료: 악기별 PDF {len(files)}개를 저장했습니다.")
            _ = messagebox.showinfo(
                "변환 완료",
                f"PDF {len(files)}개 저장 완료\n\n{files[0].parent}",
                parent=self.root,
            )
        except subprocess.TimeoutExpired:
            self.status.set("변환 시간이 5분을 초과했습니다. 다시 시도해 주세요.")
            _ = messagebox.showerror("시간 초과", self.status.get(), parent=self.root)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            self.status.set("변환에 실패했습니다. 입력 파일과 MuseScore 경로를 확인하세요.")
            _ = messagebox.showerror("변환 실패", str(exc), parent=self.root)
        finally:
            self.job = None

    def close(self) -> None:
        if self.job is not None:
            _ = messagebox.showinfo("변환 중", "변환이 완료된 뒤 창을 닫아 주세요.", parent=self.root)
            return
        self.executor.shutdown(wait=False)
        self.root.destroy()


def main() -> None:
    if "--web" in sys.argv[1:]:
        print(WEB_APP_URL)
        _ = webbrowser.open(WEB_APP_URL)
        return
    root = tk.Tk()
    _ = ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
