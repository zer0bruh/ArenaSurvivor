import argparse
import hashlib
import json
import os
import platform
import pickle
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from arena.runtime_paths import intro_stage_runtime_dir
from arena.intro_opening_cache import build_intro_opening_cache_file

# build script for local release bundles
PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_FILE = PROJECT_ROOT / "main.py"
ASSETS_DIR = PROJECT_ROOT / "Assets"
APP_NAME = "Arena Survivor"
APP_VERSION = "1.0"
APP_BUNDLE_ID = "com.z.arenasurvivor"
APP_COPYRIGHT = "Copyright Capcom Co., Ltd. All Rights Reserved."
APP_ICON_SOURCE = PROJECT_ROOT / "build_assets" / "ArenaSurvivorIcon.png"


def host_target():
    # default to the current machine unless the caller asked for something else
    system = platform.system().lower()
    if system == "darwin":
        return "mac"
    if system == "windows":
        return "windows"
    return system


def build_name(target):
    return APP_NAME


def add_data_arg(target, source, destination):
    separator = ":" if target == "mac" else ";"
    return f"{source}{separator}{destination}"


def dist_dir(target):
    return PROJECT_ROOT / "releases" / target


def output_path(target):
    base = dist_dir(target)
    if target == "mac":
        return base / f"{APP_NAME}.app"
    if target == "windows":
        return base / f"{APP_NAME}.exe"
    return base / APP_NAME


def legacy_output_paths(target):
    # old build names and folders still show up during iteration, so clear all the usual leftovers
    paths = [
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "dist" / ".DS_Store",
        PROJECT_ROOT / "releases" / ".DS_Store",
        PROJECT_ROOT / "dist" / "Arena Survivor",
        PROJECT_ROOT / "dist" / "ArenaSurvivor",
        PROJECT_ROOT / "dist" / f"{APP_NAME}.app",
        PROJECT_ROOT / "dist" / APP_NAME,
        PROJECT_ROOT / "dist" / f"{APP_NAME}.exe",
        PROJECT_ROOT / "releases" / "Arena Survivor",
        PROJECT_ROOT / "releases" / "ArenaSurvivor",
        PROJECT_ROOT / "releases" / f"{APP_NAME}.app",
        PROJECT_ROOT / "releases" / APP_NAME,
        PROJECT_ROOT / "releases" / f"{APP_NAME}.exe",
    ]
    if target == "mac":
        paths.extend([
            PROJECT_ROOT / "dist" / target / ".DS_Store",
            PROJECT_ROOT / "dist" / target / "Arena Survivor",
            PROJECT_ROOT / "dist" / target / "Arena Survivor.app",
            PROJECT_ROOT / "dist" / target / f"{APP_NAME}.app",
            dist_dir(target) / ".DS_Store",
            dist_dir(target) / "Arena Survivor",
            dist_dir(target) / "Arena Survivor.app",
            dist_dir(target) / f"{APP_NAME}.app",
        ])
    else:
        paths.extend([
            PROJECT_ROOT / "dist" / target / ".DS_Store",
            PROJECT_ROOT / "dist" / target / "Thumbs.db",
            PROJECT_ROOT / "dist" / target / "desktop.ini",
            PROJECT_ROOT / "dist" / target / "Arena Survivor",
            PROJECT_ROOT / "dist" / target / "ArenaSurvivor",
            PROJECT_ROOT / "dist" / target / f"{APP_NAME}.exe",
            dist_dir(target) / ".DS_Store",
            dist_dir(target) / "Thumbs.db",
            dist_dir(target) / "desktop.ini",
            dist_dir(target) / "Arena Survivor",
            dist_dir(target) / "ArenaSurvivor",
            dist_dir(target) / f"{APP_NAME}.exe",
        ])
    return paths


def remove_path(path):
    if not path.exists():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _remove_junk_files(root):
    if not root.exists():
        return
    junk_names = {".DS_Store", "Thumbs.db", "desktop.ini"}
    for path in root.rglob("*"):
        if path.name in junk_names or path.name.startswith("._"):
            remove_path(path)


def _prune_release_dir(target):
    root = dist_dir(target)
    if not root.exists():
        return
    _remove_junk_files(root)
    final_output_name = output_path(target).name
    if target == "mac":
        for path in root.iterdir():
            if path.name.startswith("."):
                remove_path(path)
                continue
            if path.name != final_output_name:
                remove_path(path)
        return
    if target == "windows":
        for path in root.iterdir():
            if path.name.startswith("."):
                remove_path(path)
                continue
            if path.name != final_output_name:
                remove_path(path)


def _file_signature(label, path):
    if not path.exists():
        return (label, None, None)
    digest = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return (label, path.stat().st_size, digest.hexdigest())


def _intro_stage_asset_cache_key():
    stage_root = ASSETS_DIR / "stages" / "intro_stage"
    key = [
        _file_signature("art", stage_root / "intro_stage_full_tileset.png"),
        _file_signature("collision", stage_root / "intro_stage_tileset_newest_annotations.png"),
    ]
    modified = stage_root / "intro_stage_some_modified_annotations.png"
    if modified.exists():
        key.append(_file_signature("modified", modified))
    for index in range(1, 6):
        key.append(_file_signature(f"background{index}", stage_root / "backgrounds" / f"introbackground{index}.png"))
    return tuple(key)


def _intro_stage_layout_cache_key():
    stage_root = ASSETS_DIR / "stages" / "intro_stage"
    return (
        2,
        _file_signature("placements", stage_root / "intro_stage_tileset_enemy_and_pickup_placements.png"),
        _file_signature("base_annotations", stage_root / "intro_stage_tileset_newest_annotations.png"),
    )


def build_seed_cache_dir(root):
    # bundle prebuilt caches so the shipped app does not need to preprocess the intro stage on first boot
    source_dir = Path(intro_stage_runtime_dir())
    if not source_dir.exists():
        return None
    patterns = (
        "intro_stage_cache_v*.pkl",
        "intro_stage_surface_v*.png",
        "intro_stage_annotation_v*.png",
        "intro_stage_enemy_pickup_layout_cache.json",
        "intro_opening_assets_cache_v*.pkl",
    )
    available = []
    for pattern in patterns:
        available.extend(sorted(source_dir.glob(pattern)))
    if not available:
        return None
    out_dir = root / "PackagedCache" / "intro_stage"
    out_dir.mkdir(parents=True, exist_ok=True)
    intro_stage_cache_key = _intro_stage_asset_cache_key()
    intro_stage_layout_key = _intro_stage_layout_cache_key()
    for path in available:
        destination = out_dir / path.name
        if path.suffix == ".pkl" and path.name.startswith("intro_stage_cache_v"):
            try:
                with path.open("rb") as f:
                    payload = pickle.load(f)
                payload["asset_cache_key"] = intro_stage_cache_key
                with destination.open("wb") as f:
                    pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
                continue
            except Exception:
                pass
        if path.suffix == ".json" and path.name == "intro_stage_enemy_pickup_layout_cache.json":
            try:
                with path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
                payload["cache_key"] = list(intro_stage_layout_key)
                with destination.open("w", encoding="utf-8") as f:
                    json.dump(payload, f)
                continue
            except Exception:
                pass
        shutil.copy2(path, destination)
    try:
        build_intro_opening_cache_file(out_dir / "intro_opening_assets_cache_v1.pkl", str(ASSETS_DIR))
    except Exception:
        pass
    return out_dir.parent


def _build_windows_icon(root):
    # generate an .ico on the fly from the source png if pillow is available
    try:
        from PIL import Image
    except ImportError:
        return None
    if not APP_ICON_SOURCE.exists():
        return None
    icon_path = root / f"{APP_NAME}.ico"
    with Image.open(APP_ICON_SOURCE) as img:
        img = img.convert("RGBA")
        img.save(icon_path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    return icon_path


def _build_mac_icon(root):
    # mac wants an .icns made from an iconset, so build the intermediate files here
    if not APP_ICON_SOURCE.exists():
        return None
    iconset_dir = root / f"{APP_NAME}.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)
    icon_specs = (
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    )
    for size, filename in icon_specs:
        subprocess.run(
            [
                "sips",
                "-z",
                str(size),
                str(size),
                str(APP_ICON_SOURCE),
                "--out",
                str(iconset_dir / filename),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    icon_path = root / f"{APP_NAME}.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icon_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return icon_path


def _build_icon_for_target(target, root):
    if target == "mac":
        return _build_mac_icon(root)
    if target == "windows":
        return _build_windows_icon(root)
    return None


def _update_mac_bundle_metadata(app_path):
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        return
    with plist_path.open("rb") as f:
        payload = plistlib.load(f)
    payload["CFBundleDisplayName"] = APP_NAME
    payload["CFBundleName"] = APP_NAME
    payload["CFBundleIdentifier"] = APP_BUNDLE_ID
    payload["CFBundleShortVersionString"] = APP_VERSION
    payload["CFBundleVersion"] = APP_VERSION
    payload["NSHumanReadableCopyright"] = APP_COPYRIGHT
    with plist_path.open("wb") as f:
        plistlib.dump(payload, f)


def build_target(target):
    pyinstaller_module = [sys.executable, "-m", "PyInstaller"]
    dist_dir(target).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arena_build_") as temp_dir:
        temp_root = Path(temp_dir)
        work_path = temp_root / "work"
        spec_path = temp_root / "spec"
        config_path = temp_root / "pyinstaller_config"
        packaged_cache_root = build_seed_cache_dir(temp_root)
        icon_path = _build_icon_for_target(target, temp_root)
        env = dict(os.environ)
        env["PYINSTALLER_CONFIG_DIR"] = str(config_path)

        cmd = pyinstaller_module + [
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name",
            build_name(target),
            "--distpath",
            str(dist_dir(target)),
            "--workpath",
            str(work_path),
            "--specpath",
            str(spec_path),
            "--add-data",
            add_data_arg(target, ASSETS_DIR, "Assets"),
        ]
        if target == "windows":
            cmd.append("--onefile")
        if target == "mac":
            cmd += ["--osx-bundle-identifier", APP_BUNDLE_ID]
        if icon_path is not None:
            cmd += ["--icon", str(icon_path)]
        if packaged_cache_root is not None:
            cmd += [
                "--add-data",
                add_data_arg(target, packaged_cache_root, "PackagedCache"),
            ]
        cmd.append(str(MAIN_FILE))
        subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT), env=env)

    if target == "mac":
        _update_mac_bundle_metadata(output_path(target))
    _prune_release_dir(target)


def main():
    parser = argparse.ArgumentParser(
        description="Build Arena Survivor for the current platform."
    )
    parser.add_argument(
        "--target",
        choices=("native", "mac", "windows"),
        default="native",
        help="Build target. 'native' uses the current OS.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete the existing target dist folder before building.",
    )
    args = parser.parse_args()

    current_host = host_target()
    target = current_host if args.target == "native" else args.target

    if target not in {"mac", "windows"}:
        raise SystemExit(f"Unsupported host platform: {platform.system()}")

    if target != current_host:
        raise SystemExit(
            f"Cannot build '{target}' on {platform.system()}. "
            f"Build mac on macOS and windows on Windows."
        )

    target_dist = dist_dir(target)
    if args.clean_output and target_dist.exists():
        shutil.rmtree(target_dist)
    for path in legacy_output_paths(target):
        remove_path(path)

    print(f"Building Arena Survivor for {target}...")
    build_target(target)
    print()
    print(f"Build complete: {output_path(target)}")


if __name__ == "__main__":
    main()
