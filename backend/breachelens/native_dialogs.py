"""Small native OS dialogs used by the local-only desktop executable."""
from __future__ import annotations

import platform
import shutil
import subprocess


def pick_folder() -> str | None:
    """Open a native folder picker and return the selected absolute path."""
    system = platform.system()
    if system == "Windows":
        script = r"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose a folder for Pharos to scan'
$dialog.ShowNewFolderButton = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
}
"""
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            creationflags=creationflags,
            check=False,
        )
        selected = completed.stdout.strip().splitlines()
        return selected[-1].strip() if completed.returncode == 0 and selected else None

    if system == "Darwin" and shutil.which("osascript"):
        completed = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose folder with prompt "Choose a folder for Pharos to scan")'],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    if shutil.which("zenity"):
        completed = subprocess.run(
            ["zenity", "--file-selection", "--directory", "--title=Choose a folder for Pharos to scan"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    return None
