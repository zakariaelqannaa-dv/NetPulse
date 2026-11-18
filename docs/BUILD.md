# Building NetPulse for Windows

NetPulse is packaged with [PyInstaller](https://pyinstaller.org/). The project
ships a spec file, `netpulse.spec`, that produces a **one-folder, windowed**
build of `app/__main__.py`.

---

## Before you build

- Windows 10 or Windows 11.
- Python 3.12 or newer.
- The build environment must have the project's dependencies installed:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes PyInstaller (`pyinstaller>=6.0`).

---

## Recommended build: one folder (using the spec file)

From the repository root:

```powershell
python -m PyInstaller netpulse.spec --noconfirm
```

The spec file:

- uses `app/__main__.py` as the entry script,
- adds the repository root to `pathex` so `import app...` resolves,
- sets `console=False` (windowed build — no console window),
- excludes `tkinter`, `unittest` and `pytest`,
- declares a hidden import for `psutil`,
- disables UPX compression (`upx=False`),
- leaves the icon unset (`icon=None`).

The output is written to:

```
dist/NetPulse/NetPulse.exe
```

Keep the whole `dist/NetPulse/` folder together: the `.exe` needs the adjacent
files that PyInstaller places beside it.

---

## One-folder build without the spec file (direct CLI equivalent)

If you prefer not to use the spec file, this is the equivalent command:

```powershell
python -m PyInstaller --noconfirm --onedir --windowed --name NetPulse `
    --paths . `
    --exclude-module tkinter --exclude-module unittest --exclude-module pytest `
    --hidden-import psutil `
    app/__main__.py
```

The result also lands in `dist/NetPulse/NetPulse.exe`.

---

## Single-file build

A single-file build bundles everything into one `.exe`. It is convenient to
distribute but starts more slowly (it has to unpack itself to a temporary folder)
and is harder for antivirus products to trust.

Using the direct CLI:

```powershell
python -m PyInstaller --noconfirm --onefile --windowed --name NetPulse `
    --paths . `
    --exclude-module tkinter --exclude-module unittest --exclude-module pytest `
    --hidden-import psutil `
    app/__main__.py
```

To produce a single-file build from the spec file instead, edit `netpulse.spec`,
add `a.binaries` and `a.datas` to the `EXE(...)` call, and remove the `COLLECT`
step. The one-folder build is the recommended default.

The single-file output is:

```
dist/NetPulse.exe
```

---

## Optional: bundling dnspython

`dnspython` is optional. When it is installed, NetPulse can time each configured
DNS resolver separately; without it, NetPulse measures the system resolver only.
To include it in a build, install it in the build environment and add it to the
hidden imports:

```powershell
python -m pip install "dnspython>=2.4"
```

Then either edit `netpulse.spec` and add `"dns"` to `hiddenimports`, or pass
`--hidden-import dns` on the command line.

---

## Optional: adding an icon

The spec leaves the icon unset. To add one later, place an `.ico` file in the
repository and change the `icon=` value in `netpulse.spec`:

```python
icon="assets/netpulse.ico",
```

(On the command line, use `--icon assets/netpulse.ico`.)

---

## Verifying the build

1. Run the executable:

```powershell
.\dist\NetPulse\NetPulse.exe
```

2. Confirm that **no console window** appears and the application window opens.
3. Run a full diagnosis (Start Diagnosis) and confirm the results update without
   the window freezing, and that Stop cancels a run.
4. Open the Export dialog and export a report in TXT (and optionally HTML), then
   open the file to confirm it is complete.
5. Open the Windows Network Settings page and confirm the read-only checks are
   populated (the settings themselves require administrator rights to change).
6. If you ran the diagnosis on a machine that is offline, confirm the application
   handles it gracefully and reports unavailable values instead of failing.

---

## What this build does **not** do

- **No code signing.** The executable is unsigned, so Windows SmartScreen may
  warn about an unknown publisher. Signing requires your own certificate and is
  out of scope for this project.
- **No installer.** There is no MSI or setup wizard. Distribute the
  `dist/NetPulse/` folder (or the single-file `.exe`) directly.
- **No auto-update.** NetPulse does not check for or install updates; this is
  consistent with its no-network-service, no-telemetry design.
- **No UPX compression.** UPX is disabled because it can trigger false positives
  in antivirus products.
