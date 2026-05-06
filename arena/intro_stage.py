import math
import os
import pickle
import builtins
import hashlib
import shutil

import pygame
from collections import deque

from .runtime_paths import (
    assets_dir,
    ensure_dir,
    intro_stage_runtime_dir,
    packaged_intro_stage_cache_dir,
    seed_runtime_file,
)


# all intro-stage parsing and cache generation lives here
INTRO_STAGE_TILE_SIZE = 32
INTRO_STAGE_SPAWN_X = 160
INTRO_STAGE_SPAWN_Y = 1166
INTRO_STAGE_BUCKET = 64

FLOOR_COLOR = (207, 19, 19, 255)
WALL_COLOR = (19, 207, 21, 255)
CEILING_COLOR = (43, 19, 207, 255)
FOREGROUND_COLOR = (207, 19, 195, 255)
BACKGROUND_ZONE_COLOR = (19, 207, 197, 255)
NO_CLIMB_WALL_COLOR = (248, 80, 32, 255)
COLLISION_REMOVE_COLOR = (126, 17, 186, 255)
BACKGROUND_ZONE_SCROLL_FACTORS = (
    (0.18, 0.04),
    (0.24, 0.05),
    (0.30, 0.06),
    (0.10, 0.20),
    (0.22, 0.04),
)
BACKGROUND_ZONE_RENDER_SETTINGS = (
    {"anchor": "bottom", "scroll_x": 0.18, "scroll_y": 0.0, "y_offset": 55, "repeat_y": False, "lock_to_clip_y": True},
    {"anchor": "bottom", "scroll_x": 0.24, "scroll_y": 0.0, "y_offset": 40, "repeat_y": False, "lock_to_clip_y": True},
    {"anchor": "bottom", "scroll_x": 0.30, "scroll_y": 0.0, "y_offset": 40, "repeat_y": False, "lock_to_clip_y": True},
    {"anchor": "top", "scroll_x": 0.10, "scroll_y": 0.20, "y_offset": 0, "repeat_y": True, "lock_to_clip_y": False},
    {"anchor": "bottom", "scroll_x": 0.22, "scroll_y": 0.0, "y_offset": 25, "repeat_y": False, "lock_to_clip_y": True},
)
BACKGROUND_ZONE_CAMERA_SETTINGS = (
    {"mode": "lock_y", "y_bias": 0},
    {"mode": "lock_y", "y_bias": 0},
    {"mode": "lock_y", "y_bias": 0},
    {"mode": "lock_x", "x_bias": 0},
    {"mode": "lock_y", "y_bias": 0},
)
MIN_BACKGROUND_ZONE_AREA = 10000
INTRO_STAGE_CACHE_VERSION = 29


# file path helpers so every cache/read path stays consistent
def _stage_root():
    return os.path.join(assets_dir(), "stages", "intro_stage")


def _runtime_cache_path():
    return os.path.join(intro_stage_runtime_dir(), f"intro_stage_cache_v{INTRO_STAGE_CACHE_VERSION}.pkl")


def _runtime_surface_path():
    return os.path.join(intro_stage_runtime_dir(), f"intro_stage_surface_v{INTRO_STAGE_CACHE_VERSION}.png")


def _runtime_annotation_path():
    return os.path.join(intro_stage_runtime_dir(), f"intro_stage_annotation_v{INTRO_STAGE_CACHE_VERSION}.png")


def _packaged_runtime_cache_path():
    return os.path.join(packaged_intro_stage_cache_dir(), f"intro_stage_cache_v{INTRO_STAGE_CACHE_VERSION}.pkl")


def _packaged_runtime_surface_path():
    return os.path.join(packaged_intro_stage_cache_dir(), f"intro_stage_surface_v{INTRO_STAGE_CACHE_VERSION}.png")


def _packaged_runtime_annotation_path():
    return os.path.join(packaged_intro_stage_cache_dir(), f"intro_stage_annotation_v{INTRO_STAGE_CACHE_VERSION}.png")


def _art_path():
    return os.path.join(_stage_root(), "intro_stage_full_tileset.png")


def _collision_path():
    newest = os.path.join(_stage_root(), "intro_stage_tileset_newest_annotations.png")
    if os.path.exists(newest):
        return newest
    return os.path.join(_stage_root(), "intro_stage_tileset_annotations.png")


def _modified_collision_path():
    path = os.path.join(_stage_root(), "intro_stage_some_modified_annotations.png")
    if os.path.exists(path):
        return path
    return None


def _background_paths():
    base = os.path.join(_stage_root(), "backgrounds")
    return [
        os.path.join(base, f"introbackground{i}.png")
        for i in range(1, 6)
    ]


def _file_signature(label, path):
    if not os.path.exists(path):
        return (label, None, None)
    digest = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                if not chunk:
                    break
                digest.update(chunk)
        return (label, os.path.getsize(path), digest.hexdigest())
    except OSError:
        return (label, None, None)


def _asset_cache_key():
    # changing any source art or annotation file should force a fresh rebuild
    paths = [_art_path(), _collision_path()]
    modified = _modified_collision_path()
    if modified is not None:
        paths.append(modified)
    key = [
        _file_signature("art", _art_path()),
        _file_signature("collision", _collision_path()),
    ]
    if modified is not None:
        key.append(_file_signature("modified", modified))
    for index, path in enumerate(_background_paths(), start=1):
        key.append(_file_signature(f"background{index}", path))
    return tuple(key)


def _rect_to_tuple(rect):
    if rect is None:
        return None
    return (rect.x, rect.y, rect.w, rect.h)


def _rect_from_tuple(data):
    if data is None:
        return None
    return pygame.Rect(data[0], data[1], data[2], data[3])


def _color_rgba(color):
    if isinstance(color, tuple):
        return color
    return (color.r, color.g, color.b, color.a)


def _alpha_value(color):
    if isinstance(color, tuple):
        return color[3] if len(color) > 3 else 255
    return color.a


def _leftmost_visible_column(surface, threshold=8):
    width, height = surface.get_size()
    for x in range(width):
        for y in range(height):
            r, g, b, a = surface.get_at((x, y))
            if a > 0 and (r > threshold or g > threshold or b > threshold):
                return x
    return 0


def _serialize_background_layers(layers):
    # background layer metadata gets cached separately from the actual surfaces
    serialized = []
    for idx, layer in enumerate(layers):
        serialized.append({
            "rect": _rect_to_tuple(layer.get("rect")),
            "bg_index": idx,
            "anchor": layer.get("anchor"),
            "scroll_x": layer.get("scroll_x", 0.0),
            "scroll_y": layer.get("scroll_y", 0.0),
            "x_offset": layer.get("x_offset", 0),
            "y_offset": layer.get("y_offset", 0),
            "repeat_y": layer.get("repeat_y", False),
            "lock_to_clip_y": layer.get("lock_to_clip_y", False),
            "extend_up_copies": layer.get("extend_up_copies", 0),
            "extend_up_sky_only": layer.get("extend_up_sky_only", False),
        })
    return serialized


def _deserialize_background_layers(data):
    layers = []
    bg_paths = _background_paths()
    for item in data:
        bg_index = item.get("bg_index")
        if bg_index is None or not (0 <= bg_index < len(bg_paths)):
            continue
        path = bg_paths[bg_index]
        if not os.path.exists(path):
            continue
        image = pygame.image.load(path).convert_alpha()
        layers.append({
            "rect": _rect_from_tuple(item.get("rect")),
            "image": image,
            "anchor": item.get("anchor", "bottom"),
            "scroll_x": item.get("scroll_x", 0.0),
            "scroll_y": item.get("scroll_y", 0.0),
            "x_offset": item.get("x_offset", 0),
            "y_offset": item.get("y_offset", 0),
            "repeat_y": item.get("repeat_y", False),
            "lock_to_clip_y": item.get("lock_to_clip_y", False),
            "extend_up_copies": item.get("extend_up_copies", 0),
            "extend_up_sky_only": item.get("extend_up_sky_only", False),
        })
    return layers


def _serialize_camera_zones(zones):
    return [
        {
            "rect": _rect_to_tuple(zone.get("rect")),
            "mode": zone.get("mode"),
            "x_bias": zone.get("x_bias", 0),
            "y_bias": zone.get("y_bias", 0),
        }
        for zone in zones
    ]


def _deserialize_camera_zones(data):
    return [
        {
            "rect": _rect_from_tuple(zone.get("rect")),
            "mode": zone.get("mode"),
            "x_bias": zone.get("x_bias", 0),
            "y_bias": zone.get("y_bias", 0),
        }
        for zone in data
        if zone.get("rect") is not None
    ]


def _serialize_foreground_layers(layers):
    return [{"rect": _rect_to_tuple(rect)} for rect, _layer in layers]


def _deserialize_foreground_layers(data, art_surface):
    layers = []
    for item in data:
        rect = _rect_from_tuple(item.get("rect"))
        if rect is None or rect.width <= 0 or rect.height <= 0:
            continue
        layer = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        layer.blit(art_surface, (0, 0), rect)
        layers.append((rect, layer))
    return layers


def _read_runtime_cache(cache_path, surface_path, annotation_path, cache_key):
    # load the fully processed stage if both the metadata and baked surfaces still match
    if not os.path.exists(cache_path):
        return None
    if not os.path.exists(surface_path) or not os.path.exists(annotation_path):
        return None
    try:
        with open(cache_path, "rb") as f:
            payload = pickle.load(f)
    except Exception:
        return None

    if payload.get("version") != INTRO_STAGE_CACHE_VERSION:
        return None
    if payload.get("asset_cache_key") != cache_key:
        return None

    try:
        art_surface = pygame.image.load(surface_path).convert_alpha()
        annotation_surface = pygame.image.load(annotation_path).convert_alpha()
    except Exception:
        return None

    rects = [_rect_from_tuple(item) for item in payload.get("rects", ())]
    no_climb_wall_rects = [_rect_from_tuple(item) for item in payload.get("no_climb_wall_rects", ())]
    return {
        "surface": art_surface,
        "annotation": annotation_surface,
        "rects": [rect for rect in rects if rect is not None],
        "background_layers": _deserialize_background_layers(payload.get("background_layers", ())),
        "camera_zones": _deserialize_camera_zones(payload.get("camera_zones", ())),
        "foreground_layers": _deserialize_foreground_layers(payload.get("foreground_layers", ()), art_surface),
        "no_climb_wall_rects": [rect for rect in no_climb_wall_rects if rect is not None],
        "right_stop_x": payload.get("right_stop_x"),
        "end_balcony_stop_x": payload.get("end_balcony_stop_x"),
        "big_shaft_top_floor": _rect_from_tuple(payload.get("big_shaft_top_floor")),
        "secret_roof_floor": _rect_from_tuple(payload.get("secret_roof_floor")),
        "secret_roof_wall": _rect_from_tuple(payload.get("secret_roof_wall")),
        "second_shaft_top_floor": _rect_from_tuple(payload.get("second_shaft_top_floor")),
    }


def _copy_packaged_runtime_cache(force=False):
    mappings = (
        (_runtime_cache_path(), _packaged_runtime_cache_path()),
        (_runtime_surface_path(), _packaged_runtime_surface_path()),
        (_runtime_annotation_path(), _packaged_runtime_annotation_path()),
    )
    copied = False
    ensure_dir(os.path.dirname(_runtime_cache_path()))
    for runtime_path, packaged_path in mappings:
        if not os.path.exists(packaged_path):
            continue
        if force or not os.path.exists(runtime_path):
            try:
                shutil.copy2(packaged_path, runtime_path)
                copied = True
            except Exception:
                pass
    return copied


def _load_runtime_cache(cache_key):
    cache_path = _runtime_cache_path()
    surface_path = _runtime_surface_path()
    annotation_path = _runtime_annotation_path()
    _copy_packaged_runtime_cache(force=False)
    cached = _read_runtime_cache(cache_path, surface_path, annotation_path, cache_key)
    if cached is not None:
        return cached

    packaged_cached = _read_runtime_cache(
        _packaged_runtime_cache_path(),
        _packaged_runtime_surface_path(),
        _packaged_runtime_annotation_path(),
        cache_key,
    )
    if packaged_cached is not None:
        _copy_packaged_runtime_cache(force=True)
        return packaged_cached
    return None


def _write_runtime_cache(cache_key, data):
    # save the heavy processed results so next boot can skip the expensive image analysis
    payload = {
        "version": INTRO_STAGE_CACHE_VERSION,
        "asset_cache_key": cache_key,
        "rects": [_rect_to_tuple(rect) for rect in data.get("rects", ())],
        "background_layers": _serialize_background_layers(data.get("background_layers", ())),
        "camera_zones": _serialize_camera_zones(data.get("camera_zones", ())),
        "foreground_layers": _serialize_foreground_layers(data.get("foreground_layers", ())),
        "no_climb_wall_rects": [_rect_to_tuple(rect) for rect in data.get("no_climb_wall_rects", ())],
        "right_stop_x": data.get("right_stop_x"),
        "end_balcony_stop_x": data.get("end_balcony_stop_x"),
        "big_shaft_top_floor": _rect_to_tuple(data.get("big_shaft_top_floor")),
        "secret_roof_floor": _rect_to_tuple(data.get("secret_roof_floor")),
        "secret_roof_wall": _rect_to_tuple(data.get("secret_roof_wall")),
        "second_shaft_top_floor": _rect_to_tuple(data.get("second_shaft_top_floor")),
    }
    path = _runtime_cache_path()
    try:
        ensure_dir(os.path.dirname(path))
        pygame.image.save(data["surface"], _runtime_surface_path())
        pygame.image.save(data["annotation"], _runtime_annotation_path())
        with open(path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def _is_annotation_patch_pixel(rgba):
    return rgba in {
        FLOOR_COLOR,
        WALL_COLOR,
        CEILING_COLOR,
        FOREGROUND_COLOR,
        BACKGROUND_ZONE_COLOR,
        NO_CLIMB_WALL_COLOR,
        COLLISION_REMOVE_COLOR,
        (255, 255, 255, 255),
    }


def _surface_rgba_reader(surface):
    width, height = surface.get_size()
    width = int(width)
    height = int(height)
    raw = pygame.image.tobytes(surface, "RGBA")
    row_stride = width * 4

    def read(x, y):
        idx = (y * row_stride) + (x * 4)
        return (raw[idx], raw[idx + 1], raw[idx + 2], raw[idx + 3])

    return width, height, read


def _patch_regions_from_modified(modified_surface):
    # modified annotation art only marks local overrides, so collapse it into patch rectangles
    width, height, read = _surface_rgba_reader(modified_surface)
    seen = bytearray(width * height)
    regions = []
    for y in range(height):
        for x in range(width):
            idx = (y * width) + x
            if seen[idx]:
                continue
            rgba = read(x, y)
            if not _is_annotation_patch_pixel(rgba):
                continue
            q = deque([(x, y)])
            seen[idx] = 1
            points = []
            while q:
                cx, cy = q.popleft()
                points.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        nidx = (ny * width) + nx
                        if seen[nidx]:
                            continue
                        n_rgba = read(nx, ny)
                        if _is_annotation_patch_pixel(n_rgba):
                            seen[nidx] = 1
                            q.append((nx, ny))
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            regions.append(pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
    return regions


def _load_collision_source():
    base = pygame.image.load(_collision_path()).convert_alpha()
    modified_path = _modified_collision_path()
    if modified_path is None:
        return base

    modified = pygame.image.load(modified_path).convert_alpha()
    if modified.get_size() != base.get_size():
        return base

    merged = base.copy()
    patch_regions = _patch_regions_from_modified(modified)
    for region in patch_regions:
        patch = region.inflate(18, 18).clip(base.get_rect())
        for y in range(patch.top, patch.bottom):
            for x in range(patch.left, patch.right):
                mod = modified.get_at((x, y))
                mod_rgba = _color_rgba(mod)
                base_px = base.get_at((x, y))
                base_rgba = _color_rgba(base_px)
                if _is_annotation_patch_pixel(mod_rgba):
                    merged.set_at((x, y), mod)
                elif _is_annotation_patch_pixel(base_rgba):
                    merged.set_at((x, y), mod)
    return merged


def _apply_modified_annotation_overrides(art_source, annotation_surface):
    modified_path = _modified_collision_path()
    if modified_path is None:
        return annotation_surface

    modified_source = pygame.image.load(modified_path).convert_alpha()
    _, modified_annotation = _crop_to_art(art_source, modified_source)
    if modified_annotation.get_size() != annotation_surface.get_size():
        return annotation_surface

    merged = annotation_surface.copy()

    collision_like_colors = {
        FLOOR_COLOR,
        WALL_COLOR,
        CEILING_COLOR,
        NO_CLIMB_WALL_COLOR,
        COLLISION_REMOVE_COLOR,
    }

    # In the entrance/front-wall area the modified file should be treated as
    # authoritative for collision guides, but it should not erase unrelated
    # foreground/background helper layers like the taller pink pillar mask.
    for rect in (
        pygame.Rect(400, 930, 340, 170),
    ):
        clipped = rect.clip(merged.get_rect())
        for y in range(clipped.top, clipped.bottom):
            for x in range(clipped.left, clipped.right):
                base_px = merged.get_at((x, y))
                base_rgba = _color_rgba(base_px)
                if base_rgba in collision_like_colors:
                    merged.set_at((x, y), (0, 0, 0, 0))

                mod_px = modified_annotation.get_at((x, y))
                mod_rgba = _color_rgba(mod_px)
                if mod_rgba in collision_like_colors:
                    merged.set_at((x, y), mod_px)

    return merged


def _crop_to_art(surface, collision_surface):
    crop_rect = surface.get_bounding_rect()
    if crop_rect.width <= 0 or crop_rect.height <= 0:
        crop_rect = surface.get_rect()

    art = pygame.Surface((crop_rect.width, crop_rect.height), pygame.SRCALPHA)
    art.blit(surface, (0, 0), crop_rect)

    collision = pygame.Surface((crop_rect.width, crop_rect.height), pygame.SRCALPHA)
    collision.blit(collision_surface, (0, 0), crop_rect)
    return art, collision


def _build_collision_rects(annotation_surface):
    # merge runs of annotation pixels into chunky rects the game can collide against cheaply
    width, height, read = _surface_rgba_reader(annotation_surface)
    rects = []

    # Floors are interpreted as standable top surfaces, even if the guide was
    # painted thick. This avoids converting filled red regions into chunky
    # invisible blocks.
    for comp in _connected_components(annotation_surface, FLOOR_COLOR, reader=read):
        # Ignore the long red helper strip in the second shaft that was being
        # turned into a bogus standable perch before the final balcony.
        if comp.w >= 160 and 4080 <= comp.x <= 4200 and 620 <= comp.y <= 660:
            continue
        top_by_x = {}
        for y in range(comp.top, comp.bottom):
            for x in range(comp.left, comp.right):
                if read(x, y) != FLOOR_COLOR:
                    continue
                prev = top_by_x.get(x)
                if prev is None or y < prev:
                    top_by_x[x] = y
        for x, y in top_by_x.items():
            rects.append(pygame.Rect(x, y, 1, 2))

    # Walls are interpreted as side surfaces only, not full solid columns, so
    # vertical guides don't accidentally create tiny standable ledges.
    for target in (WALL_COLOR, NO_CLIMB_WALL_COLOR):
        for comp in _connected_components(annotation_surface, target, reader=read):
            # The added climbable wall on the front side of the entrance
            # building should only collide on its inside/right face. Keeping
            # both faces creates the tiny hidden blocker near the ceiling.
            only_right_face = (
                target == WALL_COLOR and
                comp.w <= 6 and
                comp.h >= 300 and
                comp.x <= 500
            )
            # Trim a short tail off the very bottom of generated wall faces.
            # Those last few single-pixel face segments are what create the
            # tiny one-way invisible "hooks" at the lower corners of walls and
            # platform undersides in intro stage.
            face_bottom = max(comp.top + 1, comp.bottom - 8)
            for y in range(comp.top + 1, face_bottom):
                xs = []
                for x in range(comp.left, comp.right):
                    if read(x, y) == target:
                        xs.append(x)
                if not xs:
                    continue
                left_x = min(xs)
                right_x = max(xs)
                if not only_right_face:
                    rects.append(pygame.Rect(left_x, y, 2, 1))
                if right_x != left_x or only_right_face:
                    rects.append(pygame.Rect(max(left_x, right_x - 1), y, 2, 1))

    for y in range(height):
        for x in range(width):
            rgba = read(x, y)
            if rgba == CEILING_COLOR:
                ceiling_raise = 16 if (x <= 600 or x >= 4300) else 12
                rects.append(pygame.Rect(x, y - ceiling_raise, 1, 2))

    # Missing authored ceiling/pocket seal before the second shaft.
    # In cropped stage space the local opening is x=4128..4159, and the visible
    # underside of the surrounding structure sits much higher than the tiny blue
    # guide strip. Seal the full hidden pocket so the collision matches the art.
    rects.append(pygame.Rect(4128, 430, 32, 80))

    # The newest annotation includes a very tall orange unclimbable wall on the
    # extreme left edge, but that guide sits outside the cropped art bounds.
    # Add its blocking face explicitly so Zero cannot fall off the map there.
    for y in range(353, min(height, 1490)):
        rects.append(pygame.Rect(0, y, 2, 1))

    # Small purple rectangles in the newest annotation are explicit "remove
    # bad collision here" markers.
    for marker in _connected_components(annotation_surface, COLLISION_REMOVE_COLOR, reader=read):
        if marker.w < 3 or marker.h < 3:
            continue

        # Stray standable lip in the second shaft. Replace it with a clean
        # vertical wall face so the player cannot perch there or walk through.
        if 4140 <= marker.x <= 4170 and 410 <= marker.y <= 430:
            kill = marker.inflate(6, 26)
            rects = [rect for rect in rects if not rect.colliderect(kill)]
            wall_x = marker.left + 1
            wall_top = marker.top - 18
            wall_bottom = marker.bottom + 24
            for y in range(wall_top, wall_bottom):
                rects.append(pygame.Rect(wall_x, y, 2, 1))
            continue

    # Stray standable lip in the second shaft. Replace the fragmented local
    # wall with one continuous tall rect so it stays a wall only.
    rects = [
        rect for rect in rects
        if not (
            rect.w == 1 and rect.h == 2 and 4128 <= rect.x <= 4156 and 506 <= rect.y <= 508
        )
    ]

    return rects


def _connected_components(annotation_surface, target_color, reader=None):
    width, height = annotation_surface.get_size()
    width = int(width)
    height = int(height)
    if reader is None:
        _, _, reader = _surface_rgba_reader(annotation_surface)
    seen = bytearray(width * height)
    components = []
    for y in builtins.range(height):
        for x in builtins.range(width):
            idx = (y * width) + x
            if seen[idx]:
                continue
            rgba = reader(x, y)
            if rgba != target_color:
                continue
            q = deque([(x, y)])
            seen[idx] = 1
            points = []
            while q:
                cx, cy = q.popleft()
                points.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        nidx = (ny * width) + nx
                        if seen[nidx]:
                            continue
                        if reader(nx, ny) == target_color:
                            seen[nidx] = 1
                            q.append((nx, ny))
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            components.append(pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
    return components


def _is_foreground_pink(color):
    return _color_rgba(color) == FOREGROUND_COLOR


def _build_foreground_layers(art_surface, annotation_surface):
    # foreground pink marks art that should draw over the player instead of behind them
    points = []
    width, height, ann_read = _surface_rgba_reader(annotation_surface)
    for y in range(height):
        for x in range(width):
            if ann_read(x, y) == FOREGROUND_COLOR:
                points.append((x, y))

    if points:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        rect = pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
        # Extend the entrance front pillar upward using the actual opaque art
        # above the pink guide so Zero can disappear behind the whole visible
        # pillar, not just the lower marked section.
        if 480 <= rect.left <= 560 and rect.width <= 80:
            _, _, art_read = _surface_rgba_reader(art_surface)
            top = rect.top
            for y in range(rect.top - 1, -1, -1):
                found = False
                for x in range(rect.left, rect.right):
                    if art_read(x, y)[3] > 0:
                        top = y
                        found = True
                        break
                if not found:
                    break
            rect = pygame.Rect(rect.left, top, rect.width, rect.bottom - top)
        if rect.width > 0 and rect.height > 0:
            layer = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            layer.blit(art_surface, (0, 0), rect)
            return [(rect, layer)]
    return []


def _find_right_stop_x(annotation_surface):
    width, _ = annotation_surface.get_size()
    best_x = None
    best_height = 0

    for rect in _connected_components(annotation_surface, BACKGROUND_ZONE_COLOR):
        if rect.w <= 6 and rect.h >= 180 and rect.x >= int(width * 0.75):
            if rect.h > best_height or (rect.h == best_height and (best_x is None or rect.x > best_x)):
                best_height = rect.h
                best_x = rect.centerx

    return best_x


def _find_end_balcony_stop_x(annotation_surface):
    width, _ = annotation_surface.get_size()
    best_x = None
    best_height = -1

    for rect in _connected_components(annotation_surface, WALL_COLOR):
        if rect.x >= width - 60 and rect.h >= 80:
            if rect.h > best_height or (rect.h == best_height and (best_x is None or rect.x > best_x)):
                best_height = rect.h
                best_x = rect.centerx

    return best_x


def _find_second_shaft_top_floor(annotation_surface):
    width, _ = annotation_surface.get_size()
    best = None
    best_x = -1

    for rect in _connected_components(annotation_surface, FLOOR_COLOR):
        if rect.w >= 120 and rect.h <= 6 and rect.x >= int(width * 0.82):
            if rect.x > best_x:
                best_x = rect.x
                best = rect

    return best


def _find_big_shaft_top_floor(annotation_surface):
    best = None
    best_score = None

    for rect in _connected_components(annotation_surface, FLOOR_COLOR):
        if 120 <= rect.w <= 260 and rect.h <= 6 and 3450 <= rect.x <= 3800 and 520 <= rect.y <= 700:
            # Prefer the short ledge right at the top of the big shaft,
            # not the long hallway floor farther to the right.
            score = (rect.x, -rect.y)
            if best_score is None or score > best_score:
                best_score = score
                best = rect

    return best


def _find_big_shaft_right_wall(annotation_surface, top_floor):
    if top_floor is None:
        return None
    best = None
    best_x = None

    for rect in _connected_components(annotation_surface, WALL_COLOR):
        if rect.h < 200:
            continue
        if rect.left < top_floor.right:
            continue
        if rect.left > top_floor.right + 220:
            continue
        if rect.bottom < top_floor.top - 8:
            continue
        if best_x is None or rect.left < best_x:
            best_x = rect.left
            best = rect

    return best


def _find_secret_roof_floor(annotation_surface):
    best = None
    best_score = None

    for rect in _connected_components(annotation_surface, FLOOR_COLOR):
        if rect.w >= 240 and rect.h <= 24 and 430 <= rect.x <= 1100 and 430 <= rect.y <= 560:
            score = (rect.w, -rect.y)
            if best_score is None or score > best_score:
                best_score = score
                best = rect

    return best


def _find_secret_roof_floor_from_rects(collision_rects):
    by_y = {}
    for rect in collision_rects:
        if rect.w == 1 and rect.h == 2 and rect.x < 1400 and rect.y < 700:
            by_y.setdefault(rect.y, []).append(rect.x)

    best = None
    best_width = -1
    for y, xs in by_y.items():
        xs = sorted(set(xs))
        run_start = xs[0]
        prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            width = prev - run_start + 1
            if width >= 240 and run_start <= 700 and 430 <= y <= 560:
                if width > best_width:
                    best_width = width
                    best = pygame.Rect(run_start, y, width, 2)
            if x is not None:
                run_start = x
                prev = x

    return best


def _build_background_layers(annotation_surface):
    # background zones carve the stage into parallax regions with different camera behavior
    zone_rects = _connected_components(annotation_surface, BACKGROUND_ZONE_COLOR)
    zone_rects = [r for r in zone_rects if (r.w * r.h) >= MIN_BACKGROUND_ZONE_AREA]
    zone_rects.sort(key=lambda r: (r.x, r.y))
    if zone_rects:
        # Let the first background keep filling the transparent entrance area
        # to the left of its marked windows.
        first = zone_rects[0].copy()
        first.width += first.x
        first.x = 0
        first.height += first.y
        first.y = 0
        zone_rects[0] = first
        # Let the final background continue through the balcony area to the
        # right, instead of stopping at the shaft window annotation.
        last = zone_rects[-1].copy()
        extend_left = min(160, last.x)
        last.x -= extend_left
        last.width = annotation_surface.get_width() - last.x
        last.height += last.y
        last.y = 0
        zone_rects[-1] = last
    bg_paths = _background_paths()
    layers = []
    for idx, rect in enumerate(zone_rects[:len(bg_paths)]):
        path = bg_paths[idx]
        if not os.path.exists(path):
            continue
        image = pygame.image.load(path).convert_alpha()
        settings = BACKGROUND_ZONE_RENDER_SETTINGS[min(idx, len(BACKGROUND_ZONE_RENDER_SETTINGS) - 1)]
        is_last_layer = idx == (min(len(zone_rects), len(bg_paths)) - 1)
        layers.append({
            "rect": rect,
            "image": image,
            "anchor": settings["anchor"],
            "scroll_x": settings["scroll_x"],
            "scroll_y": settings["scroll_y"],
            "x_offset": -96 if is_last_layer else 0,
            "y_offset": settings["y_offset"],
            "repeat_y": settings["repeat_y"],
            "lock_to_clip_y": settings.get("lock_to_clip_y", False),
            "extend_up_copies": 4 if idx == 0 else 0,
            "extend_up_sky_only": idx == 0,
        })
    return layers


def _build_no_climb_wall_rects(annotation_surface):
    rects = []
    for rect in _connected_components(annotation_surface, NO_CLIMB_WALL_COLOR):
        if rect.w >= 2 and rect.h >= 8:
            rects.append(rect.inflate(6, 8))
    rects.append(pygame.Rect(0, 0, 24, annotation_surface.get_height()))
    return rects


def _build_camera_zones(annotation_surface):
    # camera zones are inferred from the same annotations so layout and camera stay linked
    zone_rects = _connected_components(annotation_surface, BACKGROUND_ZONE_COLOR)
    zone_rects = [r for r in zone_rects if (r.w * r.h) >= MIN_BACKGROUND_ZONE_AREA]
    zone_rects.sort(key=lambda r: (r.x, r.y))
    zones = []
    for idx, rect in enumerate(zone_rects):
        settings = BACKGROUND_ZONE_CAMERA_SETTINGS[min(idx, len(BACKGROUND_ZONE_CAMERA_SETTINGS) - 1)]
        zones.append({
            "rect": rect,
            "mode": settings["mode"],
            "x_bias": settings.get("x_bias", 0),
            "y_bias": settings.get("y_bias", 0),
        })
    return zones


def _bucketize(rects):
    buckets = {}
    for rect in rects:
        bx0 = rect.left // INTRO_STAGE_BUCKET
        bx1 = max(rect.left, rect.right - 1) // INTRO_STAGE_BUCKET
        by0 = rect.top // INTRO_STAGE_BUCKET
        by1 = max(rect.top, rect.bottom - 1) // INTRO_STAGE_BUCKET
        for by in range(by0, by1 + 1):
            for bx in range(bx0, bx1 + 1):
                buckets.setdefault((bx, by), []).append(rect)
    return buckets


def _load_intro_stage_data():
    # main loader: prefer a valid cache, otherwise rebuild from the source artwork and annotations
    cache_key = _asset_cache_key()
    cached = _load_runtime_cache(cache_key)
    if cached is not None:
        return {
            "surface": cached["surface"],
            "annotation": cached["annotation"],
            "rects": cached["rects"],
            "buckets": _bucketize(cached["rects"]),
            "background_layers": cached["background_layers"],
            "camera_zones": cached["camera_zones"],
            "foreground_layers": cached["foreground_layers"],
            "no_climb_wall_rects": cached["no_climb_wall_rects"],
            "right_stop_x": cached["right_stop_x"],
            "end_balcony_stop_x": cached["end_balcony_stop_x"],
            "big_shaft_top_floor": cached["big_shaft_top_floor"],
            "secret_roof_floor": cached["secret_roof_floor"],
            "secret_roof_wall": cached["secret_roof_wall"],
            "second_shaft_top_floor": cached["second_shaft_top_floor"],
            "camera_bounds": pygame.Rect(0, 0, cached["surface"].get_width(), cached["surface"].get_height()),
        }

    art_source = pygame.image.load(_art_path()).convert_alpha()
    collision_source = _load_collision_source()
    art_surface, annotation_surface = _crop_to_art(art_source, collision_source)
    annotation_surface = _apply_modified_annotation_overrides(art_source, annotation_surface)

    collision_rects = _build_collision_rects(annotation_surface)
    no_climb_wall_rects = _build_no_climb_wall_rects(annotation_surface)
    no_climb_components = _connected_components(annotation_surface, NO_CLIMB_WALL_COLOR)
    right_stop_x = _find_right_stop_x(annotation_surface)
    end_balcony_stop_x = _find_end_balcony_stop_x(annotation_surface)
    big_shaft_top_floor = _find_big_shaft_top_floor(annotation_surface)
    big_shaft_right_wall = _find_big_shaft_right_wall(annotation_surface, big_shaft_top_floor)
    secret_roof_floor = (
        _find_secret_roof_floor(annotation_surface)
        or _find_secret_roof_floor_from_rects(collision_rects)
    )
    second_shaft_top_floor = _find_second_shaft_top_floor(annotation_surface)

    left_edge_wall = pygame.Rect(0, 0, 24, annotation_surface.get_height())
    collision_rects.append(left_edge_wall.copy())
    no_climb_wall_rects.append(left_edge_wall.copy())

    secret_roof_wall = None
    for rect in no_climb_components:
        if 980 <= rect.x <= 1060 and 240 <= rect.y <= 520:
            if secret_roof_wall is None or rect.h > secret_roof_wall.h:
                secret_roof_wall = rect
    if secret_roof_wall is not None and secret_roof_floor is not None:
        wall_x = secret_roof_wall.centerx
        wall_top = secret_roof_wall.top
        wall_bottom = max(secret_roof_wall.bottom, secret_roof_floor.bottom + 12)
        roof_start = secret_roof_floor.right
        roof_end = max(roof_start, wall_x)
        for x in range(roof_start, roof_end):
            collision_rects.append(pygame.Rect(x, secret_roof_floor.y, 1, 2))
        ceiling_start = min(secret_roof_floor.left, 451)
        ceiling_end = max(ceiling_start, wall_x)
        for x in range(ceiling_start, ceiling_end):
            collision_rects.append(pygame.Rect(x, wall_top, 1, 2))
        collision_rects.append(pygame.Rect(wall_x, 0, 2, wall_bottom))
        no_climb_wall_rects.append(pygame.Rect(wall_x - 4, 0, 10, wall_bottom))

    end_balcony_wall = None
    for rect in no_climb_components:
        if rect.x >= annotation_surface.get_width() - 80 and rect.h >= 120:
            if end_balcony_wall is None or rect.h > end_balcony_wall.h or (
                rect.h == end_balcony_wall.h and rect.x > end_balcony_wall.x
            ):
                end_balcony_wall = rect
    if end_balcony_wall is not None:
        if end_balcony_stop_x is None:
            end_balcony_stop_x = end_balcony_wall.centerx
        wall_x = end_balcony_stop_x
        wall_top = end_balcony_wall.top
        wall_bottom = end_balcony_wall.bottom
        if second_shaft_top_floor is not None:
            wall_bottom = max(wall_bottom, second_shaft_top_floor.bottom + 28)
        for y in range(wall_top, wall_bottom):
            collision_rects.append(pygame.Rect(wall_x, y, 2, 1))
        no_climb_wall_rects.append(pygame.Rect(wall_x - 4, wall_top, 10, wall_bottom - wall_top))

    # The first tall shaft can leave a tiny top-lip gap on its right wall,
    # which lets Zero step outside the map on the ledge above the first spike.
    # Seal only the upper section of that wall so we fix the escape route
    # without touching the lower-corner hook behavior we already tuned.
    if big_shaft_right_wall is not None and big_shaft_top_floor is not None:
        seal_x = big_shaft_right_wall.left
        seal_top = 0
        seal_bottom = min(big_shaft_right_wall.bottom, big_shaft_top_floor.bottom + 24)
        if seal_bottom > seal_top:
            collision_rects.append(pygame.Rect(seal_x, seal_top, 2, seal_bottom - seal_top))

    # There is a short missing wall segment above the first vertical shaft
    # spike on the right-hand side. Seal just that gap directly instead of
    # broadening the generic wall-face generation again.
    collision_rects.append(pygame.Rect(1248, 978, 2, 124))

    data = {
        "surface": art_surface,
        "annotation": annotation_surface,
        "rects": collision_rects,
        "buckets": _bucketize(collision_rects),
        "background_layers": _build_background_layers(annotation_surface),
        "camera_zones": _build_camera_zones(annotation_surface),
        "foreground_layers": _build_foreground_layers(art_surface, annotation_surface),
        "no_climb_wall_rects": no_climb_wall_rects,
        "right_stop_x": right_stop_x,
        "end_balcony_stop_x": end_balcony_stop_x,
        "big_shaft_top_floor": big_shaft_top_floor,
        "secret_roof_floor": secret_roof_floor,
        "secret_roof_wall": secret_roof_wall,
        "second_shaft_top_floor": second_shaft_top_floor,
        "camera_bounds": pygame.Rect(0, 0, art_surface.get_width(), art_surface.get_height()),
    }
    _write_runtime_cache(cache_key, data)
    return data


def prewarm_intro_stage_cache():
    # safe helper for background startup work when we want the cache ready before gameplay
    cache_key = _asset_cache_key()
    if IntroStageMap._cache is None or IntroStageMap._cache_key != cache_key:
        IntroStageMap._cache = _load_intro_stage_data()
        IntroStageMap._cache_key = cache_key


class IntroStageMap:
    _cache = None
    _cache_key = None

    def __init__(self, game, tile_size=INTRO_STAGE_TILE_SIZE):
        # expose the processed stage data in a lightweight object the main game can use directly
        self.game = game
        self.tile_size = tile_size
        self.allow_step_up = True
        self.step_up_height = 4
        self.dash_step_up_height = 18
        self.ground_snap_height = 12
        self.ground_snap_dash_height = 22
        self.dash_render_y_nudge = 6
        cache_key = _asset_cache_key()
        if IntroStageMap._cache is None or IntroStageMap._cache_key != cache_key:
            IntroStageMap._cache = _load_intro_stage_data()
            IntroStageMap._cache_key = cache_key

        data = IntroStageMap._cache
        self.surface = data["surface"]
        self.annotation = data["annotation"]
        self.collision_rects = data["rects"]
        self._buckets = data["buckets"]
        self.camera_bounds = data["camera_bounds"].copy()

        self.start_x = 0
        self.start_y = 0
        self.width = int(math.ceil(self.surface.get_width() / self.tile_size))
        self.height = int(math.ceil(self.surface.get_height() / self.tile_size))
        self.tilemap = {}
        self.offgrid_tiles = []
        self.platform_spans = []
        self.background_layers = list(data.get("background_layers", ()))
        self.camera_zones = list(data.get("camera_zones", ()))
        self.foreground_surfaces = list(data.get("foreground_layers", ()))
        self.no_climb_wall_rects = [rect.copy() for rect in data.get("no_climb_wall_rects", ())]
        self.right_stop_x = data.get("right_stop_x")
        self.end_balcony_stop_x = data.get("end_balcony_stop_x")
        self.big_shaft_top_floor = data.get("big_shaft_top_floor")
        self.secret_roof_floor = data.get("secret_roof_floor")
        self.secret_roof_wall = data.get("secret_roof_wall")
        self.second_shaft_top_floor = data.get("second_shaft_top_floor")
        self._camera_mode = "z1"
        self._z4_entry_scroll_y = None
        self._z4_entry_scroll_x = None
        self._z5_entry_scroll_y = None
        self._z5_entry_scroll_x = None
        self._z5_upper_entry_player_x = None
        self._z4_upper_cap_y = None
        self._z4_upper_entry_scroll_x = None
        self._z4_upper_entry_player_x = None
        self._last_camera_scroll_y = None
        self._last_camera_scroll_x = None

    def reset_camera_state(self):
        self._camera_mode = "z1"
        self._z4_entry_scroll_y = None
        self._z4_entry_scroll_x = None
        self._z5_entry_scroll_y = None
        self._z5_entry_scroll_x = None
        self._z5_upper_entry_player_x = None
        self._z4_upper_cap_y = None
        self._z4_upper_entry_scroll_x = None
        self._z4_upper_entry_player_x = None
        self._last_camera_scroll_y = None
        self._last_camera_scroll_x = None

    def prime_camera_for_rect(self, player_rect, view_w, view_h, bounds, iterations=12):
        self.reset_camera_state()
        lock = None
        for _ in range(max(1, int(iterations))):
            lock = self.get_camera_lock(player_rect, view_w, view_h, bounds)
        return lock

    def prime_camera_for_intro_checkpoint(self, checkpoint_index, player_rect, view_w, view_h, bounds, iterations=12):
        self.reset_camera_state()
        if int(checkpoint_index) >= 1:
            self._camera_mode = "z4_top"
        lock = None
        for _ in range(max(1, int(iterations))):
            lock = self.get_camera_lock(player_rect, view_w, view_h, bounds)
        return lock

    def get_spawn_position(self, player_size):
        return (
            INTRO_STAGE_SPAWN_X - (player_size[0] // 2),
            INTRO_STAGE_SPAWN_Y - player_size[1],
        )

    def _dynamic_camera_wall_rects(self):
        rects = []
        wall_x = self.camera_bounds.left
        post_intro_min_x = getattr(self.game, "intro_post_camera_min_x", None)
        if post_intro_min_x is not None:
            wall_x = max(wall_x, int(round(post_intro_min_x)))
        rects.append(pygame.Rect(wall_x, self.camera_bounds.top, 2, self.camera_bounds.height))

        locked_left_x = getattr(self.game, "intro_locked_left_wall_x", None)
        if locked_left_x is not None:
            rects.append(
                pygame.Rect(
                    int(round(locked_left_x)),
                    self.camera_bounds.top,
                    2,
                    self.camera_bounds.height,
                )
            )

        locked_right_x = getattr(self.game, "intro_locked_right_wall_x", None)
        if locked_right_x is not None:
            rects.append(
                pygame.Rect(
                    int(round(locked_right_x)) - 2,
                    self.camera_bounds.top,
                    2,
                    self.camera_bounds.height,
                )
            )
        return rects

    def physics_rects_around(self, pos, size=(34, 43)):
        query = pygame.Rect(pos[0], pos[1], size[0], size[1]).inflate(96, 96)
        bx0 = query.left // INTRO_STAGE_BUCKET
        bx1 = max(query.left, query.right - 1) // INTRO_STAGE_BUCKET
        by0 = query.top // INTRO_STAGE_BUCKET
        by1 = max(query.top, query.bottom - 1) // INTRO_STAGE_BUCKET

        rects = []
        seen = set()
        for by in range(by0, by1 + 1):
            for bx in range(bx0, bx1 + 1):
                for rect in self._buckets.get((bx, by), ()):
                    key = (rect.x, rect.y, rect.w, rect.h)
                    if key in seen:
                        continue
                    seen.add(key)
                    rects.append(rect)
        for wall_rect in self._dynamic_camera_wall_rects():
            if query.colliderect(wall_rect.inflate(8, 0)):
                key = (wall_rect.x, wall_rect.y, wall_rect.w, wall_rect.h)
                if key not in seen:
                    rects.append(wall_rect)
        return rects

    def get_center_spawn_platform(self):
        return None

    def wall_cling_allowed(self, player_rect, dir_sign):
        dynamic_no_climb = self._dynamic_camera_wall_rects()
        if not self.no_climb_wall_rects and not dynamic_no_climb:
            return True
        probe = player_rect.move(2 if dir_sign > 0 else -2, 0).inflate(0, 8)
        return not any(probe.colliderect(rect) for rect in [*self.no_climb_wall_rects, *dynamic_no_climb])

    def get_shaft_zone(self):
        if len(self.camera_zones) >= 4:
            return self.camera_zones[3]["rect"].copy()
        return None

    def get_shaft_pit_trigger_y(self):
        shaft = self.get_shaft_zone()
        if shaft is None:
            return None
        return shaft.bottom - 8

    def get_camera_lock(self, player_rect, view_w, view_h, bounds):
        if not self.camera_zones or not bounds:
            return None
        ox, oy, w, h = bounds
        min_x = ox
        max_x = ox + w - view_w
        min_y = oy
        max_y = oy + h - view_h
        px = player_rect.centerx
        py = player_rect.centery
        feet_y = player_rect.bottom

        def clamp_x(val):
            if max_x < min_x:
                return ox + (w / 2) - (view_w / 2)
            return max(min_x, min(val, max_x))

        def clamp_y(val):
            if max_y < min_y:
                return oy + (h / 2) - (view_h / 2)
            return max(min_y, min(val, max_y))

        def zone_lock_y(zone):
            return clamp_y(zone["rect"].centery - (view_h / 2) + zone.get("y_bias", 0))

        def zone_lock_x(zone):
            return clamp_x(zone["rect"].centerx - (view_w / 2) + zone.get("x_bias", 0))

        def wall_lock_x(zone, extra=32):
            return clamp_x(zone["rect"].right - view_w + extra)

        def natural_y():
            # Keep transitions tied to Zero's feet so dash hitbox changes do not
            # yank the camera downward.
            return clamp_y((feet_y - 22) - (view_h / 2))

        def natural_x():
            return clamp_x(px - (view_w / 2))

        def clamp_between(lo, hi, val):
            low = min(lo, hi)
            high = max(lo, hi)
            return max(low, min(high, val))

        def lerp(a, b, t):
            return a + ((b - a) * t)

        def drop_transition_y(upper_zone, upper_lock_y, lower_zone, lower_lock_y):
            start_feet_y = upper_zone["rect"].bottom - 24
            end_feet_y = lower_zone["rect"].top + 8
            if end_feet_y <= start_feet_y:
                return clamp_between(upper_lock_y, lower_lock_y, natural_y())
            t = (feet_y - start_feet_y) / float(end_feet_y - start_feet_y)
            t = max(0.0, min(1.0, t))
            return clamp_between(upper_lock_y, lower_lock_y, lerp(upper_lock_y, lower_lock_y, t))

        zones = self.camera_zones
        if len(zones) < 5:
            zone = zones[min(len(zones) - 1, 0)]
            lock = {"mode": zone["mode"]}
            if zone["mode"] == "lock_y":
                lock["scroll_y"] = zone_lock_y(zone)
            elif zone["mode"] == "lock_x":
                lock["scroll_x"] = zone_lock_x(zone)
            return lock

        z1, z2, z3, z4, z5 = zones[:5]
        secret_floor = self.secret_roof_floor
        transition_margin = 96
        y1 = zone_lock_y(z1)
        y2 = zone_lock_y(z2)
        y3 = zone_lock_y(z3)
        y5 = zone_lock_y(z5)
        top_corridor_y = y5 + 120
        x4 = zone_lock_x(z4)
        x5 = zone_lock_x(z5)
        # Keep the end-of-zone wall just slightly on-screen in the horizontal
        # transitions so the player can read the connector without exposing the
        # next area's dead space too early.
        x12 = wall_lock_x(z1, extra=28)
        x23 = wall_lock_x(z2, extra=28)
        x34 = wall_lock_x(z3, extra=24)
        shaft_top_y = clamp_y(z4["rect"].top + 72)
        # Use the shaft zone's lower edge to define the pre-shaft corridor's
        # upper camera limit. This lets the camera rise onto the upper ledge
        # before the vertical shaft instead of staying trapped at zone 3's
        # much lower framing.
        pre_shaft_top_y = clamp_y(z4["rect"].bottom - view_h + 40)
        # Start raising well before the top ledge so the camera follows the
        # climb instead of only reacting on jump arcs.
        pre_shaft_rise_start_y = z3["rect"].top + 24
        pre_shaft_commit_y = pre_shaft_rise_start_y - 72
        shaft_entry_commit_y = pre_shaft_commit_y - 56
        fy = natural_y()

        z1_transition_x = z1["rect"].right - transition_margin
        z2_transition_x = z2["rect"].right - transition_margin
        z3_transition_x = z3["rect"].right - transition_margin
        z34_transition_x = z3["rect"].right - 176
        z4_transition_x = z4["rect"].right - transition_margin
        z12_commit_y = z2["rect"].top + 8
        z23_commit_y = z3["rect"].top + 8
        z12_start_y = z12_commit_y - 56
        z23_start_y = z23_commit_y - 56
        secret_trigger_y = z1["rect"].top - 120
        # Start applying the top cap lower in the shaft so by the time Zero is
        # standing on the upper ledge, the shaft camera has already naturally
        # reached the approved maximum height.
        z45_upper_band_y = z5["rect"].bottom + 160

        if self._camera_mode == "z1":
            if (
                secret_floor is not None
                and (secret_floor.left - 90) <= px <= (secret_floor.left + 80)
                and feet_y <= secret_trigger_y
            ):
                self._camera_mode = "z1_upper"
            elif px >= z1_transition_x:
                self._camera_mode = "z1_to_z2"
        elif self._camera_mode == "z1_upper":
            secret_right_limit = None if secret_floor is None else (secret_floor.right + 260)
            if (
                secret_floor is None
                or px < (secret_floor.left - 180)
                or (secret_right_limit is not None and px > secret_right_limit)
                or feet_y > (secret_floor.bottom + 820)
            ):
                self._camera_mode = "z1"
        elif self._camera_mode == "z1_to_z2":
            if px >= z2["rect"].left and feet_y >= z12_commit_y:
                self._camera_mode = "z2"
            elif px < z1_transition_x - 72 and feet_y < z12_start_y:
                self._camera_mode = "z1"
        elif self._camera_mode == "z2":
            if px < z2["rect"].left - 48 and feet_y < z12_commit_y - 16:
                self._camera_mode = "z1_to_z2"
            elif px >= z2_transition_x:
                self._camera_mode = "z2_to_z3"
        elif self._camera_mode == "z2_to_z3":
            if px >= z3["rect"].left and feet_y >= z23_commit_y:
                self._camera_mode = "z3"
            elif px < z2_transition_x - 72 and feet_y < z23_start_y:
                self._camera_mode = "z2"
        elif self._camera_mode == "z3":
            if px < z3["rect"].left - 48 and feet_y < z23_commit_y - 16:
                self._camera_mode = "z2_to_z3"
            elif px >= z34_transition_x:
                self._camera_mode = "z3_to_z4"
        elif self._camera_mode == "z3_to_z4":
            if feet_y <= pre_shaft_commit_y:
                self._camera_mode = "z4_top"
            elif px < z34_transition_x - 128 and feet_y >= z3["rect"].bottom - 64:
                self._camera_mode = "z3"
        elif self._camera_mode == "z4_top":
            if px < z34_transition_x - 128 and feet_y >= z3["rect"].bottom - 64:
                self._z4_upper_cap_y = None
                self._camera_mode = "z3"
            elif px < z4["rect"].left - 16 and feet_y > pre_shaft_rise_start_y:
                self._z4_upper_cap_y = None
                self._camera_mode = "z3_to_z4"
            elif px >= z4["rect"].left + 24 and feet_y <= shaft_entry_commit_y:
                self._z4_entry_scroll_y = (
                    pre_shaft_top_y if self._last_camera_scroll_y is None else self._last_camera_scroll_y
                )
                self._z4_entry_scroll_x = (
                    x4 if self._last_camera_scroll_x is None else self._last_camera_scroll_x
                )
                self._camera_mode = "z4"
        elif self._camera_mode == "z4":
            top_floor = self.big_shaft_top_floor
            if top_floor is not None:
                top_floor_y = top_floor.bottom + 6
                top_floor_min_y = top_floor.top - 12
                on_top_floor_x = (
                    player_rect.right >= top_floor.left + 16
                    and player_rect.left <= top_floor.right - 16
                )
                can_enter_upper = (
                    top_floor_min_y <= feet_y <= top_floor_y
                    and on_top_floor_x
                )
            else:
                can_enter_upper = feet_y <= z45_upper_band_y
            if can_enter_upper:
                if self._z4_upper_cap_y is None:
                    self._z4_upper_cap_y = (
                        max(top_corridor_y, natural_y())
                        if self._last_camera_scroll_y is None
                        else self._last_camera_scroll_y
                    )
                if self._z4_upper_entry_scroll_x is None:
                    self._z4_upper_entry_scroll_x = (
                        x4 if self._last_camera_scroll_x is None else self._last_camera_scroll_x
                    )
                if self._z4_upper_entry_player_x is None:
                    self._z4_upper_entry_player_x = px
                self._camera_mode = "z4_upper"
            if feet_y >= pre_shaft_commit_y and px < z4["rect"].left + 80:
                self._z4_entry_scroll_y = None
                self._z4_entry_scroll_x = None
                self._z4_upper_cap_y = None
                self._z4_upper_entry_scroll_x = None
                self._z4_upper_entry_player_x = None
                self._camera_mode = "z4_top"
            elif px < z4["rect"].left - 16 and feet_y > pre_shaft_rise_start_y:
                self._z4_entry_scroll_y = None
                self._z4_entry_scroll_x = None
                self._z4_upper_cap_y = None
                self._z4_upper_entry_scroll_x = None
                self._z4_upper_entry_player_x = None
                self._camera_mode = "z3_to_z4"
        elif self._camera_mode == "z4_upper":
            top_floor = self.big_shaft_top_floor
            if top_floor is not None:
                top_floor_drop_y = top_floor.bottom + 28
                top_floor_left = top_floor.left + 24
                should_drop = feet_y > top_floor_drop_y and px < top_floor_left
            else:
                should_drop = feet_y > z45_upper_band_y + 56 and px < z4["rect"].left + 96
            if should_drop:
                self._z4_upper_entry_scroll_x = None
                self._z4_upper_entry_player_x = None
                self._camera_mode = "z4"
            elif px >= z5["rect"].left - 24:
                self._camera_mode = "z5"
        elif self._camera_mode == "z4_to_z5":
            self._camera_mode = "z4"
        elif self._camera_mode == "z5":
            top_floor = self.second_shaft_top_floor
            if top_floor is not None:
                top_floor_y = top_floor.bottom + 6
                top_floor_x = top_floor.left - 12
                top_floor_min_y = top_floor.top - 12
            else:
                top_floor_y = z5["rect"].bottom - 24
                top_floor_x = z5["rect"].left + 8
                top_floor_min_y = z5["rect"].top - 8
            if (
                top_floor_min_y <= feet_y <= top_floor_y
                and player_rect.left >= top_floor_x
            ):
                self._z5_entry_scroll_y = (
                    top_corridor_y if self._last_camera_scroll_y is None else self._last_camera_scroll_y
                )
                self._z5_entry_scroll_x = (
                    x5 if self._last_camera_scroll_x is None else self._last_camera_scroll_x
                )
                self._z5_upper_entry_player_x = px
                self._camera_mode = "z5_upper"
            if px < z5["rect"].left - 48 and feet_y <= z45_upper_band_y + 24:
                self._camera_mode = "z4_upper"
        elif self._camera_mode == "z5_upper":
            top_floor = self.second_shaft_top_floor
            if top_floor is not None:
                top_floor_drop_y = top_floor.bottom + 28
            else:
                top_floor_drop_y = z5["rect"].bottom + 24
            if feet_y > top_floor_drop_y:
                self._z5_entry_scroll_y = None
                self._z5_entry_scroll_x = None
                self._z5_upper_entry_player_x = None
                self._camera_mode = "z5"
            elif px < z5["rect"].left - 48 and feet_y <= z45_upper_band_y + 24:
                self._z5_entry_scroll_y = None
                self._z5_entry_scroll_x = None
                self._z5_upper_entry_player_x = None
                self._camera_mode = "z4_upper"

        def finalize(lock):
            if "scroll_x" in lock:
                self._last_camera_scroll_x = lock["scroll_x"]
            if "scroll_y" in lock:
                self._last_camera_scroll_y = lock["scroll_y"]
            return lock

        if self._camera_mode == "z1":
            return finalize({"mode": "z1", "scroll_y": y1})
        if self._camera_mode == "z1_upper":
            secret_cap_y = y1
            if secret_floor is not None:
                secret_cap_y = clamp_y((secret_floor.bottom - 22) - (view_h / 2))
            return finalize({
                "mode": "z1_upper",
                "scroll_y": clamp_between(secret_cap_y, y1, natural_y()),
            })
        if self._camera_mode == "z1_to_z2":
            target_y = clamp_between(y1, y2, fy)
            if feet_y < z12_start_y:
                scroll_y = y1
            else:
                onset = max(1.0, float(z12_commit_y - z12_start_y))
                t = max(0.0, min(1.0, (feet_y - z12_start_y) / onset))
                scroll_y = lerp(y1, target_y, t)
            return finalize({
                "mode": "z1_to_z2",
                "scroll_y": scroll_y,
            })
        if self._camera_mode == "z2":
            return finalize({"mode": "z2", "scroll_y": y2})
        if self._camera_mode == "z2_to_z3":
            target_y = clamp_between(y2, y3, fy)
            if feet_y < z23_start_y:
                scroll_y = y2
            else:
                onset = max(1.0, float(z23_commit_y - z23_start_y))
                t = max(0.0, min(1.0, (feet_y - z23_start_y) / onset))
                scroll_y = lerp(y2, target_y, t)
            return finalize({
                "mode": "z2_to_z3",
                "scroll_y": scroll_y,
            })
        if self._camera_mode == "z3":
            return finalize({"mode": "z3", "scroll_y": y3})
        if self._camera_mode == "z3_to_z4":
            target_y = clamp_between(pre_shaft_top_y, y3, fy)
            if feet_y > pre_shaft_rise_start_y:
                scroll_y = y3
            else:
                rise_window = max(1.0, float(pre_shaft_rise_start_y - pre_shaft_commit_y))
                t = max(0.0, min(1.0, (pre_shaft_rise_start_y - feet_y) / rise_window))
                scroll_y = lerp(y3, target_y, t)
            return finalize({
                "mode": "z3_to_z4",
                # Keep the corridor floor framed like zone 3 while allowing the
                # camera to raise into the upper pre-shaft space without
                # revealing the pit past the right wall.
                "scroll_x": min(natural_x(), x34),
                "scroll_y": scroll_y,
            })
        if self._camera_mode == "z4_top":
            return finalize({
                "mode": "z4_top",
                "scroll_x": clamp_between(x34, x4, natural_x()),
                "scroll_y": pre_shaft_top_y,
            })
        if self._camera_mode == "z4":
            entry_floor_y = pre_shaft_top_y if self._z4_entry_scroll_y is None else self._z4_entry_scroll_y
            entry_x = x34 if self._z4_entry_scroll_x is None else self._z4_entry_scroll_x
            shaft_cap_y = top_corridor_y if self._z4_upper_cap_y is None else self._z4_upper_cap_y
            return finalize({
                "mode": "z4",
                # When entering the first tall shaft, preserve the transition
                # camera floor and let x settle into the shaft lock naturally
                # instead of snapping immediately. Once the hallway cap has
                # been established, reuse it here so the shaft top and hallway
                # share the same maximum height.
                "scroll_x": clamp_between(entry_x, x4, natural_x()),
                "scroll_y": max(shaft_cap_y, min(entry_floor_y, natural_y())),
            })
        if self._camera_mode == "z4_upper":
            cap_y = top_corridor_y if self._z4_upper_cap_y is None else self._z4_upper_cap_y
            stop_scroll_x = None
            if self.right_stop_x is not None:
                stop_scroll_x = clamp_x(self.right_stop_x - view_w)
            entry_x = x4 if self._z4_upper_entry_scroll_x is None else self._z4_upper_entry_scroll_x
            entry_player_x = px if self._z4_upper_entry_player_x is None else self._z4_upper_entry_player_x
            progress_x = max(0, px - entry_player_x)
            base_x = entry_x + progress_x
            target_x = natural_x()
            recenter_window = 180.0
            t = max(0.0, min(1.0, progress_x / recenter_window))
            scroll_x = lerp(base_x, max(base_x, target_x), t)
            if stop_scroll_x is not None:
                scroll_x = min(scroll_x, stop_scroll_x)
            return finalize({
                "mode": "z4_upper",
                # Once Zero reaches the top platform, keep the approved fixed
                # height but let the camera move horizontally through the
                # hallway until the next shaft. Use the annotated stop line
                # here too so the camera cannot overshoot before z5 starts.
                "scroll_x": scroll_x,
                "scroll_y": cap_y,
            })
        if self._camera_mode == "z4_to_z5":
            self._camera_mode = "z4"
            return self.get_camera_lock(player_rect, view_w, view_h, bounds)
        if self._camera_mode == "z5":
            hallway_floor_y = top_corridor_y if self._z4_upper_cap_y is None else self._z4_upper_cap_y
            stop_scroll_x = x5
            if self.right_stop_x is not None:
                stop_scroll_x = clamp_x(self.right_stop_x - view_w)
            return finalize({
                "mode": "z5",
                # Final short shaft: x locks to the shaft, and y behaves like
                # a shaft camera, but its lowest point matches the hallway
                # height exactly so entering it does not cut downward. Its
                # horizontal stop now uses the explicit annotation guide.
                "scroll_x": min(natural_x(), stop_scroll_x),
                "scroll_y": min(hallway_floor_y, natural_y()),
            })
        if self._camera_mode == "z5_upper":
            hallway_floor_y = (
                top_corridor_y if self._z5_entry_scroll_y is None else self._z5_entry_scroll_y
            )
            entry_x = x5 if self._z5_entry_scroll_x is None else self._z5_entry_scroll_x
            entry_player_x = (
                px if self._z5_upper_entry_player_x is None else self._z5_upper_entry_player_x
            )
            progress_x = max(0, px - entry_player_x)
            base_x = entry_x + progress_x
            target_x = natural_x()
            recenter_window = 180.0
            t = max(0.0, min(1.0, progress_x / recenter_window))
            scroll_x = lerp(base_x, max(base_x, target_x), t)
            if self.end_balcony_stop_x is not None:
                scroll_x = min(scroll_x, clamp_x(self.end_balcony_stop_x - view_w))
            return finalize({
                "mode": "z5_upper",
                "scroll_x": scroll_x,
                "scroll_y": hallway_floor_y,
            })
        self._camera_mode = "z4"
        return self.get_camera_lock(player_rect, view_w, view_h, bounds)

    def render(self, surf, offset=(0, 0)):
        for layer in self.background_layers:
            rect = layer["rect"]
            img = layer["image"]
            if img.get_width() <= 0 or img.get_height() <= 0:
                continue
            clip = rect.move(-int(offset[0]), -int(offset[1]))
            prev_clip = surf.get_clip()
            surf.set_clip(clip)
            tile_w = img.get_width()
            tile_h = img.get_height()
            start_x = rect.x + int(layer.get("x_offset", 0)) - int(offset[0] * layer["scroll_x"])
            while start_x > clip.left:
                start_x -= tile_w
            if layer.get("lock_to_clip_y"):
                if layer.get("anchor") == "bottom":
                    start_y = clip.bottom - tile_h + layer.get("y_offset", 0)
                else:
                    start_y = clip.top + layer.get("y_offset", 0)
            elif layer.get("anchor") == "bottom":
                start_y = rect.bottom - tile_h + layer.get("y_offset", 0) - int(offset[1] * layer["scroll_y"])
                while start_y > clip.top:
                    start_y -= tile_h
            else:
                start_y = rect.y + layer.get("y_offset", 0) - int(offset[1] * layer["scroll_y"])
                if layer.get("repeat_y"):
                    while start_y > clip.top:
                        start_y -= tile_h
            if layer.get("repeat_y"):
                y = start_y
                while y < clip.bottom:
                    x = start_x
                    while x < clip.right:
                        surf.blit(img, (x, y))
                        x += tile_w
                    y += tile_h
            else:
                x = start_x
                while x < clip.right:
                    auto_copies = 0
                    if tile_h > 0 and start_y > clip.top:
                        auto_copies = int(math.ceil((start_y - clip.top) / tile_h))
                    total_copies = max(auto_copies, int(layer.get("extend_up_copies", 0)))
                    for copy_idx in range(1, total_copies + 1):
                        if layer.get("extend_up_sky_only"):
                            sky_h = min(tile_h, 580)
                            dest_y = start_y - (sky_h * copy_idx)
                            sky_src = pygame.Rect(0, 0, tile_w, sky_h)
                            surf.blit(img, (x, dest_y), sky_src)
                        else:
                            dest_y = start_y - (tile_h * copy_idx)
                            surf.blit(img, (x, dest_y))
                    surf.blit(img, (x, start_y))
                    x += tile_w
            surf.set_clip(prev_clip)
        surf.blit(self.surface, (-int(offset[0]), -int(offset[1])))

    def render_foreground(self, surf, offset=(0, 0)):
        for rect, layer in self.foreground_surfaces:
            surf.blit(layer, (rect.x - int(offset[0]), rect.y - int(offset[1])))
