import os
import sys
import shutil


# keep runtime file locations in one place so packaging and local runs stay in sync
APP_FOLDER_NAME = "ArenaSurvivor"


def project_root():
    # pyinstaller exposes the unpacked app through _MEIPASS, otherwise just use the repo root
    if hasattr(sys, "_MEIPASS"):
        return getattr(sys, "_MEIPASS")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, ".."))


def assets_dir():
    return os.path.join(project_root(), "Assets")


def _home_dir():
    return os.path.expanduser("~")


def user_data_dir():
    # save files go here so we stay in the normal per-user app data spot on each os
    if sys.platform == "darwin":
        base = os.path.join(_home_dir(), "Library", "Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(_home_dir(), "AppData", "Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(_home_dir(), ".local", "share")
    return os.path.join(base, APP_FOLDER_NAME)


def user_cache_dir():
    if sys.platform == "darwin":
        base = os.path.join(_home_dir(), "Library", "Caches")
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.path.join(_home_dir(), "AppData", "Local")
        base = os.path.join(local, APP_FOLDER_NAME, "Cache")
        return base
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(_home_dir(), ".cache")
    return os.path.join(base, APP_FOLDER_NAME)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def leaderboard_records_path():
    return os.path.join(user_data_dir(), "leaderboard_records.json")


def intro_stage_runtime_dir():
    return os.path.join(user_cache_dir(), "intro_stage")


def intro_stage_layout_cache_path():
    return os.path.join(intro_stage_runtime_dir(), "intro_stage_enemy_pickup_layout_cache.json")


def packaged_cache_dir():
    # packaged builds can end up with slightly different resource roots, so try the common ones
    candidates = [os.path.join(project_root(), "PackagedCache")]
    if hasattr(sys, "_MEIPASS"):
        meipass_root = project_root()
        candidates.extend([
            os.path.normpath(os.path.join(meipass_root, "..", "Resources", "PackagedCache")),
            os.path.normpath(os.path.join(meipass_root, "..", "..", "Resources", "PackagedCache")),
        ])
        exe_root = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend([
            os.path.normpath(os.path.join(exe_root, "..", "Resources", "PackagedCache")),
            os.path.normpath(os.path.join(exe_root, "..", "..", "Resources", "PackagedCache")),
        ])
    seen = set()
    for candidate in candidates:
        norm = os.path.normpath(candidate)
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.exists(norm):
            return norm
    return os.path.normpath(candidates[0])


def packaged_intro_stage_cache_dir():
    return os.path.join(packaged_cache_dir(), "intro_stage")


def seed_runtime_file(runtime_path, packaged_path):
    # copy bundled cache files into the writable runtime area the first time we need them
    if os.path.exists(runtime_path) or not os.path.exists(packaged_path):
        return False
    ensure_dir(os.path.dirname(runtime_path))
    try:
        shutil.copy2(packaged_path, runtime_path)
        return True
    except Exception:
        return False
