"""Create a local development shortcut without altering Windows security settings."""
from pathlib import Path
import win32com.client


def main():
    root=Path(__file__).resolve().parents[1]
    pythonw=root/'.venv'/'Scripts'/'pythonw.exe'
    launcher=root/'launcher.py'
    if not pythonw.is_file() or not launcher.is_file():
        raise RuntimeError('Python 실행 환경 또는 launcher.py가 없습니다')
    destination=root/'촉매마감관리_실행.lnk'
    shell=win32com.client.Dispatch('WScript.Shell')
    shortcut=shell.CreateShortcut(str(destination))
    shortcut.TargetPath=str(pythonw)
    shortcut.Arguments='"'+str(launcher)+'"'
    shortcut.WorkingDirectory=str(root)
    shortcut.Description='촉매 마감 관리 — 로컬 Python 실행'
    shortcut.WindowStyle=1
    shortcut.Save()
    saved=shell.CreateShortcut(str(destination))
    assert saved.TargetPath.lower()==str(pythonw).lower()
    print(destination)


if __name__=='__main__':main()
