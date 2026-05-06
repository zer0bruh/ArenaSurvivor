import hashlib
import os
import pickle
import shutil

import pygame

from .assets import assets_load_spritesheet
from .core import Animation
from .runtime_paths import (
    assets_dir,
    ensure_dir,
    intro_stage_runtime_dir,
    packaged_intro_stage_cache_dir,
    seed_runtime_file,
)


INTRO_OPENING_CACHE_VERSION = 1
_intro_opening_assets_cache = None


# runtime cache paths live outside the bundle so future launches can skip the expensive prep work
def _runtime_cache_path():
    return os.path.join(
        intro_stage_runtime_dir(),
        f"intro_opening_assets_cache_v{INTRO_OPENING_CACHE_VERSION}.pkl",
    )


def _packaged_cache_path():
    return os.path.join(
        packaged_intro_stage_cache_dir(),
        f"intro_opening_assets_cache_v{INTRO_OPENING_CACHE_VERSION}.pkl",
    )


def _file_signature(label, path):
    if not os.path.exists(path):
        return (label, None, None)
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return (label, os.path.getsize(path), digest.hexdigest())


def intro_opening_cache_key(assets_root=None):
    # invalidate the cache whenever any of the sprites or background slices it depends on change
    if assets_root is None:
        assets_root = assets_dir()
    return (
        _file_signature("zero_png", os.path.join(assets_root, "playable_characters", "zero", "zero_final_spritesheet.png")),
        _file_signature("zero_json", os.path.join(assets_root, "playable_characters", "zero", "zero_final_spritesheet.json")),
        _file_signature("x_png", os.path.join(assets_root, "playable_characters", "x", "x_final_spritesheet.png")),
        _file_signature("x_json", os.path.join(assets_root, "playable_characters", "x", "x_final_spritesheet.json")),
        _file_signature("copter_sheet_png", os.path.join(assets_root, "enemies", "copter_enemy.png")),
        _file_signature("copter_sheet_json", os.path.join(assets_root, "enemies", "copter_enemy.json")),
        _file_signature("cutscene_copter1", os.path.join(assets_root, "enemies", "custscene_copter1.png")),
        _file_signature("cutscene_copter2", os.path.join(assets_root, "enemies", "custscene_copter2.png")),
        _file_signature("cutscene_copter3", os.path.join(assets_root, "enemies", "custscene_copter3.png")),
        _file_signature("intro_bg1", os.path.join(assets_root, "stages", "intro_stage", "backgrounds", "introbackground1.png")),
        _file_signature("airbase_clouds1", os.path.join(assets_root, "stages", "airbase", "airbase area background clouds1.png")),
    )


def _ensure_pygame_ready():
    # some cache builds happen from tooling, so bootstrap a tiny hidden display if needed
    started_display = False
    started_pygame = False
    if not pygame.get_init() and not os.environ.get("SDL_VIDEODRIVER"):
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    if not pygame.get_init():
        pygame.init()
        started_pygame = True
    if not pygame.display.get_init():
        pygame.display.init()
        started_display = True
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1), pygame.HIDDEN)
        started_display = True
    return started_pygame, started_display


def _cleanup_pygame(started_pygame, started_display):
    if started_display and pygame.display.get_init():
        pygame.display.quit()
    if started_pygame and pygame.get_init():
        pygame.quit()


def _crop_alpha_surface(surface):
    # trim transparent padding so cutscene frames line up more predictably later
    if surface is None:
        return None
    rect = surface.get_bounding_rect()
    if rect.width <= 0 or rect.height <= 0:
        return surface.copy()
    cropped = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    cropped.blit(surface, (0, 0), rect)
    return cropped


def _surface_to_payload(surface):
    return {
        "size": surface.get_size(),
        "rgba": pygame.image.tostring(surface, "RGBA"),
    }


def _surface_from_payload(payload):
    surface = pygame.image.fromstring(payload["rgba"], tuple(payload["size"]), "RGBA")
    if pygame.display.get_init() and pygame.display.get_surface() is not None:
        return surface.convert_alpha()
    return surface


def _serialize_value(value):
    # store pygame-heavy objects as plain payloads so pickle stays portable and lightweight
    if isinstance(value, Animation):
        return {
            "__type__": "animation",
            "images": [_surface_to_payload(img) for img in value.images],
            "durations": list(value.durations),
            "loop": bool(value.loop),
            "loop_from": int(value.loop_from),
        }
    if isinstance(value, pygame.Surface):
        return {
            "__type__": "surface",
            "surface": _surface_to_payload(value),
        }
    if isinstance(value, list):
        return {
            "__type__": "list",
            "items": [_serialize_value(item) for item in value],
        }
    return value


def _deserialize_value(value):
    if isinstance(value, dict):
        value_type = value.get("__type__")
        if value_type == "animation":
            return Animation(
                [_surface_from_payload(item) for item in value.get("images", [])],
                list(value.get("durations", [])),
                loop=bool(value.get("loop", True)),
                loop_from=int(value.get("loop_from", 0)),
            )
        if value_type == "surface":
            return _surface_from_payload(value["surface"])
        if value_type == "list":
            return [_deserialize_value(item) for item in value.get("items", [])]
    return value


def _normalize_frames_midbottom(frames):
    # normalize around midbottom because that is how the cutscene actors get placed in-world
    if not frames:
        return []
    max_w = max(frame.get_width() for frame in frames)
    max_h = max(frame.get_height() for frame in frames)
    normalized = []
    anchor_x = max_w // 2
    anchor_y = max_h - 1
    for frame in frames:
        canvas = pygame.Surface((max_w, max_h), pygame.SRCALPHA).convert_alpha()
        rect = frame.get_rect()
        rect.midbottom = (anchor_x, anchor_y)
        canvas.blit(frame, rect)
        normalized.append(canvas)
    return normalized


def _crop_frames(anim):
    if anim is None:
        return []
    return [_crop_alpha_surface(img) for img in anim.images]


def build_intro_opening_assets(assets_root=None):
    # collect just the intro-opening art we need, already cropped and normalized for rendering
    if assets_root is None:
        assets_root = assets_dir()

    zero_anims = assets_load_spritesheet(
        assets_root,
        "playable_characters/zero/zero_final_spritesheet.png",
        "playable_characters/zero/zero_final_spritesheet.json",
    )
    x_anims = assets_load_spritesheet(
        assets_root,
        "playable_characters/x/x_final_spritesheet.png",
        "playable_characters/x/x_final_spritesheet.json",
    )

    cutscene_copter_frames = []
    for name in ("custscene_copter1.png", "custscene_copter2.png", "custscene_copter3.png"):
        path = os.path.join(assets_root, "enemies", name)
        if not os.path.exists(path):
            continue
        try:
            cutscene_copter_frames.append(pygame.image.load(path).convert_alpha())
        except Exception:
            pass
    if not cutscene_copter_frames:
        copter_anims = assets_load_spritesheet(
            assets_root,
            "enemies/copter_enemy.png",
            "enemies/copter_enemy.json",
        )
        cutscene_copter_frames = _crop_frames(copter_anims.get("copter_flying"))
    cutscene_copter_frames = _normalize_frames_midbottom(cutscene_copter_frames)

    intro_opening_bg = pygame.image.load(
        os.path.join(assets_root, "stages", "intro_stage", "backgrounds", "introbackground1.png")
    ).convert_alpha()
    intro_opening_bg_front = intro_opening_bg.copy()
    intro_opening_bg_front.set_alpha(56)
    intro_opening_clouds_back = intro_opening_bg.subsurface(
        pygame.Rect(0, 18, intro_opening_bg.get_width(), 96)
    ).copy()
    intro_opening_clouds_front = intro_opening_bg.subsurface(
        pygame.Rect(0, 86, intro_opening_bg.get_width(), 88)
    ).copy()
    intro_opening_clouds_back.set_alpha(165)
    intro_opening_clouds_front.set_alpha(120)
    airbase_clouds = pygame.image.load(
        os.path.join(assets_root, "stages", "airbase", "airbase area background clouds1.png")
    ).convert_alpha()
    airbase_clouds.set_alpha(110)
    intro_opening_airbase_clouds = pygame.transform.smoothscale(
        airbase_clouds,
        (
            max(1, int(round(airbase_clouds.get_width() * 0.48))),
            max(1, int(round(airbase_clouds.get_height() * 0.48))),
        ),
    )
    intro_opening_airbase_clouds.set_alpha(120)

    return {
        "zero_idle": zero_anims.get("zero_idle"),
        "zero_jumping": zero_anims.get("zero_jumping"),
        "zero_climbing": zero_anims.get("zero_climbing"),
        "zero_falling": zero_anims.get("zero_falling"),
        "zero_air_saber_slash": zero_anims.get("zero_air_saber_slash"),
        "zero_wallkick_jump": zero_anims.get("zero_wallkick_jump"),
        "zero_wall_saber_slash": zero_anims.get("zero_wall_saber_slash"),
        "x_idle": x_anims.get("x_idle"),
        "x_falling": x_anims.get("x_falling"),
        "x_nova_strike": x_anims.get("x_nova_strike"),
        "x_exiting": x_anims.get("x_exiting"),
        "zero_wallkick_frames": _crop_frames(zero_anims.get("zero_wallkick_jump")),
        "zero_wall_saber_frames": _crop_frames(zero_anims.get("zero_wall_saber_slash")),
        "zero_climbing_frames": _crop_frames(zero_anims.get("zero_climbing")),
        "zero_idle_frames": _crop_frames(zero_anims.get("zero_idle")),
        "zero_jumping_frames": _crop_frames(zero_anims.get("zero_jumping")),
        "zero_falling_frames": _crop_frames(zero_anims.get("zero_falling")),
        "zero_air_saber_frames": _crop_frames(zero_anims.get("zero_air_saber_slash")),
        "zero_exit_frames": _crop_frames(zero_anims.get("zero_exiting")),
        "zero_exit_tail_frames": _normalize_frames_midbottom(_crop_frames(zero_anims.get("zero_exiting"))[-7:]),
        "x_idle_frames": _crop_frames(x_anims.get("x_idle")),
        "x_falling_frames": _crop_frames(x_anims.get("x_falling")),
        "x_dash_frames": _crop_frames(x_anims.get("x_dashing")),
        "x_nova_frames": _crop_frames(x_anims.get("x_nova_strike")),
        "x_fully_charged_shot_frames": _crop_frames(x_anims.get("x_fully_charged_shot")),
        "x_exit_tail_frames": _normalize_frames_midbottom(_crop_frames(x_anims.get("x_exiting"))[-7:]),
        "zero_hurt_frames": _crop_frames(zero_anims.get("zero_hurt")),
        "cutscene_copter_frames": cutscene_copter_frames,
        "intro_opening_bg": intro_opening_bg,
        "intro_opening_bg_width": intro_opening_bg.get_width(),
        "intro_opening_bg_front": intro_opening_bg_front,
        "intro_opening_clouds_back": intro_opening_clouds_back,
        "intro_opening_clouds_front": intro_opening_clouds_front,
        "intro_opening_airbase_clouds": intro_opening_airbase_clouds,
    }


def _load_cache_from_path(path, cache_key):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            payload = pickle.load(f)
    except Exception:
        return None
    if tuple(payload.get("cache_key", ())) != tuple(cache_key):
        return None
    serialized_assets = payload.get("assets")
    if not isinstance(serialized_assets, dict):
        return None
    return {key: _deserialize_value(value) for key, value in serialized_assets.items()}


def _write_cache_to_path(path, cache_key, assets):
    ensure_dir(os.path.dirname(path))
    payload = {
        "cache_key": tuple(cache_key),
        "assets": {key: _serialize_value(value) for key, value in assets.items()},
    }
    with open(path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)


def load_intro_opening_assets(assets_root=None):
    global _intro_opening_assets_cache
    if _intro_opening_assets_cache is not None:
        return _intro_opening_assets_cache
    if assets_root is None:
        assets_root = assets_dir()

    cache_key = intro_opening_cache_key(assets_root)
    runtime_path = _runtime_cache_path()
    packaged_path = _packaged_cache_path()
    seed_runtime_file(runtime_path, packaged_path)

    cached = _load_cache_from_path(runtime_path, cache_key)
    if cached is not None:
        _intro_opening_assets_cache = cached
        return cached

    packaged_cached = _load_cache_from_path(packaged_path, cache_key)
    if packaged_cached is not None:
        try:
            ensure_dir(os.path.dirname(runtime_path))
            shutil.copy2(packaged_path, runtime_path)
        except Exception:
            pass
        _intro_opening_assets_cache = packaged_cached
        return packaged_cached

    assets = build_intro_opening_assets(assets_root)
    try:
        _write_cache_to_path(runtime_path, cache_key, assets)
    except Exception:
        pass
    _intro_opening_assets_cache = assets
    return assets


def build_intro_opening_cache_file(destination_path, assets_root=None):
    started_pygame, started_display = _ensure_pygame_ready()
    try:
        assets = build_intro_opening_assets(assets_root)
        _write_cache_to_path(destination_path, intro_opening_cache_key(assets_root), assets)
    finally:
        _cleanup_pygame(started_pygame, started_display)
    return destination_path
