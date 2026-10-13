"""Passive HWND capture of our frozen GUI diagnostic; sends no app input."""
from pathlib import Path
import ctypes, json, subprocess, time, sys
from ctypes import wintypes
from PIL import ImageGrab
root=Path.cwd();out=root/'docs/production-release-20261013';exe=Path(sys.argv[1]) if len(sys.argv)>1 else root/'deploy-operating/NasdaqAutoTrader/NasdaqAutoTrader.exe'
user32=ctypes.WinDLL('user32',use_last_error=True)
callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user32.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
process=subprocess.Popen([str(exe),'--gui-smoke',str(out/'desktop-capture-retry')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
captured={}
while process.poll() is None:
    windows=[]
    @callback_type
    def collect(hwnd,param):
        pid=wintypes.DWORD();user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==process.pid:
            title=ctypes.create_unicode_buffer(512);user32.GetWindowTextW(hwnd,title,512)
            if title.value.startswith(('NASDAQ Auto Trader','최종 조건 검토')): windows.append((hwnd,title.value))
        return True
    user32.EnumWindows(collect,0)
    for hwnd,title in windows:
        label='review' if title.startswith('최종') else 'main'
        try:
            image=ImageGrab.grab(window=int(hwnd))
        except OSError:
            continue
        if image.width>500 and image.height>300:
            path=out/('frozen-gui-native-review.png' if label=='review' else 'frozen-gui-native.png')
            image.save(path)
            captured[label]={'hwnd':int(hwnd),'title':title,'pid':process.pid,'path':str(path),'size':image.size}
    time.sleep(.1)
stdout,stderr=process.communicate(timeout=5)
(out/'native-window-capture.json').write_text(json.dumps({'capture':'PIL_windows_PrintWindow_by_exact_own_process_hwnd','exit':process.returncode,'windows':captured,'input_actions':0,'approval_or_start_actions':0},ensure_ascii=False,indent=2),encoding='utf-8')
assert process.returncode==0 and {'main','review'}<=c