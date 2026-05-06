# Building ArenaSurvivor

This project can be packaged as a desktop app with `PyInstaller`.

## One cross-platform build script

Use:

```bash
python build_release.py
```

That builds the native target for the OS you are currently on:

- macOS -> `.app`
- Windows -> `.exe` bundle folder

You can also be explicit:

```bash
python build_release.py --target mac
python build_release.py --target windows
```

Those must still be run on the matching OS.

## Install packaging tool

```bash
pip install pyinstaller
```

## macOS

Run:

```bash
python build_release.py --target mac
```

Output:

- `releases/mac/Arena Survivor.app`

## Windows

Run:

```bat
python build_release.py --target windows
```

Output:

- `releases/windows/Arena Survivor.exe`

## Updating the app later

When you change code or assets:

1. Update the source project.
2. Test the game normally.
3. Re-run the build script for each platform.
4. Replace the old packaged app/exe with the new build artifact in `releases/mac` or `releases/windows`.

## Notes

- Assets are bundled into the packaged build automatically.
- Leaderboards and runtime caches are stored in the user's writable app-data folders, not inside the app bundle.
- A Mac build should be created on macOS, and a Windows build should be created on Windows.
- The script removes old `build`/`dist` leftovers and prunes the target release folder so only the final app artifact remains.
