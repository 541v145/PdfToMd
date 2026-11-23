# Dodaje "Pretvori u Markdown" u desni klik na PDF (samo za trenutnog korisnika) i precicu u Start meni.
# (Fajl je namjerno ASCII: Windows PowerShell 5.1 cita .ps1 bez BOM-a kao ANSI.)
# Uklanjanje: install_menu.ps1 -Uninstall
param([switch]$Uninstall)

$app = $PSScriptRoot
$key = "HKCU:\Software\Classes\SystemFileAssociations\.pdf\shell\PdfToMd"
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "PDF u Markdown.lnk"

if ($Uninstall) {
    Remove-Item $key -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $lnk -Force -ErrorAction SilentlyContinue
    "Uklonjeno."
    return
}

$pythonw = Join-Path $app ".venv\Scripts\pythonw.exe"
$gui = Join-Path $app "gui.py"

New-Item -Path "$key\command" -Force | Out-Null
Set-ItemProperty -Path $key -Name "MUIVerb" -Value "Pretvori u Markdown"
Set-ItemProperty -Path $key -Name "Icon" -Value "imageres.dll,-102"
Set-ItemProperty -Path $key -Name "MultiSelectModel" -Value "Player"
Set-ItemProperty -Path "$key\command" -Name "(default)" -Value "`"$pythonw`" `"$gui`" `"%1`""

$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = "`"$gui`""
$s.WorkingDirectory = $app
$s.IconLocation = "imageres.dll,102"
$s.Save()

"Instalirano: desni klik na PDF -> 'Pretvori u Markdown' (Windows 11: 'Show more options' / Shift+F10), i Start meni -> 'PDF u Markdown'."
