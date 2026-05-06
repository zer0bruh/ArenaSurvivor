import pygame
import random
import sys
import json
import os
import math
import re
import time
import hashlib
import shutil
from datetime import datetime
from collections import defaultdict
from typing import Any, cast

try:
    from PIL import Image, ImageSequence
except Exception:
    Image = None
    ImageSequence = None

from arena.core import Animation, Effect
from arena.combat_data import (
    ANIM_OFFSETS,
    DASH_H,
    DEFAULT_ACTION,
    HITBOX_ALIGN_TO_ANIM,
    HITBOX_H,
    HITBOX_OFFSETS,
    HITBOX_SIZES,
    OY_GROUND,
    SWORD_HITBOXES,
    ensure_sword_hitbox_frames,
)
from arena.stage_assets import load_animated_stage, load_snow_animation
from arena.assets import (
    assets_load_spritesheet,
    build_arena_assets,
    get_stage_stone_folder,
)
from arena.runtime_paths import (
    assets_dir as runtime_assets_dir,
    ensure_dir as ensure_runtime_dir,
    intro_stage_layout_cache_path,
    leaderboard_records_path,
    packaged_intro_stage_cache_dir,
    project_root,
    seed_runtime_file,
)
from arena.entities import (
    ArenaPhysicsEntity,
    GigaBeam,
    ArenaCopterEnemy,
    ArenaPickup,
    ArenaBirdEnemy,
    ArenaMetEnemy,
    ArenaCannonEnemy,
    ArenaHeliRocketEnemy,
    ArenaHeavyEnemy,
    ArenaWheelEnemy,
    ArenaSpikeEnemy,
    ArenaVileBoss,
)
from arena.intro_stage import (
    IntroStageMap,
    INTRO_STAGE_SPAWN_X,
    INTRO_STAGE_SPAWN_Y,
    prewarm_intro_stage_cache,
)
from arena.intro_opening_cache import load_intro_opening_assets
from arena.tilemap import ArenaTilemap
from arena.player import ArenaPlayer

# main game bootstrap, state, menus, cutscenes, and arena flow all live in here
BASE_DIR = project_root()
ASSETS_DIR = runtime_assets_dir()
SECRETS_DIR = os.path.join(ASSETS_DIR, "secrets")

AUDIO_DIR = os.path.join(ASSETS_DIR, "audio")
MUSIC_DIR = os.path.join(AUDIO_DIR, "music")
SFX_DIR = os.path.join(AUDIO_DIR, "sfx")
LEADERBOARD_RECORDS_PATH = leaderboard_records_path()
LEGACY_LEADERBOARD_RECORDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaderboard_records.json")

pygame.mixer.pre_init(48000, -16, 2, 512)
pygame.init()
pygame.mixer.init()
pygame.joystick.init()
pygame.mixer.set_reserved(1)

pygame.joystick.init()

# Render scale snapping helps prevent sub-pixel jitter during movement.
PIXEL_PERFECT_SCALE = False
# Per-frame offset stabilization for vertical-air actions.
FRAME_STABILIZE = False
# Auto-align action offsets based on sprite anchors (can introduce jitter).
AUTO_ALIGN_ACTIONS = False

#BUTTON INPUTS
# ---- CONTROLLER BUTTON MAP ----
BTN_B = 0
BTN_A = 1
BTN_SELECT = 2
BTN_START = 3
BTN_Y = 4
BTN_X = 5
BTN_L = 10
BTN_R = 13

MOUSE_ATTACK_BUTTON = 1
MOUSE_GIGA_BUTTON = 3
# Extra mouse buttons can vary by platform/driver, so accept the common
# side-button ids instead of relying on a single value.
MOUSE_DASH_BUTTONS = {4, 5, 6, 7}

# ---- CONTROLLER AXIS MAP ----
AXIS_HORIZONTAL = 0
AXIS_VERTICAL = 1

AXIS_DEADZONE = 0.5

dpad_cooldown = 0
DPAD_DELAY = 0.18



joystick = None

def detect_controller():
    # grab the first controller if one is connected so the rest of the input code can stay simple
    global joystick

    if pygame.joystick.get_count() > 0:
        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        print("Controller connected:", joystick.get_name())
    else:
        print("No controller detected")

detect_controller()

ARENA_W, ARENA_H = 378, 246

def _load_minimap_player_icon():
    # use the real ui icon when available, otherwise draw a tiny readable fallback
    path = os.path.join(ASSETS_DIR, "menu_and_ui", "minimap_player_icon.png")
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception:
        fallback = pygame.Surface((15, 19), pygame.SRCALPHA)
        pygame.draw.rect(fallback, (8, 10, 14, 255), (3, 2, 9, 9), border_radius=2)
        pygame.draw.rect(fallback, (214, 34, 30, 255), (4, 3, 7, 7), border_radius=2)
        pygame.draw.rect(fallback, (236, 244, 252, 255), (6, 5, 3, 2))
        pygame.draw.polygon(fallback, (250, 208, 58, 255), [(11, 7), (14, 6), (14, 8)])
        return fallback

def _make_effect_surface(size, color, shape="circle"):
    # quick fallback particles so missing effect art does not break gameplay
    surf = pygame.Surface(size, pygame.SRCALPHA)
    if shape == "circle":
        r = min(size) // 2
        pygame.draw.circle(surf, color, (size[0] // 2, size[1] // 2), r)
    elif shape == "triangle":
        w, h = size
        pygame.draw.polygon(surf, color, [(0, h), (w // 2, 0), (w, h)])
    else:
        surf.fill(color)
    return surf

def _load_effect_images_or_fallback(_name, fallback):
    return fallback

_effect_images_cache = None


def build_effect_images():
    # central place for effect sprites plus a few procedural fallbacks
    global _effect_images_cache
    if _effect_images_cache is not None:
        return _effect_images_cache

    effects = {}
    misc_anims = {}
    try:
        misc_anims = assets_load_spritesheet(
            ASSETS_DIR,
            'miscellaneous/miscellaneous.png',
            'miscellaneous/miscellaneous.json'
        )
    except Exception:
        misc_anims = {}

    effects['wall_kick_spark'] = (
        (misc_anims.get('wallkick_spark_effect', None).images
         if misc_anims.get('wallkick_spark_effect', None) else None) or
        _load_effect_images_or_fallback("wall_kick_spark", [_make_effect_surface((6, 6), (255, 240, 160))])
    )
    effects['dash_booster'] = (
        (misc_anims.get('dash_booster_effect', None).images
         if misc_anims.get('dash_booster_effect', None) else None) or
        _load_effect_images_or_fallback("dash_booster", [_make_effect_surface((8, 12), (120, 200, 255), shape="triangle")])
    )
    # Use the wall slide dash particle for both dash smoke and wall slide smoke by default.
    effects['dash_smoke'] = (
        (misc_anims.get('wall_slide_dash particle', None).images
         if misc_anims.get('wall_slide_dash particle', None) else None) or
        _load_effect_images_or_fallback("dash_smoke", [_make_effect_surface((10, 10), (160, 160, 160))])
    )
    effects['wall_slide_smoke'] = (
        (misc_anims.get('wall_slide_dash particle', None).images
         if misc_anims.get('wall_slide_dash particle', None) else None) or
        _load_effect_images_or_fallback("wall_slide_smoke", [_make_effect_surface((8, 8), (150, 150, 150))])
    )
    effects['enemy_destroyed'] = (
        (misc_anims.get('enemy_destroyed', None).images
         if misc_anims.get('enemy_destroyed', None) else None) or
        _load_effect_images_or_fallback("enemy_destroyed", [_make_effect_surface((18, 18), (255, 180, 80))])
    )
    effects['small_hp_pickup'] = (
        (misc_anims.get('small_hp_pickup', None).images
         if misc_anims.get('small_hp_pickup', None) else None) or
        [_make_effect_surface((12, 12), (120, 255, 120))]
    )
    effects['large_hp_pickup'] = (
        (misc_anims.get('large_hp_pickup', None).images
         if misc_anims.get('large_hp_pickup', None) else None) or
        [_make_effect_surface((14, 14), (120, 255, 120))]
    )
    effects['small_special_ammo_pickup'] = (
        (misc_anims.get('small_special_ammo_pickup', None).images
         if misc_anims.get('small_special_ammo_pickup', None) else None) or
        [_make_effect_surface((12, 12), (120, 220, 255))]
    )
    effects['large_special_ammo_pickup'] = (
        (misc_anims.get('large_special_ammo_pickup', None).images
         if misc_anims.get('large_special_ammo_pickup', None) else None) or
        [_make_effect_surface((14, 14), (120, 220, 255))]
    )
    effects['zero_hp_bar'] = (
        (misc_anims.get('zero_hp_bar', None).images
         if misc_anims.get('zero_hp_bar', None) else None) or
        [_make_effect_surface((16, 96), (40, 90, 160))]
    )
    effects['health_gauge'] = (
        (misc_anims.get('health_gauge', None).images
         if misc_anims.get('health_gauge', None) else None) or
        [_make_effect_surface((8, 80), (240, 70, 70))]
    )
    effects['giga_attack_energy_bar'] = (
        (misc_anims.get('giga_attack_energy_bar', None).images
         if misc_anims.get('giga_attack_energy_bar', None) else None) or
        [_make_effect_surface((16, 96), (40, 90, 160))]
    )
    effects['nova_strike_energy_gauge'] = (
        (misc_anims.get('nova_strike_energy_gauge', None).images
         if misc_anims.get('nova_strike_energy_gauge', None) else None) or
        [_make_effect_surface((8, 80), (80, 180, 255))]
    )
    _effect_images_cache = effects
    return effects


def _load_secret_gif_frames(path):
    # gif support is only for the secret overlay, so keep the conversion helper local here
    if Image is None or ImageSequence is None or not os.path.exists(path):
        if not os.path.exists(path):
            return [], []
        try:
            frame = pygame.image.load(path).convert_alpha()
            return [frame], [220]
        except Exception:
            return [], []
    try:
        gif = Image.open(path)
    except Exception:
        try:
            frame = pygame.image.load(path).convert_alpha()
            return [frame], [220]
        except Exception:
            return [], []

    frames = []
    durations = []
    try:
        for frame in ImageSequence.Iterator(gif):
            rgba = frame.convert("RGBA")
            surf = pygame.image.frombytes(rgba.tobytes(), rgba.size, "RGBA").convert_alpha()
            frames.append(surf)
            durations.append(max(16, int(frame.info.get("duration", 50) * 0.62)))
    except Exception:
        try:
            frame = pygame.image.load(path).convert_alpha()
            return [frame], [220]
        except Exception:
            return [], []
    return frames, durations


UI_BAR_SCALE = 3
UI_BAR_MARGIN_X = 4
UI_BAR_MARGIN_Y = 4
UI_BAR_GAP = 4
UI_BAR_FREE_TOP_OFFSET = 24
UI_HP_BAR_CROP = pygame.Rect(57, 22, 14, 84)
UI_GIGA_BAR_CROP = pygame.Rect(57, 39, 14, 52)
_UI_BAR_CACHE = {}
MINIMAP_TILE_SIZE = 6
MINIMAP_BORDER = 2
MINIMAP_PADDING = 3
MINIMAP_MARGIN_X = 8
MINIMAP_MARGIN_Y = 0
MINIMAP_FREE_TOP_OFFSET = 8
_MINIMAP_CACHE = {}


def _crop_alpha_surface(surface):
    if surface is None:
        return None
    rect = surface.get_bounding_rect()
    if rect.width <= 0 or rect.height <= 0:
        return surface.copy()
    cropped = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    cropped.blit(surface, (0, 0), rect)
    return cropped


def _compose_face_frame(base_surface, overlay_surface=None):
    if base_surface is None:
        return None
    base = base_surface.copy()
    if overlay_surface is None:
        return _crop_alpha_surface(base)
    composed = base.copy()
    composed.blit(overlay_surface, (0, 0))
    crop_rect = base_surface.get_bounding_rect()
    if crop_rect.width <= 0 or crop_rect.height <= 0:
        return _crop_alpha_surface(composed)
    cropped = pygame.Surface((crop_rect.width, crop_rect.height), pygame.SRCALPHA)
    cropped.blit(composed, (0, 0), crop_rect)
    return cropped


def _surfaces_equal(a, b):
    if a is None or b is None:
        return False
    if a.get_size() != b.get_size():
        return False
    return pygame.image.tobytes(a, "RGBA") == pygame.image.tobytes(b, "RGBA")


def _draw_face_detail(surface, rel_x, rel_y, color):
    if surface is None:
        return
    bounds = surface.get_bounding_rect(min_alpha=1)
    if bounds.width <= 0 or bounds.height <= 0:
        return
    px = bounds.x + max(0, min(bounds.width - 1, int(round(rel_x * max(1, bounds.width - 1)))))
    py = bounds.y + max(0, min(bounds.height - 1, int(round(rel_y * max(1, bounds.height - 1)))))
    surface.set_at((px, py), color)


def _build_synthetic_face_variant(base_surface, *, blink_level=0, mouth_level=0):
    if base_surface is None:
        return None
    face = base_surface.copy()
    stroke = (8, 8, 8, 255)
    shadow = (28, 28, 28, 255)
    if blink_level > 0:
        eye_y = 0.36 if blink_level == 1 else 0.39
        for rel_x in (0.32, 0.42, 0.60, 0.70):
            _draw_face_detail(face, rel_x, eye_y, stroke)
        if blink_level >= 2:
            for rel_x in (0.34, 0.62):
                _draw_face_detail(face, rel_x, eye_y + 0.02, shadow)
    if mouth_level > 0:
        mouth_y = 0.73 if mouth_level == 1 else 0.76
        mouth_points = (0.42, 0.50, 0.58) if mouth_level == 1 else (0.40, 0.46, 0.54, 0.60)
        for rel_x in mouth_points:
            _draw_face_detail(face, rel_x, mouth_y, stroke)
        if mouth_level >= 2:
            for rel_x in (0.46, 0.54):
                _draw_face_detail(face, rel_x, mouth_y + 0.05, shadow)
    return _crop_alpha_surface(face)


def _build_dialogue_face_bank(face_source):
    # prebuild a few face variants so dialogue can fake blinking and mouth movement cheaply
    if not face_source or not getattr(face_source, "images", None):
        return {}

    source_images = list(face_source.images)
    raw_base = source_images[0]
    base = _compose_face_frame(raw_base)
    if base is None:
        return {}

    def _candidate(index, fallback):
        if index >= len(source_images):
            return fallback
        composed = _compose_face_frame(raw_base, source_images[index])
        if composed is not None and not _surfaces_equal(base, composed):
            return composed
        return fallback

    blink_a = _candidate(1, _build_synthetic_face_variant(base, blink_level=1))
    blink_b = _candidate(2, _build_synthetic_face_variant(base, blink_level=2))
    talk_a = _candidate(3, _build_synthetic_face_variant(base, mouth_level=1))
    talk_b = _candidate(4, _build_synthetic_face_variant(base, mouth_level=2))
    talk_c = _candidate(5, _build_synthetic_face_variant(base, mouth_level=1))
    return {
        "base": base,
        "blink_a": blink_a or base,
        "blink_b": blink_b or blink_a or base,
        "talk_a": talk_a or base,
        "talk_b": talk_b or talk_a or base,
        "talk_c": talk_c or talk_a or base,
    }


def _dialogue_face_image(face_bank, timer_value, speaking=False):
    if not face_bank:
        return None
    base = face_bank.get("base")
    blink_phase = timer_value % 3.4
    if 2.58 <= blink_phase < 2.70:
        return face_bank.get("blink_a", base)
    if 2.70 <= blink_phase < 2.82:
        return face_bank.get("blink_b", face_bank.get("blink_a", base))
    if 2.82 <= blink_phase < 2.94:
        return face_bank.get("blink_a", base)
    if speaking:
        mouth_index = int(timer_value * 5.0) % 3
        if mouth_index == 0:
            return face_bank.get("talk_a", base)
        if mouth_index == 1:
            return face_bank.get("talk_b", face_bank.get("talk_a", base))
        return face_bank.get("talk_c", face_bank.get("talk_a", base))
    return base


def _sanitize_intro_surface(surface):
    if surface is None:
        return None
    cleaned = surface.copy().convert_alpha()
    w, h = cleaned.get_size()
    for y in range(h):
        for x in range(w):
            color = cleaned.get_at((x, y))
            if color.a == 0:
                cleaned.set_at((x, y), (0, 0, 0, 0))
                continue
            if color.r == 255 and color.g == 0 and color.b == 255:
                cleaned.set_at((x, y), (255, 0, 255, 0))
    return cleaned


def _clean_lightning_draw_surface(surface):
    if surface is None:
        return None
    cleaned = surface.copy().convert_alpha()
    w, h = cleaned.get_size()
    for y in range(h):
        for x in range(w):
            color = cleaned.get_at((x, y))
            if color.a == 0:
                cleaned.set_at((x, y), (0, 0, 0, 0))
                continue
            is_black_matte = color.r < 20 and color.g < 20 and color.b < 20
            is_magenta_matte = color.r > 220 and color.g < 100 and color.b > 220
            if is_black_matte or is_magenta_matte:
                cleaned.set_at((x, y), (0, 0, 0, 0))
    return cleaned


def _strip_edge_connected_matte(surface):
    if surface is None:
        return None
    rect = surface.get_bounding_rect()
    if rect.width <= 0 or rect.height <= 0:
        return surface.copy().convert_alpha()

    cropped = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA).convert_alpha()
    cropped.blit(surface, (0, 0), rect)
    w, h = cropped.get_size()
    edge_points = []
    for x in range(w):
        edge_points.append((x, 0))
        edge_points.append((x, h - 1))
    for y in range(h):
        edge_points.append((0, y))
        edge_points.append((w - 1, y))

    visited = set()
    for start in edge_points:
        if start in visited:
            continue
        color = cropped.get_at(start)
        if color.a == 0:
            visited.add(start)
            continue
        target = (color.r, color.g, color.b, color.a)
        stack = [start]
        while stack:
            x, y = stack.pop()
            if (x, y) in visited:
                continue
            visited.add((x, y))
            current = cropped.get_at((x, y))
            if (current.r, current.g, current.b, current.a) != target:
                continue
            cropped.set_at((x, y), (0, 0, 0, 0))
            if x > 0:
                stack.append((x - 1, y))
            if x + 1 < w:
                stack.append((x + 1, y))
            if y > 0:
                stack.append((x, y - 1))
            if y + 1 < h:
                stack.append((x, y + 1))
    return cropped


def _crop_nonblack_surface(surface):
    if surface is None:
        return None, None
    w, h = surface.get_size()
    min_x, min_y = w, h
    max_x, max_y = -1, -1
    for y in range(h):
        for x in range(w):
            color = surface.get_at((x, y))
            if color.a > 0 and (color.r or color.g or color.b):
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if max_x < min_x or max_y < min_y:
        return None, None
    rect = pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    cropped = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA).convert_alpha()
    cropped.blit(surface, (0, 0), rect)
    return cropped, rect


def _load_intro_boss_sheet():
    # the intro boss art comes from a separate sheet and gets cached on first use
    png_path = os.path.join(ASSETS_DIR, "menu_and_ui", "intro_and_bosses.png")
    json_path = os.path.join(ASSETS_DIR, "menu_and_ui", "intro_and_bosses.json")
    if not (os.path.exists(png_path) and os.path.exists(json_path)):
        return [], {}, (0, 0)

    try:
        sheet = pygame.image.load(png_path).convert_alpha()
        with open(json_path) as f:
            data = json.load(f)
    except Exception:
        return [], {}, (0, 0)

    frames_data = data.get("frames", {})
    if not frames_data:
        return [], {}, (0, 0)

    frame_items = list(frames_data.items()) if isinstance(frames_data, dict) else []
    tagged_items = [(name, info) for name, info in frame_items if "#" in name]
    if tagged_items:
        frame_items = tagged_items
    if not frame_items:
        return [], {}, (0, 0)

    first_frame = frame_items[0][1]
    source_size = first_frame.get("sourceSize") or first_frame.get("frame") or {}
    canvas_w = int(source_size.get("w", 0))
    canvas_h = int(source_size.get("h", 0))
    if canvas_w <= 0 or canvas_h <= 0:
        return [], {}, (0, 0)

    rect_signatures = []
    for _, frame_info in frame_items:
        rect_data = frame_info.get("frame") or {}
        rect_signatures.append((
            int(rect_data.get("x", 0)),
            int(rect_data.get("y", 0)),
            int(rect_data.get("w", canvas_w)),
            int(rect_data.get("h", canvas_h)),
        ))

    identical_rect_export = (
        len(set(rect_signatures)) == 1
        and rect_signatures[0] == (0, 0, canvas_w, canvas_h)
        and sheet.get_width() % canvas_w == 0
        and sheet.get_height() % canvas_h == 0
        and (sheet.get_width() > canvas_w or sheet.get_height() > canvas_h)
    )

    images = []
    tag_ranges = {}
    if identical_rect_export:
        cols = sheet.get_width() // canvas_w
        rows = sheet.get_height() // canvas_h

        tag_order = []
        for tag in data.get("meta", {}).get("frameTags", []):
            name = tag.get("name")
            if name and name not in tag_order:
                tag_order.append(name)

        for tag_name in tag_order:
            if tag_name not in tag_ranges:
                matching_tags = [tag for tag in data.get("meta", {}).get("frameTags", []) if tag.get("name") == tag_name]
                if matching_tags:
                    tag_ranges[tag_name] = {
                        "from": matching_tags[0].get("from", 0),
                        "to": matching_tags[0].get("to", 0),
                        "direction": matching_tags[0].get("direction", "forward"),
                    }

        column_frames = []
        for col in range(cols):
            col_frames = []
            for row in range(rows):
                rect = pygame.Rect(col * canvas_w, row * canvas_h, canvas_w, canvas_h)
                frame = pygame.Surface((canvas_w, canvas_h), pygame.SRCALPHA).convert_alpha()
                frame.blit(sheet, (0, 0), rect)
                if frame.get_bounding_rect().width > 0 and frame.get_bounding_rect().height > 0:
                    col_frames.append(_sanitize_intro_surface(frame))
            if col_frames:
                column_frames.append(col_frames)

        if len(column_frames) < len(tag_order):
            return [], {}, (0, 0)

        images = []
        rebuilt_ranges = {}
        cursor = 0
        for col_idx, tag_name in enumerate(tag_order):
            frames_for_tag = column_frames[col_idx]
            if not frames_for_tag:
                continue
            start = cursor
            images.extend(frames_for_tag)
            cursor += len(frames_for_tag)
            rebuilt_ranges[tag_name] = {
                "from": start,
                "to": cursor - 1,
                "direction": tag_ranges.get(tag_name, {}).get("direction", "forward"),
            }
        tag_ranges = rebuilt_ranges
    else:
        for _, frame_info in frame_items:
            rect_data = frame_info.get("frame") or {}
            rect = pygame.Rect(
                int(rect_data.get("x", 0)),
                int(rect_data.get("y", 0)),
                int(rect_data.get("w", canvas_w)),
                int(rect_data.get("h", canvas_h)),
            )
            if rect.width <= 0 or rect.height <= 0:
                continue
            frame = pygame.Surface((canvas_w, canvas_h), pygame.SRCALPHA).convert_alpha()
            frame.blit(sheet, (0, 0), rect)
            images.append(_sanitize_intro_surface(frame))

    if not tag_ranges:
        if len(images) < len(frame_items):
            return [], {}, (0, 0)

        current_tag = None
        current_start = 0
        for idx, (frame_name, _) in enumerate(frame_items):
            if "#" in frame_name:
                parsed_tag = frame_name.split("#", 1)[1].split(" ", 1)[0]
            else:
                parsed_tag = "default"
            if parsed_tag != current_tag:
                if current_tag is not None:
                    tag_ranges[current_tag] = {
                        "from": current_start,
                        "to": idx - 1,
                        "direction": "forward",
                    }
                current_tag = parsed_tag
                current_start = idx
        if current_tag is not None:
            tag_ranges[current_tag] = {
                "from": current_start,
                "to": len(frame_items) - 1,
                "direction": "forward",
            }

    return images, tag_ranges, (canvas_w, canvas_h)


def _apply_ui_bar_frame_overlay(scaled, cropped, scale):
    outline = tuple(cropped.get_at((min(2, cropped.get_width() - 1), 0)))
    white = tuple(cropped.get_at((min(2, cropped.get_width() - 1), min(1, cropped.get_height() - 1))))
    gray = tuple(cropped.get_at((min(3, cropped.get_width() - 1), min(2, cropped.get_height() - 1))))

    overlay = pygame.Surface(scaled.get_size(), pygame.SRCALPHA)
    rect = pygame.Rect(0, 0, *scaled.get_size())
    border = max(1, int(scale))
    radius = max(border * 2 + 2, 8)

    pygame.draw.rect(overlay, outline, rect, border_radius=radius)
    pygame.draw.rect(
        overlay,
        white,
        rect.inflate(-(border * 2), -(border * 2)),
        border_radius=max(0, radius - border),
    )
    pygame.draw.rect(
        overlay,
        gray,
        rect.inflate(-(border * 4), -(border * 4)),
        border_radius=max(0, radius - border * 2),
    )
    pygame.draw.rect(
        overlay,
        (0, 0, 0, 0),
        rect.inflate(-(border * 6), -(border * 6)),
        border_radius=max(0, radius - border * 3),
    )

    framed = scaled.copy()
    framed.blit(overlay, (0, 0))
    return framed


def _get_scaled_ui_bar(effect_images, key, value, max_value, crop_rect, scale):
    frames = effect_images.get(key, [])
    if not frames:
        return None
    if max_value <= 0:
        idx = 0
    elif len(frames) == max_value + 1:
        idx = max(0, min(int(round(value)), len(frames) - 1))
    else:
        ratio = max(0.0, min(1.0, float(value) / float(max_value)))
        idx = int(round(ratio * (len(frames) - 1)))
    cache_key = (key, idx, crop_rect.x, crop_rect.y, crop_rect.w, crop_rect.h, scale)
    cached = _UI_BAR_CACHE.get(cache_key)
    if cached is not None:
        return cached
    cropped = pygame.Surface((crop_rect.w, crop_rect.h), pygame.SRCALPHA)
    cropped.blit(frames[idx], (0, 0), crop_rect)
    scaled = pygame.transform.scale(
        cropped,
        (crop_rect.w * scale, crop_rect.h * scale),
    )
    scaled = scaled.convert_alpha()
    scaled = _apply_ui_bar_frame_overlay(scaled, cropped, scale)
    _UI_BAR_CACHE[cache_key] = scaled
    return scaled

def _get_player_status_bars(arena_ctx, arena_player):
    # cache-friendly helper for the two vertical status bars used in gameplay
    if not arena_ctx or not arena_player:
        return None, None, 0

    hp_bar = _get_scaled_ui_bar(
        arena_ctx.effect_images,
        'zero_hp_bar',
        arena_player.health,
        arena_player.max_health,
        UI_HP_BAR_CROP,
        UI_BAR_SCALE,
    )
    giga_bar = _get_scaled_ui_bar(
        arena_ctx.effect_images,
        'giga_attack_energy_bar',
        arena_player.giga_energy,
        arena_player.max_giga_energy,
        UI_GIGA_BAR_CROP,
        UI_BAR_SCALE,
    )
    tallest = 0
    if hp_bar is not None:
        tallest = hp_bar.get_height()
    if giga_bar is not None:
        tallest = max(tallest, giga_bar.get_height())
    return hp_bar, giga_bar, tallest


def _get_pause_menu_layout():
    # keep all the sliding pause-menu geometry in one place so draw code stays readable
    pause_panel_scale = min(
        (HEIGHT - 24) / pause_menu_panel_raw.get_height(),
        (WIDTH * 0.44) / pause_menu_panel_raw.get_width(),
    )
    pause_panel_ratio = pause_panel_scale / max(0.0001, PAUSE_MENU_REFERENCE_PANEL_SCALE)
    panel_w = int(round(pause_menu_panel_raw.get_width() * pause_panel_scale))
    panel_h = int(round(pause_menu_panel_raw.get_height() * pause_panel_scale))
    target_x = WIDTH - panel_w - PAUSE_MENU_RIGHT_MARGIN
    panel_x = int(round(WIDTH + ((target_x - WIDTH) * pause_slide)))
    panel_y = (HEIGHT - panel_h) // 2
    guide_scale = pause_panel_scale / 2.0

    def guide_pos(x, y):
        return (
            panel_x + int(round(x * guide_scale)),
            panel_y + int(round(y * guide_scale)),
        )

    separator_source = _crop_alpha_surface(pause_menu_separator_raw)
    separator_left = panel_x + int(round(8 * pause_panel_scale))
    separator_right = panel_x + panel_w - int(round(8 * pause_panel_scale))
    separator_rect = pygame.Rect(
        separator_left,
        guide_pos(124, 160)[1],
        max(1, separator_right - separator_left),
        max(1, int(round(separator_source.get_height() * guide_scale))),
    )
    top_content = pygame.Rect(
        panel_x + int(round(18 * pause_panel_scale)),
        panel_y + int(round(15 * pause_panel_scale)),
        panel_w - int(round(36 * pause_panel_scale)),
        int(round(104 * pause_panel_scale)),
    )
    bottom_content = pygame.Rect(
        panel_x + int(round(18 * pause_panel_scale)),
        panel_y + int(round(135 * pause_panel_scale)),
        panel_w - int(round(36 * pause_panel_scale)),
        int(round(236 * pause_panel_scale)),
    )
    face_area = pygame.Rect(
        panel_x + int(round(137 * guide_scale)),
        panel_y + int(round(20 * guide_scale)),
        int(round(82 * guide_scale)),
        int(round(104 * guide_scale)),
    )
    return {
        "pause_panel_scale": pause_panel_scale,
        "pause_panel_ratio": pause_panel_ratio,
        "panel_w": panel_w,
        "panel_h": panel_h,
        "panel_x": panel_x,
        "panel_y": panel_y,
        "guide_scale": guide_scale,
        "guide_pos": guide_pos,
        "separator_source": separator_source,
        "separator_rect": separator_rect,
        "top_content": top_content,
        "bottom_content": bottom_content,
        "face_area": face_area,
    }


def _draw_status_bars(
    screen,
    arena_ctx,
    arena_player,
    arena_tilemap,
    arena_bounds,
    render_scroll,
    arena_screen_rect,
    viewport_rect,
    arena_scale,
    window_scale,
):
    # hud placement is partly screen-space and partly arena-aware so it does not overlap the walls
    if not arena_ctx or not arena_player or not arena_tilemap:
        return
    if _intro_vile_hide_status_bars(arena_ctx):
        return

    tile_screen = int(round(arena_tilemap.tile_size * arena_scale * window_scale))
    hp_bar, giga_bar, tallest = _get_player_status_bars(arena_ctx, arena_player)
    if hp_bar is None:
        return

    arena_left = arena_screen_rect.left
    arena_top = arena_screen_rect.top
    hud_left = arena_left + tile_screen + UI_BAR_MARGIN_X
    hud_top = arena_top + tile_screen + UI_BAR_MARGIN_Y

    if arena_bounds and render_scroll and viewport_rect:
        ox, oy, _, _ = arena_bounds
        scale_x = arena_screen_rect.width / ARENA_W
        scale_y = arena_screen_rect.height / ARENA_H
        left_wall_screen = arena_screen_rect.left + ((ox - render_scroll[0]) * scale_x)
        top_wall_screen = arena_screen_rect.top + ((oy - render_scroll[1]) * scale_y)
        free_left = viewport_rect.left + UI_BAR_MARGIN_X
        free_top = viewport_rect.top + UI_BAR_MARGIN_Y + UI_BAR_FREE_TOP_OFFSET
        clamped_left = int(round(left_wall_screen + tile_screen + UI_BAR_MARGIN_X))
        clamped_top = int(round(top_wall_screen + tile_screen + UI_BAR_MARGIN_Y))
        hud_left = max(free_left, clamped_left)
        hud_top = max(free_top, clamped_top)

    hp_pos = (hud_left, hud_top + tallest - hp_bar.get_height())
    screen.blit(hp_bar, hp_pos)

    if giga_bar is not None:
        giga_pos = (
            hp_pos[0] + hp_bar.get_width() + UI_BAR_GAP,
            hud_top + tallest - giga_bar.get_height(),
        )
        screen.blit(giga_bar, giga_pos)


def _get_cached_minimap_panel(arena_ctx, arena_tilemap, tile_size=MINIMAP_TILE_SIZE):
    # build the static minimap panel once per stage layout, then only stamp the player marker later
    if not arena_ctx or not arena_tilemap:
        return None
    cache_key = (
        getattr(arena_ctx, "stage_key", None),
        arena_tilemap.start_x,
        arena_tilemap.start_y,
        arena_tilemap.width,
        arena_tilemap.height,
        arena_tilemap.tile_size,
        tile_size,
    )
    cached = _MINIMAP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    map_w = arena_tilemap.width * tile_size
    map_h = arena_tilemap.height * tile_size
    panel_w = map_w + (MINIMAP_PADDING * 2) + (MINIMAP_BORDER * 2)
    panel_h = map_h + (MINIMAP_PADDING * 2) + (MINIMAP_BORDER * 2)
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    outer = panel.get_rect()
    inner = outer.inflate(-MINIMAP_BORDER * 2, -MINIMAP_BORDER * 2)
    core = inner.inflate(-MINIMAP_PADDING * 2, -MINIMAP_PADDING * 2)

    pygame.draw.rect(panel, (245, 245, 245, 255), outer, border_radius=4)
    pygame.draw.rect(panel, (122, 132, 142, 255), inner, border_radius=3)
    pygame.draw.rect(panel, (10, 16, 24, 232), core, border_radius=2)

    solid_surface = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
    for tile in arena_tilemap.tilemap.values():
        if tile['type'] not in ('stone', 'grass'):
            continue
        rel_x = tile['pos'][0] - arena_tilemap.start_x
        rel_y = tile['pos'][1] - arena_tilemap.start_y
        if not (0 <= rel_x < arena_tilemap.width and 0 <= rel_y < arena_tilemap.height):
            continue
        tile_rect = pygame.Rect(
            rel_x * tile_size,
            rel_y * tile_size,
            tile_size,
            tile_size,
        )
        solid_surface.fill((188, 198, 216, 255), tile_rect)
        if tile_size >= 3:
            highlight = pygame.Rect(tile_rect.x, tile_rect.y, tile_rect.w, 1)
            solid_surface.fill((232, 236, 242, 255), highlight)
    panel.blit(solid_surface, (MINIMAP_BORDER + MINIMAP_PADDING, MINIMAP_BORDER + MINIMAP_PADDING))

    cached = {
        "panel": panel,
        "map_rect": pygame.Rect(
            MINIMAP_BORDER + MINIMAP_PADDING,
            MINIMAP_BORDER + MINIMAP_PADDING,
            map_w,
            map_h,
        ),
    }
    _MINIMAP_CACHE[cache_key] = cached
    return cached


def _get_minimap_surface_with_player(
    arena_ctx,
    arena_player,
    arena_tilemap,
    arena_bounds,
    tile_size=MINIMAP_TILE_SIZE,
):
    cached = _get_cached_minimap_panel(arena_ctx, arena_tilemap, tile_size=tile_size)
    if not cached or not arena_player or not arena_bounds:
        return None

    panel = cached["panel"].copy()
    map_rect = cached["map_rect"]

    ox, oy, w, h = arena_bounds
    player_rect = arena_player.rect()
    px = (player_rect.centerx - ox) / max(1, w)
    py = ((player_rect.bottom - 1) - oy) / max(1, h)
    marker_x = int(round(map_rect.left + px * (map_rect.width - 1)))
    marker_y = int(round(map_rect.top + py * (map_rect.height - 1)))
    marker_icon = minimap_player_icon_flipped if arena_player.flip else minimap_player_icon
    marker_rect = marker_icon.get_rect(midbottom=(marker_x, marker_y + 1))
    marker_rect.clamp_ip(map_rect.inflate(-2, -2))
    panel.blit(marker_icon, marker_rect)
    return panel


def _draw_minimap(
    screen,
    arena_ctx,
    arena_player,
    arena_tilemap,
    arena_bounds,
    render_scroll,
    arena_screen_rect,
    viewport_rect,
):
    # minimap tries to live in the free ui corner but still respects arena wall clamping
    panel = _get_minimap_surface_with_player(
        arena_ctx,
        arena_player,
        arena_tilemap,
        arena_bounds,
        tile_size=MINIMAP_TILE_SIZE,
    )
    if panel is None:
        return

    tile_screen = int(round(arena_tilemap.tile_size * (arena_screen_rect.width / ARENA_W)))
    minimap_left = viewport_rect.right - panel.get_width() - MINIMAP_MARGIN_X
    minimap_top = viewport_rect.top + MINIMAP_MARGIN_Y + MINIMAP_FREE_TOP_OFFSET

    if render_scroll:
        scale_x = arena_screen_rect.width / ARENA_W
        scale_y = arena_screen_rect.height / ARENA_H
        right_wall_screen = arena_screen_rect.left + (((ox + w) - render_scroll[0]) * scale_x)
        top_wall_screen = arena_screen_rect.top + ((oy - render_scroll[1]) * scale_y)
        clamped_left = int(round(right_wall_screen - tile_screen - MINIMAP_MARGIN_X - panel.get_width()))
        clamped_top = int(round(top_wall_screen + tile_screen + MINIMAP_MARGIN_Y))
        minimap_left = min(minimap_left, clamped_left)
        minimap_top = max(minimap_top, clamped_top)

    screen.blit(panel, (minimap_left, minimap_top))


def draw_pause_menu():
    # full pause overlay, including the player portrait, stats, and confirmation sub-state
    if pause_slide <= 0.001 or not arena_ctx or not arena_player or not arena_tilemap:
        return

    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, int(PAUSE_DIM_ALPHA * pause_slide)))
    game_surface.blit(dim, (0, 0))

    layout = _get_pause_menu_layout()
    pause_panel_scale = layout["pause_panel_scale"]
    pause_panel_ratio = layout["pause_panel_ratio"]
    panel_w = layout["panel_w"]
    panel_h = layout["panel_h"]
    panel_x = layout["panel_x"]
    panel_y = layout["panel_y"]
    guide_scale = layout["guide_scale"]
    guide_pos = layout["guide_pos"]
    top_content = layout["top_content"]
    bottom_content = layout["bottom_content"]
    face_area = layout["face_area"]
    separator_source = layout["separator_source"]
    separator_rect = layout["separator_rect"].copy()
    panel = pygame.transform.scale(pause_menu_panel_raw, (panel_w, panel_h))
    game_surface.blit(panel, (panel_x, panel_y))
    separator_img = pygame.transform.scale(
        separator_source,
        (separator_rect.width, separator_rect.height),
    )
    game_surface.blit(separator_img, separator_rect)

    minimap_panel = None
    if current_stage != "intro_stage":
        minimap_panel = _get_minimap_surface_with_player(
            arena_ctx,
            arena_player,
            arena_tilemap,
            arena_bounds,
            tile_size=PAUSE_MINIMAP_TILE_SIZE,
        )
    if minimap_panel is not None:
        available_w = int(round(154 * guide_scale))
        available_h = int(round(114 * guide_scale))
        scale_ratio = min(
            available_w / minimap_panel.get_width(),
            available_h / minimap_panel.get_height(),
            1.0,
        )
        if scale_ratio < 1.0:
            minimap_panel = pygame.transform.scale(
                minimap_panel,
                (
                    max(1, int(minimap_panel.get_width() * scale_ratio)),
                    max(1, int(minimap_panel.get_height() * scale_ratio)),
                ),
            )

    if pause_zero_face_anim:
        face_img = pause_zero_face_anim.img()
    elif pause_zero_face_source and pause_zero_face_source.images:
        face_img = _compose_face_frame(pause_zero_face_source.images[0])
    else:
        face_img = minimap_player_icon
    face_scale = min(
        face_area.width / max(1, face_img.get_width()),
        face_area.height / max(1, face_img.get_height()),
    )
    face_scale *= PAUSE_FACE_SCALE_MULTIPLIER
    face_target = (
        max(1, int(round(face_img.get_width() * face_scale))),
        max(1, int(round(face_img.get_height() * face_scale))),
    )
    face_scaled = pygame.transform.scale(face_img, face_target)
    face_draw = face_scaled.get_rect(
        midright=(
            face_area.right - int(round(PAUSE_FACE_X_OFFSET * guide_scale)),
            face_area.centery + int(round(8 * guide_scale)),
        )
    )
    game_surface.blit(face_scaled, face_draw)

    option_x, option_y = guide_pos(30, 173)
    line_gap = int(round(16 * guide_scale))
    item_gap = int(round(34 * guide_scale))
    option_text_scale = 2.3 * pause_panel_ratio
    option_letter_spacing = -17.5 * pause_panel_ratio
    option_space_width = max(1, int(round(30 * pause_panel_ratio)))
    option_blocks = _get_pause_menu_option_blocks()
    for idx, lines in enumerate(option_blocks):
        highlighted = idx == pause_selected_index
        block_y = option_y + (idx * item_gap)
        if len(lines) == 1:
            block_y += int(round(line_gap * 0.95))
        for line_idx, text in enumerate(lines):
            draw_text_left_on(
                game_surface,
                text,
                option_x + int(round(16 * guide_scale)),
                block_y + (line_idx * line_gap),
                highlighted=highlighted,
                scale=option_text_scale,
                force_upper=True,
                letter_spacing=option_letter_spacing,
                space_width=option_space_width,
            )
        if highlighted:
            cursor_mid_y = block_y + ((len(lines) - 1) * line_gap) // 2 + int(round(10 * guide_scale))
            cursor_points = [
                (option_x, cursor_mid_y),
                (option_x + int(round(10 * guide_scale)), cursor_mid_y - int(round(6 * guide_scale))),
                (option_x + int(round(10 * guide_scale)), cursor_mid_y + int(round(6 * guide_scale))),
            ]
            pygame.draw.polygon(game_surface, (255, 208, 64), cursor_points)

    if minimap_panel is not None:
        minimap_draw = minimap_panel.get_rect()
        minimap_draw.center = guide_pos(124, 334)
        game_surface.blit(minimap_panel, minimap_draw)

    if pause_confirm_active:
        box = pygame.Rect(0, 0, 440, 150)
        box.center = (WIDTH // 2, HEIGHT // 2 + 8)
        shadow = box.move(6, 6)
        pygame.draw.rect(game_surface, (0, 0, 0), shadow, border_radius=8)
        pygame.draw.rect(game_surface, (34, 42, 58), box, border_radius=8)
        pygame.draw.rect(game_surface, (214, 224, 242), box, width=4, border_radius=8)
        prompt = "SKIP INTRO STAGE?"
        draw_text_centered_on(game_surface, prompt, box.top + 24, scale=2.2, letter_spacing=-15)
        options = ("YES", "NO")
        option_y = box.top + 82
        left_x = box.centerx - 104
        right_x = box.centerx + 24
        for idx, label in enumerate(options):
            x = left_x if idx == 0 else right_x
            highlighted = idx == pause_confirm_choice
            draw_text_left_on(game_surface, label, x, option_y, highlighted=highlighted, scale=2.3, letter_spacing=-15)


def draw_arena_result():
    if not arena_result_data:
        return
    game_surface.fill((0, 0, 0))
    heading = arena_result_data.get("heading", "")
    subheading = arena_result_data.get("subheading", "")
    stage_label = arena_result_data.get("stage_label", "")
    score_text = f"SCORE: {int(arena_result_data.get('score', 0)):06d}"
    time_text = f"TIME: {_format_elapsed_time(arena_result_data.get('elapsed_time', 0.0))}"
    step = arena_result_data.get("step", "banner")

    draw_text_centered_on(game_surface, heading, 150, highlighted=True, scale=3.2, letter_spacing=-16)
    if subheading:
        draw_text_centered_on(game_surface, subheading, 214, scale=2.3, letter_spacing=-15)
    draw_text_centered_on(game_surface, stage_label, 292, scale=1.9, letter_spacing=-14)
    draw_text_centered_on(game_surface, score_text, 348, scale=1.9, letter_spacing=-14)
    draw_text_centered_on(game_surface, time_text, 390, scale=1.9, letter_spacing=-14)

    panel = pygame.Rect(0, 0, 760, 244)
    panel.center = (WIDTH // 2, 658)
    pygame.draw.rect(game_surface, (22, 28, 38), panel, border_radius=8)
    pygame.draw.rect(game_surface, (190, 202, 220), panel, width=4, border_radius=8)

    if step == "banner":
        draw_text_centered_on(game_surface, "PRESS ANY BUTTON", panel.top + 76, scale=2.5, letter_spacing=-16)
        draw_text_centered_on(game_surface, "TO CONTINUE", panel.top + 120, scale=2.0, letter_spacing=-15)
    elif step == "save_prompt":
        draw_text_centered_on(game_surface, "SAVE RECORD TO LEADERBOARD?", panel.top + 34, scale=2.15, letter_spacing=-15)
        options = ("YES", "NO")
        for idx, label in enumerate(options):
            x = panel.centerx - 128 if idx == 0 else panel.centerx + 34
            draw_text_left_on(
                game_surface,
                label,
                x,
                panel.top + 108,
                highlighted=idx == arena_result_data.get("save_choice", 0),
                scale=2.5,
                letter_spacing=-16,
            )
    elif step == "name_input":
        entered = str(arena_result_data.get("name_input", ""))
        caret = "_" if (pygame.time.get_ticks() // 300) % 2 == 0 else ""
        display_name = (entered + caret) if len(entered) < 12 else entered
        draw_text_centered_on(game_surface, "ENTER NAME", panel.top + 26, scale=2.3, letter_spacing=-15)
        input_box = pygame.Rect(panel.left + 68, panel.top + 92, panel.width - 136, 72)
        pygame.draw.rect(game_surface, (8, 12, 18), input_box, border_radius=6)
        pygame.draw.rect(game_surface, (214, 224, 242), input_box, width=3, border_radius=6)
        draw_text_centered_on(game_surface, display_name or "_", input_box.top + 18, scale=2.4, letter_spacing=-15)


def draw_pause_menu_overlay(screen, x_offset, y_offset, window_scale):
    if pause_slide <= 0.001 or not arena_ctx or not arena_player:
        return

    layout = _get_pause_menu_layout()
    guide_pos = layout["guide_pos"]
    guide_scale = layout["guide_scale"]
    pause_panel_ratio = layout["pause_panel_ratio"]
    separator_rect = layout["separator_rect"]
    panel_x = layout["panel_x"]
    panel_w = layout["panel_w"]

    def to_screen(x, y):
        return (
            x_offset + int(round(x * window_scale)),
            y_offset + int(round(y * window_scale)),
        )

    hp_bar, giga_bar, tallest = _get_player_status_bars(arena_ctx, arena_player)
    if hp_bar is not None and not _intro_vile_hide_status_bars(arena_ctx):
        bars_x, bars_y = guide_pos(18 + PAUSE_STATUS_BARS_X_OFFSET, 18)
        bars_screen_x, bars_screen_y = to_screen(bars_x, bars_y)
        hp_y = bars_screen_y + tallest - hp_bar.get_height()
        screen.blit(hp_bar, (bars_screen_x, hp_y))
        if giga_bar is not None:
            giga_x = bars_screen_x + hp_bar.get_width() + UI_BAR_GAP
            giga_y = bars_screen_y + tallest - giga_bar.get_height()
            screen.blit(giga_bar, (giga_x, giga_y))

    score_value = getattr(arena_ctx, "score", 0)
    total_seconds = int(getattr(arena_ctx, "elapsed_time", 0.0))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    stat_scale = 1.9 * pause_panel_ratio * window_scale
    score_label = "SCORE"
    score_separator = ":"
    score_value_text = f"{score_value:06d}"
    time_label = "TIME"
    time_separator = ":"
    time_value = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    stat_letter_spacing = -14 * pause_panel_ratio * window_scale
    stat_space_width = max(1, int(round(30 * pause_panel_ratio * window_scale)))
    score_gap_before_colon = 0
    score_gap_after_colon = max(1, int(round(3 * guide_scale * window_scale)))
    time_gap_before_colon = 0
    time_gap_after_colon = max(1, int(round(3 * guide_scale * window_scale)))

    stat_y = y_offset + int(round(separator_rect.top * window_scale)) - max(1, int(round(38 * window_scale)))
    stat_gap = max(1, int(round(7 * guide_scale * window_scale)))
    while True:
        score_label_w = calculate_text_width_ex(score_label, highlighted=False, scale=stat_scale, force_upper=True, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
        score_separator_w = calculate_text_width_ex(score_separator, highlighted=False, scale=stat_scale, force_upper=True, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
        score_value_w = calculate_text_width_ex(score_value_text, highlighted=False, scale=stat_scale, force_upper=True, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
        score_w = score_label_w + score_gap_before_colon + score_separator_w + score_gap_after_colon + score_value_w
        time_label_w = calculate_text_width_ex(time_label, highlighted=False, scale=stat_scale, force_upper=True, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
        time_separator_w = calculate_text_width_ex(time_separator, highlighted=False, scale=stat_scale, force_upper=True, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
        time_value_w = calculate_text_width_ex(time_value, highlighted=False, scale=stat_scale, force_upper=True, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
        time_w = time_label_w + time_gap_before_colon + time_separator_w + time_gap_after_colon + time_value_w
        total_w = score_w + stat_gap + time_w
        min_stat_scale = 1.6 * pause_panel_ratio * window_scale
        if total_w <= int(round(panel_w * window_scale)) - max(1, int(round(24 * window_scale))) or stat_scale <= min_stat_scale:
            break
        stat_scale = max(min_stat_scale, stat_scale - (0.1 * pause_panel_ratio * window_scale))
        stat_letter_spacing = -14 * pause_panel_ratio * window_scale * (stat_scale / max(0.0001, 1.9 * pause_panel_ratio * window_scale))
    group_x = x_offset + int(round((panel_x + (panel_w / 2)) * window_scale)) - (total_w // 2) - max(1, int(round(9 * window_scale)))
    score_x = group_x
    time_x = group_x + score_w + stat_gap
    draw_text_left_on(screen, score_label, score_x, stat_y, highlighted=False, scale=stat_scale, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
    draw_text_left_on(screen, score_separator, score_x + score_label_w + score_gap_before_colon, stat_y, highlighted=False, scale=stat_scale, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
    draw_text_left_on(screen, score_value_text, score_x + score_label_w + score_gap_before_colon + score_separator_w + score_gap_after_colon, stat_y, highlighted=False, scale=stat_scale, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
    draw_text_left_on(screen, time_label, time_x, stat_y, highlighted=False, scale=stat_scale, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
    draw_text_left_on(screen, time_separator, time_x + time_label_w + time_gap_before_colon, stat_y, highlighted=False, scale=stat_scale, letter_spacing=stat_letter_spacing, space_width=stat_space_width)
    draw_text_left_on(screen, time_value, time_x + time_label_w + time_gap_before_colon + time_separator_w + time_gap_after_colon, stat_y, highlighted=False, scale=stat_scale, letter_spacing=stat_letter_spacing, space_width=stat_space_width)










# ---- Arena Gameplay Types ----


















NEIGHBOR_OFFSETS = [
    (-2, -1), (-1, -1), (0, -1), (1, -1), (2, -1),
    (-2,  0), (-1,  0), (0,  0), (1,  0), (2,  0),
    (-2,  1), (-1,  1), (0,  1), (1,  1), (2,  1),
    (-2,  2), (-1,  2), (0,  2), (1,  2), (2,  2),
    (-2,  3), (-1,  3), (0,  3), (1,  3), (2,  3),
]
PHYSICS_TILES = {'grass', 'stone'}


WINDOW_WIDTH, WINDOW_HEIGHT = 1512, 984
WIDTH, HEIGHT = 1512, 984
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)

game_surface = pygame.Surface((WIDTH, HEIGHT))

fade_surface = pygame.Surface((WIDTH, HEIGHT)).convert()
fade_surface.fill((0, 0, 0))
fade_alpha = 0

pygame.display.set_caption("Arena Survivor")

game_logo = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "title screen logo.png")
).convert_alpha()
minimap_player_icon = _load_minimap_player_icon()
minimap_player_icon_flipped = pygame.transform.flip(minimap_player_icon, True, False)
pause_menu_panel_raw = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "pause_menu.png")
).convert_alpha()
pause_menu_template_raw = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "pause_menu_template.png")
).convert_alpha()
pause_menu_separator_raw = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "pause_menu_separator.png")
).convert_alpha()

font_sheet = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "font.png")
).convert_alpha()

misc_ui_anims = assets_load_spritesheet(
    ASSETS_DIR,
    "miscellaneous/miscellaneous.png",
    "miscellaneous/miscellaneous.json"
)
pause_zero_face_source = misc_ui_anims.get("zero_face", None)
pause_x_face_source = misc_ui_anims.get("x_face_icon", None)
stage_ready_anim_source = misc_ui_anims.get("start_ready", None)

cursor_move_sound = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "cursor moving sound.wav")
)
text_appearing_sound = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "text appearing sound.wav")
)

cursor_select_sound = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "cursor starting sound.wav")
)
menu_start_sound = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "menu start sound.wav")
)
menu_open_sound = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "menu_open.wav")
)
thumbs_up_sound = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "thumbs up sound.wav")
)

capcom_sound = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "capcom_logo_sound.mp3")
)

sfx_ground_slash1 = [
    pygame.mixer.Sound(os.path.join(SFX_DIR, "ground slash 1 type 1.wav")),
    pygame.mixer.Sound(os.path.join(SFX_DIR, "ground slash 1 type 2.wav")),
]
sfx_ground_slash2 = [
    pygame.mixer.Sound(os.path.join(SFX_DIR, "ground slash 2 type 1.wav")),
    pygame.mixer.Sound(os.path.join(SFX_DIR, "ground slash 2 type 2.wav")),
]
sfx_ground_slash3 = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "ground slash 3.wav")
)
sfx_air_wall_slash = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "air wall slash.wav")
)
sfx_spawn = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "spawning sound.wav")
)
sfx_jump_sounds = [
    pygame.mixer.Sound(os.path.join(SFX_DIR, "jumping sound 1.wav")),
    pygame.mixer.Sound(os.path.join(SFX_DIR, "jumping sound 2.wav")),
    pygame.mixer.Sound(os.path.join(SFX_DIR, "jumping sound 3.wav")),
    pygame.mixer.Sound(os.path.join(SFX_DIR, "jumping sound 4.wav")),
]
sfx_land = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "landing sound.wav")
)
sfx_dash = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "dashing sound.wav")
)
sfx_wall_jump = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "wall jumping sound.wav")
)
sfx_wall_jump.set_volume(0.5)
sfx_wall_land = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "wall land sound.wav")
)
sfx_wall_land.set_volume(0.5)

sfx_giga_attack = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "giga attack sound.wav")
)
sfx_life_energy_gain = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "life and energy gain loop short.wav")
)
sfx_hitmarker = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "hitmarker sound.wav")
)
sfx_blocked_hit = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "blocked_hit.wav")
)
sfx_hurt_sounds = [
    pygame.mixer.Sound(os.path.join(SFX_DIR, "hurt sound 1.wav")),
    pygame.mixer.Sound(os.path.join(SFX_DIR, "hurt sound 2.wav")),
]
sfx_death = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "death sound.wav")
)
sfx_enemy_destroyed = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "enemy destroyed.wav")
)
sfx_rocket_fired = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "rocket_fired.wav")
)
sfx_cannon_shoot = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "cannon_shoot.wav")
)
sfx_met_projectile = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "met_projectile.wav")
)
sfx_heavy_shocker = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "heavy_shocker.wav")
)
sfx_nova_strike = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "nova_strike.wav")
)
sfx_x_buster_charging = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "x_buster_charging.wav")
)
_x_buster_loop_path = os.path.join(SFX_DIR, "x_buster_charging_loop.wav")
if not os.path.exists(_x_buster_loop_path):
    _x_buster_loop_path = os.path.join(SFX_DIR, "x_buster_charge_end.wav")
sfx_x_buster_charge_end = pygame.mixer.Sound(_x_buster_loop_path)
sfx_x_buster_charged_shot = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "x_buster_charged_shot.wav")
)
sfx_exiting = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "exiting sound.wav")
)
sfx_warning = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "warning.wav")
)
sfx_vile_jump = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "vile_jump.wav")
)
sfx_vile_step_land_1 = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "vile_step_land_1.wav")
)
sfx_vile_step_land_2 = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "vile_step_land_2.wav")
)
sfx_vile_punch = pygame.mixer.Sound(
    os.path.join(SFX_DIR, "vile_punch.wav")
)
secret_foxy_frames = []
secret_foxy_durations = []
try:
    secret_foxy_sound = pygame.mixer.Sound(
        os.path.join(SECRETS_DIR, "foxy_jumpscare.mp3")
    )
    secret_foxy_sound.set_volume(1.0)
except Exception:
    secret_foxy_sound = None
sfx_enemy_destroyed.set_volume(0.4)
sfx_blocked_hit.set_volume(0.5)
sfx_met_projectile.set_volume(0.62)
sfx_cannon_shoot.set_volume(0.58)
sfx_rocket_fired.set_volume(0.55)
sfx_heavy_shocker.set_volume(0.45)
sfx_nova_strike.set_volume(0.6)
sfx_x_buster_charging.set_volume(0.95)
sfx_x_buster_charge_end.set_volume(0.82)
sfx_x_buster_charged_shot.set_volume(1.0)
sfx_exiting.set_volume(0.5)
sfx_vile_step_land_1.set_volume(0.42)
sfx_vile_step_land_2.set_volume(0.42)


def _ensure_secret_foxy_assets():
    global secret_foxy_frames, secret_foxy_durations, secret_foxy_sound
    if not secret_foxy_frames:
        secret_foxy_frames, secret_foxy_durations = _load_secret_gif_frames(
            os.path.join(SECRETS_DIR, "foxy_jumpscare.gif")
        )
    if secret_foxy_sound is None:
        try:
            secret_foxy_sound = pygame.mixer.Sound(
                os.path.join(SECRETS_DIR, "foxy_jumpscare.mp3")
            )
            secret_foxy_sound.set_volume(1.0)
        except Exception:
            secret_foxy_sound = None

title_intro = os.path.join(
    MUSIC_DIR, "menu", "title theme intro.wav"
)

title_loop = os.path.join(
    MUSIC_DIR, "menu", "title theme loop.wav"
)

stage_select_intro = os.path.join(
    MUSIC_DIR, "stage_select", "stage select theme intro.wav"
)

stage_select_loop = os.path.join(
    MUSIC_DIR, "stage_select", "stage select theme loop.wav"
)

stage_intro_music_intro = os.path.join(
    MUSIC_DIR, "stage_start", "stage start.mp3"
)
boss_battle_music_intro = os.path.join(
    MUSIC_DIR, "boss", "boss battle theme intro.wav"
)
boss_battle_music_loop = os.path.join(
    MUSIC_DIR, "boss", "boss battle theme loop.wav"
)

stage_music = {
    "intro_stage": {
        "intro": os.path.join(MUSIC_DIR, "intro", "intro stage theme intro.wav"),
        "loop": os.path.join(MUSIC_DIR, "intro", "intro stage theme loop.wav"),
    },
    "amazon": {
        "intro": os.path.join(MUSIC_DIR, "amazon", "amazon area theme intro.wav"),
        "loop": os.path.join(MUSIC_DIR, "amazon", "amazon area theme loop.wav"),
    },
    "magma": {
        "intro": os.path.join(MUSIC_DIR, "magma", "magma area theme intro.wav"),
        "loop": os.path.join(MUSIC_DIR, "magma", "magma area theme loop.wav"),
    },
    "northern": {
        "intro": os.path.join(MUSIC_DIR, "northern", "northern area theme intro.wav"),
        "loop": os.path.join(MUSIC_DIR, "northern", "northern area theme loop.wav"),
    },
    "airbase": {
        "intro": os.path.join(MUSIC_DIR, "airbase", "airbase area theme intro.wav"),
        "loop": os.path.join(MUSIC_DIR, "airbase", "airbase area theme loop.wav"),
    },
    "seabase": {
        "intro": os.path.join(MUSIC_DIR, "seabase", "seabase area theme intro.wav"),
        "loop": os.path.join(MUSIC_DIR, "seabase", "seabase area theme loop.wav"),
    },
    "wepcenter": {
        "intro": os.path.join(MUSIC_DIR, "wepcenter", "wepcenter area theme intro.wav"),
        "loop": os.path.join(MUSIC_DIR, "wepcenter", "wepcenter area theme loop.wav"),
    },
}
gateway_music_intro = os.path.join(MUSIC_DIR, "gateway", "gateway theme intro.wav")
gateway_music_loop = os.path.join(MUSIC_DIR, "gateway", "gateway theme loop.wav")


def _db_to_gain(db):
    return 10 ** (db / 20.0)


MUSIC_VOLUME_OVERRIDES = {
    title_intro: _db_to_gain(0.8),
    title_loop: _db_to_gain(-0.4),
    stage_select_intro: _db_to_gain(0.2),
    stage_select_loop: _db_to_gain(0.8),
    stage_intro_music_intro: _db_to_gain(-0.2),
    stage_music["intro_stage"]["intro"]: 1.0,
    stage_music["intro_stage"]["loop"]: 1.0,
    stage_music["amazon"]["intro"]: _db_to_gain(-1.4),
    stage_music["amazon"]["loop"]: _db_to_gain(-0.4),
    stage_music["magma"]["intro"]: _db_to_gain(-3.8),
    stage_music["magma"]["loop"]: _db_to_gain(-2.8),
    stage_music["northern"]["intro"]: _db_to_gain(0.8),
    stage_music["northern"]["loop"]: _db_to_gain(0.8),
    stage_music["airbase"]["intro"]: 1.0,
    stage_music["airbase"]["loop"]: 1.0,
    stage_music["seabase"]["intro"]: _db_to_gain(-4.8),
    stage_music["seabase"]["loop"]: _db_to_gain(-4.0),
    stage_music["wepcenter"]["intro"]: 1.0,
    stage_music["wepcenter"]["loop"]: _db_to_gain(-0.1),
    boss_battle_music_intro: _db_to_gain(1.8),
    boss_battle_music_loop: _db_to_gain(1.8),
}


def _music_volume_for(path):
    return MUSIC_VOLUME_OVERRIDES.get(path, 1.0)


def _current_intro_stage_music_pair():
    if intro_stage_secret_gateway_active:
        return gateway_music_intro, gateway_music_loop
    return stage_music["intro_stage"]["intro"], stage_music["intro_stage"]["loop"]



_stage_view_backgrounds = {}


def _load_stage_view_backgrounds(stage_key):
    cached = _stage_view_backgrounds.get(stage_key)
    if cached is not None:
        return cached

    assets = {}
    if stage_key == "amazon":
        assets["frames"] = load_animated_stage(ASSETS_DIR, WIDTH, HEIGHT, "amazon", "amazon area")
    elif stage_key == "magma":
        assets["frames"] = load_animated_stage(ASSETS_DIR, WIDTH, HEIGHT, "magma", "magma area")
    elif stage_key == "northern":
        bg = pygame.image.load(
            os.path.join(ASSETS_DIR, "stages", "northern", "northern area background1.png")
        ).convert()
        assets["background"] = pygame.transform.scale(bg, (WIDTH, HEIGHT))
        assets["snow_frames"] = load_snow_animation(ASSETS_DIR, WIDTH, HEIGHT)
    elif stage_key == "airbase":
        clouds = pygame.image.load(
            os.path.join(ASSETS_DIR, "stages", "airbase", "airbase area background clouds1.png")
        ).convert_alpha()
        clouds.set_alpha(110)
        airbase_bg = pygame.image.load(
            os.path.join(ASSETS_DIR, "stages", "airbase", "airbase area background1.png")
        ).convert()
        assets["clouds"] = clouds
        assets["airbase"] = airbase_bg
        assets["clouds_width"] = clouds.get_width()
        assets["airbase_width"] = airbase_bg.get_width()
    elif stage_key == "seabase":
        seabase_bg = pygame.image.load(
            os.path.join(ASSETS_DIR, "stages", "seabase", "seabase area background1.png")
        ).convert()
        scale_factor = HEIGHT / seabase_bg.get_height()
        seabase_bg = pygame.transform.scale(
            seabase_bg,
            (int(seabase_bg.get_width() * scale_factor), HEIGHT)
        )
        assets["background"] = seabase_bg
        assets["width"] = seabase_bg.get_width()
    elif stage_key == "wepcenter":
        assets["frames"] = load_animated_stage(ASSETS_DIR, WIDTH, HEIGHT, "wepcenter", "wepcenter area")

    _stage_view_backgrounds[stage_key] = assets
    return assets


snow_index = 0
snow_timer = 0
SNOW_ANIMATION_SPEED = 3

airbase_x = 0
clouds_x = 0

AIRBASE_SCROLL_SPEED = 2.0
CLOUDS_SCROLL_SPEED = 4.0

seabase_x = 0
SEABASE_SCROLL_SPEED = 10.0

current_stage = None

# ---- ARENA GAMEPLAY STATE ----
arena_assets_cache = {}
arena_anim_offsets_cache = {}
arena_ctx = None
arena_player = None
arena_copters = []
arena_enemy_projectiles = []
arena_tilemap = None
arena_movement = [False, False]
arena_key_movement = [False, False]
arena_joy_dir = 0
arena_debug_hitboxes = False
arena_render_scroll = (0, 0)
arena_surface = None
arena_bounds = (0, 0, 0, 0)
ARENA_OFFSCREEN_MARGIN = 48
ARENA_RESPAWN_DELAY_FRAMES = 300
ARENA_RESPAWN_STAGGER_FRAMES = 6
ARENA_RESPAWN_RETRY_DELAY_FRAMES = 6
ARENA_DYNAMIC_ENEMY_POOL = (
    "met",
    "wheel",
    "bird",
    "spike",
    "cannon",
    "heli_rocket",
    "copter_enemy",
    "heavy",
)
ARENA_DYNAMIC_ENEMY_SIZES = {
    "met": (22, 18),
    "wheel": (26, 26),
    "bird": (30, 14),
    "spike": (40, 40),
    "cannon": (26, 26),
    "heli_rocket": (28, 30),
    "copter_enemy": (36, 24),
    "heavy": (34, 40),
}
ARENA_HELICOPTER_TYPES = ("copter_enemy", "heli_rocket")
ARENA_HELICOPTER_TARGET_RATIO = 0.18
ARENA_ENEMY_POPULATION_STEPS = (
    (45.0, 12),
    (90.0, 15),
    (135.0, 18),
    (180.0, 22),
    (240.0, 27),
    (float("inf"), 32),
)
ARENA_DYNAMIC_INITIAL_ENEMY_COUNT = 11
ARENA_DYNAMIC_SPAWN_ZONE_ATTEMPTS = 2
ARENA_DYNAMIC_FILL_ATTEMPT_FACTOR = 4
ARENA_DYNAMIC_RESPAWN_BUDGET_PER_FRAME = 1
ARENA_DYNAMIC_GROWTH_BUDGET_PER_FRAME = 1
ARENA_DYNAMIC_GROWTH_INTERVAL_FRAMES = 5
ARENA_DYNAMIC_TYPE_SEARCH_LIMIT = 4
ARENA_DYNAMIC_TYPE_TARGET_SHARES = {
    "met": 0.12,
    "wheel": 0.15,
    "bird": 0.12,
    "spike": 0.10,
    "cannon": 0.12,
    "heli_rocket": 0.11,
    "copter_enemy": 0.13,
    "heavy": 0.15,
}
ARENA_DYNAMIC_TYPE_CAPS = {
    "heavy": 1,
    "spike": 2,
    "cannon": 2,
    "heli_rocket": 2,
    "copter_enemy": 3,
}
ARENA_DYNAMIC_MIN_SPAWN_DISTANCE = 110
ARENA_DYNAMIC_RECENT_SPAWN_MEMORY = 8
ARENA_ENEMY_NEAR_MARGIN = 64
ARENA_ENEMY_ACTIVE_MARGIN = 160
ARENA_ENEMY_FAR_MARGIN = 320
ARENA_RENDER_CULL_MARGIN = 96
ARENA_LATE_WAVE_THROTTLE_START = 22
ARENA_LATE_WAVE_THROTTLE_HEAVY_START = 27
ARENA_TEST_ENEMY = None
INTRO_STAGE_GUIDED_MODE = True
intro_stage_guided_mode_selected = INTRO_STAGE_GUIDED_MODE
intro_stage_guidance_seen_persistent = set()
intro_stage_guided_giga_unlocked = not INTRO_STAGE_GUIDED_MODE
intro_stage_secret_gateway_active = False
INTRO_STAGE_LAYOUT_CACHE_VERSION = 2
INTRO_STAGE_PLACEMENT_CACHE = None
INTRO_STAGE_PLACEMENT_CACHE_KEY = None
arena_stage_start_active = False
arena_stage_ready_anim = None
ARENA_STAGE_READY_SCALE = 4.0
INTRO_CUTSCENE_PANEL_POP_DURATION = 0.22
INTRO_CUTSCENE_TEXT_SPEED = 16.0
INTRO_CUTSCENE_TEXT_HOLD_MULTIPLIER = 2.6
INTRO_CUTSCENE_TEXT_SOUND_COOLDOWN = 0.07
INTRO_CUTSCENE_FINAL_HOLD = 0.65
INTRO_STAGE_OPENING_DIALOGUE_DELAY = 0.55
INTRO_STAGE_OPENING_X_EXIT_DURATION = 1.12
ARENA_GIGA_BACKGROUND_SCROLL_SPEED = 320.0
ARENA_GIGA_BACKGROUND_OVERSCAN = 1.08
INTRO_VILE_BALCONY_TRIGGER_OFFSET = 150
INTRO_VILE_PLAYER_WALK_TARGET_OFFSET = 238
INTRO_VILE_WARNING_INTERVAL = 0.58
INTRO_VILE_WARNING_COUNT = 3
INTRO_VILE_GRAB_OFFSET_X = -30
INTRO_VILE_GRAB_OFFSET_Y = -8
INTRO_VILE_POST_DIALOGUE_HOLD = 0.4
INTRO_VILE_RESCUE_DIALOGUE = [
    {"speaker": "X", "text": "Are you alright Zero?"},
    {"speaker": "Zero", "text": "I'm ok, thanks."},
    {"speaker": "X", "text": "We have enemy combattants swarming multiple zones."},
    {"speaker": "X", "text": "Dispatch now, I'll catch up with you later."},
]
INTRO_STAGE_GUIDANCE = [
    {
        "id": "basic_combat",
        "x": 590,
        "lines": [
            {
                "speaker": "",
                "text": "Zero is a skilled melee combattant, try pressing (J or LEFT MOUSE on keyboard or Y on controller) to perform saber attacks, and use (SPACE on keyboard or B on controller) to jump on platforms and move ahead.",
            },
        ],
    },
    {
        "id": "dash_mobility",
        "x": 2060,
        "lines": [
            {
                "speaker": "",
                "text": "Press (K or SIDE MOUSE on keyboard or A on controller) to dash forward and gain speed. Holding the button allows for further dashes, and these can be chained with (SPACE on keyboard or B on controller) to perform dash jumps for even better mobility.",
            },
        ],
    },
    {
        "id": "heavy_combo",
        "x": 2525,
        "lines": [
            {
                "speaker": "",
                "text": "Some enemies have much more health than others. Try attacking consecutively and chaining multiple sword hits to defeat them.",
            },
        ],
    },
    {
        "id": "wall_climb",
        "x": 3340,
        "lines": [
            {
                "speaker": "",
                "text": "Zero can perform a double jump or an air dash per air time, as well as latching onto and climbing walls. Try holding (LEFT or RIGHT on keyboard or movement stick d-pad on controller) to slide down a wall, followed by jumps in order to ascend.",
            },
        ],
    },
    {
        "id": "giga_attack",
        "x": 3920,
        "lines": [
            {
                "speaker": "",
                "text": "Surrounded? Try pressing (X on keyboard or X on controller) to unleash a giga attack, wiping enemies on screen. This can only be performed at full energy.",
            },
        ],
    },
]

INTRO_STAGE_CHECKPOINT_IDS = ("dash_mobility", "wall_climb")


def _intro_stage_guidance_x(trigger_id):
    for spec in INTRO_STAGE_GUIDANCE:
        if spec.get("id") == trigger_id:
            return int(spec.get("x", 0))
    return 0


INTRO_STAGE_CHECKPOINT_XS = tuple(
    _intro_stage_guidance_x(trigger_id) for trigger_id in INTRO_STAGE_CHECKPOINT_IDS
)
INTRO_STAGE_FIXED_CONTENT = {
    "enemies": [],
    "pickups": [],
}
INTRO_STAGE_SHOW_PLACEMENT_OVERLAY = False

# lightweight container for runtime-only arena state that does not belong on one entity
class ArenaContext:
    pass


def _set_animation_to_frame_index(animation, frame_index):
    if animation is None or not getattr(animation, "images", None):
        return
    target = max(0, min(int(frame_index), len(animation.images) - 1))
    frame_tick = 0
    durations = getattr(animation, "durations", None) or []
    for i in range(target):
        if i < len(durations):
            frame_tick += max(1, int(durations[i]))
    animation.frame = frame_tick
    animation.done = False


def _set_vile_disarmed_pose(ctx, boss, mode="hold"):
    if boss is None or getattr(boss, "expired", False):
        return
    boss.set_action("vile_disarmed")
    timer = getattr(ctx, "intro_vile_disarmed_anim_timer", 0.0)
    if mode == "intro":
        timer += 1.0 / 60.0
        index = min(2, int(timer / 0.09))
    elif mode == "escape":
        timer += 1.0 / 60.0
        index = 3 + (int(timer / 0.09) % 2)
    else:
        index = 2
    ctx.intro_vile_disarmed_anim_timer = timer
    _set_animation_to_frame_index(boss.animation, index)


def _intro_vile_player_control_enabled(ctx):
    return bool(
        ctx
        and getattr(ctx, "intro_vile_sequence_active", False)
        and getattr(ctx, "intro_vile_state", "") == "fight"
    )


def _arena_scripted_input_locked(ctx):
    if not ctx:
        return False
    if getattr(ctx, "intro_opening_active", False) and not getattr(ctx, "cutscene_active", False):
        return True
    if getattr(ctx, "intro_vile_sequence_active", False) and not _intro_vile_player_control_enabled(ctx):
        return True
    return False


def _current_arena_input_dir():
    return (
        (1 if (arena_key_movement[1] or arena_joy_dir > 0) else 0)
        - (1 if (arena_key_movement[0] or arena_joy_dir < 0) else 0)
    )


# small helper so enemy deaths always spawn the same pooled-looking burst
def spawn_enemy_destroyed_effect(ctx, rect):
    if not ctx or not hasattr(ctx, "effects"):
        return
    images = getattr(ctx, "effect_images", {}).get("enemy_destroyed")
    if not images:
        return
    w = images[0].get_width()
    h = images[0].get_height()
    x = rect.centerx - (w / 2)
    y = rect.centery - (h / 2)
    ctx.effects.append(Effect(images, (x, y), img_dur=3, loop=False, layer=1))


def spawn_enemy_drop(ctx, enemy, rect):
    if not ctx or not hasattr(ctx, "pickups"):
        return
    roll_drop = getattr(enemy, "roll_pickup_drop", None)
    if not callable(roll_drop):
        return
    drop = roll_drop()
    if not drop:
        return
    pickup_key = drop.get("pickup_key")
    if not pickup_key:
        return
    amount = drop.get("amount")
    try:
        ctx.pickups.append(
            ArenaPickup(
                ctx,
                pickup_key,
                (rect.centerx, rect.centery),
                amount=amount,
                vel=(0.0, 0.0),
            )
        )
    except Exception:
        pass


def _get_arena_view_rect():
    if not arena_ctx:
        return pygame.Rect(0, 0, ARENA_W, ARENA_H)
    scroll_x, scroll_y = getattr(arena_ctx, "render_scroll", arena_render_scroll)
    return pygame.Rect(int(scroll_x), int(scroll_y), ARENA_W, ARENA_H)


# dynamic fills are only for the looping arena mode, not the scripted intro stage
def _dynamic_arena_spawns_enabled():
    return current_stage != "intro_stage" and ARENA_TEST_ENEMY is None


def _arena_target_enemy_count(elapsed_seconds):
    elapsed = max(0.0, float(elapsed_seconds))
    for threshold, target in ARENA_ENEMY_POPULATION_STEPS:
        if elapsed < threshold:
            return target
    return ARENA_ENEMY_POPULATION_STEPS[-1][1]


def _arena_target_helicopter_count(target_count):
    return max(0, int(round(max(0, target_count) * ARENA_HELICOPTER_TARGET_RATIO)))


def _offscreen_spawn_zones(bounds, view_rect, enemy_size=(36, 24)):
    ox, oy, w, h = bounds
    enemy_w, enemy_h = enemy_size
    margin = ARENA_OFFSCREEN_MARGIN
    arena_rect = pygame.Rect(int(ox), int(oy), int(w), int(h))
    visible = view_rect.inflate(margin * 2, margin * 2)

    zones = []

    left_w = visible.left - arena_rect.left - enemy_w
    if left_w > margin:
        zones.append(("left", pygame.Rect(arena_rect.left, arena_rect.top, left_w, arena_rect.height - enemy_h)))

    right_x = visible.right
    right_w = arena_rect.right - right_x - enemy_w
    if right_w > margin:
        zones.append(("right", pygame.Rect(right_x, arena_rect.top, right_w, arena_rect.height - enemy_h)))

    top_h = visible.top - arena_rect.top - enemy_h
    if top_h > margin:
        zones.append(("top", pygame.Rect(arena_rect.left, arena_rect.top, arena_rect.width - enemy_w, top_h)))

    bottom_y = visible.bottom
    bottom_h = arena_rect.bottom - bottom_y - enemy_h
    if bottom_h > margin:
        zones.append(("bottom", pygame.Rect(arena_rect.left, bottom_y, arena_rect.width - enemy_w, bottom_h)))

    return zones


def _choose_offscreen_spawn(bounds, view_rect, enemy_size=(36, 24)):
    ox, oy, w, h = bounds
    enemy_w, enemy_h = enemy_size
    margin = ARENA_OFFSCREEN_MARGIN
    arena_rect = pygame.Rect(int(ox), int(oy), int(w), int(h))
    visible = view_rect.inflate(margin * 2, margin * 2)
    zones = _offscreen_spawn_zones(bounds, view_rect, enemy_size=enemy_size)

    random.shuffle(zones)
    for _, zone in zones:
        if zone.width <= 0 or zone.height <= 0:
            continue
        x = random.randint(zone.left, zone.right)
        y = random.randint(zone.top, zone.bottom)
        enemy_rect = pygame.Rect(x, y, enemy_w, enemy_h)
        if not enemy_rect.colliderect(visible):
            return x, y

    fallback_x = arena_rect.left + margin
    fallback_y = arena_rect.top + margin
    if arena_player:
        player_x, player_y = arena_player.sprite_focus_point()
        corners = [
            (arena_rect.left + margin, arena_rect.top + margin),
            (arena_rect.right - enemy_w - margin, arena_rect.top + margin),
            (arena_rect.left + margin, arena_rect.bottom - enemy_h - margin),
            (arena_rect.right - enemy_w - margin, arena_rect.bottom - enemy_h - margin),
        ]
        fallback_x, fallback_y = max(
            corners,
            key=lambda pos: math.hypot((pos[0] + enemy_w / 2) - player_x, (pos[1] + enemy_h / 2) - player_y),
        )
    return int(fallback_x), int(fallback_y)


def _choose_offscreen_copter_spawn(bounds, view_rect, enemy_size=(36, 24)):
    return _choose_offscreen_spawn(bounds, view_rect, enemy_size=enemy_size)


def _enemy_is_offscreen(enemy, view_rect=None, margin=None):
    if enemy is None:
        return False
    view = view_rect or _get_arena_view_rect()
    padding = ARENA_OFFSCREEN_MARGIN if margin is None else int(margin)
    return not enemy.rect().colliderect(view.inflate(padding * 2, padding * 2))


def _arena_enemy_update_divisor(enemy, view_rect=None):
    if enemy is None:
        return 0
    if current_stage == "intro_stage":
        return 1
    if getattr(enemy, "entry_mode", False):
        return 1
    if getattr(enemy, "camera_activation_pending", False):
        return 1
    view = view_rect or _get_arena_view_rect()
    near_rect = view.inflate(ARENA_ENEMY_NEAR_MARGIN * 2, ARENA_ENEMY_NEAR_MARGIN * 2)
    if enemy.rect().colliderect(near_rect):
        return 1
    live_enemy_count = len(arena_copters)
    late_wave_extra = 0
    if live_enemy_count >= ARENA_LATE_WAVE_THROTTLE_HEAVY_START:
        late_wave_extra = 2
    elif live_enemy_count >= ARENA_LATE_WAVE_THROTTLE_START:
        late_wave_extra = 1
    active_rect = view.inflate(ARENA_ENEMY_ACTIVE_MARGIN * 2, ARENA_ENEMY_ACTIVE_MARGIN * 2)
    if enemy.rect().colliderect(active_rect):
        return 2 + late_wave_extra
    far_rect = view.inflate(ARENA_ENEMY_FAR_MARGIN * 2, ARENA_ENEMY_FAR_MARGIN * 2)
    if enemy.rect().colliderect(far_rect):
        return 3 + late_wave_extra
    return 0


def _tick_dormant_enemy(enemy):
    if enemy is None:
        return
    hit_flash_timer = getattr(enemy, "hit_flash_timer", 0)
    if hit_flash_timer > 0:
        enemy.hit_flash_timer = hit_flash_timer - 1
    spawn_delay = getattr(enemy, "spawn_delay", 0)
    if spawn_delay > 0:
        enemy.spawn_delay = spawn_delay - 1
        animation = getattr(enemy, "animation", None)
        if animation is not None:
            animation.update()
        return
    if getattr(enemy, "camera_activation_pending", False):
        animation = getattr(enemy, "animation", None)
        if animation is not None:
            animation.update()


def _arena_render_visible(rect, render_scroll, margin=0):
    view = pygame.Rect(
        int(render_scroll[0]) - margin,
        int(render_scroll[1]) - margin,
        ARENA_W + (margin * 2),
        ARENA_H + (margin * 2),
    )
    return rect.colliderect(view)


def _enemy_center(enemy):
    rect = enemy.rect()
    return float(rect.centerx), float(rect.centery)


def _is_helicopter_enemy_instance(enemy):
    return isinstance(enemy, (ArenaCopterEnemy, ArenaHeliRocketEnemy))


def _current_helicopter_count():
    return sum(1 for enemy in arena_copters if _is_helicopter_enemy_instance(enemy))


def _dynamic_enemy_type_for_instance(enemy):
    if isinstance(enemy, ArenaMetEnemy):
        return "met"
    if isinstance(enemy, ArenaWheelEnemy):
        return "wheel"
    if isinstance(enemy, ArenaBirdEnemy):
        return "bird"
    if isinstance(enemy, ArenaSpikeEnemy):
        return "spike"
    if isinstance(enemy, ArenaCannonEnemy):
        return "cannon"
    if isinstance(enemy, ArenaHeliRocketEnemy):
        return "heli_rocket"
    if isinstance(enemy, ArenaCopterEnemy):
        return "copter_enemy"
    if isinstance(enemy, ArenaHeavyEnemy):
        return "heavy"
    return None


def _current_dynamic_enemy_type_counts():
    counts = defaultdict(int)
    for enemy in arena_copters:
        enemy_type = _dynamic_enemy_type_for_instance(enemy)
        if enemy_type is not None:
            counts[enemy_type] += 1
    return counts


def _spawn_candidate_score(enemy):
    center_x, center_y = _enemy_center(enemy)
    score = 0.0
    if arena_player is not None:
        player_x, player_y = arena_player.sprite_focus_point()
        score += math.hypot(center_x - player_x, center_y - player_y)
    else:
        ox, oy, w, h = arena_bounds
        arena_cx = ox + (w / 2.0)
        arena_cy = oy + (h / 2.0)
        score += math.hypot(center_x - arena_cx, center_y - arena_cy)

    nearby_scores = []
    for other in arena_copters:
        if other is enemy:
            continue
        ox, oy = _enemy_center(other)
        nearby_scores.append(math.hypot(center_x - ox, center_y - oy))
    for ox, oy in getattr(arena_ctx, "recent_enemy_spawn_points", ()):
        nearby_scores.append(math.hypot(center_x - ox, center_y - oy))
    if nearby_scores:
        score += min(nearby_scores) * 1.35
    return score


def _enemy_spawn_spacing_ok(enemy, min_distance=None):
    if enemy is None:
        return False
    threshold = float(ARENA_DYNAMIC_MIN_SPAWN_DISTANCE if min_distance is None else min_distance)
    center_x, center_y = _enemy_center(enemy)
    for other in arena_copters:
        ox, oy = _enemy_center(other)
        if math.hypot(center_x - ox, center_y - oy) < threshold:
            return False
    for ox, oy in getattr(arena_ctx, "recent_enemy_spawn_points", ()):
        if math.hypot(center_x - ox, center_y - oy) < threshold:
            return False
    return True


def _remember_enemy_spawn(enemy):
    if enemy is None or arena_ctx is None:
        return
    memory = list(getattr(arena_ctx, "recent_enemy_spawn_points", []))
    memory.append(_enemy_center(enemy))
    if len(memory) > ARENA_DYNAMIC_RECENT_SPAWN_MEMORY:
        memory = memory[-ARENA_DYNAMIC_RECENT_SPAWN_MEMORY:]
    arena_ctx.recent_enemy_spawn_points = memory


def _spawn_bird_enemy_at(center_x, center_y, move_dir, flight_slope=0.0, *, spawn_delay=0):
    if not arena_ctx:
        return None
    enemy = ArenaBirdEnemy(
        arena_ctx,
        (center_x, center_y),
        move_dir=move_dir,
        flight_slope=flight_slope,
        spawn_delay=spawn_delay,
    )
    rect = enemy.rect()
    rect.center = (int(round(center_x)), int(round(center_y)))
    ox, oy = enemy._hitbox_offsets()
    enemy.pos[0] = float(rect.x - ox)
    enemy.pos[1] = float(rect.y - oy)
    _resolve_enemy_spawn_position(enemy, grounded=False)
    if _rect_collides_tilemap(arena_tilemap, enemy.rect()):
        return None
    return enemy


def _bird_spawn_parameters(zone_name, zone_rect, view_rect):
    player_x = view_rect.centerx
    player_y = view_rect.centery
    if arena_player is not None:
        player_x, player_y = arena_player.sprite_focus_point()
    player_y = max(zone_rect.top, min(player_y, zone_rect.bottom))
    if zone_name == "left":
        move_dir = 1
        center_x = zone_rect.left
    elif zone_name == "right":
        move_dir = -1
        center_x = zone_rect.right
    else:
        move_dir = 1 if player_x < view_rect.centerx else -1
        center_x = zone_rect.left if move_dir > 0 else zone_rect.right
    target_y = player_y + random.uniform(-12.0, 12.0)
    spawn_y = max(zone_rect.top, min(zone_rect.bottom, target_y + random.uniform(-40.0, 40.0)))
    travel_frames = max(12.0, abs(player_x - center_x) / max(0.001, 3.2))
    flight_slope = (target_y - spawn_y) / travel_frames
    flight_slope = max(-0.75, min(0.75, flight_slope))
    return center_x, spawn_y, move_dir, flight_slope


def _spawn_spike_enemy_offscreen(zone_name, zone_rect, *, spawn_delay=0):
    attempts = 12
    for _ in range(attempts):
        if zone_rect.width <= 0 or zone_rect.height <= 0:
            break
        if zone_name == "left":
            center_y = random.randint(zone_rect.top, zone_rect.bottom)
            enemy = _spawn_spike_wall_enemy(
                center_y,
                surface_normal=(1, 0),
                move_dir=random.choice((-1, 1)),
                spawn_delay=spawn_delay,
            )
        elif zone_name == "right":
            center_y = random.randint(zone_rect.top, zone_rect.bottom)
            enemy = _spawn_spike_wall_enemy(
                center_y,
                surface_normal=(-1, 0),
                move_dir=random.choice((-1, 1)),
                spawn_delay=spawn_delay,
            )
        elif zone_name == "top":
            center_x = random.randint(zone_rect.left, zone_rect.right)
            center_y = random.randint(zone_rect.top, zone_rect.bottom)
            enemy = _spawn_spike_underside_enemy(
                center_x,
                center_y,
                move_dir=random.choice((-1, 1)),
                spawn_delay=spawn_delay,
            )
        else:
            center_x = random.randint(zone_rect.left, zone_rect.right)
            center_y = random.randint(zone_rect.top, zone_rect.bottom)
            enemy = _spawn_spike_enemy(
                center_x,
                center_y,
                surface_normal=(0, -1),
                move_dir=random.choice((-1, 1)),
                spawn_delay=spawn_delay,
            )
        if enemy is not None and _enemy_is_offscreen(enemy):
            return enemy
    return None


def _spawn_enemy_type_offscreen(enemy_type, *, spawn_delay=0):
    if not arena_ctx or not arena_bounds:
        return None
    view_rect = _get_arena_view_rect()
    enemy_size = ARENA_DYNAMIC_ENEMY_SIZES.get(enemy_type, (32, 32))
    zones = _offscreen_spawn_zones(arena_bounds, view_rect, enemy_size=enemy_size)
    if enemy_type == "bird":
        side_zones = [spec for spec in zones if spec[0] in ("left", "right")]
        if side_zones:
            zones = side_zones
    random.shuffle(zones)
    ground_enemy_map = {
        "met": ArenaMetEnemy,
        "wheel": ArenaWheelEnemy,
        "cannon": ArenaCannonEnemy,
        "heavy": ArenaHeavyEnemy,
    }
    air_enemy_map = {
        "copter_enemy": ArenaCopterEnemy,
        "heli_rocket": ArenaHeliRocketEnemy,
    }

    best_enemy = None
    best_score = None
    for zone_name, zone_rect in zones:
        if zone_rect.width <= 0 or zone_rect.height <= 0:
            continue
        for _ in range(ARENA_DYNAMIC_SPAWN_ZONE_ATTEMPTS):
            enemy = None
            if enemy_type in ground_enemy_map:
                center_x = random.randint(zone_rect.left, zone_rect.right)
                preferred_y = random.randint(zone_rect.top, zone_rect.bottom)
                enemy = _spawn_ground_enemy_at(
                    ground_enemy_map[enemy_type],
                    center_x,
                    preferred_y,
                    spawn_delay=spawn_delay,
                )
            elif enemy_type in air_enemy_map:
                center_x = random.randint(zone_rect.left, zone_rect.right)
                center_y = random.randint(zone_rect.top, zone_rect.bottom)
                enemy = _spawn_air_enemy(
                    air_enemy_map[enemy_type],
                    center_x,
                    center_y,
                    spawn_delay=spawn_delay,
                )
            elif enemy_type == "bird":
                center_x, center_y, move_dir, flight_slope = _bird_spawn_parameters(zone_name, zone_rect, view_rect)
                enemy = _spawn_bird_enemy_at(
                    center_x,
                    center_y,
                    move_dir,
                    flight_slope,
                    spawn_delay=spawn_delay,
                )
            elif enemy_type == "spike":
                enemy = _spawn_spike_enemy_offscreen(zone_name, zone_rect, spawn_delay=spawn_delay)
            if enemy is None or not _enemy_is_offscreen(enemy, view_rect=view_rect):
                continue
            if not _enemy_spawn_spacing_ok(enemy):
                continue
            score = _spawn_candidate_score(enemy)
            if best_score is None or score > best_score:
                best_enemy = enemy
                best_score = score
    return best_enemy


# bias the random pick using current population so the arena stays mixed instead of spammy
def _choose_dynamic_enemy_type():
    target_count = int(getattr(arena_ctx, "dynamic_enemy_target", _arena_target_enemy_count(getattr(arena_ctx, "elapsed_time", 0.0))) or 0)
    target_helicopters = _arena_target_helicopter_count(target_count)
    current_helicopters = _current_helicopter_count()
    type_counts = _current_dynamic_enemy_type_counts()

    def under_cap(enemy_type):
        cap = ARENA_DYNAMIC_TYPE_CAPS.get(enemy_type)
        if cap is None:
            return True
        return type_counts.get(enemy_type, 0) < cap

    if current_helicopters < target_helicopters:
        primary_pool = [enemy_type for enemy_type in ARENA_HELICOPTER_TYPES if under_cap(enemy_type)]
        secondary_pool = [enemy_type for enemy_type in ARENA_DYNAMIC_ENEMY_POOL if enemy_type not in ARENA_HELICOPTER_TYPES and under_cap(enemy_type)]
    elif current_helicopters > target_helicopters:
        primary_pool = [enemy_type for enemy_type in ARENA_DYNAMIC_ENEMY_POOL if enemy_type not in ARENA_HELICOPTER_TYPES and under_cap(enemy_type)]
        secondary_pool = [enemy_type for enemy_type in ARENA_HELICOPTER_TYPES if under_cap(enemy_type)]
    else:
        primary_pool = [enemy_type for enemy_type in ARENA_DYNAMIC_ENEMY_POOL if under_cap(enemy_type)]
        secondary_pool = []
    if not primary_pool and not secondary_pool:
        primary_pool = list(ARENA_DYNAMIC_ENEMY_POOL)

    def sort_pool(pool):
        ranked = []
        for enemy_type in pool:
            share = float(ARENA_DYNAMIC_TYPE_TARGET_SHARES.get(enemy_type, 0.0))
            desired_count = share * max(1, target_count)
            deficit = desired_count - type_counts.get(enemy_type, 0)
            ranked.append((deficit, random.random(), enemy_type))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [enemy_type for _, _, enemy_type in ranked]

    return sort_pool(primary_pool) + sort_pool(secondary_pool)


def _spawn_random_arena_enemy_offscreen(*, spawn_delay=0):
    enemy_types = _choose_dynamic_enemy_type()
    if ARENA_DYNAMIC_TYPE_SEARCH_LIMIT > 0:
        enemy_types = enemy_types[:ARENA_DYNAMIC_TYPE_SEARCH_LIMIT]
    for enemy_type in enemy_types:
        enemy = _spawn_enemy_type_offscreen(enemy_type, spawn_delay=spawn_delay)
        if enemy is not None:
            return enemy
    return None


def _fill_dynamic_arena_enemy_slots(target_count):
    if not _dynamic_arena_spawns_enabled() or target_count <= 0:
        return
    attempts = max(target_count * ARENA_DYNAMIC_FILL_ATTEMPT_FACTOR, 6)
    while len(arena_copters) < target_count and attempts > 0:
        enemy = _spawn_random_arena_enemy_offscreen()
        if enemy is not None:
            arena_copters.append(enemy)
            _remember_enemy_spawn(enemy)
        attempts -= 1


def _sync_dynamic_arena_enemy_population(force_fill=False):
    if not _dynamic_arena_spawns_enabled() or not arena_ctx:
        return
    target_count = _arena_target_enemy_count(getattr(arena_ctx, "elapsed_time", 0.0))
    pending = getattr(arena_ctx, "pending_enemy_respawns", [])
    queued_growth = int(getattr(arena_ctx, "pending_enemy_growth", 0) or 0)
    arena_ctx.dynamic_enemy_target = target_count
    if force_fill:
        initial_target = min(target_count, ARENA_DYNAMIC_INITIAL_ENEMY_COUNT)
        _fill_dynamic_arena_enemy_slots(initial_target)
        return
    missing = max(0, target_count - len(arena_copters) - len(pending) - queued_growth)
    if missing > 0:
        arena_ctx.pending_enemy_growth = queued_growth + missing


def _update_pending_enemy_respawns():
    if not _dynamic_arena_spawns_enabled() or not arena_ctx:
        return
    updated_respawns = []
    spawn_budget = ARENA_DYNAMIC_RESPAWN_BUDGET_PER_FRAME
    for timer in getattr(arena_ctx, "pending_enemy_respawns", []):
        timer -= 1
        if timer <= 0:
            if spawn_budget > 0:
                enemy = _spawn_random_arena_enemy_offscreen()
                if enemy is not None:
                    arena_copters.append(enemy)
                    _remember_enemy_spawn(enemy)
                    spawn_budget -= 1
                else:
                    updated_respawns.append(ARENA_RESPAWN_RETRY_DELAY_FRAMES * 2)
            else:
                updated_respawns.append(ARENA_RESPAWN_RETRY_DELAY_FRAMES)
            continue
        updated_respawns.append(timer)
    arena_ctx.pending_enemy_respawns = updated_respawns
    growth_remaining = int(getattr(arena_ctx, "pending_enemy_growth", 0) or 0)
    growth_cooldown = int(getattr(arena_ctx, "growth_spawn_cooldown", 0) or 0)
    if growth_cooldown > 0:
        growth_cooldown -= 1
    growth_spawns = min(growth_remaining, ARENA_DYNAMIC_GROWTH_BUDGET_PER_FRAME)
    while growth_spawns > 0 and spawn_budget > 0 and growth_cooldown <= 0:
        enemy = _spawn_random_arena_enemy_offscreen()
        if enemy is None:
            growth_cooldown = 2
            break
        arena_copters.append(enemy)
        _remember_enemy_spawn(enemy)
        growth_remaining -= 1
        growth_spawns -= 1
        spawn_budget -= 1
        growth_cooldown = ARENA_DYNAMIC_GROWTH_INTERVAL_FRAMES
    arena_ctx.pending_enemy_growth = max(0, growth_remaining)
    arena_ctx.growth_spawn_cooldown = max(0, growth_cooldown)


def _spawn_copter_offscreen(spawn_delay=0):
    if not arena_ctx or not arena_bounds:
        return None
    view_rect = _get_arena_view_rect()
    enemy_pos = _choose_offscreen_copter_spawn(arena_bounds, view_rect)
    return ArenaCopterEnemy(arena_ctx, enemy_pos, spawn_delay=spawn_delay)


def _iter_tilemap_collision_rects(tilemap):
    rects = getattr(tilemap, "collision_rects", None)
    if rects is not None:
        return rects
    out = []
    for tile in getattr(tilemap, "tilemap", {}).values():
        if tile.get("type") not in {"grass", "stone"}:
            continue
        tx, ty = tile["pos"]
        out.append(pygame.Rect(tx * tilemap.tile_size, ty * tilemap.tile_size, tilemap.tile_size, tilemap.tile_size))
    return out


def _iter_standable_surfaces(tilemap):
    spans = getattr(tilemap, "platform_spans", None)
    tile_size = getattr(tilemap, "tile_size", 16) or 16
    if spans:
        surfaces = []
        for x0, x1, y in spans:
            if x1 <= x0:
                continue
            surfaces.append(
                pygame.Rect(
                    int(x0 * tile_size),
                    int(y * tile_size),
                    int((x1 - x0) * tile_size),
                    tile_size,
                )
            )
        if surfaces:
            return surfaces
    return [rect for rect in _iter_tilemap_collision_rects(tilemap) if rect.width >= rect.height]


def _find_ground_top_for_x(tilemap, center_x, min_y=None, max_y=None):
    best = None
    for rect in _iter_standable_surfaces(tilemap):
        if rect.left > center_x or rect.right < center_x:
            continue
        if min_y is not None and rect.top < min_y:
            continue
        if max_y is not None and rect.top > max_y:
            continue
        if best is None or rect.top < best.top:
                best = rect
    return None if best is None else best.top


def _find_ground_top_near_x(tilemap, center_x, preferred_y=None, max_distance=144):
    candidates = []
    for rect in _iter_standable_surfaces(tilemap):
        if rect.left > center_x or rect.right < center_x:
            continue
        candidates.append(rect)
    if not candidates:
        return None
    if preferred_y is None:
        return min(candidates, key=lambda rect: rect.top).top
    best = min(candidates, key=lambda rect: (abs(rect.top - preferred_y), rect.top))
    if abs(best.top - preferred_y) <= max_distance:
        return best.top
    return best.top


def _intro_stage_placement_image_path():
    return os.path.join(
        ASSETS_DIR,
        "stages",
        "intro_stage",
        "intro_stage_tileset_enemy_and_pickup_placements.png",
    )


def _intro_stage_base_annotation_path():
    return os.path.join(
        ASSETS_DIR,
        "stages",
        "intro_stage",
        "intro_stage_tileset_newest_annotations.png",
    )


def _intro_stage_crop_offset():
    art_path = os.path.join(
        ASSETS_DIR,
        "stages",
        "intro_stage",
        "intro_stage_full_tileset.png",
    )
    if Image is None or not os.path.isfile(art_path):
        return (0, 0)
    try:
        art_img = Image.open(art_path).convert("RGBA")
    except Exception:
        return (0, 0)
    alpha = art_img.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return (0, 0)
    return (int(bbox[0]), int(bbox[1]))


def _intro_stage_file_signature(label, path):
    if not os.path.isfile(path):
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


# read enemy / pickup placement markup from the intro-stage helper art and cache the result
def _load_intro_stage_marker_layout():
    global INTRO_STAGE_PLACEMENT_CACHE, INTRO_STAGE_PLACEMENT_CACHE_KEY
    placement_path = _intro_stage_placement_image_path()
    base_path = _intro_stage_base_annotation_path()
    if Image is None or not os.path.isfile(placement_path) or not os.path.isfile(base_path):
        return INTRO_STAGE_FIXED_CONTENT
    cache_key = (
        INTRO_STAGE_LAYOUT_CACHE_VERSION,
        _intro_stage_file_signature("placements", placement_path),
        _intro_stage_file_signature("base_annotations", base_path),
    )
    if INTRO_STAGE_PLACEMENT_CACHE is not None and INTRO_STAGE_PLACEMENT_CACHE_KEY == cache_key:
        return INTRO_STAGE_PLACEMENT_CACHE
    cache_path = intro_stage_layout_cache_path()
    packaged_cache_path = os.path.join(
        packaged_intro_stage_cache_dir(),
        "intro_stage_enemy_pickup_layout_cache.json",
    )
    seed_runtime_file(cache_path, packaged_cache_path)

    def _load_layout_from_path(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except Exception:
            return None
        if tuple(cached.get("cache_key", ())) != cache_key:
            return None
        layout = cached.get("layout")
        if isinstance(layout, dict) and "enemies" in layout and "pickups" in layout:
            return layout
        return None

    if os.path.isfile(cache_path):
        layout = _load_layout_from_path(cache_path)
        if layout is not None:
            INTRO_STAGE_PLACEMENT_CACHE = layout
            INTRO_STAGE_PLACEMENT_CACHE_KEY = cache_key
            return layout

    if os.path.isfile(packaged_cache_path):
        layout = _load_layout_from_path(packaged_cache_path)
        if layout is not None:
            try:
                ensure_runtime_dir(os.path.dirname(cache_path))
                shutil.copy2(packaged_cache_path, cache_path)
            except Exception:
                pass
            INTRO_STAGE_PLACEMENT_CACHE = layout
            INTRO_STAGE_PLACEMENT_CACHE_KEY = cache_key
            return layout

    try:
        placement_img = Image.open(placement_path).convert("RGBA")
        base_img = Image.open(base_path).convert("RGBA")
    except Exception:
        return INTRO_STAGE_FIXED_CONTENT
    if placement_img.size != base_img.size:
        return INTRO_STAGE_FIXED_CONTENT
    crop_x, crop_y = _intro_stage_crop_offset()

    width, height = placement_img.size
    enemies = []
    pickups = []
    triggers = []
    visited = set()

    def classify_component(bounds, pixel_count):
        min_x, min_y, max_x, max_y = bounds
        comp_w = max_x - min_x + 1
        comp_h = max_y - min_y + 1
        if pixel_count >= 1600 and 40 <= comp_w <= 44 and 56 <= comp_h <= 60:
            return ("enemy", "heavy")
        if 740 <= pixel_count <= 820 and 37 <= comp_w <= 40 and 30 <= comp_h <= 33:
            return ("enemy", "cannon")
        if 620 <= pixel_count <= 700 and 29 <= comp_w <= 32 and 30 <= comp_h <= 33:
            return ("enemy", "copter_enemy")
        if 930 <= pixel_count <= 1050 and 37 <= comp_w <= 40 and 35 <= comp_h <= 39:
            return ("enemy", "heli_rocket")
        if 660 <= pixel_count <= 740 and 33 <= comp_w <= 36 and 33 <= comp_h <= 36:
            return ("enemy", "wheel")
        if 410 <= pixel_count <= 470 and 21 <= comp_w <= 24 and 38 <= comp_h <= 41:
            return ("enemy", "spike")
        if 410 <= pixel_count <= 470 and 38 <= comp_w <= 41 and 21 <= comp_h <= 24:
            return ("enemy", "spike")
        if 320 <= pixel_count <= 370 and 20 <= comp_w <= 22 and 20 <= comp_h <= 22:
            return ("enemy", "met")
        if 760 <= pixel_count <= 900 and 33 <= comp_w <= 36 and 41 <= comp_h <= 45:
            return ("trigger", "command_room_swarm")
        if 140 <= pixel_count <= 160 and 15 <= comp_w <= 16 and 11 <= comp_h <= 12:
            return ("pickup", "large_hp_pickup")
        if 140 <= pixel_count <= 170 and 13 <= comp_w <= 14 and 13 <= comp_h <= 14:
            return ("pickup", "small_special_ammo_pickup")
        return None

    for y in range(height):
        for x in range(width):
            if (x, y) in visited:
                continue
            base_px = base_img.getpixel((x, y))
            new_px = placement_img.getpixel((x, y))
            if base_px == new_px:
                continue
            if new_px[:3] == (0, 0, 0):
                continue
            stack = [(x, y)]
            visited.add((x, y))
            pixels = []
            min_x = max_x = x
            min_y = max_y = y
            while stack:
                px, py = stack.pop()
                pixels.append((px, py))
                if px < min_x:
                    min_x = px
                if px > max_x:
                    max_x = px
                if py < min_y:
                    min_y = py
                if py > max_y:
                    max_y = py
                for nx, ny in (
                    (px + 1, py),
                    (px - 1, py),
                    (px, py + 1),
                    (px, py - 1),
                    (px + 1, py + 1),
                    (px - 1, py - 1),
                    (px + 1, py - 1),
                    (px - 1, py + 1),
                ):
                    if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                        nbase = base_img.getpixel((nx, ny))
                        nnew = placement_img.getpixel((nx, ny))
                        if nbase != nnew and nnew[:3] != (0, 0, 0):
                            visited.add((nx, ny))
                            stack.append((nx, ny))
            pixel_count = len(pixels)
            classification = classify_component((min_x, min_y, max_x, max_y), pixel_count)
            if classification is None:
                continue
            kind, placement_type = classification
            adj_min_x = min_x - crop_x
            adj_min_y = min_y - crop_y
            adj_max_x = max_x - crop_x
            adj_max_y = max_y - crop_y
            spec = {
                "type": placement_type,
                "x": int(round((adj_min_x + adj_max_x) / 2.0)),
                "y": int(round((adj_min_y + adj_max_y) / 2.0)),
                "bbox": (adj_min_x, adj_min_y, adj_max_x, adj_max_y),
            }
            if kind == "enemy":
                enemies.append(spec)
            elif kind == "pickup":
                pickups.append(spec)
            else:
                triggers.append(spec)

    enemies.sort(key=lambda spec: (spec["x"], spec["y"], spec["type"]))
    pickups.sort(key=lambda spec: (spec["x"], spec["y"], spec["type"]))
    triggers.sort(key=lambda spec: (spec["x"], spec["y"], spec["type"]))

    INTRO_STAGE_PLACEMENT_CACHE = {"enemies": enemies, "pickups": pickups, "triggers": triggers}
    INTRO_STAGE_PLACEMENT_CACHE_KEY = cache_key
    try:
        ensure_runtime_dir(os.path.dirname(cache_path))
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cache_key": list(cache_key),
                    "layout": INTRO_STAGE_PLACEMENT_CACHE,
                },
                f,
            )
    except Exception:
        pass
    return INTRO_STAGE_PLACEMENT_CACHE


def _place_enemy_rect(enemy, center_x, bottom_y):
    rect = enemy.rect()
    rect.midbottom = (int(round(center_x)), int(round(bottom_y)))
    ox, oy = enemy._hitbox_offsets()
    enemy.pos[0] = rect.x - ox
    enemy.pos[1] = rect.y - oy


def _spawn_ground_enemy(enemy_cls, center_x, *, y_min=0, y_max=None, spawn_delay=0):
    if not arena_ctx or not arena_tilemap:
        return None
    ground_top = _find_ground_top_for_x(arena_tilemap, center_x, min_y=y_min, max_y=y_max)
    if ground_top is None:
        return None
    enemy = enemy_cls(arena_ctx, (center_x, ground_top), spawn_delay=spawn_delay)
    _place_enemy_rect(enemy, center_x, ground_top)
    _resolve_enemy_spawn_position(enemy, grounded=True)
    if _rect_collides_tilemap(arena_tilemap, enemy.rect()):
        return None
    return enemy


def _spawn_ground_enemy_at(enemy_cls, center_x, preferred_y=None, *, spawn_delay=0, use_exact=False):
    if not arena_ctx or not arena_tilemap:
        return None
    if use_exact and preferred_y is not None:
        enemy = enemy_cls(arena_ctx, (center_x, preferred_y), spawn_delay=spawn_delay)
        _place_enemy_rect(enemy, center_x, preferred_y)
        _resolve_enemy_spawn_position(enemy, grounded=True)
        if _rect_collides_tilemap(arena_tilemap, enemy.rect()):
            return None
        return enemy
    ground_top = _find_ground_top_near_x(arena_tilemap, center_x, preferred_y=preferred_y)
    if ground_top is None:
        return None
    enemy = enemy_cls(arena_ctx, (center_x, ground_top), spawn_delay=spawn_delay)
    _place_enemy_rect(enemy, center_x, ground_top)
    _resolve_enemy_spawn_position(enemy, grounded=True)
    if _rect_collides_tilemap(arena_tilemap, enemy.rect()):
        return None
    return enemy


def _image_visible_bounds(img):
    mask = pygame.mask.from_surface(img)
    rects = mask.get_bounding_rects()
    if rects:
        min_x = min(r.x for r in rects)
        min_y = min(r.y for r in rects)
        max_x = max(r.x + r.w for r in rects)
        max_y = max(r.y + r.h for r in rects)
        return pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
    bounds = img.get_bounding_rect()
    if bounds.width <= 0 or bounds.height <= 0:
        return pygame.Rect(0, 0, img.get_width(), img.get_height())
    return bounds


def _place_enemy_sprite_bbox(enemy, bbox):
    img = enemy.animation.img()
    bounds = enemy._frame_bounds(img) if hasattr(enemy, "_frame_bounds") else _image_visible_bounds(img)
    draw_ox, draw_oy = enemy._draw_offset(img)
    enemy.pos[0] = float(bbox[0] - draw_ox - bounds.x)
    enemy.pos[1] = float(bbox[1] - draw_oy - bounds.y)


def _infer_spike_surface_normal_from_bbox(bbox):
    width = (bbox[2] - bbox[0] + 1)
    height = (bbox[3] - bbox[1] + 1)
    if width > height:
        return (0, 1)
    center_y = int(round((bbox[1] + bbox[3]) / 2.0))
    left_probe_x = bbox[0] - 3
    right_probe_x = bbox[2] + 3
    left_hits = 0
    right_hits = 0
    for dy in (-10, -5, 0, 5, 10):
        if arena_tilemap and arena_tilemap.physics_rects_around((left_probe_x, center_y + dy), (2, 2)):
            probe = pygame.Rect(left_probe_x, center_y + dy, 2, 2)
            if any(probe.colliderect(rect) for rect in arena_tilemap.physics_rects_around(probe.topleft, probe.size)):
                left_hits += 1
        if arena_tilemap and arena_tilemap.physics_rects_around((right_probe_x, center_y + dy), (2, 2)):
            probe = pygame.Rect(right_probe_x, center_y + dy, 2, 2)
            if any(probe.colliderect(rect) for rect in arena_tilemap.physics_rects_around(probe.topleft, probe.size)):
                right_hits += 1
    if right_hits > left_hits:
        return (-1, 0)
    return (1, 0)


def _place_spike_sprite_bbox(enemy, bbox, normal):
    enemy.surface_normal = normal
    visual_center = (
        (bbox[0] + bbox[2]) / 2.0,
        (bbox[1] + bbox[3]) / 2.0,
    )
    img = enemy.game.assets['spike_idle'].images[0]
    base_center = pygame.Vector2(img.get_width() / 2.0, img.get_height() / 2.0)
    visual_center_local = pygame.Vector2(enemy.sprite_center_local)
    delta = visual_center_local - base_center
    angle = -enemy._surface_angle()
    rotated_delta = delta.rotate(angle)
    desired_center = (
        visual_center[0] + rotated_delta.x,
        visual_center[1] + rotated_delta.y,
    )
    enemy.pos[0], enemy.pos[1] = desired_center


def _configure_intro_spike_motion(enemy, center, normal):
    enemy.surface_normal = normal
    enemy.pos[0], enemy.pos[1] = center
    search = 18
    if normal[0] != 0:
        up_ok = enemy._find_surface_near(
            arena_tilemap,
            (center[0], center[1] - 16),
            normal,
            search,
            prefer=(0, -1),
            source_center=center,
        ) is not None
        down_ok = enemy._find_surface_near(
            arena_tilemap,
            (center[0], center[1] + 16),
            normal,
            search,
            prefer=(0, 1),
            source_center=center,
        ) is not None
        if not up_ok and not down_ok:
            enemy.can_move = False
            enemy.state = 'guard'
            enemy.set_action('spike_idle', force=True)
        else:
            enemy.can_move = True
            enemy.move_dir = -1 if up_ok and not down_ok else 1
            enemy.state = 'move'
            enemy._set_move_animation(force=True)
    else:
        left_ok = enemy._find_surface_near(
            arena_tilemap,
            (center[0] - 16, center[1]),
            normal,
            search,
            prefer=(-1, 0),
            source_center=center,
        ) is not None
        right_ok = enemy._find_surface_near(
            arena_tilemap,
            (center[0] + 16, center[1]),
            normal,
            search,
            prefer=(1, 0),
            source_center=center,
        ) is not None
        if not left_ok and not right_ok:
            enemy.can_move = False
            enemy.state = 'guard'
            enemy.set_action('spike_idle', force=True)
        else:
            enemy.can_move = True
            enemy.move_dir = -1 if left_ok and not right_ok else 1
            enemy.state = 'move'
            enemy._set_move_animation(force=True)


def _spawn_spike_enemy_from_bbox(bbox, *, spawn_delay=0):
    if not arena_ctx or not arena_tilemap:
        return None
    normal = _infer_spike_surface_normal_from_bbox(bbox)
    enemy = ArenaSpikeEnemy(
        arena_ctx,
        (0, 0),
        surface_normal=normal,
        move_dir=1,
        spawn_delay=spawn_delay,
    )
    _place_spike_sprite_bbox(enemy, bbox, normal)
    desired_center = (float(enemy.pos[0]), float(enemy.pos[1]))
    candidates = []
    direct = enemy._snap_center_to_surface(
        arena_tilemap,
        desired_center,
        normal,
        source_center=desired_center,
    )
    if direct is not None:
        candidates.append((direct, normal))
    if enemy.attach_to_surface(arena_tilemap, desired_center, preferred_normal=normal):
        candidates.append(((enemy.pos[0], enemy.pos[1]), enemy.surface_normal))
    snapped = enemy._find_surface_near(
        arena_tilemap,
        desired_center,
        normal,
        40,
        prefer=normal,
        source_center=desired_center,
    )
    if snapped is not None:
        candidates.append((snapped, normal))
    if enemy._mounted_center_is_clear(arena_tilemap, desired_center, normal):
        candidates.append((desired_center, normal))

    best_guard = None
    for center, candidate_normal in candidates:
        if not enemy._mounted_center_is_clear(arena_tilemap, center, candidate_normal):
            continue
        if enemy._surface_fully_supported(arena_tilemap, center, candidate_normal):
            _configure_intro_spike_motion(enemy, center, candidate_normal)
            return enemy
        if best_guard is None:
            best_guard = (center, candidate_normal)

    if best_guard is not None:
        center, candidate_normal = best_guard
        enemy.surface_normal = candidate_normal
        enemy.pos[0], enemy.pos[1] = center
        enemy.can_move = False
        enemy.state = 'guard'
        enemy.set_action('spike_idle', force=True)
        return enemy
    return None


def _rect_collides_tilemap(tilemap, rect):
    for solid in tilemap.physics_rects_around(rect.topleft, rect.size):
        if rect.colliderect(solid):
            return True
    return False


def _ground_support_distance(tilemap, rect, max_probe=12):
    best = None
    probe = pygame.Rect(rect.left, rect.bottom, rect.width, max_probe)
    for solid in tilemap.physics_rects_around(probe.topleft, probe.size):
        if solid.left >= rect.right or solid.right <= rect.left:
            continue
        distance = solid.top - rect.bottom
        if 0 <= distance <= max_probe and (best is None or distance < best):
            best = distance
    return best


def _resolve_enemy_spawn_position(enemy, *, grounded=False):
    if not arena_tilemap:
        return
    start_x = float(enemy.pos[0])
    start_y = float(enemy.pos[1])
    start_rect = enemy.rect()
    if not _rect_collides_tilemap(arena_tilemap, start_rect):
        if grounded:
            snap = _ground_support_distance(arena_tilemap, start_rect, max_probe=10)
            if snap is not None:
                enemy.pos[1] += snap
        return
    best = None
    for dy in range(-48, 49):
        for dx in range(-24, 25):
            enemy.pos[0] = start_x + dx
            enemy.pos[1] = start_y + dy
            rect = enemy.rect()
            if _rect_collides_tilemap(arena_tilemap, rect):
                continue
            penalty = abs(dx) + abs(dy) * (3 if grounded else 1)
            if grounded:
                support = _ground_support_distance(arena_tilemap, rect, max_probe=10)
                if support is None:
                    continue
                penalty += support * 4
                candidate = (penalty, dx, dy, support)
            else:
                candidate = (penalty, dx, dy, 0)
            if best is None or candidate < best:
                best = candidate
        if grounded and best is not None and best[0] == 0:
            break
    enemy.pos[0] = start_x
    enemy.pos[1] = start_y
    if best is not None:
        _, dx, dy, support = best
        enemy.pos[0] = start_x + dx
        enemy.pos[1] = start_y + dy + support
    elif grounded:
        snap = _ground_support_distance(arena_tilemap, start_rect, max_probe=10)
        if snap is not None:
            enemy.pos[1] += snap


def _light_snap_enemy_to_ground(enemy, max_probe=8):
    if not arena_tilemap:
        return
    rect = enemy.rect()
    if _rect_collides_tilemap(arena_tilemap, rect):
        return
    snap = _ground_support_distance(arena_tilemap, rect, max_probe=max_probe)
    if snap is not None:
        enemy.pos[1] += snap


def _spawn_air_enemy(enemy_cls, center_x, center_y, *, spawn_delay=0):
    if not arena_ctx:
        return None
    enemy = enemy_cls(arena_ctx, (center_x, center_y), spawn_delay=spawn_delay)
    rect = enemy.rect()
    rect.center = (int(round(center_x)), int(round(center_y)))
    ox, oy = enemy._hitbox_offsets()
    enemy.pos[0] = rect.x - ox
    enemy.pos[1] = rect.y - oy
    _resolve_enemy_spawn_position(enemy, grounded=False)
    if arena_tilemap and _rect_collides_tilemap(arena_tilemap, enemy.rect()):
        return None
    if hasattr(enemy, "home_pos"):
        enemy.home_pos = [float(enemy.pos[0]), float(enemy.pos[1])]
    if hasattr(enemy, "base_pos"):
        enemy.base_pos = [float(enemy.pos[0]), float(enemy.pos[1])]
    return enemy


def _spawn_fixed_pickup(pickup_key, center_x, preferred_y=None, *, amount=None, persistent=True, use_exact=False):
    if not arena_ctx or not arena_tilemap:
        return None
    ground_top = preferred_y if (use_exact and preferred_y is not None) else _find_ground_top_near_x(arena_tilemap, center_x, preferred_y=preferred_y)
    if ground_top is None:
        return None
    try:
        pickup = ArenaPickup(
            arena_ctx,
            pickup_key,
            (center_x, ground_top),
            amount=amount,
            vel=(0.0, 0.0),
            persistent=persistent,
        )
    except Exception:
        return None
    pickup.pos[0] = float(center_x)
    pickup.pos[1] = float(ground_top)
    pickup.rest_y = float(ground_top)
    pickup.grounded = True
    pickup.velocity[0] = 0.0
    pickup.velocity[1] = 0.0
    return pickup


def _place_pickup_sprite_bbox(pickup, bbox):
    frame_idx = pickup.animation.frame_index()
    anchor_x, anchor_y = pickup.frame_anchors[min(frame_idx, len(pickup.frame_anchors) - 1)]
    img = pickup.animation.img()
    bounds = _image_visible_bounds(img)
    pickup.pos[0] = float(bbox[0] + anchor_x - bounds.x)
    pickup.pos[1] = float(bbox[1] + anchor_y - bounds.y)
    pickup.rest_y = pickup.pos[1]
    pickup.grounded = True
    pickup.velocity[0] = 0.0
    pickup.velocity[1] = 0.0


def _resolve_pickup_spawn_position(pickup):
    if not arena_tilemap:
        return
    start_x = float(pickup.pos[0])
    start_y = float(pickup.pos[1])
    start_rect = pickup.rect()
    if not _rect_collides_tilemap(arena_tilemap, start_rect):
        snap = _ground_support_distance(arena_tilemap, start_rect, max_probe=10)
        if snap is not None:
            pickup.pos[1] += snap
            pickup.rest_y = pickup.pos[1]
        return
    best = None
    for dy in range(-32, 33):
        for dx in range(-20, 21):
            pickup.pos[0] = start_x + dx
            pickup.pos[1] = start_y + dy
            rect = pickup.rect()
            if _rect_collides_tilemap(arena_tilemap, rect):
                continue
            support = _ground_support_distance(arena_tilemap, rect, max_probe=10)
            if support is None:
                continue
            penalty = abs(dx) + abs(dy) * 3 + support * 4
            candidate = (penalty, dx, dy, support)
            if best is None or candidate < best:
                best = candidate
    pickup.pos[0] = start_x
    pickup.pos[1] = start_y
    if best is not None:
        _, dx, dy, support = best
        pickup.pos[0] = start_x + dx
        pickup.pos[1] = start_y + dy + support
        pickup.rest_y = pickup.pos[1]


def _light_snap_pickup_to_ground(pickup, max_probe=8):
    if not arena_tilemap:
        return
    rect = pickup.rect()
    if _rect_collides_tilemap(arena_tilemap, rect):
        return
    snap = _ground_support_distance(arena_tilemap, rect, max_probe=max_probe)
    if snap is not None:
        pickup.pos[1] += snap
        pickup.rest_y = pickup.pos[1]


def _intro_stage_content_point(spec):
    if not arena_bounds:
        return 0, 0
    ox, oy, w, h = arena_bounds
    x = spec.get("x")
    y = spec.get("y")
    if x is None:
        x = ox + int(round(w * float(spec.get("x_frac", 0.5))))
    if y is None:
        y = oy + int(round(h * float(spec.get("y_frac", 0.5))))
    return int(round(x)), int(round(y))


# spawn the scripted intro-stage enemies and pickups from the placement markup
def _spawn_intro_stage_fixed_content():
    if current_stage != "intro_stage" or not arena_tilemap or not arena_bounds:
        return [], []
    enemy_map = {
        "met": ArenaMetEnemy,
        "wheel": ArenaWheelEnemy,
        "cannon": ArenaCannonEnemy,
        "heavy": ArenaHeavyEnemy,
        "heli_rocket": ArenaHeliRocketEnemy,
    }
    layout = _load_intro_stage_marker_layout()
    enemies = []
    pickups = []
    spike_index = 0
    spike_adjustments = (
        (2, 20),
        (-2, 20),
        (2, -5),
        (0, 12),
    )
    for spec in layout.get("enemies", ()):
        center_x, center_y = _intro_stage_content_point(spec)
        enemy_type = spec.get("type")
        spawn_delay = int(spec.get("spawn_delay", 0))
        bbox = spec.get("bbox")
        enemy = None
        if enemy_type in {"met", "wheel", "cannon", "heavy"}:
            enemy = _spawn_ground_enemy_at(
                enemy_map[enemy_type],
                center_x,
                center_y,
                spawn_delay=spawn_delay,
                use_exact=("x" in spec and "y" in spec),
            )
        elif enemy_type == "heli_rocket":
            enemy = _spawn_air_enemy(ArenaHeliRocketEnemy, center_x, center_y, spawn_delay=spawn_delay)
        elif enemy_type == "copter_enemy":
            enemy = _spawn_air_enemy(ArenaCopterEnemy, center_x, center_y, spawn_delay=spawn_delay)
        elif enemy_type == "bird":
            move_dir = int(spec.get("move_dir", 1))
            flight_slope = float(spec.get("flight_slope", 0.0))
            enemy = _spawn_bird_enemy(move_dir, center_y, flight_slope, spawn_delay=spawn_delay)
        elif enemy_type == "spike":
            if bbox:
                enemy = _spawn_spike_enemy_from_bbox(bbox, spawn_delay=spawn_delay)
            else:
                enemy = _spawn_spike_enemy_auto(center_x, center_y, spawn_delay=spawn_delay)
            if enemy is not None and spike_index < len(spike_adjustments):
                dx, dy = spike_adjustments[spike_index]
                enemy.pos[0] += dx
                enemy.pos[1] += dy
            if enemy is not None:
                enemy.can_move = False
                enemy.state = 'guard'
                enemy.set_action('spike_idle', force=True)
            spike_index += 1
        elif enemy_type == "spike_wall":
            enemy = _spawn_spike_wall_enemy(
                center_y,
                surface_normal=tuple(spec.get("surface_normal", (1, 0))),
                move_dir=int(spec.get("move_dir", 1)),
                spawn_delay=spawn_delay,
            )
        elif enemy_type == "spike_underside":
            enemy = _spawn_spike_underside_enemy(
                center_x,
                center_y,
                move_dir=int(spec.get("move_dir", 1)),
                spawn_delay=spawn_delay,
            )
        elif enemy_type == "spike_side":
            enemy = _spawn_spike_platform_side_enemy(
                center_x,
                center_y,
                surface_normal=tuple(spec.get("surface_normal", (1, 0))),
                spawn_delay=spawn_delay,
            )
        if enemy is not None:
            enemy.intro_debug_bbox = bbox
            if bbox and enemy_type != "spike":
                _place_enemy_sprite_bbox(enemy, bbox)
                if enemy_type in {"met", "wheel", "cannon", "heavy"}:
                    _light_snap_enemy_to_ground(enemy)
                if hasattr(enemy, "home_pos"):
                    enemy.home_pos = [float(enemy.pos[0]), float(enemy.pos[1])]
            enemies.append(enemy)

    for spec in layout.get("pickups", ()):
        center_x, center_y = _intro_stage_content_point(spec)
        bbox = spec.get("bbox")
        pickup_type = spec["type"]
        if current_stage == "intro_stage" and pickup_type == "small_special_ammo_pickup":
            pickup_type = "large_special_ammo_pickup"
        pickup = _spawn_fixed_pickup(
            pickup_type,
            center_x,
            center_y,
            amount=spec.get("amount"),
            persistent=bool(spec.get("persistent", True)),
            use_exact=("x" in spec and "y" in spec),
        )
        if pickup is not None:
            pickup.intro_debug_bbox = bbox
            if bbox:
                _place_pickup_sprite_bbox(pickup, bbox)
                _light_snap_pickup_to_ground(pickup)
            pickups.append(pickup)
    return enemies, pickups


INTRO_COMMAND_ROOM_SWARM_TRIGGER_X = 4010
INTRO_COMMAND_ROOM_SWARM_TRIGGER_Y = 617
INTRO_COMMAND_ROOM_SWARM_QUEUE_INTERVAL = 1


def _intro_stage_trigger_spec(trigger_type):
    layout = _load_intro_stage_marker_layout()
    for spec in layout.get("triggers", ()):
        if spec.get("type") == trigger_type:
            return spec
    return None


# generate the command-room ambush wave around the player's current area
def _build_intro_command_room_swarm_specs(player=None):
    if current_stage != "intro_stage" or not arena_tilemap:
        return []
    trigger_spec = _intro_stage_trigger_spec("command_room_swarm")
    center_x = int(trigger_spec["x"]) if trigger_spec else INTRO_COMMAND_ROOM_SWARM_TRIGGER_X
    trigger_y = int(trigger_spec["y"]) if trigger_spec else INTRO_COMMAND_ROOM_SWARM_TRIGGER_Y
    baseline_y = trigger_y + 10
    arc_specs = (
        ("copter_enemy", -84, -46, 0),
        ("copter_enemy", -42, -74, 4),
        ("heli_rocket", 0, -92, 8),
        ("copter_enemy", 42, -74, 12),
        ("copter_enemy", 84, -46, 16),
    )
    specs = []
    for enemy_type, dx, dy, delay in arc_specs:
        target_x = center_x + dx
        target_y = baseline_y + dy
        spawn_x = center_x + int(round(dx * 1.55))
        spawn_y = target_y - 78 - int(round(abs(dx) * 0.08))
        specs.append({
            "enemy_type": enemy_type,
            "spawn_x": spawn_x,
            "spawn_y": spawn_y,
            "target_x": target_x,
            "target_y": target_y,
            "spawn_delay": delay,
        })
    return specs


def _spawn_intro_command_room_swarm_member(spec):
    enemy_type = spec.get("enemy_type")
    spawn_x = spec.get("spawn_x", 0)
    spawn_y = spec.get("spawn_y", 0)
    spawn_delay = spec.get("spawn_delay", 0)
    target_x = spec.get("target_x", spawn_x)
    target_y = spec.get("target_y", spawn_y)
    if enemy_type == "heli_rocket":
        enemy = _spawn_air_enemy(ArenaHeliRocketEnemy, spawn_x, spawn_y, spawn_delay=spawn_delay)
    else:
        enemy = _spawn_air_enemy(ArenaCopterEnemy, spawn_x, spawn_y, spawn_delay=spawn_delay)
    if enemy is None:
        return None
    enemy.camera_activation_pending = False
    if hasattr(enemy, "home_pos"):
        enemy.home_pos = [float(target_x), float(target_y)]
    if hasattr(enemy, "base_pos"):
        enemy.base_pos = [float(target_x), float(target_y)]
    if hasattr(enemy, "entry_mode"):
        enemy.entry_mode = True
    if hasattr(enemy, "entry_speed_scale"):
        enemy.entry_speed_scale = 2.25
    return enemy


def _spawn_intro_command_room_swarm(player=None):
    spawned = []
    for spec in _build_intro_command_room_swarm_specs(player):
        enemy = _spawn_intro_command_room_swarm_member(spec)
        if enemy is not None:
            spawned.append(enemy)
    return spawned


def _update_intro_pending_swarm_spawns(ctx):
    if current_stage != "intro_stage" or not ctx:
        return
    pending = list(getattr(ctx, "intro_pending_swarm_spawns", []) or [])
    if not pending:
        return
    timer = int(getattr(ctx, "intro_pending_swarm_spawn_timer", 0) or 0)
    if timer > 0:
        ctx.intro_pending_swarm_spawn_timer = timer - 1
        return
    enemy = pending.pop(0)
    if enemy is not None:
        arena_copters.append(enemy)
    ctx.intro_pending_swarm_spawns = pending
    ctx.intro_pending_swarm_spawn_timer = INTRO_COMMAND_ROOM_SWARM_QUEUE_INTERVAL


def _queue_intro_command_room_swarm(ctx, player=None):
    if not ctx:
        return []
    cached_enemies = list(getattr(ctx, "intro_command_room_swarm_cache", []) or [])
    if not cached_enemies:
        specs = _build_intro_command_room_swarm_specs(player)
        cached_enemies = []
        for spec in specs:
            enemy = _spawn_intro_command_room_swarm_member(spec)
            if enemy is not None:
                cached_enemies.append(enemy)
        ctx.intro_command_room_swarm_cache = list(cached_enemies)
    ctx.intro_pending_swarm_spawns = list(cached_enemies)
    ctx.intro_pending_swarm_spawn_timer = 0
    ctx.intro_command_room_swarm_cache = []
    return ctx.intro_pending_swarm_spawns


def _prime_intro_command_room_swarm_cache(ctx):
    if current_stage != "intro_stage" or not ctx:
        return
    if getattr(ctx, "intro_command_room_swarm_cache", None):
        return
    cached_enemies = []
    for spec in _build_intro_command_room_swarm_specs():
        enemy = _spawn_intro_command_room_swarm_member(spec)
        if enemy is not None:
            cached_enemies.append(enemy)
    ctx.intro_command_room_swarm_cache = cached_enemies


def _maybe_trigger_intro_command_room_swarm(ctx, player):
    global intro_stage_guided_giga_unlocked
    if current_stage != "intro_stage" or not ctx or not player or not arena_tilemap:
        return
    if getattr(ctx, "intro_command_room_swarm_triggered", False):
        return
    trigger_spec = _intro_stage_trigger_spec("command_room_swarm")
    trigger_x = int(trigger_spec["x"]) if trigger_spec else INTRO_COMMAND_ROOM_SWARM_TRIGGER_X
    trigger_y = int(trigger_spec["y"]) if trigger_spec else INTRO_COMMAND_ROOM_SWARM_TRIGGER_Y
    near_middle = abs(player.rect().centerx - trigger_x) <= 56
    near_height = abs(player.rect().centery - trigger_y) <= 56
    if not (near_middle and near_height):
        return

    queued_specs = _queue_intro_command_room_swarm(ctx, player)
    ctx.intro_command_room_swarm_triggered = True
    ctx.intro_command_room_swarm_alive = bool(queued_specs)
    if getattr(ctx, "intro_stage_guided", False):
        ctx.intro_guided_giga_unlocked = True
        intro_stage_guided_giga_unlocked = True


def _maybe_trigger_intro_guidance(ctx, player):
    global intro_stage_guidance_seen_persistent
    if current_stage != "intro_stage" or not ctx or not player:
        return
    if not getattr(ctx, "intro_stage_guided", False):
        return
    if getattr(ctx, "cutscene_active", False):
        return
    if getattr(ctx, "intro_opening_active", False) or getattr(ctx, "intro_vile_sequence_active", False):
        return
    seen = getattr(ctx, "intro_guidance_seen", None)
    if seen is None:
        seen = set()
        ctx.intro_guidance_seen = seen
    player_rect = player.rect()
    player_x = player.rect().centerx
    for spec in INTRO_STAGE_GUIDANCE:
        trigger_id = spec.get("id")
        if trigger_id in seen:
            continue
        if trigger_id == "giga_attack" and not getattr(ctx, "intro_guided_giga_unlocked", False):
            continue
        if (
            trigger_id == "basic_combat"
            and arena_tilemap is not None
            and getattr(arena_tilemap, "secret_roof_floor", None) is not None
            and getattr(arena_tilemap, "secret_roof_wall", None) is not None
        ):
            secret_floor = arena_tilemap.secret_roof_floor
            secret_wall = arena_tilemap.secret_roof_wall
            at_secret_roof_height = (
                player_rect.bottom >= secret_floor.top - 12
                and player_rect.bottom <= secret_floor.bottom + 20
            )
            on_secret_roof_run = (
                player_rect.centerx >= secret_floor.left - 8
                and player_rect.centerx <= secret_wall.right + 20
            )
            if at_secret_roof_height and on_secret_roof_run:
                continue
        if player_x < int(spec.get("x", 0)):
            continue
        seen.add(trigger_id)
        intro_stage_guidance_seen_persistent = set(seen)
        _start_arena_cutscene(ctx, spec.get("lines", []))
        break


# debug-only overlay for seeing the parsed intro-stage placement markers in-world
def _draw_intro_stage_placement_overlay(surface, ctx, offset):
    if not INTRO_STAGE_SHOW_PLACEMENT_OVERLAY or current_stage != "intro_stage":
        return
    if not ctx:
        return
    for enemy in arena_copters:
        bbox = getattr(enemy, "intro_debug_bbox", None)
        if not bbox:
            continue
        rect = pygame.Rect(
            int(round(bbox[0] - offset[0])),
            int(round(bbox[1] - offset[1])),
            int(round(bbox[2] - bbox[0] + 1)),
            int(round(bbox[3] - bbox[1] + 1)),
        )
        pygame.draw.rect(surface, (255, 210, 40), rect, 1)
    for pickup in getattr(ctx, "pickups", []):
        bbox = getattr(pickup, "intro_debug_bbox", None)
        if not bbox:
            continue
        rect = pygame.Rect(
            int(round(bbox[0] - offset[0])),
            int(round(bbox[1] - offset[1])),
            int(round(bbox[2] - bbox[0] + 1)),
            int(round(bbox[3] - bbox[1] + 1)),
        )
        pygame.draw.rect(surface, (80, 220, 255), rect, 1)


def _spawn_bird_enemy(move_dir, center_y, flight_slope=0.0, *, spawn_delay=0):
    if not arena_ctx or not arena_bounds:
        return None
    ox, oy, w, h = arena_bounds
    margin = 52
    center_x = (ox - margin) if move_dir > 0 else (ox + w + margin)
    return ArenaBirdEnemy(arena_ctx, (center_x, center_y), move_dir=move_dir, flight_slope=flight_slope, spawn_delay=spawn_delay)


def _spawn_spike_enemy(center_x, center_y, *, surface_normal=(1, 0), move_dir=1, spawn_delay=0):
    if not arena_ctx or not arena_tilemap:
        return None
    enemy = ArenaSpikeEnemy(
        arena_ctx,
        (center_x, center_y),
        surface_normal=surface_normal,
        move_dir=move_dir,
        spawn_delay=spawn_delay,
    )
    mount_depth = enemy.mount_depth
    tile_size = getattr(arena_tilemap, "tile_size", 16) or 16
    contact_half = max(2.0, min((enemy._hh / 2.0) - 1.0, (tile_size / 2.0) - 2.0))
    ox, oy, w, h = arena_bounds if arena_bounds else (0, 0, 0, 0)
    inner_left = ox + tile_size
    inner_right = (ox + w) - tile_size
    best = None
    for rect in _iter_tilemap_collision_rects(arena_tilemap):
        if surface_normal == (1, 0):
            if rect.height < contact_half * 2:
                continue
            candidate_y = max(rect.top + contact_half, min(center_y, rect.bottom - contact_half))
            candidate = (rect.right + mount_depth, candidate_y)
        elif surface_normal == (-1, 0):
            if rect.height < contact_half * 2:
                continue
            candidate_y = max(rect.top + contact_half, min(center_y, rect.bottom - contact_half))
            candidate = (rect.left - mount_depth, candidate_y)
        elif surface_normal == (0, 1):
            if rect.width < contact_half * 2:
                continue
            candidate_x = max(rect.left + contact_half, min(center_x, rect.right - contact_half))
            candidate = (candidate_x, rect.bottom + mount_depth)
        else:
            if rect.width < contact_half * 2:
                continue
            candidate_x = max(rect.left + contact_half, min(center_x, rect.right - contact_half))
            candidate = (candidate_x, rect.top - mount_depth)
        dist = math.hypot(candidate[0] - center_x, candidate[1] - center_y)
        if best is None or dist < best[0]:
            best = (dist, candidate, rect)
    if best is None or best[0] > 140:
        return None
    _, candidate_center, support_rect = best
    is_platform_side = (
        surface_normal[0] != 0
        and arena_bounds is not None
        and support_rect.left > inner_left
        and support_rect.right < inner_right
    )
    if is_platform_side:
        candidate_center = (candidate_center[0], support_rect.centery)
        enemy.can_move = False
        enemy.surface_normal = surface_normal
        if not (
            enemy._surface_fully_supported(arena_tilemap, candidate_center, surface_normal)
            and enemy._mounted_center_is_clear(arena_tilemap, candidate_center, surface_normal)
        ):
            return None
        enemy.pos[0], enemy.pos[1] = candidate_center
        enemy.set_action('spike_idle', force=True)
        return enemy
    if not enemy.attach_to_surface(arena_tilemap, candidate_center, preferred_normal=surface_normal):
        if not (
            enemy._surface_fully_supported(arena_tilemap, candidate_center, surface_normal)
            and enemy._mounted_center_is_clear(arena_tilemap, candidate_center, surface_normal)
        ):
            return None
        enemy.surface_normal = surface_normal
        enemy.pos[0], enemy.pos[1] = candidate_center
    return enemy


def _spawn_spike_wall_enemy(center_y, *, surface_normal=(1, 0), move_dir=1, spawn_delay=0):
    if not arena_ctx or not arena_tilemap or not arena_bounds:
        return None
    enemy = ArenaSpikeEnemy(
        arena_ctx,
        (0, 0),
        surface_normal=surface_normal,
        move_dir=move_dir,
        spawn_delay=spawn_delay,
    )
    ox, oy, w, h = arena_bounds
    tile_size = getattr(arena_tilemap, "tile_size", 16) or 16
    inner_left = ox + tile_size
    inner_right = (ox + w) - tile_size
    inner_top = oy + tile_size
    inner_bottom = (oy + h) - tile_size
    body_half = enemy._hh / 2.0
    clamped_y = max(inner_top + body_half, min(center_y, inner_bottom - body_half))
    if surface_normal == (1, 0):
        candidate_center = (inner_left + enemy.mount_depth, clamped_y)
    else:
        candidate_center = (inner_right - enemy.mount_depth, clamped_y)
    if not enemy.attach_to_surface(arena_tilemap, candidate_center, preferred_normal=surface_normal):
        if not (
            enemy._surface_fully_supported(arena_tilemap, candidate_center, surface_normal)
            and enemy._mounted_center_is_clear(arena_tilemap, candidate_center, surface_normal)
        ):
            return None
        enemy.surface_normal = surface_normal
        enemy.pos[0], enemy.pos[1] = candidate_center
    return enemy


def _pick_spike_side_span(preferred_x=None, preferred_y=None, min_tiles=1):
    if not arena_tilemap:
        return None
    spans = []
    for x0, x1, y in getattr(arena_tilemap, "platform_spans", []):
        if (x1 - x0) < min_tiles:
            continue
        spans.append((x0, x1, y))
    if not spans:
        return None
    tile_size = getattr(arena_tilemap, "tile_size", 16) or 16
    if preferred_x is None:
        preferred_x = arena_bounds[0] + (arena_bounds[2] / 2)
    if preferred_y is None:
        preferred_y = arena_bounds[1] + (arena_bounds[3] / 2)

    def sort_key(span):
        x0, x1, y = span
        cx = ((x0 + x1) / 2.0) * tile_size
        cy = (y * tile_size) + (tile_size / 2.0)
        return (abs(cx - preferred_x) + abs(cy - preferred_y), - (x1 - x0), y)

    return min(spans, key=sort_key)


def _spawn_spike_platform_side_enemy(preferred_x, preferred_y, *, surface_normal=(1, 0), spawn_delay=0):
    if not arena_ctx or not arena_tilemap:
        return None
    enemy = ArenaSpikeEnemy(
        arena_ctx,
        (0, 0),
        surface_normal=surface_normal,
        move_dir=1 if surface_normal[0] > 0 else -1,
        spawn_delay=spawn_delay,
    )
    span = _pick_spike_side_span(preferred_x=preferred_x, preferred_y=preferred_y, min_tiles=1)
    if span is None:
        return None
    x0, x1, y = span
    tile_size = getattr(arena_tilemap, "tile_size", 16) or 16
    if surface_normal == (1, 0):
        seed_center = ((x1 * tile_size) + enemy.mount_depth, (y * tile_size) + (tile_size / 2.0))
    else:
        seed_center = ((x0 * tile_size) - enemy.mount_depth, (y * tile_size) + (tile_size / 2.0))
    center_x, center_y = enemy._platform_side_center(arena_tilemap, seed_center, surface_normal)
    enemy.can_move = False
    enemy.state = 'guard'
    enemy.surface_normal = surface_normal
    enemy.pos[0], enemy.pos[1] = (center_x, center_y)
    enemy.set_action('spike_idle', force=True)
    return enemy


def _pick_spike_underside_span(preferred_x=None, preferred_y=None, min_tiles=3):
    if not arena_tilemap:
        return None
    spans = []
    for x0, x1, y in getattr(arena_tilemap, "platform_spans", []):
        length_tiles = x1 - x0
        if length_tiles < min_tiles:
            continue
        spans.append((x0, x1, y))
    if not spans:
        return None
    tile_size = getattr(arena_tilemap, "tile_size", 16) or 16
    if preferred_x is None:
        preferred_x = arena_bounds[0] + (arena_bounds[2] / 2)
    if preferred_y is None:
        preferred_y = arena_bounds[1] + (arena_bounds[3] / 2)

    def sort_key(span):
        x0, x1, y = span
        cx = ((x0 + x1) / 2.0) * tile_size
        cy = y * tile_size
        return (abs(cx - preferred_x) + abs(cy - preferred_y), - (x1 - x0), y)

    return min(spans, key=sort_key)


def _spawn_spike_underside_enemy(preferred_x, preferred_y, *, move_dir=1, spawn_delay=0):
    if not arena_ctx or not arena_tilemap:
        return None
    enemy = ArenaSpikeEnemy(
        arena_ctx,
        (0, 0),
        surface_normal=(0, 1),
        move_dir=move_dir,
        spawn_delay=spawn_delay,
    )
    span = _pick_spike_underside_span(preferred_x=preferred_x, preferred_y=preferred_y, min_tiles=3)
    if span is None:
        return None
    x0, x1, y = span
    tile_size = getattr(arena_tilemap, "tile_size", 16) or 16
    body_half = enemy._hh / 2.0
    left_px = x0 * tile_size
    right_px = x1 * tile_size
    candidate_x = max(left_px + body_half, min(preferred_x, right_px - body_half))
    candidate_y = ((y + 1) * tile_size) + enemy.mount_depth
    candidate_center = (candidate_x, candidate_y)
    if not enemy.attach_to_surface(arena_tilemap, candidate_center, preferred_normal=(0, 1)):
        enemy.surface_normal = (0, 1)
        enemy.pos[0], enemy.pos[1] = candidate_center
    return enemy


def _spawn_spike_enemy_auto(center_x, center_y, *, spawn_delay=0):
    if not arena_ctx or not arena_tilemap:
        return None
    probe = ArenaSpikeEnemy(
        arena_ctx,
        (center_x, center_y),
        surface_normal=(1, 0),
        move_dir=1,
        spawn_delay=spawn_delay,
    )
    best = None
    for normal in ((1, 0), (-1, 0), (0, 1)):
        snapped = probe._snap_center_to_surface(arena_tilemap, (center_x, center_y), normal, source_center=(center_x, center_y))
        if snapped is None:
            snapped = probe._find_surface_near(
                arena_tilemap,
                (center_x, center_y),
                normal,
                320,
                prefer=normal,
                source_center=(center_x, center_y),
            )
        if snapped is None:
            continue
        dist = math.hypot(snapped[0] - center_x, snapped[1] - center_y)
        if best is None or dist < best[0]:
            best = (dist, normal, snapped)
    if best is None:
        return None
    _, normal, snapped = best
    enemy = ArenaSpikeEnemy(
        arena_ctx,
        snapped,
        surface_normal=normal,
        move_dir=1,
        spawn_delay=spawn_delay,
    )
    enemy.surface_normal = normal
    enemy.pos[0], enemy.pos[1] = snapped
    if normal[0] != 0:
        up_ok = enemy._find_surface_near(
            arena_tilemap,
            (snapped[0], snapped[1] - 16),
            normal,
            16,
            prefer=(0, -1),
            source_center=snapped,
        ) is not None
        down_ok = enemy._find_surface_near(
            arena_tilemap,
            (snapped[0], snapped[1] + 16),
            normal,
            16,
            prefer=(0, 1),
            source_center=snapped,
        ) is not None
        enemy.move_dir = -1 if up_ok and not down_ok else 1
    else:
        left_ok = enemy._find_surface_near(
            arena_tilemap,
            (snapped[0] - 16, snapped[1]),
            normal,
            16,
            prefer=(-1, 0),
            source_center=snapped,
        ) is not None
        right_ok = enemy._find_surface_near(
            arena_tilemap,
            (snapped[0] + 16, snapped[1]),
            normal,
            16,
            prefer=(1, 0),
            source_center=snapped,
        ) is not None
        enemy.move_dir = -1 if left_ok and not right_ok else 1
    enemy.state = 'move'
    enemy._set_move_animation(force=True)
    return enemy


# initial arena population before the dynamic refill logic takes over
def _spawn_standard_arena_enemy_set():
    if not arena_tilemap or not arena_bounds:
        return []
    ox, oy, w, h = arena_bounds
    floor_band_top = oy + int(h * 0.45)
    if ARENA_TEST_ENEMY == "met":
        spawn_specs = (
            (ArenaMetEnemy, ox + int(w * 0.24), 0),
            (ArenaMetEnemy, ox + int(w * 0.50), 18),
            (ArenaMetEnemy, ox + int(w * 0.76), 36),
        )
    elif ARENA_TEST_ENEMY == "wheel":
        spawn_specs = (
            (ArenaWheelEnemy, ox + int(w * 0.24), 0),
            (ArenaWheelEnemy, ox + int(w * 0.50), 18),
            (ArenaWheelEnemy, ox + int(w * 0.76), 36),
        )
    elif ARENA_TEST_ENEMY == "bird":
        air_specs = (
            (1, oy + int(h * 0.28), 0.06, 0),
            (-1, oy + int(h * 0.42), -0.04, 24),
            (1, oy + int(h * 0.58), 0.02, 48),
        )
        enemies = []
        for move_dir, center_y, flight_slope, spawn_delay in air_specs:
            enemy = _spawn_bird_enemy(move_dir, center_y, flight_slope, spawn_delay=spawn_delay)
            if enemy is not None:
                enemies.append(enemy)
        return enemies
    elif ARENA_TEST_ENEMY == "spike":
        enemies = []
        side_specs = (
            (ox + int(w * 0.22), oy + int(h * 0.20), (1, 0), 1, 0),
            (ox + int(w * 0.78), oy + int(h * 0.46), (-1, 0), -1, 18),
        )
        wall_specs = (
            ((1, 0), oy + int(h * 0.34), 1, 36),
            ((-1, 0), oy + int(h * 0.46), -1, 54),
        )
        underside_specs = (
            (ox + int(w * 0.34), oy + int(h * 0.28), 1, 72),
            (ox + int(w * 0.66), oy + int(h * 0.54), -1, 90),
        )
        for center_x, center_y, surface_normal, move_dir, spawn_delay in side_specs:
            enemy = _spawn_spike_platform_side_enemy(
                center_x,
                center_y,
                surface_normal=surface_normal,
                spawn_delay=spawn_delay,
            )
            if enemy is not None:
                enemies.append(enemy)
        for surface_normal, center_y, move_dir, spawn_delay in wall_specs:
            enemy = _spawn_spike_wall_enemy(
                center_y,
                surface_normal=surface_normal,
                move_dir=move_dir,
                spawn_delay=spawn_delay,
            )
            if enemy is not None:
                enemies.append(enemy)
        for preferred_x, preferred_y, move_dir, spawn_delay in underside_specs:
            enemy = _spawn_spike_underside_enemy(
                preferred_x,
                preferred_y,
                move_dir=move_dir,
                spawn_delay=spawn_delay,
            )
            if enemy is not None:
                enemies.append(enemy)
        return enemies
    elif ARENA_TEST_ENEMY == "cannon":
        spawn_specs = (
            (ArenaCannonEnemy, ox + int(w * 0.24), 0),
            (ArenaCannonEnemy, ox + int(w * 0.50), 18),
            (ArenaCannonEnemy, ox + int(w * 0.76), 36),
        )
    elif ARENA_TEST_ENEMY == "heli_rocket":
        air_specs = (
            (ArenaHeliRocketEnemy, ox + int(w * 0.28), oy + int(h * 0.30), 0),
            (ArenaHeliRocketEnemy, ox + int(w * 0.54), oy + int(h * 0.42), 22),
            (ArenaHeliRocketEnemy, ox + int(w * 0.76), oy + int(h * 0.33), 44),
        )
        enemies = []
        for enemy_cls, spawn_x, spawn_y, spawn_delay in air_specs:
            enemy = _spawn_air_enemy(enemy_cls, spawn_x, spawn_y, spawn_delay=spawn_delay)
            if enemy is not None:
                enemies.append(enemy)
        return enemies
    else:
        spawn_specs = (
            (ArenaHeavyEnemy, ox + int(w * 0.62), 0),
        )
    enemies = []
    for enemy_cls, spawn_x, spawn_delay in spawn_specs:
        enemy = _spawn_ground_enemy(
            enemy_cls,
            spawn_x,
            y_min=floor_band_top,
            y_max=oy + h,
            spawn_delay=spawn_delay,
        )
        if enemy is not None:
            enemies.append(enemy)
    return enemies


# central cleanup path so drops, score-side effects, and visuals stay consistent
def destroy_enemy(ctx, enemy, rect):
    spawn_enemy_destroyed_effect(ctx, rect)
    spawn_enemy_drop(ctx, enemy, rect)
    if ctx is not None:
        ctx.score = getattr(ctx, "score", 0) + int(getattr(enemy, "score_value", 100))
        if _dynamic_arena_spawns_enabled():
            pending = getattr(ctx, "pending_enemy_respawns", None)
            if pending is not None:
                target_count = int(getattr(ctx, "dynamic_enemy_target", _arena_target_enemy_count(getattr(ctx, "elapsed_time", 0.0))) or 0)
                future_total = max(0, len(arena_copters) - 1) + len(pending)
                if future_total < target_count:
                    stagger = min(len(pending) * ARENA_RESPAWN_STAGGER_FRAMES, ARENA_RESPAWN_STAGGER_FRAMES * 12)
                    pending.append(ARENA_RESPAWN_DELAY_FRAMES + stagger)
    try:
        play_destroy_sfx = True
        if ctx is not None:
            now_ms = pygame.time.get_ticks()
            last_ms = int(getattr(ctx, "enemy_destroy_sfx_ms", -1000))
            if (now_ms - last_ms) < 45:
                play_destroy_sfx = False
            else:
                ctx.enemy_destroy_sfx_ms = now_ms
        if play_destroy_sfx:
            sfx_enemy_destroyed.play()
    except Exception:
        pass


# one-off secret overlay trigger that sets up its timers and cached assets
def _trigger_secret_foxy(ctx):
    global intro_stage_secret_gateway_active
    if not ctx or getattr(ctx, "secret_foxy_triggered", False):
        return
    _ensure_secret_foxy_assets()
    if not secret_foxy_frames:
        return
    ctx.secret_foxy_triggered = True
    ctx.secret_foxy_active = True
    ctx.secret_foxy_frame_index = 0
    ctx.secret_foxy_frame_elapsed_ms = 0.0
    ctx.secret_foxy_finished_hold_ms = 0.0
    ctx.secret_gateway_music_active = True
    intro_stage_secret_gateway_active = True
    try:
        play_music(gateway_music_intro, gateway_music_loop)
        ctx.secret_foxy_prev_music_volume = None
    except Exception:
        ctx.secret_foxy_prev_music_volume = None
    if secret_foxy_sound is not None:
        try:
            secret_foxy_sound.play()
        except Exception:
            pass


def _update_secret_foxy(ctx, dt_seconds):
    _ensure_secret_foxy_assets()
    if not ctx or not getattr(ctx, "secret_foxy_active", False) or not secret_foxy_frames:
        return
    dt_ms = dt_seconds * 1000.0
    frame_index = getattr(ctx, "secret_foxy_frame_index", 0)
    frame_elapsed = getattr(ctx, "secret_foxy_frame_elapsed_ms", 0.0) + dt_ms

    while frame_index < len(secret_foxy_frames):
        duration = secret_foxy_durations[min(frame_index, len(secret_foxy_durations) - 1)]
        if frame_elapsed < duration:
            break
        frame_elapsed -= duration
        frame_index += 1

    if frame_index >= len(secret_foxy_frames):
        hold_ms = getattr(ctx, "secret_foxy_finished_hold_ms", 0.0) + dt_ms
        ctx.secret_foxy_finished_hold_ms = hold_ms
        ctx.secret_foxy_frame_index = len(secret_foxy_frames) - 1
        ctx.secret_foxy_frame_elapsed_ms = 0.0
        if hold_ms >= 220.0:
            ctx.secret_foxy_active = False
        return

    ctx.secret_foxy_frame_index = frame_index
    ctx.secret_foxy_frame_elapsed_ms = frame_elapsed


def _draw_secret_foxy_overlay(surface, ctx):
    _ensure_secret_foxy_assets()
    if not ctx or not getattr(ctx, "secret_foxy_active", False) or not secret_foxy_frames:
        return
    frame_index = max(0, min(getattr(ctx, "secret_foxy_frame_index", 0), len(secret_foxy_frames) - 1))
    frame = secret_foxy_frames[frame_index]
    max_w = int(surface.get_width() * 0.86)
    max_h = int(surface.get_height() * 0.94)
    scale = min(max_w / frame.get_width(), max_h / frame.get_height())
    draw_w = max(1, int(round(frame.get_width() * scale)))
    draw_h = max(1, int(round(frame.get_height() * scale)))
    draw = pygame.transform.scale(frame, (draw_w, draw_h))

    dim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 64))
    surface.blit(dim, (0, 0))
    rect = draw.get_rect(center=(surface.get_width() // 2, surface.get_height() // 2))
    surface.blit(draw, rect)


INTRO_STAGE_OPENING_ACTION_DURATION = 12.80
INTRO_STAGE_OPENING_SKY_DURATION = 9.80
INTRO_STAGE_OPENING_FALL_END = 11.45
INTRO_STAGE_OPENING_DIALOGUE = [
    {"speaker": "X", "text": "Zero, I'll clear the enemies out here."},
    {"speaker": "X", "text": "You go ahead and deal with the ones inside."},
]

_intro_opening_assets = None
_intro_stage_startup_prewarmed = False
_intro_stage_startup_prewarm_steps = None
_intro_stage_startup_prewarm_cooldown = 0


def _normalize_frames_by_bbox_rightbottom(frames, ref_index=0):
    if not frames:
        return []
    bounds = [frame.get_bounding_rect(min_alpha=1) for frame in frames]
    ref_rect = bounds[max(0, min(ref_index, len(bounds) - 1))]
    normalized = []
    for frame, rect in zip(frames, bounds):
        canvas = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
        dx = ref_rect.right - rect.right
        dy = ref_rect.bottom - rect.bottom
        canvas.blit(frame, (dx, dy))
        normalized.append(canvas)
    return normalized


def _load_intro_stage_opening_assets():
    global _intro_opening_assets
    if _intro_opening_assets is not None:
        return _intro_opening_assets
    _intro_opening_assets = load_intro_opening_assets(ASSETS_DIR)
    return _intro_opening_assets


# queue a little startup work early so the intro stage feels instant later
def _prewarm_intro_stage_startup():
    global _intro_stage_startup_prewarmed
    if _intro_stage_startup_prewarmed:
        return
    _load_intro_stage_opening_assets()
    prewarm_intro_stage_cache()
    _intro_stage_startup_prewarmed = True


def _ensure_intro_stage_arena_assets_cached():
    stone_folder = "intro_stage"
    if stone_folder in arena_assets_cache:
        return
    assets, anim_offsets = build_arena_assets(
        ASSETS_DIR,
        "assets:airbase_tiles",
        auto_align_actions=AUTO_ALIGN_ACTIONS,
        frame_stabilize=FRAME_STABILIZE,
    )
    arena_assets_cache[stone_folder] = assets
    arena_anim_offsets_cache[stone_folder] = anim_offsets


def _run_intro_stage_startup_prewarm_step(*, aggressive=False):
    global _intro_stage_startup_prewarmed
    global _intro_stage_startup_prewarm_steps, _intro_stage_startup_prewarm_cooldown
    if _intro_stage_startup_prewarmed:
        return
    if _intro_stage_startup_prewarm_steps is None:
        _intro_stage_startup_prewarm_steps = [
            _load_intro_stage_marker_layout,
            prewarm_intro_stage_cache,
            _load_intro_stage_opening_assets,
        ]
    if _intro_stage_startup_prewarm_cooldown > 0 and not aggressive:
        _intro_stage_startup_prewarm_cooldown -= 1
        return
    steps_to_run = 2 if aggressive else 1
    while steps_to_run > 0 and _intro_stage_startup_prewarm_steps:
        step = _intro_stage_startup_prewarm_steps.pop(0)
        try:
            step()
        except Exception:
            pass
        steps_to_run -= 1
    if not _intro_stage_startup_prewarm_steps:
        _intro_stage_startup_prewarmed = True
        _intro_stage_startup_prewarm_steps = []
        _intro_stage_startup_prewarm_cooldown = 0
    else:
        _intro_stage_startup_prewarm_cooldown = 0 if aggressive else 8


def _prewarm_intro_stage_startup_blocking():
    while not _intro_stage_startup_prewarmed:
        _run_intro_stage_startup_prewarm_step(aggressive=True)


def _clamp01(value):
    return max(0.0, min(1.0, value))


def _play_sound_safe(sound):
    if sound is None:
        return
    try:
        sound.play()
    except Exception:
        pass


# cutscenes reuse the gameplay dash particles so movement beats still feel connected
def _spawn_cutscene_dash_effect(ctx, center_x, bottom_y, dash_dir, *, scale=0.8):
    if not ctx or not hasattr(ctx, "effects"):
        return
    dash_dir = 1 if dash_dir >= 0 else -1
    dir_sign = -1 if dash_dir > 0 else 1
    back_x = center_x - (dash_dir * 12)
    smoke_x = back_x + (15 * dir_sign)
    smoke_y = bottom_y + 13
    booster_x = back_x + (20 * dir_sign)
    booster_y = bottom_y + 44
    smoke_images = getattr(ctx, "effect_images", {}).get("dash_smoke")
    if smoke_images:
        x = smoke_x - ((smoke_images[0].get_width() * scale) / 2.0)
        y = smoke_y - (smoke_images[0].get_height() * scale)
        ctx.effects.append(
            Effect(
                smoke_images,
                (x, y),
                img_dur=4,
                loop=False,
                vel=(-0.35 * dash_dir, -2.5),
                damp=(0.9, 0.88),
                life=16,
                layer=-1,
                scale=scale,
            )
        )
    booster_images = getattr(ctx, "effect_images", {}).get("dash_booster")
    if booster_images:
        booster_img = booster_images[0]
        x = booster_x - ((booster_img.get_width() * scale) / 2.0)
        y = booster_y - (booster_img.get_height() * scale)
        ctx.effects.append(
            Effect(
                booster_images,
                (x, y),
                img_dur=2,
                loop=False,
                life=6,
                layer=-1,
                flip=(dash_dir < 0),
                scale=scale,
            )
        )


def _play_intro_opening_sound_once(ctx, key, sound):
    if not ctx:
        return
    flags = getattr(ctx, "intro_opening_sound_flags", None)
    if flags is None:
        flags = set()
        ctx.intro_opening_sound_flags = flags
    if key in flags:
        return
    _play_sound_safe(sound)
    flags.add(key)


def _lerp(a, b, t):
    return a + ((b - a) * t)


def _ease_in_out(t):
    t = _clamp01(t)
    return t * t * (3.0 - (2.0 * t))


def _anim_image_for_seconds(anim, elapsed_seconds):
    if anim is None or not getattr(anim, "images", None):
        return None
    frame_tick = max(0, int(round(elapsed_seconds * BASE_FPS)))
    if anim.loop and getattr(anim, "_total", 0) > 0:
        if frame_tick >= anim._total:
            loop_duration = anim._total - anim._loop_start_tick
            if loop_duration > 0:
                frame_tick = anim._loop_start_tick + ((frame_tick - anim._loop_start_tick) % loop_duration)
            else:
                frame_tick = anim._loop_start_tick
    else:
        frame_tick = min(frame_tick, max(0, anim._total - 1))
    for idx, boundary in enumerate(anim._boundaries):
        if frame_tick < boundary:
            return anim.images[idx]
    return anim.images[-1]


def _loop_tail_frames(frames, elapsed_seconds, fps=12.0, tail_count=2):
    if not frames:
        return None
    if len(frames) <= tail_count:
        return frames[int(elapsed_seconds * fps) % len(frames)]
    frame_index = int(elapsed_seconds * fps)
    if frame_index < len(frames):
        return frames[frame_index]
    tail_start = len(frames) - tail_count
    return frames[tail_start + ((frame_index - tail_start) % tail_count)]


def _draw_cutscene_actor(surface, img, world_x, world_y, offset, *, anchor="midbottom", flip=False, scale=1.0):
    if img is None:
        return
    frame = img
    if scale != 1.0:
        frame = pygame.transform.scale(
            frame,
            (
                max(1, int(round(frame.get_width() * scale))),
                max(1, int(round(frame.get_height() * scale))),
            ),
        )
    if flip:
        frame = pygame.transform.flip(frame, True, False)
    rect = frame.get_rect()
    setattr(rect, anchor, (int(round(world_x - offset[0])), int(round(world_y - offset[1]))))
    surface.blit(frame, rect)


def _draw_intro_opening_sky(surface, t, copter_frames, ctx, opening_assets):
    surface.fill((18, 10, 42))

    intro_opening_bg = opening_assets.get("intro_opening_bg")
    intro_opening_bg_width = max(1, int(opening_assets.get("intro_opening_bg_width", 1)))
    intro_opening_bg_front = opening_assets.get("intro_opening_bg_front")
    intro_opening_clouds_back = opening_assets.get("intro_opening_clouds_back")
    intro_opening_clouds_front = opening_assets.get("intro_opening_clouds_front")
    intro_opening_airbase_clouds = opening_assets.get("intro_opening_airbase_clouds")
    if intro_opening_bg is None or intro_opening_airbase_clouds is None:
        return

    bg_scroll = int((t * 54.0) % intro_opening_bg_width)
    front_scroll = int((t * 90.0) % intro_opening_bg_width)
    cloud_back_scroll = int((t * 74.0) % intro_opening_bg_width)
    cloud_front_scroll = int((t * 126.0) % intro_opening_airbase_clouds.get_width())
    bg_y = -286
    front_y = -310

    surface.blit(intro_opening_bg, (-bg_scroll, bg_y))
    surface.blit(intro_opening_bg, (intro_opening_bg_width - bg_scroll, bg_y))
    surface.blit(intro_opening_bg_front, (-front_scroll, front_y))
    surface.blit(intro_opening_bg_front, (intro_opening_bg_width - front_scroll, front_y))
    surface.blit(intro_opening_clouds_back, (-cloud_back_scroll, 18))
    surface.blit(intro_opening_clouds_back, (intro_opening_bg_width - cloud_back_scroll, 18))
    surface.blit(intro_opening_clouds_front, (-bg_scroll, 54))
    surface.blit(intro_opening_clouds_front, (intro_opening_bg_width - bg_scroll, 54))
    surface.blit(intro_opening_airbase_clouds, (-cloud_front_scroll, -8))
    surface.blit(intro_opening_airbase_clouds, (intro_opening_airbase_clouds.get_width() - cloud_front_scroll, -8))
    surface.blit(intro_opening_airbase_clouds, ((intro_opening_airbase_clouds.get_width() * 2) - cloud_front_scroll, -8))

    if not copter_frames:
        return

    distant_specs = [
        {
            "scale": 0.74,
            "start": (ARENA_W * 0.58, -156),
            "target": (ARENA_W * 0.54, -32),
            "arrive_window": (1.20, 2.05),
            "explode_t": 1.20,
            "fall_dx": -152.0,
            "fall_dy": 286.0,
            "explosion_offsets": [
                (-18, -10, 0.00, 0.86),
                (18, 2, 0.06, 0.78),
                (4, 18, 0.12, 0.70),
                (26, -18, 0.18, 0.62),
                (-4, 6, 0.24, 0.58),
                (30, 16, 0.30, 0.50),
            ],
        },
        {
            "scale": 0.72,
            "start": (-196, ARENA_H * 0.58),
            "target": (ARENA_W * 0.80, ARENA_H * 0.69),
            "arrive_window": (0.42, 3.85),
            "explode_t": 3.55,
            "fall_dx": 126.0,
            "fall_dy": 260.0,
            "explosion_offsets": [
                (-16, -8, 0.00, 0.84),
                (16, 8, 0.06, 0.76),
                (30, -12, 0.12, 0.68),
                (-4, 20, 0.18, 0.60),
                (6, -22, 0.24, 0.54),
                (24, 18, 0.30, 0.48),
            ],
        },
        {
            "scale": 0.74,
            "start": (-188, 92),
            "target": (ARENA_W * 0.74, 116),
            "arrive_window": (1.08, 4.75),
            "explode_t": 4.25,
            "fall_dx": 108.0,
            "fall_dy": 270.0,
            "explosion_offsets": [
                (-26, -10, 0.00, 0.90),
                (10, 8, 0.05, 0.80),
                (22, -18, 0.10, 0.72),
                (-2, 20, 0.16, 0.64),
                (18, 18, 0.22, 0.58),
                (-12, 6, 0.28, 0.52),
            ],
        },
    ]
    explosion_frames = []
    if ctx and getattr(ctx, "effect_images", None):
        explosion_frames = ctx.effect_images.get("enemy_destroyed", [])
    for idx, spec in enumerate(distant_specs):
        scale = spec["scale"]
        start_x, start_y = spec["start"]
        target_x, target_y = spec["target"]
        arrive_start, arrive_end = spec["arrive_window"]
        explode_t = spec["explode_t"]
        if t < arrive_start:
            continue
        frame = copter_frames[int(t * 12.0) % len(copter_frames)]
        if idx == 0 and t >= explode_t:
            travel = 1.0
        else:
            travel = _clamp01((t - arrive_start) / max(0.001, arrive_end - arrive_start))
        world_x = _lerp(start_x, target_x, travel)
        world_y = _lerp(start_y, target_y, travel)
        if t >= explode_t:
            hit_t = t - explode_t
            frame = copter_frames[0]
            world_x = target_x + (spec["fall_dx"] * hit_t)
            world_y = target_y + (hit_t * 42.0) + ((hit_t * hit_t) * spec["fall_dy"])
            if world_y > ARENA_H + 160:
                continue
        _draw_cutscene_actor(surface, frame, world_x, world_y, (0, 0), anchor="center", flip=True, scale=scale)
        if t >= explode_t and explosion_frames:
            for dx, dy, phase, boom_scale in spec["explosion_offsets"]:
                local_t = hit_t - phase
                if 0.0 <= local_t <= 0.72:
                    _draw_opening_explosion(surface, explosion_frames, world_x + dx, world_y + dy, local_t, boom_scale * scale / 0.48)

    for lane, phase in ((0.18, 0.00), (0.46, 0.16), (0.72, 0.31)):
        cycle_t = (t * 2.6) + phase
        progress = cycle_t - math.floor(cycle_t)
        x1 = ARENA_W + 36 - (progress * (ARENA_W + 120))
        y1 = (ARENA_H * (0.90 - lane * 0.42)) + (progress * 14)
        x2 = x1 - 48
        y2 = y1 - 48
        pygame.draw.line(surface, (180, 255, 220), (int(x1), int(y1)), (int(x2), int(y2)), 3)
        pygame.draw.line(surface, (250, 255, 255), (int(x1 - 1), int(y1 - 1)), (int(x2 - 1), int(y2 - 1)), 1)

    if ctx:
        haze = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        haze.fill((24, 10, 52, 28))
        surface.blit(haze, (0, 0))


def _draw_opening_explosion(surface, frames, x, y, time_value, scale, offset=(0, 0)):
    if not frames:
        return
    visible_order = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11]
    ordered_frames = [frames[i] for i in visible_order if i < len(frames)]
    if not ordered_frames:
        ordered_frames = list(frames)
    if time_value < 0.0:
        return
    progress = _clamp01(time_value / 0.72)
    index = min(len(ordered_frames) - 1, int(round(progress * (len(ordered_frames) - 1))))
    frame = ordered_frames[index]
    _draw_cutscene_actor(surface, frame, x, y, offset, anchor="center", scale=scale)


def _draw_opening_flash(surface, alpha):
    if alpha <= 0:
        return
    flash = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    flash.fill((220, 255, 255, int(alpha)))
    surface.blit(flash, (0, 0))


# kick off the scripted intro-stage opening and freeze normal gameplay control
def _start_intro_stage_opening(ctx, player):
    if not ctx:
        return
    if current_stage in stage_music:
        if current_stage == "intro_stage":
            intro_path, loop_path = _current_intro_stage_music_pair()
            play_music(intro_path, loop_path)
        else:
            play_music(
                stage_music[current_stage]["intro"],
                stage_music[current_stage]["loop"],
            )
    ctx.cutscene_started = True
    ctx.intro_opening_active = True
    ctx.intro_opening_timer = 0.0
    ctx.intro_opening_dialogue_started = False
    ctx.intro_opening_dialogue_finished = False
    ctx.intro_opening_x_exit_active = False
    ctx.intro_opening_x_exit_timer = 0.0
    ctx.intro_opening_sound_flags = set()
    ctx.intro_opening_explosion_sound_cooldown = 0.0
    ctx.intro_opening_base_scroll = tuple(getattr(ctx, "render_scroll", (0, 0)))
    ctx.intro_opening_scroll = tuple(getattr(ctx, "render_scroll", (0, 0)))
    ctx.intro_opening_assets = _load_intro_stage_opening_assets()
    ctx.intro_opening_landing_x = INTRO_STAGE_SPAWN_X + 72
    ctx.intro_opening_partner_x = ctx.intro_opening_landing_x + 36
    ctx.intro_opening_ground_y = INTRO_STAGE_SPAWN_Y
    ctx.intro_opening_final_scroll = _compute_intro_opening_final_scroll(
        ctx,
        player,
        ctx.intro_opening_landing_x,
        ctx.intro_opening_ground_y,
    )
    if player is not None:
        player.spawn_timer = 0
        player.spawn_sound_played = False
        player.velocity = [0, 0]
        player.hspeed = 0
        player.air_hspeed = 0
        player.set_action("zero_idle", force=True)


def _finish_intro_stage_opening(ctx, player):
    global arena_stage_start_active, arena_stage_ready_anim
    if not ctx:
        return
    ctx.intro_opening_active = False
    live_scroll = tuple(getattr(ctx, "intro_opening_scroll", getattr(ctx, "render_scroll", (0, 0))))
    ctx.render_scroll = live_scroll
    ctx.intro_post_camera_min_x = ctx.render_scroll[0]
    ctx.intro_post_cutscene_hold = 0.0
    if player is not None:
        current_rect = player.rect()
        if getattr(player, "action", None) != "zero_idle":
            player.set_action("zero_idle", force=True)
        _place_player_midbottom(player, current_rect.centerx, current_rect.bottom)
        if arena_tilemap is not None:
            _snap_player_spawn_to_ground(player, arena_tilemap, max_drop=12)
        player.velocity = [0, 0]
        player.hspeed = 0
        player.air_hspeed = 0
        player.grounded = True
        player.collisions = {"up": False, "down": True, "left": False, "right": False}
        player.air_time = 0
        player.air_jumps = player.max_air_jumps
        player.coyote_timer = player.coyote_max
        player.landing_timer = 0
        player.wall_land_timer = 0
        player.wall_slide = False
        player.wall_dir = 0
        player.jump_is_air = False
        player.air_dash_used = False
        player.dash_jump_used = False
        player.flip = False
        player.landing_sound_suppressed_frames = max(getattr(player, "landing_sound_suppressed_frames", 0), 24)
    arena_stage_start_active = True
    _arm_stage_ready_banner()


def _arm_stage_ready_banner():
    global arena_stage_start_active, arena_stage_ready_anim
    arena_stage_start_active = True
    if stage_ready_anim_source and stage_ready_anim_source.images:
        arena_stage_ready_anim = Animation(
            stage_ready_anim_source.images,
            stage_ready_anim_source.durations,
            loop=False,
        )
    else:
        arena_stage_ready_anim = None


def _setup_intro_stage_respawn_spawn(ctx, player):
    global arena_stage_start_active, arena_stage_ready_anim
    global intro_stage_checkpoint_spawn
    if not ctx or player is None:
        return

    if intro_stage_checkpoint_spawn is not None:
        landing_x, ground_y = intro_stage_checkpoint_spawn
    else:
        landing_x = INTRO_STAGE_SPAWN_X + 72
        ground_y = INTRO_STAGE_SPAWN_Y
    ctx.intro_opening_active = False
    ctx.intro_opening_landing_x = landing_x
    ctx.intro_opening_ground_y = ground_y
    landing_rect = pygame.Rect(
        landing_x - (player.size[0] // 2),
        ground_y - player.size[1],
        player.size[0],
        player.size[1],
    )
    respawn_camera_lock = None
    global arena_tilemap
    checkpoint_index = int(getattr(ctx, "intro_checkpoint_index", -1))
    if arena_tilemap and hasattr(arena_tilemap, "prime_camera_for_intro_checkpoint"):
        try:
            respawn_camera_lock = arena_tilemap.prime_camera_for_intro_checkpoint(
                checkpoint_index,
                landing_rect,
                ARENA_W,
                ARENA_H,
                getattr(ctx, "arena_bounds", None),
            )
        except Exception:
            respawn_camera_lock = None
    elif arena_tilemap and hasattr(arena_tilemap, "prime_camera_for_rect"):
        try:
            respawn_camera_lock = arena_tilemap.prime_camera_for_rect(
                landing_rect,
                ARENA_W,
                ARENA_H,
                getattr(ctx, "arena_bounds", None),
            )
        except Exception:
            respawn_camera_lock = None
    ctx.intro_opening_final_scroll = _compute_intro_opening_scroll_for_rect(
        ctx,
        player,
        landing_rect,
        tuple(getattr(ctx, "render_scroll", (0, 0))),
        use_camera_lock=False,
        x_bias=56,
    )
    if respawn_camera_lock:
        scroll_x, scroll_y = ctx.intro_opening_final_scroll
        if "scroll_x" in respawn_camera_lock:
            scroll_x = respawn_camera_lock["scroll_x"]
        if "scroll_y" in respawn_camera_lock:
            scroll_y = respawn_camera_lock["scroll_y"]
        ctx.intro_opening_final_scroll = (scroll_x, scroll_y)
    ctx.render_scroll = ctx.intro_opening_final_scroll
    ctx.intro_post_camera_min_x = ctx.render_scroll[0]
    if checkpoint_index >= 1:
        ctx.intro_locked_left_wall_x = int(round(ctx.render_scroll[0]))
    else:
        ctx.intro_locked_left_wall_x = None
    ctx.intro_locked_right_wall_x = None
    ctx.intro_post_cutscene_hold = 0.0
    ctx.cutscene_active = False
    ctx.intro_vile_sequence_active = False
    ctx.intro_locked_camera_scroll = None

    spawn_uses_anim = player.spawn_time > 0 and 'zero_spawning' in player.game.assets
    if spawn_uses_anim:
        player.spawn_timer = player.spawn_time
        player.spawn_sound_played = False
        player.set_action('zero_spawning', force=True)
    else:
        player.set_action("zero_idle", force=True)
    _place_player_midbottom(player, landing_x, ground_y)
    player.velocity = [0, 0]
    player.hspeed = 0
    player.air_hspeed = 0
    player.grounded = True
    player.collisions = {"up": False, "down": True, "left": False, "right": False}
    player.air_time = 0
    player.air_jumps = player.max_air_jumps
    player.coyote_timer = player.coyote_max
    player.landing_timer = 0
    player.wall_land_timer = 0
    player.wall_slide = False
    player.wall_dir = 0
    player.jump_is_air = False
    player.air_dash_used = False
    player.dash_jump_used = False
    player.flip = False
    player.dead = False
    player.death_timer = 0
    _arm_stage_ready_banner()


def _maybe_update_intro_stage_checkpoint(ctx, player):
    global intro_stage_checkpoint_index, intro_stage_checkpoint_spawn
    if current_stage != "intro_stage" or not ctx or not player or not arena_tilemap:
        return
    player_x = player.rect().centerx
    next_index = int(getattr(ctx, "intro_checkpoint_index", -1)) + 1
    if next_index < 0 or next_index >= len(INTRO_STAGE_CHECKPOINT_XS):
        return
    checkpoint_x = INTRO_STAGE_CHECKPOINT_XS[next_index]
    if player_x < checkpoint_x:
        return
    ground_y = _find_ground_top_near_x(
        arena_tilemap,
        checkpoint_x,
        preferred_y=player.rect().bottom,
        max_distance=320,
    )
    if ground_y is None:
        ground_y = player.rect().bottom
    intro_stage_checkpoint_index = next_index
    intro_stage_checkpoint_spawn = (checkpoint_x, int(ground_y))
    ctx.intro_checkpoint_index = next_index
    player.invuln_timer = 0
    player.hurt_timer = 0
    player.landing_sound_suppressed_frames = max(getattr(player, "landing_sound_suppressed_frames", 0), player.spawn_time + 24)


def _compute_intro_opening_final_scroll(ctx, player, landing_zero_x, ground_y):
    fallback = tuple(getattr(ctx, "render_scroll", (0, 0)))
    if ctx is None or player is None:
        return fallback

    old_pos = list(player.pos)
    old_flip = bool(player.flip)
    try:
        player.pos[0] = landing_zero_x - (player.size[0] // 2)
        player.pos[1] = ground_y - player.size[1]
        player.flip = False
        cam_cx, cam_cy = player.camera_center()
    finally:
        player.pos[0], player.pos[1] = old_pos
        player.flip = old_flip

    landing_rect = pygame.Rect(
        landing_zero_x - (player.size[0] // 2),
        ground_y - player.size[1],
        player.size[0],
        player.size[1],
    )
    return _compute_intro_opening_scroll_for_rect(ctx, player, landing_rect, fallback, use_camera_lock=True, x_bias=56)


def _compute_intro_opening_scroll_for_rect(ctx, player, player_rect, fallback, use_camera_lock=False, x_bias=0):
    if ctx is None or player is None:
        return fallback
    arena_bounds = getattr(ctx, "arena_bounds", None)
    if not arena_bounds:
        return fallback
    ox, oy, w, h = arena_bounds
    cam_cx = player_rect.centerx
    cam_cy = player_rect.centery
    target_x = cam_cx - (ARENA_W / 2) + x_bias
    target_y = cam_cy - (ARENA_H / 2)
    min_x = ox
    max_x = ox + w - ARENA_W
    min_y = oy
    max_y = oy + h - ARENA_H
    if max_x < min_x:
        target_x = ox + (w / 2) - (ARENA_W / 2)
        max_x = min_x = target_x
    if max_y < min_y:
        target_y = oy + (h / 2) - (ARENA_H / 2)
        max_y = min_y = target_y
    target_x = max(min_x, min(target_x, max_x))
    target_y = max(min_y, min(target_y, max_y))

    global arena_tilemap
    try:
        if use_camera_lock and arena_tilemap and hasattr(arena_tilemap, "get_camera_lock"):
            camera_lock = arena_tilemap.get_camera_lock(player_rect, ARENA_W, ARENA_H, arena_bounds)
            if camera_lock:
                if "scroll_x" in camera_lock:
                    target_x = camera_lock["scroll_x"]
                if "scroll_y" in camera_lock:
                    target_y = camera_lock["scroll_y"]
    except Exception:
        pass

    return (target_x, target_y)


# drive the entire intro opening timeline: camera, actors, cues, and handoff back to gameplay
def _update_intro_stage_opening(ctx, player, dt_seconds):
    if not ctx or not getattr(ctx, "intro_opening_active", False):
        return

    if getattr(ctx, "intro_opening_dialogue_started", False):
        if getattr(ctx, "cutscene_active", False):
            _update_arena_cutscene(ctx, dt_seconds)
        elif getattr(ctx, "intro_opening_x_exit_active", False):
            ctx.intro_opening_x_exit_timer = getattr(ctx, "intro_opening_x_exit_timer", 0.0) + dt_seconds
            if ctx.intro_opening_x_exit_timer >= INTRO_STAGE_OPENING_X_EXIT_DURATION:
                _finish_intro_stage_opening(ctx, player)
        elif not getattr(ctx, "intro_opening_dialogue_finished", False):
            ctx.intro_opening_dialogue_finished = True
            ctx.intro_opening_x_exit_active = True
            ctx.intro_opening_x_exit_timer = 0.0
            _play_intro_opening_sound_once(ctx, "x_exit", sfx_exiting)
        return

    ctx.intro_opening_timer = getattr(ctx, "intro_opening_timer", 0.0) + dt_seconds
    t = ctx.intro_opening_timer
    ctx.intro_opening_explosion_sound_cooldown = max(
        0.0,
        getattr(ctx, "intro_opening_explosion_sound_cooldown", 0.0) - dt_seconds,
    )
    base_x, base_y = getattr(ctx, "intro_opening_base_scroll", getattr(ctx, "render_scroll", (0, 0)))
    landing_zero_x = getattr(ctx, "intro_opening_landing_x", INTRO_STAGE_SPAWN_X + 4)
    landing_partner_x = getattr(ctx, "intro_opening_partner_x", landing_zero_x + 30)
    final_scroll_x, final_scroll_y = getattr(ctx, "intro_opening_final_scroll", getattr(ctx, "render_scroll", (base_x, base_y)))
    scroll_x = base_x
    final_ground_y = getattr(ctx, "intro_opening_ground_y", INTRO_STAGE_SPAWN_Y)
    zero_latch_end = 8.40
    zero_slash_end = 8.84
    zero_pause_end = 9.26
    front_gunship_blast_start = 9.57
    landing_blast_end = INTRO_STAGE_OPENING_FALL_END + 0.66

    if t >= zero_latch_end and t < zero_slash_end:
        _play_intro_opening_sound_once(ctx, "zero_gunship_slash", sfx_air_wall_slash)
    if t >= zero_pause_end and t < INTRO_STAGE_OPENING_SKY_DURATION:
        _play_intro_opening_sound_once(ctx, "x_nova_dash", sfx_nova_strike)

    explosion_windows = (
        (1.20, 2.22),
        (3.55, 4.57),
        (4.25, 5.27),
        (front_gunship_blast_start, INTRO_STAGE_OPENING_SKY_DURATION),
        (INTRO_STAGE_OPENING_SKY_DURATION, INTRO_STAGE_OPENING_FALL_END),
        (INTRO_STAGE_OPENING_FALL_END, landing_blast_end),
    )
    explosion_active = any(start <= t <= end for start, end in explosion_windows)
    if explosion_active and getattr(ctx, "intro_opening_explosion_sound_cooldown", 0.0) <= 0.0:
        _play_sound_safe(sfx_enemy_destroyed)
        ctx.intro_opening_explosion_sound_cooldown = 0.16

    if t < INTRO_STAGE_OPENING_SKY_DURATION:
        prefall_start = 8.85
        if t >= prefall_start:
            prep_p = _clamp01((t - prefall_start) / max(0.001, (INTRO_STAGE_OPENING_SKY_DURATION - prefall_start)))
            scroll_x = _lerp(base_x, final_scroll_x, prep_p)
        scroll_y = base_y - 170
    elif t < INTRO_STAGE_OPENING_FALL_END:
        fall_elapsed = max(0.0, t - INTRO_STAGE_OPENING_SKY_DURATION)
        fall_duration = max(0.001, (INTRO_STAGE_OPENING_FALL_END - INTRO_STAGE_OPENING_SKY_DURATION))
        fall_speed = 0.14 * 60.0 * 60.0
        zero_start_y = final_ground_y - (0.5 * fall_speed * fall_duration * fall_duration)
        zero_y = zero_start_y + (0.5 * fall_speed * fall_elapsed * fall_elapsed)
        if zero_y > final_ground_y:
            zero_y = final_ground_y
        if player is not None:
            player.pos[0] = int(round(landing_zero_x - (player.size[0] // 2)))
            player.pos[1] = int(round(zero_y - player.size[1]))
            player.velocity = [0, 0]
            player.hspeed = 0
            player.air_hspeed = 0
            player.flip = False
            scroll_x, scroll_y = _compute_intro_opening_scroll_for_rect(
                ctx,
                player,
                player.rect(),
                (final_scroll_x, final_scroll_y),
                use_camera_lock=False,
                x_bias=56,
            )
        else:
            scroll_x, scroll_y = final_scroll_x, final_scroll_y
    else:
        scroll_x = final_scroll_x
        scroll_y = final_scroll_y
        if player is not None:
            player.pos[0] = int(round(landing_zero_x - (player.size[0] // 2)))
            player.pos[1] = int(round(final_ground_y - player.size[1]))
            player.velocity = [0, 0]
            player.hspeed = 0
            player.air_hspeed = 0
            player.flip = False
            if getattr(player, "action", None) != "zero_idle":
                player.set_action("zero_idle", force=True)
    ctx.intro_opening_scroll = (scroll_x, scroll_y)
    ctx.render_scroll = ctx.intro_opening_scroll

    if t >= INTRO_STAGE_OPENING_ACTION_DURATION:
        ctx.intro_opening_dialogue_started = True
        _start_arena_cutscene(ctx, INTRO_STAGE_OPENING_DIALOGUE)


def _draw_intro_stage_opening(surface, ctx, offset, player=None):
    if not ctx or not getattr(ctx, "intro_opening_active", False):
        return

    assets = getattr(ctx, "intro_opening_assets", None) or _load_intro_stage_opening_assets()
    t = getattr(ctx, "intro_opening_timer", 0.0)
    base_x, base_y = getattr(ctx, "intro_opening_base_scroll", offset)
    landing_zero_x = getattr(ctx, "intro_opening_landing_x", INTRO_STAGE_SPAWN_X + 4)
    landing_partner_x = getattr(ctx, "intro_opening_partner_x", landing_zero_x + 30)
    ground_y = getattr(ctx, "intro_opening_ground_y", 1166)

    copter_start_x = -160
    copter_crash_x = landing_zero_x + 42
    copter_y = 106
    zero_start_x = -44
    x_start_x = ARENA_W + 118
    copter_frames = assets.get("cutscene_copter_frames") or []
    explosion_frames = []
    if ctx and getattr(ctx, "effect_images", None):
        explosion_frames = ctx.effect_images.get("enemy_destroyed", [])

    def _copter_frame(local_t, speed=1.0):
        if not copter_frames:
            return None
        frame = int(local_t * speed * 6.0) % len(copter_frames)
        return copter_frames[frame]

    def _destroyed_copter_frame():
        if not copter_frames:
            return None
        return copter_frames[0]

    zero_climbing_frames = assets.get("zero_climbing_frames") or []
    zero_wallkick_frames = assets.get("zero_wallkick_frames") or []
    zero_wall_saber_frames = assets.get("zero_wall_saber_frames") or []
    zero_idle_frames = assets.get("zero_idle_frames") or []
    zero_jumping_frames = assets.get("zero_jumping_frames") or []
    zero_falling_frames = assets.get("zero_falling_frames") or []
    zero_air_saber_frames = assets.get("zero_air_saber_frames") or []
    x_idle_frames = assets.get("x_idle_frames") or []
    x_falling_frames = assets.get("x_falling_frames") or []
    x_nova_frames = assets.get("x_nova_frames") or []
    zero_wallkick_anim = assets.get("zero_wallkick_jump")
    zero_wall_saber_anim = assets.get("zero_wall_saber_slash")
    zero_jumping_anim = assets.get("zero_jumping")
    zero_falling_anim = assets.get("zero_falling")

    latch_frame = (zero_wallkick_anim.images[-1] if zero_wallkick_anim and getattr(zero_wallkick_anim, "images", None) else None) or (
        zero_wallkick_frames[-1] if zero_wallkick_frames else (
            zero_climbing_frames[min(1, len(zero_climbing_frames) - 1)] if zero_climbing_frames else None
        )
    )
    slash_frame = (zero_wall_saber_anim.images[min(2, len(zero_wall_saber_anim.images) - 1)] if zero_wall_saber_anim and getattr(zero_wall_saber_anim, "images", None) else None) or (
        zero_wall_saber_frames[min(len(zero_wall_saber_frames) // 2, len(zero_wall_saber_frames) - 1)] if zero_wall_saber_frames else (
            zero_air_saber_frames[min(len(zero_air_saber_frames) // 2, len(zero_air_saber_frames) - 1)] if zero_air_saber_frames else None
        )
    )
    zero_jump_frame = (zero_jumping_anim.images[min(1, len(zero_jumping_anim.images) - 1)] if zero_jumping_anim and getattr(zero_jumping_anim, "images", None) else None) or (
        zero_jumping_frames[min(1, len(zero_jumping_frames) - 1)] if zero_jumping_frames else (zero_idle_frames[0] if zero_idle_frames else None)
    )
    zero_fall_frame = zero_falling_frames[min(1, len(zero_falling_frames) - 1)] if zero_falling_frames else zero_jump_frame
    zero_land_frame = zero_idle_frames[0] if zero_idle_frames else zero_jump_frame
    x_nova_frame = x_nova_frames[min(2, len(x_nova_frames) - 1)] if x_nova_frames else None
    x_fall_frame = x_falling_frames[min(1, len(x_falling_frames) - 1)] if x_falling_frames else (x_idle_frames[0] if x_idle_frames else None)
    x_land_frame = x_idle_frames[0] if x_idle_frames else x_fall_frame

    copter_scale = 1.18
    final_zero_x = landing_zero_x
    final_x_x = landing_partner_x
    final_copter_x = int(round((final_zero_x + final_x_x) * 0.5))
    hero_arrival_start = 6.10
    hero_arrival_end = 7.55
    zero_jump_end = 8.35
    zero_latch_end = 8.40
    zero_slash_end = 8.84
    zero_pause_end = 9.26

    if t < INTRO_STAGE_OPENING_SKY_DURATION:
        _draw_intro_opening_sky(surface, t, copter_frames, ctx, assets)

        if t < hero_arrival_start:
            return
        if t < hero_arrival_end:
            p = _clamp01((t - hero_arrival_start) / max(0.001, (hero_arrival_end - hero_arrival_start)))
            copter_x = _lerp(copter_start_x, ARENA_W * 0.60, p)
            copter_img = _copter_frame(t, 1.6)
            _draw_cutscene_actor(surface, copter_img, copter_x, copter_y, (0, 0), anchor="center", flip=True, scale=copter_scale)
        elif t < zero_jump_end:
            p = _clamp01((t - hero_arrival_end) / max(0.001, (zero_jump_end - hero_arrival_end)))
            local_t = max(0.0, t - hero_arrival_end)
            copter_x = _lerp(ARENA_W * 0.60, ARENA_W * 0.56, _ease_in_out(p))
            zero_x = _lerp(zero_start_x, copter_x - 46, p)
            jump_start_y = ARENA_H + 18
            jump_end_y = copter_y + 58
            zero_y = _lerp(jump_start_y, jump_end_y, p) - (4.0 * 76.0 * p * (1.0 - p))
            copter_img = _copter_frame(t, 1.6)
            _draw_cutscene_actor(surface, copter_img, copter_x, copter_y, (0, 0), anchor="center", flip=True, scale=copter_scale)
            if p < 0.54:
                zero_img = _anim_image_for_seconds(zero_jumping_anim, local_t) if zero_jumping_anim else zero_jump_frame
            else:
                descent_elapsed = max(0.0, local_t - ((zero_jump_end - hero_arrival_end) * 0.54))
                zero_img = _anim_image_for_seconds(zero_falling_anim, descent_elapsed) if zero_falling_anim else zero_fall_frame
            _draw_cutscene_actor(surface, zero_img if zero_img else latch_frame, zero_x, zero_y, (0, 0), anchor="midbottom", flip=False, scale=1.00)
        elif t < zero_latch_end:
            copter_x = ARENA_W * 0.56
            zero_x = copter_x - 46
            zero_y = copter_y + 58
            copter_img = _copter_frame(t, 1.6)
            _draw_cutscene_actor(surface, copter_img, copter_x, copter_y, (0, 0), anchor="center", flip=True, scale=copter_scale)
            _draw_cutscene_actor(surface, latch_frame, zero_x, zero_y, (0, 0), anchor="midbottom", flip=True, scale=1.00)
        elif t < zero_slash_end:
            local_t = t - zero_latch_end
            copter_x = ARENA_W * 0.56
            zero_x = copter_x - 46
            zero_y = copter_y + 58
            copter_img = _copter_frame(t, 1.6)
            _draw_cutscene_actor(surface, copter_img, copter_x, copter_y, (0, 0), anchor="center", flip=True, scale=copter_scale)
            slash_anim_t = min(local_t * 1.25, 0.56)
            slash_img = _anim_image_for_seconds(zero_wall_saber_anim, slash_anim_t)
            _draw_cutscene_actor(surface, slash_img if slash_img else (slash_frame or latch_frame), zero_x, zero_y, (0, 0), anchor="midbottom", flip=True, scale=1.00)
        elif t < zero_pause_end:
            copter_x = ARENA_W * 0.56
            zero_x = copter_x - 46
            zero_y = copter_y + 58
            copter_img = _copter_frame(t, 1.6)
            _draw_cutscene_actor(surface, copter_img, copter_x, copter_y, (0, 0), anchor="center", flip=True, scale=copter_scale)
            _draw_cutscene_actor(surface, latch_frame, zero_x, zero_y, (0, 0), anchor="midbottom", flip=True, scale=1.00)
        else:
            local_t = t - zero_pause_end
            p = _ease_in_out(local_t / max(0.001, (INTRO_STAGE_OPENING_SKY_DURATION - zero_pause_end)))
            copter_x = ARENA_W * 0.56
            copter_img = _destroyed_copter_frame() if p > 0.58 else _copter_frame(t, 1.6)
            zero_x = copter_x - 46
            zero_y = copter_y + 58
            x_x = _lerp(x_start_x, copter_x + 30, p)
            x_y = copter_y + 34
            _draw_cutscene_actor(surface, copter_img, copter_x, copter_y, (0, 0), anchor="center", flip=True, scale=copter_scale)
            _draw_cutscene_actor(surface, latch_frame, zero_x, zero_y, (0, 0), anchor="midbottom", flip=True, scale=1.00)
            nova_img = _loop_tail_frames(x_nova_frames, local_t * 1.45, fps=10.0, tail_count=2)
            _draw_cutscene_actor(surface, nova_img if nova_img else (x_nova_frame or x_fall_frame), x_x, x_y, (0, 0), anchor="midbottom", flip=True, scale=1.00)
            if p > 0.58:
                boom_t = (p - 0.58) / 0.42
                _draw_opening_flash(surface, 84 * _ease_in_out((p - 0.58) / 0.14))
                front_blasts = [
                    (-40, 8, 0.00, 1.42),
                    (-26, -14, 0.04, 1.30),
                    (-8, 18, 0.08, 1.18),
                    (12, -10, 0.12, 1.14),
                    (30, 12, 0.16, 1.02),
                    (44, -6, 0.20, 0.94),
                    (10, -24, 0.24, 0.90),
                ]
                for dx, dy, phase, blast_scale in front_blasts:
                    local_boom_t = max(0.0, (boom_t - phase) * 0.72)
                    _draw_opening_explosion(surface, explosion_frames, copter_x + dx, copter_y + dy, local_boom_t, blast_scale)
        return

    if t < INTRO_STAGE_OPENING_FALL_END:
        fall_elapsed = max(0.0, t - INTRO_STAGE_OPENING_SKY_DURATION)
        fall_duration = max(0.001, (INTRO_STAGE_OPENING_FALL_END - INTRO_STAGE_OPENING_SKY_DURATION))
        fall_t = _clamp01(fall_elapsed / fall_duration)
        zero_x = final_zero_x
        x_x = final_x_x
        fall_speed = 0.14 * 60.0 * 60.0
        zero_start_y = ground_y - (0.5 * fall_speed * fall_duration * fall_duration)
        x_start_y = zero_start_y - 6
        zero_y = zero_start_y + (0.5 * fall_speed * fall_elapsed * fall_elapsed)
        x_y = x_start_y + (0.5 * fall_speed * fall_elapsed * fall_elapsed)
        if zero_y > ground_y:
            zero_y = ground_y
        if x_y > ground_y:
            x_y = ground_y
        copter_x = final_copter_x
        copter_drop_y = zero_y - 40
        copter_img = _destroyed_copter_frame()
        _draw_cutscene_actor(surface, copter_img, copter_x, copter_drop_y, offset, anchor="center", flip=True, scale=copter_scale)
        boom_t = max(0.0, t - INTRO_STAGE_OPENING_SKY_DURATION)
        if explosion_frames:
            crash_offsets = [
                (-40, 2, 0.00, 1.34),
                (-24, -14, 0.06, 1.20),
                (-6, 18, 0.12, 1.10),
                (16, -20, 0.18, 1.00),
                (34, 8, 0.24, 0.94),
                (46, -4, 0.30, 0.88),
                (10, 24, 0.36, 0.84),
            ]
            for dx, dy, phase, boom_scale in crash_offsets:
                if fall_t < phase:
                    continue
                local_t = ((boom_t * 1.65) + (phase * 1.35)) % 0.72
                _draw_opening_explosion(
                    surface,
                    explosion_frames,
                    copter_x + dx,
                    copter_drop_y + dy,
                    local_t,
                    boom_scale,
                    offset=offset,
                )
            if fall_t > 0.58:
                impact_trail_t = (fall_t - 0.58) / 0.42
                impact_trail_blasts = [
                    (-24, 20, 0.00, 1.10),
                    (8, 18, 0.08, 1.02),
                    (34, 12, 0.16, 0.94),
                ]
                for dx, dy, phase, boom_scale in impact_trail_blasts:
                    local_t = 0.10 + max(0.0, impact_trail_t - phase)
                    _draw_opening_explosion(
                        surface,
                        explosion_frames,
                        copter_x + dx,
                        copter_drop_y + dy,
                        local_t,
                        boom_scale,
                        offset=offset,
                    )
        if zero_falling_frames:
            if zero_falling_anim and getattr(zero_falling_anim, "images", None):
                # Use all frames if available, up to 6 frames for the full falling animation
                zero_fall_loop = list(zero_falling_anim.images[:6] if len(zero_falling_anim.images) >= 6 else zero_falling_anim.images[:3] if len(zero_falling_anim.images) >= 3 else zero_falling_anim.images)
            else:
                # Use cropped frames similarly
                zero_fall_loop = list(zero_falling_frames[:6] if len(zero_falling_frames) >= 6 else zero_falling_frames[:3] if len(zero_falling_frames) >= 3 else zero_falling_frames)
            
            # Determine the tail count for looping the falling animation
            if len(zero_fall_loop) >= 6:
                tail_count = 4  # Loop frames 3-6 (indices 2-5)
            elif len(zero_fall_loop) >= 3:
                tail_count = 2  # Loop frames 2-3 (indices 1-2)
            else:
                tail_count = max(1, len(zero_fall_loop) - 1)
            
            zero_fall_img = _loop_tail_frames(zero_fall_loop, fall_elapsed, fps=BASE_FPS / 4.0, tail_count=tail_count)
        else:
            zero_fall_img = zero_fall_frame
        if x_falling_frames:
            if fall_t < 0.16:
                x_fall_img = x_falling_frames[0]
            else:
                x_fall_img = x_falling_frames[min(1, len(x_falling_frames) - 1)]
        else:
            x_fall_img = x_fall_frame
        _draw_cutscene_actor(surface, zero_fall_img, zero_x, zero_y, offset, anchor="midbottom", flip=False, scale=1.0)
        _draw_cutscene_actor(surface, x_fall_img, x_x, x_y, offset, anchor="midbottom", flip=True, scale=1.00)
    else:
        landing_boom_t = min(0.78, max(0.0, t - INTRO_STAGE_OPENING_FALL_END))
        final_copter_y = ground_y - 38
        if landing_boom_t < 0.44:
            copter_img = _destroyed_copter_frame()
            _draw_cutscene_actor(surface, copter_img, final_copter_x, final_copter_y, offset, anchor="center", flip=True, scale=copter_scale)
        if explosion_frames and landing_boom_t < 0.66:
            landing_blasts = [
                (-6, 4, 0.18, 1.52),
                (24, -2, 0.22, 1.34),
                (6, -18, 0.26, 1.18),
                (16, 14, 0.14, 1.08),
            ]
            for dx, dy, phase, boom_scale in landing_blasts:
                _draw_opening_explosion(
                    surface,
                    explosion_frames,
                    final_copter_x + dx,
                    final_copter_y + dy,
                    phase + landing_boom_t,
                    boom_scale,
                    offset=offset,
                )
            if landing_boom_t < 0.22:
                _draw_opening_explosion(
                    surface,
                    explosion_frames,
                    final_copter_x + 4,
                    final_copter_y - 6,
                    0.10 + (landing_boom_t * 1.5),
                    1.74,
                    offset=offset,
                )
        if player is not None and landing_boom_t < 0.14:
            _draw_cutscene_actor(surface, zero_land_frame, final_zero_x, ground_y, offset, anchor="midbottom", flip=False, scale=1.0)
        elif player is not None:
            player.render(surface, offset=offset)
        else:
            _draw_cutscene_actor(surface, zero_land_frame, final_zero_x, ground_y, offset, anchor="midbottom", flip=False, scale=1.0)
        if getattr(ctx, "intro_opening_x_exit_active", False):
            _draw_intro_opening_x_exit(
                surface,
                final_x_x,
                ground_y,
                offset,
                assets.get("x_exit_tail_frames") or [],
                getattr(ctx, "intro_opening_x_exit_timer", 0.0),
            )
        else:
            _draw_cutscene_actor(surface, x_land_frame, final_x_x, ground_y, offset, anchor="midbottom", flip=True, scale=1.00)


# generic text cutscene starter used for short arena dialogue beats
def _start_arena_cutscene(ctx, lines):
    if not ctx or not lines:
        return
    ctx.cutscene_lines = list(lines)
    ctx.cutscene_index = 0
    ctx.cutscene_active = True
    ctx.cutscene_type_timer = 0.0
    ctx.cutscene_visible_progress = 0.0
    ctx.cutscene_visible_chars = 0
    ctx.cutscene_panel_timer = 0.0
    ctx.cutscene_auto_advance_timer = 0.0
    ctx.cutscene_text_sound_cooldown = 0.0
    ctx.cutscene_started = True


def _cutscene_current_line(ctx):
    if not ctx or not getattr(ctx, "cutscene_active", False):
        return None
    lines = getattr(ctx, "cutscene_lines", [])
    if not lines:
        return None
    return lines[min(ctx.cutscene_index, len(lines) - 1)]


def _cutscene_line_fully_revealed(ctx):
    current = _cutscene_current_line(ctx)
    if current is None:
        return False
    total_chars = len(current.get("text", ""))
    return getattr(ctx, "cutscene_visible_chars", 0) >= total_chars


def _cutscene_reveal_hold_active():
    try:
        keys = pygame.key.get_pressed()
    except Exception:
        keys = ()
    for key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_j, pygame.K_k, pygame.K_x):
        if key < len(keys) and keys[key]:
            return True

    try:
        mouse_buttons = pygame.mouse.get_pressed(5)
    except Exception:
        mouse_buttons = ()
    for btn in (MOUSE_ATTACK_BUTTON, MOUSE_GIGA_BUTTON, *sorted(MOUSE_DASH_BUTTONS)):
        idx = btn - 1
        if 0 <= idx < len(mouse_buttons) and mouse_buttons[idx]:
            return True

    if joystick:
        for btn in (BTN_A, BTN_B, BTN_X, BTN_Y, BTN_START):
            try:
                if joystick.get_button(btn):
                    return True
            except Exception:
                continue
    return False


def _advance_arena_cutscene(ctx, source="any"):
    if not ctx or not getattr(ctx, "cutscene_active", False):
        return
    lines = getattr(ctx, "cutscene_lines", [])
    if not lines:
        ctx.cutscene_active = False
        return
    current = lines[min(ctx.cutscene_index, len(lines) - 1)]
    total_chars = len(current.get("text", ""))
    if ctx.cutscene_visible_chars < total_chars:
        ctx.cutscene_visible_progress = float(total_chars)
        ctx.cutscene_visible_chars = total_chars
        return
    ctx.cutscene_index += 1
    if ctx.cutscene_index >= len(lines):
        ctx.cutscene_active = False
        return
    ctx.cutscene_type_timer = 0.0
    ctx.cutscene_visible_progress = 0.0
    ctx.cutscene_visible_chars = 0
    ctx.cutscene_auto_advance_timer = 0.0
    ctx.cutscene_text_sound_cooldown = 0.0


def _update_arena_cutscene(ctx, dt_seconds):
    if not ctx or not getattr(ctx, "cutscene_active", False):
        return
    lines = getattr(ctx, "cutscene_lines", [])
    if not lines:
        ctx.cutscene_active = False
        return
    current = lines[min(ctx.cutscene_index, len(lines) - 1)]
    text = current.get("text", "")
    target_chars = len(text)
    ctx.cutscene_panel_timer = getattr(ctx, "cutscene_panel_timer", 0.0) + dt_seconds
    ctx.cutscene_text_sound_cooldown = max(
        0.0,
        getattr(ctx, "cutscene_text_sound_cooldown", 0.0) - dt_seconds,
    )
    if getattr(ctx, "cutscene_panel_timer", 0.0) < INTRO_CUTSCENE_PANEL_POP_DURATION:
        return
    if ctx.cutscene_visible_chars >= target_chars:
        return
    prev_visible = ctx.cutscene_visible_chars
    ctx.cutscene_type_timer += dt_seconds
    chars_per_second = INTRO_CUTSCENE_TEXT_SPEED
    if _cutscene_reveal_hold_active():
        chars_per_second *= INTRO_CUTSCENE_TEXT_HOLD_MULTIPLIER
    current_progress = float(getattr(ctx, "cutscene_visible_progress", float(prev_visible)))
    reveal = current_progress + (dt_seconds * chars_per_second)
    ctx.cutscene_visible_progress = max(0.0, min(float(target_chars), reveal))
    reveal = int(ctx.cutscene_visible_progress)
    ctx.cutscene_visible_chars = max(0, min(target_chars, reveal))
    if ctx.cutscene_visible_chars > prev_visible:
        ctx.cutscene_auto_advance_timer = 0.0
        for idx in range(prev_visible, ctx.cutscene_visible_chars):
            ch = text[idx]
            if ch.isspace():
                continue
            if getattr(ctx, "cutscene_text_sound_cooldown", 0.0) > 0.0:
                continue
            try:
                text_appearing_sound.play()
            except Exception:
                pass
            ctx.cutscene_text_sound_cooldown = INTRO_CUTSCENE_TEXT_SOUND_COOLDOWN
            break


def _cutscene_space_width(scale):
    return max(1, int(round(5 * scale)))


def _guidance_text_runs(text):
    runs = []
    text = str(text or "")
    idx = 0
    while idx < len(text):
        start = text.find("(", idx)
        if start < 0:
            if idx < len(text):
                runs.append((text[idx:], False))
            break
        if start > idx:
            runs.append((text[idx:start], False))
        end = text.find(")", start)
        if end < 0:
            runs.append((text[start:], True))
            break
        runs.append((text[start:end + 1], True))
        idx = end + 1
    return runs


# keep guidance text wrapping consistent with the game's sprite-font spacing rules
def _wrap_guidance_text(text, max_width, scale=1, letter_spacing=None, space_width=None):
    if letter_spacing is None:
        letter_spacing = LETTER_SPACING
    if space_width is None:
        space_width = _cutscene_space_width(scale)
    lines = []
    current_line = []
    current_width = 0

    for run_text, highlighted in _guidance_text_runs(text):
        parts = re.split(r"(\s+)", run_text)
        for part in parts:
            if not part:
                continue
            if part.isspace():
                if current_line:
                    current_line.append((" ", highlighted))
                    current_width += space_width
                continue
            token_width = calculate_text_width_ex(
                part,
                highlighted=highlighted,
                scale=scale,
                force_upper=True,
                letter_spacing=letter_spacing,
                space_width=space_width,
            )
            if current_line and current_width + token_width > max_width:
                while current_line and current_line[-1][0] == " ":
                    current_line.pop()
                lines.append(current_line)
                current_line = []
                current_width = 0
            current_line.append((part, highlighted))
            current_width += token_width

    while current_line and current_line[-1][0] == " ":
        current_line.pop()
    if current_line:
        lines.append(current_line)
    return lines or [[]]


def _draw_guidance_text_line(surface, runs, x, y, scale=1, letter_spacing=None, space_width=None):
    if letter_spacing is None:
        letter_spacing = LETTER_SPACING
    if space_width is None:
        space_width = _cutscene_space_width(scale)
    offset_x = 0
    for text, highlighted in runs:
        if text == " ":
            offset_x += space_width
            continue
        draw_text_left_on(
            surface,
            text,
            x + offset_x,
            y,
            highlighted=highlighted,
            scale=scale,
            letter_spacing=letter_spacing,
            space_width=space_width,
        )
        offset_x += calculate_text_width_ex(
            text,
            highlighted=highlighted,
            scale=scale,
            force_upper=True,
            letter_spacing=letter_spacing,
            space_width=space_width,
        )


def _wrap_cutscene_text(text, max_width, scale=1, letter_spacing=None, space_width=None):
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if calculate_text_width_ex(
            candidate,
            highlighted=False,
            scale=scale,
            force_upper=True,
            letter_spacing=letter_spacing,
            space_width=space_width,
        ) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_cutscene_text_layout(text, max_width, max_lines, layout_options):
    if not text:
        scale, letter_spacing, line_height = layout_options[-1]
        return {
            "scale": scale,
            "letter_spacing": letter_spacing,
            "space_width": _cutscene_space_width(scale),
            "line_height": line_height,
            "wrapped": [""],
        }

    best = None
    for scale, letter_spacing, line_height in layout_options:
        space_width = _cutscene_space_width(scale)
        wrapped = _wrap_cutscene_text(
            text,
            max_width,
            scale=scale,
            letter_spacing=letter_spacing,
            space_width=space_width,
        )
        layout = {
            "scale": scale,
            "letter_spacing": letter_spacing,
            "space_width": space_width,
            "line_height": line_height,
            "wrapped": wrapped,
        }
        if len(wrapped) <= max_lines:
            return layout
        best = layout
    return best


def _draw_intro_opening_x_exit(surface, x, ground_y, offset, exit_frames, local_t):
    _draw_intro_opening_exit(surface, x, ground_y, offset, exit_frames, local_t, flip=True)


def _get_scaled_giga_background_surface(ctx, target_size):
    if not ctx:
        return None
    bg = getattr(ctx, "assets", {}).get("giga_attack_background")
    if bg is None:
        return None
    target_w = max(1, int(round(target_size[0] * ARENA_GIGA_BACKGROUND_OVERSCAN)))
    target_h = max(1, int(round(target_size[1] * ARENA_GIGA_BACKGROUND_OVERSCAN)))
    cache_key = (id(bg), target_w, target_h)
    cached_key = getattr(ctx, "giga_background_cache_key", None)
    cached_surface = getattr(ctx, "giga_background_surface", None)
    if cached_surface is not None and cached_key == cache_key:
        return cached_surface
    scaled = pygame.transform.scale(bg, (target_w, target_h))
    ctx.giga_background_cache_key = cache_key
    ctx.giga_background_surface = scaled
    return scaled


def _giga_beam_visible_in_view(beam, render_scroll, view_size):
    if beam is None:
        return False
    beam_rect = pygame.Rect(int(beam.pos[0]), int(beam.pos[1]), int(getattr(beam, "width", 0)), int(getattr(beam, "height", 0)))
    view_rect = pygame.Rect(int(render_scroll[0]), int(render_scroll[1]), int(view_size[0]), int(view_size[1]))
    return beam_rect.colliderect(view_rect)


def _should_draw_giga_background(ctx, player, render_scroll, view_size):
    if not ctx or not player or not player.giga_active:
        return False
    if getattr(ctx, "assets", {}).get("giga_attack_background") is None:
        return False
    beams = list(getattr(ctx, "giga_beams", []) or [])
    any_visible = any(_giga_beam_visible_in_view(beam, render_scroll, view_size) for beam in beams)
    if any_visible:
        ctx.giga_background_beam_seen = True
        return True
    return not getattr(ctx, "giga_background_beam_seen", False)


def _draw_giga_attack_background(surface, ctx):
    if not surface or not ctx:
        return
    bg = _get_scaled_giga_background_surface(ctx, surface.get_size())
    if bg is None:
        return
    bg_w = bg.get_width()
    bg_h = bg.get_height()
    scroll_y = int(getattr(ctx, "giga_background_scroll", 0.0)) % bg_h
    draw_y = scroll_y - bg_h
    draw_x = (surface.get_width() - bg_w) // 2
    while draw_y < surface.get_height():
        surface.blit(bg, (draw_x, draw_y))
        draw_y += bg_h


# helper for the short exit burst during the opening sequence
def _draw_intro_opening_exit(surface, x, ground_y, offset, exit_frames, local_t, *, flip):
    if not exit_frames:
        return
    static_frames = exit_frames[:-1] or exit_frames
    beam_frame = exit_frames[-1]
    frame_duration = 0.10
    static_duration = frame_duration * len(static_frames)
    if local_t < static_duration:
        frame_index = min(len(static_frames) - 1, int(local_t / frame_duration))
        _draw_cutscene_actor(
            surface,
            static_frames[frame_index],
            x,
            ground_y,
            offset,
            anchor="midbottom",
            flip=flip,
            scale=1.0,
        )
        return

    travel_duration = max(0.001, INTRO_STAGE_OPENING_X_EXIT_DURATION - static_duration)
    travel_progress = _clamp01((local_t - static_duration) / travel_duration)
    screen_bottom = ground_y - offset[1]
    offscreen_bottom = -beam_frame.get_height() - 12
    beam_screen_bottom = _lerp(screen_bottom, offscreen_bottom, _ease_in_out(travel_progress))
    beam_y = beam_screen_bottom + offset[1]
    _draw_cutscene_actor(
        surface,
        beam_frame,
        x,
        beam_y,
        offset,
        anchor="midbottom",
        flip=flip,
        scale=1.0,
    )


def _play_sound_safe(sound):
    if sound is None:
        return
    try:
        sound.play()
    except Exception:
        pass


def _lock_intro_balcony_camera(ctx, scroll):
    if not ctx:
        return
    lock_x = int(round(scroll[0]))
    lock_y = int(round(scroll[1]))
    ctx.intro_locked_camera_scroll = (lock_x, lock_y)
    ctx.intro_locked_left_wall_x = lock_x
    ctx.intro_locked_right_wall_x = lock_x + ARENA_W


def _place_player_midbottom(player, center_x, bottom_y):
    rect = player.rect()
    rect.midbottom = (int(round(center_x)), int(round(bottom_y)))
    ox, oy = player._hitbox_offsets()
    player.pos[0] = rect.x - ox
    player.pos[1] = rect.y - oy


def _snap_player_spawn_to_ground(player, tilemap, max_drop=8):
    if player is None or tilemap is None:
        return
    rect = player.rect()
    support = pygame.Rect(rect.left + 2, rect.bottom - 2, max(1, rect.w - 4), max_drop + 4)
    best_distance = None
    best_rect = None
    for ground in tilemap.physics_rects_around(support.topleft, support.size):
        if ground.left >= support.right or ground.right <= support.left:
            continue
        distance = ground.top - rect.bottom
        if -2 <= distance <= max_drop and (best_distance is None or abs(distance) < abs(best_distance)):
            best_distance = distance
            best_rect = ground
    if best_rect is None:
        return
    _place_player_midbottom(player, rect.centerx, best_rect.top)
    player.velocity = [0, 0]
    player.hspeed = 0
    player.air_hspeed = 0
    player.grounded = True
    player.collisions = {"up": False, "down": True, "left": False, "right": False}
    player.air_time = 0
    player.landing_timer = 0
    player.wall_land_timer = 0
    player.coyote_timer = player.coyote_max
    player.landing_sound_suppressed_frames = max(getattr(player, "landing_sound_suppressed_frames", 0), 24)


def _format_elapsed_time(total_seconds):
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _stage_display_name(stage_key):
    if stage_key == "intro_stage":
        return "INTRO STAGE"
    if not stage_key:
        return "UNKNOWN STAGE"
    return stage_key.replace("_", " ").upper()


# runtime save path first, then fall back to the legacy local json if needed
def _load_leaderboard_records():
    candidate_paths = [LEADERBOARD_RECORDS_PATH]
    if LEGACY_LEADERBOARD_RECORDS_PATH not in candidate_paths:
        candidate_paths.append(LEGACY_LEADERBOARD_RECORDS_PATH)
    for path in candidate_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_leaderboard_records(records):
    try:
        ensure_runtime_dir(os.path.dirname(LEADERBOARD_RECORDS_PATH))
        with open(LEADERBOARD_RECORDS_PATH, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
    except Exception:
        pass


def _append_leaderboard_record(name, result_data):
    records = _load_leaderboard_records()
    records.append(
        {
            "name": name,
            "stage": result_data.get("stage_key", ""),
            "stage_label": result_data.get("stage_label", ""),
            "result": result_data.get("outcome", ""),
            "score": int(result_data.get("score", 0)),
            "elapsed_seconds": int(result_data.get("elapsed_time", 0.0)),
            "elapsed_label": _format_elapsed_time(result_data.get("elapsed_time", 0.0)),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    _save_leaderboard_records(records[-250:])


def _clear_arena_runtime():
    global arena_player, arena_copters, arena_enemy_projectiles, arena_tilemap, arena_ctx
    arena_player = None
    arena_copters = []
    arena_enemy_projectiles = []
    arena_tilemap = None
    arena_ctx = None


def _complete_intro_stage_to_stage_select():
    _set_paused(False)
    _stop_all_audio_immediately()
    _begin_ui_major_transition("intro_to_stage_select", play_start_sound=True)


def _finish_return_to_title_screen():
    global state, selected_index, current_selection, menu_root_drawn_once
    global arena_player, arena_copters, arena_enemy_projectiles, arena_tilemap, arena_ctx
    global airbase_x, clouds_x, seabase_x
    global menu_confirm_target, menu_current_view, menu_submenu_scroll

    play_music(title_intro, title_loop)
    airbase_x = 0
    clouds_x = 0
    seabase_x = 0
    state = "menu"
    selected_index = 0
    current_selection = "game_icon"
    arena_player = None
    arena_copters = []
    arena_enemy_projectiles = []
    arena_tilemap = None
    arena_ctx = None
    menu_confirm_target = None
    menu_current_view = None
    menu_submenu_scroll = 0
    menu_root_drawn_once = False


# full reset path back to the title without restarting the whole app
def _return_to_title_screen():
    _begin_ui_major_transition("return_to_title", play_start_sound=True)


def _begin_ui_major_transition(action, **payload):
    global ui_major_transition
    play_start_sound = bool(payload.pop("play_start_sound", False))
    _stop_all_audio_immediately()
    if play_start_sound:
        _play_menu_start_sound()
    ui_major_transition = {
        "action": action,
        "timer": 0.0,
        "alpha": 0.0,
    }
    ui_major_transition.update(payload)


def _complete_ui_major_transition(transition):
    global state, arena_result_data, current_selection, menu_root_drawn_once
    global airbase_x, clouds_x, seabase_x
    action = transition.get("action")
    if action == "capcom_to_menu":
        state = "menu"
        menu_root_drawn_once = False
        play_music(title_intro, title_loop)
        return
    if action == "return_to_title":
        _finish_return_to_title_screen()
        return
    if action == "intro_to_stage_select":
        play_music(stage_select_intro, stage_select_loop)
        if current_stage in stage_slots:
            current_selection = current_stage
        state = "stage_select"
        airbase_x = 0
        clouds_x = 0
        seabase_x = 0
        _clear_arena_runtime()
        return
    if action == "stage_select_to_menu":
        _finish_return_to_title_screen()
        return
    if action == "arena_result_finish":
        destination = transition.get("destination", "stage_select")
        if destination == "stage_select":
            play_music(stage_select_intro, stage_select_loop)
            if current_stage in stage_slots:
                current_selection = current_stage
            state = "stage_select"
        else:
            play_music(title_intro, title_loop)
            state = "menu"
            menu_root_drawn_once = False
        airbase_x = 0
        clouds_x = 0
        seabase_x = 0
        _clear_arena_runtime()
        arena_result_data = None


def _begin_intro_stage_black_transition(action):
    global intro_stage_black_transition
    intro_stage_black_transition = {
        "action": action,
        "timer": 0.0,
        "alpha": 0.0,
    }


def _restart_current_stage():
    global state, paused, pause_slide
    global current_music, music_intro_playing, music_loop_path
    global intro_stage_respawn_via_spawn
    _set_paused(False)
    paused = False
    pause_slide = 0.0
    stop_music(120)
    pygame.mixer.music.stop()
    current_music = None
    music_intro_playing = False
    music_loop_path = None
    intro_stage_respawn_via_spawn = current_stage == "intro_stage"
    _clear_arena_runtime()
    if current_stage in stage_music:
        if current_stage == "intro_stage":
            intro_path, loop_path = _current_intro_stage_music_pair()
            play_music(intro_path, loop_path)
        else:
            play_music(stage_music[current_stage]["intro"], stage_music[current_stage]["loop"])
    state = "stage_viewer"


def _begin_arena_result(outcome, destination="stage_select"):
    global state, paused, pause_slide, arena_result_data
    global current_music, music_intro_playing, music_loop_path

    arena_result_data = {
        "outcome": outcome,
        "destination": destination,
        "step": "banner",
        "save_choice": 0,
        "name_input": "",
        "stage_key": current_stage,
        "stage_label": _stage_display_name(current_stage),
        "score": int(getattr(arena_ctx, "score", 0)) if arena_ctx else 0,
        "elapsed_time": float(getattr(arena_ctx, "elapsed_time", 0.0)) if arena_ctx else 0.0,
    }
    if outcome == "success":
        arena_result_data["heading"] = "MISSION SUCCESSFUL"
        arena_result_data["subheading"] = "STAGE EXITED"
    else:
        arena_result_data["heading"] = "GAME OVER"
        arena_result_data["subheading"] = "MISSION FAILED"

    _set_paused(False)
    paused = False
    pause_slide = 0.0
    stop_music(80)
    pygame.mixer.music.stop()
    current_music = None
    music_intro_playing = False
    music_loop_path = None
    state = "arena_result"


def _finish_arena_result():
    destination = (arena_result_data or {}).get("destination", "stage_select")
    if destination == "title":
        _begin_ui_major_transition("arena_result_finish", destination=destination, play_start_sound=True)
        return
    _begin_ui_major_transition("arena_result_finish", destination=destination)


def _confirm_arena_result():
    global arena_result_data
    if not arena_result_data:
        return
    step = arena_result_data.get("step")
    if step == "banner":
        arena_result_data["step"] = "save_prompt"
        arena_result_data["save_choice"] = 0
        return
    if step == "save_prompt":
        if arena_result_data.get("save_choice", 0) == 0:
            arena_result_data["step"] = "name_input"
            arena_result_data["name_input"] = ""
        else:
            _finish_arena_result()
        return
    if step == "name_input":
        entered = str(arena_result_data.get("name_input", "")).strip()
        if not entered:
            return
        _append_leaderboard_record(entered, arena_result_data)
        _finish_arena_result()


def _cancel_arena_result():
    global arena_result_data
    if not arena_result_data:
        return
    step = arena_result_data.get("step")
    if step == "name_input":
        arena_result_data["step"] = "save_prompt"
    elif step == "save_prompt":
        arena_result_data["step"] = "banner"


def _finish_intro_stage_to_stage_select():
    _complete_intro_stage_to_stage_select()


def _intro_vile_use_held_zero_overlay(ctx):
    if not ctx:
        return False
    return getattr(ctx, "intro_vile_state", "") in {"rescue_grab_hold", "rescue_charge", "rescue_shot"}


def _intro_vile_hide_status_bars(ctx):
    if not ctx:
        return False
    state = getattr(ctx, "intro_vile_state", "")
    hidden_states = {
        "rescue_grab_hold",
        "rescue_charge",
        "rescue_shot",
        "rescue_drop_zero",
        "rescue_x_dash",
        "rescue_standoff",
        "rescue_vile_escape",
        "rescue_dialogue",
        "rescue_x_exit",
        "rescue_zero_thumbs",
        "rescue_zero_exit",
        "rescue_fade_out",
        "rescue_end",
    }
    return bool(getattr(ctx, "intro_vile_sequence_active", False) and state in hidden_states)


def _intro_vile_hide_player_sprite(ctx):
    if not ctx:
        return False
    state = getattr(ctx, "intro_vile_state", "")
    return _intro_vile_use_held_zero_overlay(ctx) or state in {
        "rescue_zero_thumbs",
        "rescue_zero_exit",
        "rescue_fade_out",
        "rescue_end",
    }


# begin the vile boss sequence and swap the stage into its scripted control mode
def _start_intro_vile_sequence(ctx, player):
    global arena_key_movement, arena_movement, arena_joy_dir
    global current_music, music_intro_playing, music_loop_path
    if not ctx or not player or getattr(ctx, "intro_vile_triggered", False):
        return
    if not arena_tilemap or not hasattr(arena_tilemap, "second_shaft_top_floor"):
        return
    balcony_floor = getattr(arena_tilemap, "second_shaft_top_floor", None)
    if balcony_floor is None:
        return
    ctx.intro_vile_triggered = True
    ctx.intro_vile_sequence_active = True
    ctx.intro_vile_state = "walk_in"
    ctx.intro_vile_timer = 0.0
    ctx.intro_vile_warning_plays = 0
    ctx.intro_vile_warning_timer = 0.0
    ctx.intro_vile_ground_y = balcony_floor.top
    walk_target_x = balcony_floor.left + INTRO_VILE_PLAYER_WALK_TARGET_OFFSET
    walk_target_x = max(balcony_floor.left + 120, min(walk_target_x, balcony_floor.right - 140))
    ctx.intro_vile_walk_target_x = walk_target_x
    ctx.intro_vile_player_facing_dir = 1
    ctx.intro_vile_boss = None
    ctx.intro_vile_x_actor = None
    ctx.intro_vile_arm_effect = None
    ctx.intro_vile_shot = None
    ctx.damage_health_floor = 0
    ctx.intro_locked_camera_scroll = tuple(getattr(ctx, "render_scroll", (0, 0)))
    ctx.intro_locked_left_wall_x = None
    ctx.intro_locked_right_wall_x = None
    arena_key_movement = [False, False]
    arena_movement = [False, False]
    arena_joy_dir = 0
    try:
        pygame.mixer.music.fadeout(1100)
    except Exception:
        pass
    current_music = None
    music_intro_playing = False
    music_loop_path = None
    player.set_jump_hold(False)
    player.set_dash_hold(False)
    player.attack_active = False
    player.attack_action = ''
    player.attack_kind = None
    player.attack_timer = 0
    player.attack_end_timer = 0
    player.dash_timer = 0
    player.dash_time = 0
    player.dash_ending = False
    player.dash_in_air = False
    player.hspeed = 0.0
    player.air_hspeed = 0.0
    player.velocity[0] = 0.0


def _begin_intro_vile_rescue(ctx, player):
    if not ctx or getattr(ctx, "intro_vile_state", "") == "rescue_hold":
        return
    ctx.intro_vile_state = "rescue_punch_center"
    ctx.intro_vile_timer = 0.45
    ctx.damage_health_floor = 1
    boss = getattr(ctx, "intro_vile_boss", None)
    if boss is not None and not getattr(boss, "expired", False):
        boss.state = "scripted"
        boss.velocity[0] = 0.0
        boss.velocity[1] = 0.0
        boss.set_action("vile_punching", force=True)
        desired_dir = -1 if player.rect().centerx < boss.rect().centerx else 1
        boss._set_facing_dir(desired_dir)
        _set_animation_to_frame_index(boss.animation, 2)
    try:
        pygame.mixer.music.fadeout(900)
    except Exception:
        pass
    try:
        getattr(ctx, "sfx_x_buster_charging", None).stop()
    except Exception:
        pass
    try:
        getattr(ctx, "sfx_x_buster_charge_end", None).stop()
    except Exception:
        pass
    charge_channel = getattr(ctx, "intro_vile_charge_channel", None)
    if charge_channel is not None:
        try:
            charge_channel.stop()
        except Exception:
            pass
    player.attack_active = False
    player.attack_action = ''
    player.attack_kind = None
    player.attack_timer = 0
    player.attack_end_timer = 0
    player.dash_timer = 0
    player.dash_time = 0
    player.dash_ending = False
    player.dash_in_air = False
    player.hspeed = 0.0
    player.air_hspeed = 0.0
    target_scroll = getattr(ctx, "intro_locked_camera_scroll", None) or getattr(ctx, "render_scroll", (0, 0))
    player.velocity[0] = 5.0 if player.rect().centerx < (target_scroll[0] + (ARENA_W / 2.0)) else -5.0
    player.velocity[1] = 0.0
    player.health = 1
    player.set_action("zero_hurt", force=True)
    ctx.intro_vile_arm_effect = None
    ctx.intro_vile_explosion = None
    ctx.intro_vile_shot = None
    ctx.intro_vile_disarmed_anim_timer = 0.0
    ctx.intro_vile_charge_loop_started = False
    ctx.intro_vile_charge_loop_delay = 0.0
    ctx.intro_vile_thumbs_sound_played = False
    ctx.intro_vile_x_actor = {
        "state": "offscreen",
        "x": float(getattr(ctx, "render_scroll", (0, 0))[0] - 64),
        "y": float(getattr(ctx, "intro_vile_ground_y", player.rect().bottom)),
        "impact_done": False,
        "flip": False,
        "anim_timer": 0.0,
        "anim_index": 0,
    }


def _update_intro_vile_sequence(ctx, player, dt_seconds):
    if not ctx or not player or not arena_tilemap:
        return
    boss = getattr(ctx, "intro_vile_boss", None)
    state = getattr(ctx, "intro_vile_state", "idle")
    arm = getattr(ctx, "intro_vile_arm_effect", None)
    if arm is not None:
        arm["x"] += arm.get("vel_x", 0.0)
        arm["y"] += arm.get("vel_y", 0.0)
        arm["vel_y"] = arm.get("vel_y", 0.0) + 0.22
        arm["timer"] = max(0.0, arm.get("timer", 0.0) - dt_seconds)
        if arm["timer"] <= 0.0:
            ctx.intro_vile_arm_effect = None
    explosion = getattr(ctx, "intro_vile_explosion", None)
    if explosion is not None:
        explosion["timer"] += dt_seconds
        if explosion["timer"] >= explosion.get("frame_time", 0.06):
            explosion["timer"] -= explosion.get("frame_time", 0.06)
            explosion["index"] += 1
            frames = explosion.get("frames") or []
            if explosion["index"] >= len(frames):
                ctx.intro_vile_explosion = None
    player.set_jump_hold(False)
    player.set_dash_hold(False)

    if state == "walk_in":
        target_x = getattr(ctx, "intro_vile_walk_target_x", player.rect().centerx)
        dx = target_x - player.rect().centerx
        current_scroll = getattr(ctx, "intro_locked_camera_scroll", None) or getattr(ctx, "render_scroll", (0, 0))
        if arena_bounds:
            ox, oy, w, h = arena_bounds
            target_scroll_x = player.camera_center()[0] - (ARENA_W / 2) + 44
            min_x = ox
            max_x = ox + w - ARENA_W
            if max_x < min_x:
                target_scroll_x = ox + (w / 2) - (ARENA_W / 2)
            else:
                target_scroll_x = max(min_x, min(target_scroll_x, max_x))
            scroll_x = current_scroll[0] + ((target_scroll_x - current_scroll[0]) * 0.18)
            if abs(scroll_x - target_scroll_x) < 0.5:
                scroll_x = target_scroll_x
            ctx.intro_locked_camera_scroll = (scroll_x, current_scroll[1])
        if abs(dx) <= 6:
            player.update(arena_tilemap, (0, 0))
            _lock_intro_balcony_camera(ctx, getattr(ctx, "intro_locked_camera_scroll", getattr(ctx, "render_scroll", (0, 0))))
            ctx.intro_vile_state = "warning"
            ctx.intro_vile_warning_plays = 0
            ctx.intro_vile_warning_timer = 0.01
        else:
            move = 0.92 if dx > 0 else -0.92
            player.update(arena_tilemap, (move, 0))
            player.flip = move < 0
        return

    if state == "warning":
        player.update(arena_tilemap, (0, 0))
        ctx.intro_vile_warning_timer -= dt_seconds
        if ctx.intro_vile_warning_timer <= 0.0:
            _play_sound_safe(getattr(ctx, "sfx_warning", None))
            ctx.intro_vile_warning_plays += 1
            if ctx.intro_vile_warning_plays >= INTRO_VILE_WARNING_COUNT:
                ctx.intro_vile_state = "warning_gap"
                ctx.intro_vile_timer = 2.0
            else:
                ctx.intro_vile_warning_timer = INTRO_VILE_WARNING_INTERVAL
        return

    if state == "warning_gap":
        player.update(arena_tilemap, (0, 0))
        ctx.intro_vile_timer = max(0.0, getattr(ctx, "intro_vile_timer", 0.0) - dt_seconds)
        if ctx.intro_vile_timer <= 0.0:
            landing_x = player.rect().centerx + 86
            ground_y = getattr(ctx, "intro_vile_ground_y", player.rect().bottom)
            boss = ArenaVileBoss(ctx, (landing_x, ground_y))
            boss.begin_drop(landing_x, ground_y, facing_dir=-1)
            ctx.intro_vile_boss = boss
            ctx.intro_vile_state = "drop"
        return

    if state == "drop":
        player.update(arena_tilemap, (0, 0))
        if boss is not None:
            boss.update(None, arena_bounds, tilemap=arena_tilemap)
            if boss.state == "idle":
                boss.begin_laughing(loops=3)
                ctx.intro_vile_state = "laugh"
        return

    if state == "laugh":
        player.update(arena_tilemap, (0, 0))
        if boss is not None:
            boss.update(None, arena_bounds, tilemap=arena_tilemap)
            if boss.state == "idle":
                boss.begin_fight()
                ctx.damage_health_floor = 1
                ctx.intro_vile_state = "fight"
                if not getattr(ctx, "intro_vile_battle_music_started", False):
                    play_music(boss_battle_music_intro, boss_battle_music_loop)
                    ctx.intro_vile_battle_music_started = True
        return

    if state == "fight":
        player.update(arena_tilemap, (0, 0))
        if boss is not None:
            boss.update(player, arena_bounds, tilemap=arena_tilemap)
        if player.health <= 1:
            _begin_intro_vile_rescue(ctx, player)
        return

    ground_y = getattr(ctx, "intro_vile_ground_y", player.rect().bottom)
    actor = getattr(ctx, "intro_vile_x_actor", None)

    if state == "rescue_punch_center":
        target_scroll = getattr(ctx, "intro_locked_camera_scroll", None) or getattr(ctx, "render_scroll", (0, 0))
        target_x = target_scroll[0] + (ARENA_W / 2.0)
        if boss is not None and not getattr(boss, "expired", False):
            desired_dir = -1 if player.rect().centerx < boss.rect().centerx else 1
            boss._set_facing_dir(desired_dir)
            boss.set_action("vile_punching")
            _set_animation_to_frame_index(boss.animation, 2)
        player.set_action("zero_hurt")
        dx = target_x - player.rect().centerx
        move = max(-5.0, min(5.0, dx))
        player.update(arena_tilemap, (0, 0))
        player.pos[0] += move
        if abs(dx) <= 5 or getattr(ctx, "intro_vile_timer", 0.0) <= 0.0:
            _place_player_midbottom(player, target_x, ground_y)
            player.velocity[0] = 0.0
            ctx.intro_vile_state = "rescue_move_left"
        else:
            ctx.intro_vile_timer = max(0.0, getattr(ctx, "intro_vile_timer", 0.0) - dt_seconds)
        return

    if state == "rescue_move_left":
        player.update(arena_tilemap, (0, 0))
        if boss is not None and not getattr(boss, "expired", False):
            target_x = player.rect().centerx + 34
            dx = target_x - boss.rect().centerx
            if abs(dx) > 5:
                boss.set_action("vile_walking")
                move = -boss.walk_speed if dx < 0 else boss.walk_speed
                boss._set_facing_dir(-1 if move < 0 else 1)
                boss.update(None, arena_bounds, tilemap=arena_tilemap, projectiles=None)
                boss.pos[0] += move
                boss._update_walking_audio()
            else:
                boss.set_action("vile_idle", force=True)
                boss._set_facing_dir(-1)
                ctx.intro_vile_state = "rescue_laugh"
                boss.begin_laughing(loops=3)
        return

    if state == "rescue_laugh":
        player.update(arena_tilemap, (0, 0))
        if boss is not None and not getattr(boss, "expired", False):
            boss.update(None, arena_bounds, tilemap=arena_tilemap)
            if boss.state == "idle":
                ctx.intro_vile_state = "rescue_grab_windup"
                boss.state = "scripted"
                boss.set_action("vile_punching", force=True)
        return

    if state == "rescue_grab_windup":
        player.update(arena_tilemap, (0, 0))
        if boss is not None and not getattr(boss, "expired", False):
            boss._set_facing_dir(-1)
            boss.animation.update()
            if boss.animation.frame_index() >= min(2, max(0, len(boss.animation.images) - 1)):
                _set_animation_to_frame_index(boss.animation, 2)
                ctx.intro_vile_state = "rescue_grab_hold"
                ctx.intro_vile_timer = 2.05
                grab_x = boss.rect().centerx + INTRO_VILE_GRAB_OFFSET_X
                grab_y = boss.rect().bottom + INTRO_VILE_GRAB_OFFSET_Y
                _place_player_midbottom(player, grab_x, grab_y)
        return

    if state == "rescue_grab_hold":
        if boss is not None and not getattr(boss, "expired", False):
            boss._set_facing_dir(-1)
            boss.set_action("vile_punching")
            _set_animation_to_frame_index(boss.animation, 2)
            grab_x = boss.rect().centerx + INTRO_VILE_GRAB_OFFSET_X
            grab_y = boss.rect().bottom + INTRO_VILE_GRAB_OFFSET_Y
            _place_player_midbottom(player, grab_x, grab_y)
            player.set_action("zero_hurt")
        ctx.intro_vile_timer = max(0.0, getattr(ctx, "intro_vile_timer", 0.0) - dt_seconds)
        if ctx.intro_vile_timer <= 0.0:
            ctx.intro_vile_state = "rescue_charge"
            ctx.intro_vile_timer = 2.35
            ctx.intro_vile_charge_loop_started = False
            startup_sound = getattr(ctx, "sfx_x_buster_charging", None)
            ctx.intro_vile_charge_loop_delay = 0.0
            charge_channel = getattr(ctx, "intro_vile_charge_channel", None)
            if startup_sound is not None:
                try:
                    ctx.intro_vile_charge_loop_delay = max(0.0, float(startup_sound.get_length()) - 0.02)
                except Exception:
                    ctx.intro_vile_charge_loop_delay = 0.18
            charge_sound = getattr(ctx, "sfx_x_buster_charging", None)
            if charge_channel is not None and charge_sound is not None:
                try:
                    charge_channel.stop()
                    charge_channel.play(charge_sound)
                except Exception:
                    pass
            elif charge_sound:
                try:
                    charge_sound.stop()
                    charge_sound.play()
                except Exception:
                    pass
        return

    if state == "rescue_charge":
        if boss is not None and not getattr(boss, "expired", False):
            boss._set_facing_dir(-1)
            boss.set_action("vile_punching")
            _set_animation_to_frame_index(boss.animation, 2)
            grab_x = boss.rect().centerx + INTRO_VILE_GRAB_OFFSET_X
            grab_y = boss.rect().bottom + INTRO_VILE_GRAB_OFFSET_Y
            _place_player_midbottom(player, grab_x, grab_y)
            player.set_action("zero_hurt")
        ctx.intro_vile_charge_loop_delay = max(0.0, getattr(ctx, "intro_vile_charge_loop_delay", 0.0) - dt_seconds)
        if (
            not getattr(ctx, "intro_vile_charge_loop_started", False)
            and getattr(ctx, "intro_vile_charge_loop_delay", 0.0) <= 0.0
        ):
            loop_sound = getattr(ctx, "sfx_x_buster_charge_end", None)
            charge_channel = getattr(ctx, "intro_vile_charge_channel", None)
            if loop_sound:
                try:
                    if charge_channel is not None:
                        charge_channel.stop()
                        charge_channel.play(loop_sound, loops=-1)
                    else:
                        loop_sound.stop()
                        loop_sound.play(-1)
                    ctx.intro_vile_charge_loop_started = True
                except Exception:
                    pass
        ctx.intro_vile_timer = max(0.0, getattr(ctx, "intro_vile_timer", 0.0) - dt_seconds)
        if ctx.intro_vile_timer <= 0.0:
            charge_sound = getattr(ctx, "sfx_x_buster_charging", None)
            if charge_sound:
                try:
                    charge_sound.stop()
                except Exception:
                    pass
            loop_sound = getattr(ctx, "sfx_x_buster_charge_end", None)
            if loop_sound:
                try:
                    loop_sound.stop()
                except Exception:
                    pass
            charge_channel = getattr(ctx, "intro_vile_charge_channel", None)
            if charge_channel is not None:
                try:
                    charge_channel.stop()
                except Exception:
                    pass
            _play_sound_safe(getattr(ctx, "sfx_x_buster_charged_shot", None))
            ctx.intro_vile_state = "rescue_shot"
            shot_y = boss.rect().centery - 12 if boss is not None else player.rect().centery
            scroll_x = getattr(ctx, "render_scroll", (0, 0))[0]
            ctx.intro_vile_shot = {
                "x": float(scroll_x - 24),
                "y": float(shot_y),
                "speed": 6.25,
                "anim_timer": 0.0,
                "anim_index": 0,
            }
        return

    if state == "rescue_shot":
        shot = getattr(ctx, "intro_vile_shot", None)
        if boss is not None and not getattr(boss, "expired", False):
            boss._set_facing_dir(-1)
            boss.set_action("vile_punching")
            _set_animation_to_frame_index(boss.animation, 2)
            grab_x = boss.rect().centerx + INTRO_VILE_GRAB_OFFSET_X
            grab_y = boss.rect().bottom + INTRO_VILE_GRAB_OFFSET_Y
            _place_player_midbottom(player, grab_x, grab_y)
            player.set_action("zero_hurt")
        if shot is not None:
            shot["anim_timer"] = shot.get("anim_timer", 0.0) + dt_seconds
            while shot["anim_timer"] >= 0.075:
                shot["anim_timer"] -= 0.075
                shot["anim_index"] = 1 - int(shot.get("anim_index", 0))
            shot["x"] += shot["speed"]
            target_x = (boss.rect().centerx - 18) if boss is not None else player.rect().centerx
            if shot["x"] >= target_x:
                ctx.intro_vile_shot = None
                if boss is not None and not getattr(boss, "expired", False):
                    boss.state = "scripted"
                    boss.set_action("vile_disarmed", force=True)
                    boss._set_facing_dir(-1)
                    boss.velocity[0] = 4.6
                    boss.velocity[1] = -2.7
                    ctx.intro_vile_disarmed_anim_timer = 0.0
                if boss is not None:
                    _play_sound_safe(getattr(ctx, "sfx_enemy_destroyed", None))
                    explosion_frames = getattr(ctx, "effect_images", {}).get("enemy_destroyed") or []
                    if explosion_frames:
                        ctx.intro_vile_explosion = {
                            "x": float(boss.rect().centerx - 10),
                            "y": float(boss.rect().centery - 20),
                            "frames": explosion_frames,
                            "index": 0,
                            "timer": 0.0,
                            "frame_time": 0.055,
                        }
                    ctx.intro_vile_arm_effect = {
                        "x": float(boss.rect().centerx - 22),
                        "y": float(boss.rect().centery - 12),
                        "vel_x": 2.1,
                        "vel_y": -3.5,
                        "timer": 1.0,
                        "flip": bool(getattr(boss, "flip", False)),
                    }
                ctx.intro_vile_state = "rescue_drop_zero"
                ctx.intro_vile_timer = 1.55
        return

    if state == "rescue_drop_zero":
        if boss is not None and not getattr(boss, "expired", False):
            boss._set_facing_dir(-1)
            boss.place_midbottom(boss.rect().centerx + boss.velocity[0], ground_y)
            boss.velocity[0] *= 0.94
            boss.velocity[1] = 0.0
            _set_vile_disarmed_pose(ctx, boss, "intro")
        player.set_action("zero_hurt")
        player.flip = False
        player.velocity[1] = min(6.5, player.velocity[1] + 0.42)
        player.pos[1] += player.velocity[1]
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
            player.velocity[1] = 0.0
            player.set_action("zero_idle", force=True)
            player.flip = False
        if actor:
            actor["state"] = "dash"
            actor["x"] = float(getattr(ctx, "render_scroll", (0, 0))[0] - 56)
            actor["y"] = float(ground_y)
            actor["flip"] = False
            actor["anim_timer"] = 0.0
            actor["anim_index"] = 0
        ctx.intro_vile_timer = max(0.0, getattr(ctx, "intro_vile_timer", 0.0) - dt_seconds)
        if ctx.intro_vile_timer <= 0.0:
            ctx.intro_vile_state = "rescue_x_dash"
            _play_sound_safe(getattr(ctx, "sfx_dash", None))
        return

    if state == "rescue_x_dash":
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
            player.set_action("zero_idle")
            player.flip = False
        else:
            player.set_action("zero_hurt")
            player.flip = False
        if actor:
            actor["state"] = "dash"
            actor["anim_index"] = 2
            actor["x"] += 4.8
            actor["y"] = float(ground_y)
            x_target = player.rect().centerx + 38
            if actor["x"] >= x_target:
                actor["x"] = float(x_target)
                actor["state"] = "idle"
                actor["flip"] = False
                ctx.intro_vile_state = "rescue_standoff"
                ctx.intro_vile_timer = 0.8
        return

    if state == "rescue_standoff":
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
            player.set_action("zero_idle")
            player.flip = False
        else:
            player.set_action("zero_hurt")
            player.flip = False
        if boss is not None and not getattr(boss, "expired", False):
            boss._set_facing_dir(-1)
            boss.place_midbottom(boss.rect().centerx, ground_y)
            _set_vile_disarmed_pose(ctx, boss, "hold")
        ctx.intro_vile_timer = max(0.0, getattr(ctx, "intro_vile_timer", 0.0) - dt_seconds)
        if ctx.intro_vile_timer <= 0.0:
            ctx.intro_vile_state = "rescue_vile_escape"
            ctx.intro_vile_timer = 1.35
            ctx.intro_vile_disarmed_anim_timer = 0.0
            _play_sound_safe(getattr(ctx, "sfx_vile_jump", None))
        return

    if state == "rescue_vile_escape":
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
            player.set_action("zero_idle")
            player.flip = False
        else:
            player.set_action("zero_hurt")
            player.flip = False
        if boss is not None and not getattr(boss, "expired", False):
            boss._set_facing_dir(-1)
            _set_vile_disarmed_pose(ctx, boss, "escape")
            boss.pos[0] += 2.2
            boss.pos[1] -= 3.0
            boss.velocity[1] = min(6.0, boss.velocity[1] + 0.16)
            boss.pos[1] += boss.velocity[1]
            if boss.rect().bottom < getattr(ctx, "render_scroll", (0, 0))[1] - 40 or boss.rect().left > getattr(ctx, "render_scroll", (0, 0))[0] + ARENA_W + 60:
                boss.expired = True
        ctx.intro_vile_timer = max(0.0, getattr(ctx, "intro_vile_timer", 0.0) - dt_seconds)
        if ctx.intro_vile_timer <= 0.0:
            if actor:
                actor["state"] = "idle"
                actor["flip"] = True
            ctx.intro_vile_state = "rescue_dialogue"
            _start_arena_cutscene(ctx, INTRO_VILE_RESCUE_DIALOGUE)
        return

    if state == "rescue_dialogue":
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
            player.set_action("zero_idle")
            player.flip = False
        else:
            player.set_action("zero_hurt")
            player.flip = False
        _update_arena_cutscene(ctx, dt_seconds)
        if not getattr(ctx, "cutscene_active", False):
            ctx.intro_vile_state = "rescue_x_exit"
            ctx.intro_vile_timer = 0.0
            if actor:
                actor["state"] = "exit"
                actor["exit_timer"] = 0.0
            _play_sound_safe(sfx_exiting)
        return

    if state == "rescue_x_exit":
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
            player.set_action("zero_idle")
            player.flip = False
        if actor:
            actor["state"] = "exit"
            actor["exit_timer"] = actor.get("exit_timer", 0.0) + dt_seconds
            if actor["exit_timer"] >= INTRO_STAGE_OPENING_X_EXIT_DURATION:
                actor["state"] = "offscreen"
                ctx.intro_vile_state = "rescue_zero_thumbs"
                ctx.intro_vile_timer = 0.0
                ctx.intro_vile_zero_exit_active = False
                ctx.intro_vile_zero_exit_timer = 0.0
                ctx.intro_vile_thumbs_sound_played = False
        return

    if state == "rescue_zero_thumbs":
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
        player.set_action("zero_idle")
        player.flip = False
        ctx.intro_vile_timer = getattr(ctx, "intro_vile_timer", 0.0) + dt_seconds
        zero_exit_frames = (getattr(ctx, "intro_opening_assets", None) or _load_intro_stage_opening_assets()).get("zero_exit_frames") or []
        hold_idx = min(MENU_CONFIRM_HOLD_FRAME, max(0, len(zero_exit_frames) - 1))
        thumbs_anim_time = 0.10 * (hold_idx + 1)
        if (
            not getattr(ctx, "intro_vile_thumbs_sound_played", False)
            and ctx.intro_vile_timer >= thumbs_anim_time
        ):
            try:
                thumbs_up_sound.play()
            except Exception:
                pass
            ctx.intro_vile_thumbs_sound_played = True
        if ctx.intro_vile_timer >= thumbs_anim_time + 1.5:
            ctx.intro_vile_state = "rescue_zero_exit"
            ctx.intro_vile_zero_exit_active = True
            ctx.intro_vile_zero_exit_timer = 0.0
            _play_sound_safe(sfx_exiting)
        return

    if state == "rescue_zero_exit":
        if player.rect().bottom >= ground_y:
            _place_player_midbottom(player, player.rect().centerx, ground_y)
        player.set_action("zero_idle")
        player.flip = False
        ctx.intro_vile_zero_exit_timer = getattr(ctx, "intro_vile_zero_exit_timer", 0.0) + dt_seconds
        if ctx.intro_vile_zero_exit_timer >= INTRO_STAGE_OPENING_X_EXIT_DURATION:
            ctx.intro_vile_zero_exit_active = False
            ctx.intro_vile_state = "rescue_fade_out"
            ctx.intro_vile_timer = 0.0
            ctx.intro_vile_fade_alpha = 0.0
        return

    if state == "rescue_fade_out":
        ctx.intro_vile_timer = getattr(ctx, "intro_vile_timer", 0.0) + dt_seconds
        fade_p = _clamp01(ctx.intro_vile_timer / MENU_CONFIRM_FADE_DURATION)
        ctx.intro_vile_fade_alpha = 255.0 * fade_p
        if fade_p >= 1.0:
            ctx.intro_vile_state = "rescue_end"
            ctx.intro_vile_timer = 0.0
        return

    if state == "rescue_end":
        ctx.intro_vile_timer = getattr(ctx, "intro_vile_timer", 0.0) + dt_seconds
        if ctx.intro_vile_timer >= 2.0:
            _finish_intro_stage_to_stage_select()
        return


def _draw_intro_vile_x_actor(surface, ctx, offset):
    if not ctx:
        return
    actor = getattr(ctx, "intro_vile_x_actor", None)
    if not actor:
        return
    assets = getattr(ctx, "intro_opening_assets", None) or _load_intro_stage_opening_assets()
    state = actor.get("state", "idle")
    if state == "offscreen":
        frame = None
    elif state == "fall":
        frames = assets.get("x_falling_frames") or assets.get("x_idle_frames") or []
        frame = frames[min(len(frames) - 1, 1)] if frames else None
    elif state == "shot":
        frames = assets.get("x_fully_charged_shot_frames") or assets.get("x_idle_frames") or []
        frame = frames[min(len(frames) - 1, 0)] if frames else None
    elif state == "dash":
        frames = assets.get("x_dash_frames") or assets.get("x_nova_frames") or []
        if frames:
            frame_index = int(actor.get("anim_index", 0)) % len(frames)
            frame = frames[frame_index]
        else:
            frame = None
    elif state == "exit":
        frame = None
    elif state == "idle":
        frames = assets.get("x_idle_frames") or []
        frame = frames[0] if frames else None
    else:
        frame = None
    if state == "exit":
        _draw_intro_opening_exit(
            surface,
            actor["x"],
            actor["y"],
            offset,
            assets.get("x_exit_tail_frames") or [],
            float(actor.get("exit_timer", 0.0)),
            flip=True,
        )
        return
    if frame is None:
        return
    _draw_cutscene_actor(
        surface,
        frame,
        actor["x"],
        actor["y"],
        offset,
        anchor="midbottom",
        flip=bool(actor.get("flip", False)),
        scale=1.0,
    )


def _draw_intro_vile_shot(surface, ctx, offset):
    if not ctx:
        return
    shot = getattr(ctx, "intro_vile_shot", None)
    if not shot:
        return
    assets = getattr(ctx, "intro_opening_assets", None) or _load_intro_stage_opening_assets()
    frames = assets.get("x_fully_charged_shot_frames") or []
    if not frames:
        return
    if len(frames) >= 2:
        tail = frames[-2:]
        img = tail[int(shot.get("anim_index", 0)) % 2]
    else:
        img = frames[-1]
    _draw_cutscene_actor(
        surface,
        img,
        shot["x"],
        shot["y"],
        offset,
        anchor="center",
        flip=False,
        scale=0.85,
    )


def _draw_intro_vile_arm_effect(surface, ctx, offset):
    if not ctx:
        return
    arm = getattr(ctx, "intro_vile_arm_effect", None)
    if not arm:
        return
    anim = getattr(ctx, "assets", {}).get("destroyed_arm")
    if anim is None or not getattr(anim, "images", None):
        return
    img = anim.images[0]
    _draw_cutscene_actor(
        surface,
        img,
        arm["x"],
        arm["y"],
        offset,
        anchor="center",
        flip=bool(arm.get("flip", False)),
        scale=1.0,
    )


def _draw_intro_vile_explosion(surface, ctx, offset):
    if not ctx:
        return
    explosion = getattr(ctx, "intro_vile_explosion", None)
    if not explosion:
        return
    frames = explosion.get("frames") or []
    if not frames:
        return
    index = max(0, min(int(explosion.get("index", 0)), len(frames) - 1))
    _draw_cutscene_actor(
        surface,
        frames[index],
        explosion["x"],
        explosion["y"],
        offset,
        anchor="center",
        flip=False,
        scale=1.0,
    )


def _draw_intro_vile_zero_end(surface, ctx, offset):
    if not ctx:
        return
    state = getattr(ctx, "intro_vile_state", "")
    if state not in {"rescue_zero_thumbs", "rescue_zero_exit"}:
        return
    player = globals().get("arena_player")
    if player is None:
        return
    assets = getattr(ctx, "intro_opening_assets", None) or _load_intro_stage_opening_assets()
    zero_exit_frames = assets.get("zero_exit_frames") or []
    if state == "rescue_zero_thumbs":
        if not zero_exit_frames:
            return
        hold_idx = min(MENU_CONFIRM_HOLD_FRAME, len(zero_exit_frames) - 1)
        frame_duration = 0.10
        local_t = float(getattr(ctx, "intro_vile_timer", 0.0))
        if local_t < frame_duration * (hold_idx + 1):
            frame_index = min(hold_idx, int(local_t / frame_duration))
        else:
            frame_index = hold_idx
        img = zero_exit_frames[frame_index]
        _draw_cutscene_actor(
            surface,
            img,
            player.rect().centerx,
            player.rect().bottom,
            offset,
            anchor="midbottom",
            flip=False,
            scale=1.0,
        )
        return
    if state == "rescue_zero_exit":
        hold_idx = min(MENU_CONFIRM_HOLD_FRAME, max(0, len(zero_exit_frames) - 1))
        remaining_frames = zero_exit_frames[hold_idx + 1:] if len(zero_exit_frames) > hold_idx + 1 else zero_exit_frames[-1:]
        _draw_intro_opening_exit(
            surface,
            player.rect().centerx,
            player.rect().bottom,
            offset,
            remaining_frames,
            float(getattr(ctx, "intro_vile_zero_exit_timer", 0.0)),
            flip=False,
        )


def _draw_intro_vile_held_zero(surface, ctx, offset):
    if not ctx or not _intro_vile_use_held_zero_overlay(ctx):
        return
    boss = getattr(ctx, "intro_vile_boss", None)
    if boss is None or getattr(boss, "expired", False):
        return
    held_img = None
    assets = getattr(ctx, "assets", {})
    exact_anim = assets.get("held_zero_behind_arm")
    if exact_anim is not None and getattr(exact_anim, "images", None):
        held_img = exact_anim.images[0]
    if held_img is None:
        exact_anim = assets.get("zero_held_behind_arm")
        if exact_anim is not None and getattr(exact_anim, "images", None):
            held_img = exact_anim.images[0]
    if held_img is None:
        exact_anim = assets.get("held_zero_behind_fist")
    if exact_anim is not None and getattr(exact_anim, "images", None):
        held_img = exact_anim.images[0]
    for key in assets.keys():
        if held_img is not None:
            break
        lowered = str(key).lower()
        if "held" in lowered and "zero" in lowered and ("arm" in lowered or "fist" in lowered):
            anim = assets.get(key)
            if anim is not None and getattr(anim, "images", None):
                held_img = anim.images[0]
                break
    use_same_canvas_as_boss = held_img is not None
    if held_img is None:
        intro_assets = getattr(ctx, "intro_opening_assets", None) or _load_intro_stage_opening_assets()
        frames = intro_assets.get("zero_hurt_frames") or []
        if not frames:
            return
        held_img = frames[min(len(frames) - 1, 0)]
    if use_same_canvas_as_boss:
        boss_img = boss.animation.img()
        ox, oy = boss._draw_offset(boss_img)
        draw_x = int(round(boss.pos[0] - offset[0] + ox))
        draw_y = int(round(boss.pos[1] - offset[1] + oy + int(getattr(boss, "render_y_nudge", 0))))
        surface.blit(pygame.transform.flip(held_img, boss.flip, False), (draw_x, draw_y))
        return
    draw_x = boss.rect().centerx + INTRO_VILE_GRAB_OFFSET_X
    draw_y = boss.rect().bottom + INTRO_VILE_GRAB_OFFSET_Y
    _draw_cutscene_actor(
        surface,
        held_img,
        draw_x,
        draw_y,
        offset,
        anchor="midbottom",
        flip=False,
        scale=1.0,
    )


# draw the portrait box and text reveal for intro dialogue beats
def _draw_intro_opening_dialogue(surface, ctx):
    if not ctx or not getattr(ctx, "cutscene_active", False):
        return
    lines = getattr(ctx, "cutscene_lines", [])
    if not lines:
        return
    current = lines[min(ctx.cutscene_index, len(lines) - 1)]
    speaker = current.get("speaker", "")
    text = current.get("text", "")
    visible_text = text[:max(0, min(len(text), getattr(ctx, "cutscene_visible_chars", 0)))]
    anonymous = not str(speaker).strip()
    speaker_is_zero = speaker.strip().lower() == "zero"
    speaker_highlight = speaker_is_zero
    speaking_now = getattr(ctx, "cutscene_visible_chars", 0) < len(text)
    panel_progress = _clamp01(getattr(ctx, "cutscene_panel_timer", 0.0) / INTRO_CUTSCENE_PANEL_POP_DURATION)
    panel_scale = 0.26 + (0.74 * _ease_in_out(panel_progress))
    max_box_w = min(int(surface.get_width() * 1.58), 520)
    max_box_h = min(int(surface.get_height() * 0.94), 252)
    box_w = max(1, int(round(max_box_w * panel_scale)))
    box_h = max(1, int(round(max_box_h * panel_scale)))
    box = pygame.Rect(0, 0, box_w, box_h)
    box.center = (
        surface.get_width() // 2,
        max((box_h // 2) + 10, int(round(surface.get_height() * 0.24))),
    )

    shadow = pygame.Surface((box_w, box_h))
    shadow.fill((0, 0, 0))
    surface.blit(shadow, box.topleft)
    pygame.draw.rect(surface, (214, 214, 214), box, 2)

    dialog_timer = getattr(ctx, "cutscene_panel_timer", 0.0) + getattr(ctx, "cutscene_type_timer", 0.0)
    zero_face = _dialogue_face_image(intro_zero_face_bank, dialog_timer, speaking=speaking_now and speaker_is_zero)
    x_face = _dialogue_face_image(intro_x_face_bank, dialog_timer, speaking=speaking_now and not speaker_is_zero)
    face_scale = 2

    if not anonymous and zero_face is not None:
        zero_scaled = pygame.transform.flip(
            pygame.transform.scale(
                zero_face,
                (max(1, zero_face.get_width() * face_scale), max(1, zero_face.get_height() * face_scale)),
            ),
            True,
            False,
        )
        zero_rect = zero_scaled.get_rect(
            midright=(box.left - 6, box.centery)
        )
        surface.blit(zero_scaled, zero_rect)

    if not anonymous and x_face is not None:
        x_scaled = pygame.transform.scale(
            x_face,
            (max(1, x_face.get_width() * face_scale), max(1, x_face.get_height() * face_scale)),
        )
        x_rect = x_scaled.get_rect(
            midleft=(box.right + 6, box.centery)
        )
        surface.blit(x_scaled, x_rect)

    if panel_progress < 1.0:
        return

    text_scale = 3
    text_spacing = -12
    content_left = box.left + 18
    content_top = box.top + 16
    wrap_width = box.w - 36
    wrapped = _wrap_cutscene_text(visible_text, wrap_width, scale=text_scale, letter_spacing=text_spacing)
    line_y = content_top
    if not anonymous:
        draw_text_left_on(
            surface,
            speaker.upper(),
            content_left,
            content_top,
            highlighted=speaker_highlight,
            scale=text_scale,
            letter_spacing=text_spacing,
        )
        line_y = content_top + 32
    for line in wrapped[:5]:
        draw_text_left_on(
            surface,
            line,
            content_left,
            line_y,
            highlighted=speaker_highlight,
            scale=text_scale,
            letter_spacing=text_spacing,
        )
        line_y += 28


def _draw_arena_cutscene(surface, ctx):
    if not ctx or not getattr(ctx, "cutscene_active", False):
        return
    if current_stage == "intro_stage" and (
        getattr(ctx, "intro_opening_active", False)
        or getattr(ctx, "intro_vile_sequence_active", False)
    ):
        _draw_intro_opening_dialogue(surface, ctx)
        return
    lines = getattr(ctx, "cutscene_lines", [])
    if not lines:
        return
    current = lines[min(ctx.cutscene_index, len(lines) - 1)]
    speaker = current.get("speaker", "")
    text = current.get("text", "")
    visible_text = text[:max(0, min(len(text), getattr(ctx, "cutscene_visible_chars", 0)))]
    anonymous = not str(speaker).strip()

    box_w = int(surface.get_width() * 0.84)
    box_h = int(surface.get_height() * 0.34)
    box_x = (surface.get_width() - box_w) // 2
    box_y = int(surface.get_height() * 0.58)
    box = pygame.Rect(box_x, box_y, box_w, box_h)

    shadow = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    shadow.fill((0, 0, 0, 210))
    surface.blit(shadow, box.topleft)
    pygame.draw.rect(surface, (214, 214, 214), box, 2)

    text_layout = _fit_cutscene_text_layout(
        text,
        box.w - 40,
        6 if anonymous else 4,
        (
            (2.7, -14, 32),
            (2.5, -14, 30),
            (2.35, -13, 28),
            (2.2, -12, 27),
            (2.0, LETTER_SPACING, 28),
        ),
    )
    text_scale = text_layout["scale"]
    text_spacing = text_layout["letter_spacing"]
    text_space_width = text_layout["space_width"]
    line_height = text_layout["line_height"]
    content_left = box.left + 20
    line_y = box.top + 16
    if not anonymous:
        draw_text_left_on(
            surface,
            f"({speaker})",
            content_left,
            line_y,
            highlighted=False,
            scale=text_scale,
            letter_spacing=text_spacing,
            space_width=text_space_width,
        )
        line_y += line_height + 6

    wrapped = _wrap_cutscene_text(
        visible_text,
        box.w - 40,
        scale=text_scale,
        letter_spacing=text_spacing,
        space_width=text_space_width,
    )
    if current_stage == "intro_stage" and anonymous:
        wrapped_runs = _wrap_guidance_text(
            visible_text,
            box.w - 40,
            scale=text_scale,
            letter_spacing=text_spacing,
            space_width=text_space_width,
        )
        for runs in wrapped_runs[:6]:
            _draw_guidance_text_line(
                surface,
                runs,
                content_left,
                line_y,
                scale=text_scale,
                letter_spacing=text_spacing,
                space_width=text_space_width,
            )
            line_y += line_height
    else:
        for line in wrapped[:6 if anonymous else 4]:
            draw_text_left_on(
                surface,
                line,
                content_left,
                line_y,
                highlighted=False,
                scale=text_scale,
                letter_spacing=text_spacing,
                space_width=text_space_width,
            )
            line_y += line_height





# big reset for gameplay objects, tilemap, player, stage assets, and per-run state
def init_arena_gameplay():
    global arena_assets_cache, arena_anim_offsets_cache, arena_ctx
    global arena_player, arena_copters, arena_enemy_projectiles, arena_tilemap
    global arena_movement, arena_key_movement, arena_joy_dir
    global arena_debug_hitboxes, arena_render_scroll, arena_surface, arena_bounds
    global paused, pause_selected_index, pause_slide
    global arena_stage_start_active, arena_stage_ready_anim, reset_next_dt
    global intro_stage_respawn_via_spawn
    global intro_stage_guidance_seen_persistent, intro_stage_guided_giga_unlocked
    global intro_stage_secret_gateway_active
    global intro_stage_checkpoint_index, intro_stage_checkpoint_spawn

    if current_stage == "intro_stage":
        if not intro_stage_respawn_via_spawn:
            intro_stage_guidance_seen_persistent = set()
            intro_stage_guided_giga_unlocked = not intro_stage_guided_mode_selected
            intro_stage_secret_gateway_active = False
            intro_stage_checkpoint_index = -1
            intro_stage_checkpoint_spawn = None
        stone_folder = "intro_stage"
        if stone_folder not in arena_assets_cache:
            assets, anim_offsets = build_arena_assets(
                ASSETS_DIR,
                "assets:airbase_tiles",
                auto_align_actions=AUTO_ALIGN_ACTIONS,
                frame_stabilize=FRAME_STABILIZE,
            )
            arena_assets_cache[stone_folder] = assets
            arena_anim_offsets_cache[stone_folder] = anim_offsets
    else:
        stone_folder = get_stage_stone_folder(current_stage, ASSETS_DIR)
        if stone_folder not in arena_assets_cache:
            assets, anim_offsets = build_arena_assets(
                ASSETS_DIR,
                stone_folder,
                auto_align_actions=AUTO_ALIGN_ACTIONS,
                frame_stabilize=FRAME_STABILIZE,
            )
            arena_assets_cache[stone_folder] = assets
            arena_anim_offsets_cache[stone_folder] = anim_offsets
            print(f"Arena tiles: {stone_folder} ({len(assets['stone'])} frames)")

    arena_ctx = ArenaContext()
    arena_ctx.assets = arena_assets_cache[stone_folder]
    arena_ctx.anim_offsets_override = arena_anim_offsets_cache[stone_folder]
    arena_ctx.anim_draw_offsets_override = dict(arena_ctx.anim_offsets_override)
    if 'zero_air_saber_slash' in arena_ctx.anim_draw_offsets_override:
        ox_r, ox_l, oy = arena_ctx.anim_draw_offsets_override['zero_air_saber_slash']
        arena_ctx.anim_draw_offsets_override['zero_air_saber_slash'] = (ox_l + 24, ox_l, oy)
    arena_ctx.stage_key = current_stage
    arena_ctx.top_floor_decor_pair = current_stage in ("airbase", "magma")
    arena_ctx.ceiling_from_floor = current_stage in ("northern", "wepcenter", "amazon")
    arena_ctx.anim_frame_offsets = arena_ctx.assets.get('_anim_frame_offsets', {})
    arena_ctx.giga_beams = []
    arena_ctx.giga_background_scroll = 0.0
    arena_ctx.giga_background_beam_seen = False
    arena_ctx.giga_background_surface = None
    arena_ctx.giga_background_cache_key = None
    arena_ctx.effects = []
    arena_ctx.pickups = []
    arena_ctx.effect_images = build_effect_images()
    arena_ctx.sfx_hurt_sounds = sfx_hurt_sounds
    arena_ctx.sfx_death = sfx_death
    arena_ctx.sfx_land = sfx_land
    arena_ctx.sfx_dash = sfx_dash
    arena_ctx.sfx_ground_slash1 = sfx_ground_slash1
    arena_ctx.sfx_ground_slash2 = sfx_ground_slash2
    arena_ctx.sfx_ground_slash3 = sfx_ground_slash3
    arena_ctx.sfx_air_wall_slash = sfx_air_wall_slash
    arena_ctx.sfx_giga_attack = sfx_giga_attack
    arena_ctx.sfx_wall_jump = sfx_wall_jump
    arena_ctx.sfx_wall_land = sfx_wall_land
    arena_ctx.sfx_blocked_hit = sfx_blocked_hit
    arena_ctx.sfx_met_projectile = sfx_met_projectile
    arena_ctx.sfx_cannon_shoot = sfx_cannon_shoot
    arena_ctx.intro_shaft_offscreen_timer = 0
    arena_ctx.sfx_jump_sounds = sfx_jump_sounds
    arena_ctx.sfx_spawn = sfx_spawn
    arena_ctx.sfx_life_energy_gain = sfx_life_energy_gain
    arena_ctx.sfx_gain_channel = pygame.mixer.Channel(0)
    arena_ctx.sfx_hitmarker = sfx_hitmarker
    arena_ctx.sfx_enemy_destroyed = sfx_enemy_destroyed
    arena_ctx.sfx_rocket_fired = sfx_rocket_fired
    arena_ctx.sfx_heavy_shocker = sfx_heavy_shocker
    arena_ctx.sfx_nova_strike = sfx_nova_strike
    arena_ctx.sfx_x_buster_charging = sfx_x_buster_charging
    arena_ctx.sfx_x_buster_charge_end = sfx_x_buster_charge_end
    arena_ctx.sfx_x_buster_charged_shot = sfx_x_buster_charged_shot
    try:
        arena_ctx.intro_vile_charge_channel = pygame.mixer.Channel(2)
    except Exception:
        arena_ctx.intro_vile_charge_channel = None
    arena_ctx.sfx_warning = sfx_warning
    arena_ctx.sfx_vile_jump = sfx_vile_jump
    arena_ctx.sfx_vile_step_land_1 = sfx_vile_step_land_1
    arena_ctx.sfx_vile_step_land_2 = sfx_vile_step_land_2
    arena_ctx.sfx_vile_punch = sfx_vile_punch
    arena_ctx.score = 0
    arena_ctx.elapsed_time = 0.0
    arena_ctx.pending_enemy_respawns = []
    arena_ctx.pending_enemy_growth = 0
    arena_ctx.growth_spawn_cooldown = 0
    arena_ctx.dynamic_enemy_target = 0
    arena_ctx.performance_frame = 0
    arena_ctx.perf_active_enemies = 0
    arena_ctx.perf_throttled_enemies = 0
    arena_ctx.perf_dormant_enemies = 0
    arena_ctx.secret_foxy_triggered = False
    arena_ctx.secret_foxy_active = False
    arena_ctx.secret_foxy_frame_index = 0
    arena_ctx.secret_foxy_frame_elapsed_ms = 0.0
    arena_ctx.secret_foxy_finished_hold_ms = 0.0
    arena_ctx.secret_foxy_prev_music_volume = None
    arena_ctx.secret_gateway_music_active = bool(intro_stage_secret_gateway_active)
    arena_ctx.cutscene_active = False
    arena_ctx.cutscene_started = False
    arena_ctx.cutscene_lines = []
    arena_ctx.cutscene_index = 0
    arena_ctx.cutscene_type_timer = 0.0
    arena_ctx.cutscene_visible_progress = 0.0
    arena_ctx.cutscene_visible_chars = 0
    arena_ctx.cutscene_panel_timer = 0.0
    arena_ctx.cutscene_auto_advance_timer = 0.0
    arena_ctx.cutscene_text_sound_cooldown = 0.0
    arena_ctx.intro_opening_active = False
    arena_ctx.intro_opening_timer = 0.0
    arena_ctx.intro_opening_dialogue_started = False
    arena_ctx.intro_opening_dialogue_finished = False
    arena_ctx.intro_opening_x_exit_active = False
    arena_ctx.intro_opening_x_exit_timer = 0.0
    arena_ctx.intro_opening_base_scroll = (0, 0)
    arena_ctx.intro_opening_scroll = (0, 0)
    arena_ctx.intro_opening_assets = None
    arena_ctx.intro_opening_landing_x = INTRO_STAGE_SPAWN_X
    arena_ctx.intro_opening_partner_x = INTRO_STAGE_SPAWN_X + 28
    arena_ctx.intro_opening_ground_y = INTRO_STAGE_SPAWN_Y
    arena_ctx.intro_post_camera_min_x = None
    arena_ctx.intro_post_cutscene_hold = 0.0
    arena_ctx.intro_locked_left_wall_x = None
    arena_ctx.intro_locked_right_wall_x = None
    arena_ctx.intro_locked_camera_scroll = None
    arena_ctx.intro_vile_triggered = False
    arena_ctx.intro_vile_sequence_active = False
    arena_ctx.intro_vile_state = "idle"
    arena_ctx.intro_vile_timer = 0.0
    arena_ctx.intro_vile_warning_plays = 0
    arena_ctx.intro_vile_warning_timer = 0.0
    arena_ctx.intro_vile_walk_target_x = None
    arena_ctx.intro_vile_player_facing_dir = 1
    arena_ctx.intro_vile_ground_y = None
    arena_ctx.intro_vile_boss = None
    arena_ctx.intro_vile_x_actor = None
    arena_ctx.intro_vile_explosion = None
    arena_ctx.intro_vile_disarmed_anim_timer = 0.0
    arena_ctx.intro_vile_charge_loop_started = False
    arena_ctx.intro_vile_charge_loop_delay = 0.0
    arena_ctx.intro_vile_thumbs_sound_played = False
    arena_ctx.intro_vile_zero_exit_active = False
    arena_ctx.intro_vile_zero_exit_timer = 0.0
    arena_ctx.intro_vile_fade_alpha = 0.0
    arena_ctx.intro_vile_battle_music_started = False
    arena_ctx.damage_health_floor = 0
    arena_ctx.intro_stage_guided = intro_stage_guided_mode_selected
    arena_ctx.intro_guidance_seen = set(intro_stage_guidance_seen_persistent)
    arena_ctx.intro_guided_giga_unlocked = (
        intro_stage_guided_giga_unlocked if intro_stage_guided_mode_selected else True
    )
    arena_ctx.intro_command_room_swarm_triggered = False
    arena_ctx.intro_command_room_swarm_alive = False
    arena_ctx.intro_command_room_swarm_cache = []
    arena_ctx.intro_pending_swarm_spawns = []
    arena_ctx.intro_pending_swarm_spawn_timer = 0
    arena_ctx.intro_checkpoint_index = intro_stage_checkpoint_index

    if current_stage == "intro_stage":
        arena_tilemap = IntroStageMap(arena_ctx)
    else:
        tile_size = 32 if isinstance(stone_folder, str) and stone_folder.startswith('assets:') else 16
        arena_tilemap = ArenaTilemap(arena_ctx, tile_size=tile_size)
    arena_surface = pygame.Surface((ARENA_W, ARENA_H), pygame.SRCALPHA).convert_alpha()

    player_width = 34
    player_height = 43
    if hasattr(arena_tilemap, "get_spawn_position"):
        spawn_x, spawn_y = arena_tilemap.get_spawn_position((player_width, player_height))
    else:
        spawn_platform = arena_tilemap.get_center_spawn_platform()
        if spawn_platform is not None:
            span_x0, span_x1, line_y = spawn_platform
            center_px_x = (span_x0 * arena_tilemap.tile_size) + (((span_x1 - span_x0) * arena_tilemap.tile_size) / 2)
        else:
            center_tile_x = arena_tilemap.start_x + arena_tilemap.width // 2
            center_px_x = center_tile_x * arena_tilemap.tile_size + arena_tilemap.tile_size // 2
            line_y = arena_tilemap.start_y + arena_tilemap.height // 2 + 2
        spawn_x = center_px_x - player_width // 2
        spawn_y = line_y * arena_tilemap.tile_size - player_height
    arena_player = ArenaPlayer(arena_ctx, (spawn_x, spawn_y), (player_width, player_height))
    arena_player.health = arena_player.max_health
    if current_stage != "intro_stage":
        _snap_player_spawn_to_ground(arena_player, arena_tilemap, max_drop=10)
    arena_player.landing_sound_suppressed_frames = max(
        getattr(arena_player, "landing_sound_suppressed_frames", 0),
        getattr(arena_player, "spawn_time", 0) + 24,
    )

    arena_movement = [False, False]
    arena_key_movement = [False, False]
    arena_joy_dir = 0
    arena_debug_hitboxes = False
    paused = False
    pause_selected_index = 0
    pause_slide = 0.0

    arena_width_px = arena_tilemap.width * arena_tilemap.tile_size
    arena_height_px = arena_tilemap.height * arena_tilemap.tile_size
    arena_origin_x = arena_tilemap.start_x * arena_tilemap.tile_size
    arena_origin_y = arena_tilemap.start_y * arena_tilemap.tile_size
    if hasattr(arena_tilemap, "camera_bounds"):
        cb = arena_tilemap.camera_bounds
        arena_bounds = (cb.x, cb.y, cb.w, cb.h)
    else:
        arena_bounds = (arena_origin_x, arena_origin_y, arena_width_px, arena_height_px)
    ox, oy, w, h = arena_bounds
    cam_cx, cam_cy = arena_player.camera_center()
    target_x = cam_cx - ARENA_W / 2
    target_y = cam_cy - ARENA_H / 2
    min_x = ox
    max_x = ox + w - ARENA_W
    min_y = oy
    max_y = oy + h - ARENA_H
    if max_x < min_x:
        target_x = ox + (w / 2) - (ARENA_W / 2)
        max_x = min_x = target_x
    if max_y < min_y:
        target_y = oy + (h / 2) - (ARENA_H / 2)
        max_y = min_y = target_y
    camera_lock = None
    if arena_tilemap and hasattr(arena_tilemap, "get_camera_lock"):
        try:
            camera_lock = arena_tilemap.get_camera_lock(arena_player.rect(), ARENA_W, ARENA_H, arena_bounds)
        except Exception:
            camera_lock = None
    if camera_lock:
        if "scroll_x" in camera_lock:
            target_x = camera_lock["scroll_x"]
        if "scroll_y" in camera_lock:
            target_y = camera_lock["scroll_y"]
    arena_render_scroll = (
        max(min_x, min(target_x, max_x)),
        max(min_y, min(target_y, max_y)),
    )
    arena_ctx.render_scroll = arena_render_scroll
    arena_ctx.arena_view_width = ARENA_W
    arena_ctx.arena_view_height = ARENA_H
    arena_ctx.arena_bounds = arena_bounds
    if current_stage == "intro_stage":
        _prime_intro_command_room_swarm_cache(arena_ctx)
    arena_stage_start_active = current_stage != "intro_stage"
    if stage_ready_anim_source and stage_ready_anim_source.images:
        arena_stage_ready_anim = Animation(
            stage_ready_anim_source.images,
            stage_ready_anim_source.durations,
            loop=False,
        )
    else:
        arena_stage_ready_anim = None
    arena_copters = []
    arena_enemy_projectiles = []
    if current_stage != "intro_stage":
        if _dynamic_arena_spawns_enabled():
            _sync_dynamic_arena_enemy_population(force_fill=True)
        else:
            arena_copters.extend(_spawn_standard_arena_enemy_set())
    else:
        intro_enemies, intro_pickups = _spawn_intro_stage_fixed_content()
        arena_copters.extend(intro_enemies)
        arena_ctx.pickups.extend(intro_pickups)
        if intro_stage_respawn_via_spawn:
            _setup_intro_stage_respawn_spawn(arena_ctx, arena_player)
            intro_stage_respawn_via_spawn = False
        else:
            _start_intro_stage_opening(arena_ctx, arena_player)
    reset_next_dt = True


# pause toggling also owns the little slide animation and confirmation reset
def _set_paused(opened, *, from_input=False):
    global paused, pause_selected_index
    global arena_movement, arena_key_movement, arena_joy_dir
    global pause_confirm_active, pause_confirm_choice, pause_confirm_action

    previous_paused = paused
    paused = opened
    if previous_paused != opened and state == "stage_viewer" and from_input:
        try:
            menu_open_sound.play()
        except Exception:
            pass
    if opened:
        pause_selected_index = 0
    pause_confirm_active = False
    pause_confirm_choice = 0
    pause_confirm_action = None
    arena_movement = [False, False]
    arena_key_movement = [False, False]
    arena_joy_dir = 0
    if arena_player:
        arena_player.set_jump_hold(False)
        arena_player.set_dash_hold(False)


def _get_pause_menu_options():
    return [
        "RESUME GAME",
        "SKIP INTRO STAGE" if current_stage == "intro_stage" else "RETURN TO STAGE SELECT",
        "RETURN TO TITLE SCREEN",
    ]


def _get_pause_menu_option_blocks():
    return [
        ["RESUME GAME"],
        ["SKIP INTRO", "STAGE"] if current_stage == "intro_stage" else ["RETURN TO", "STAGE SELECT"],
        ["RETURN TO", "TITLE SCREEN"],
    ]


def _pause_option_label(index):
    options = _get_pause_menu_options()
    if 0 <= index < len(options):
        return options[index]
    return ""


def _draw_arena_stage_ready(arena_x, arena_y, arena_scale, render_scroll):
    if not arena_stage_ready_anim or arena_stage_ready_anim.done or not arena_player:
        return
    ready_img = arena_stage_ready_anim.img()
    if not ready_img:
        return
    ready_img = _crop_alpha_surface(ready_img)
    draw_w = max(1, int(round(ready_img.get_width() * ARENA_STAGE_READY_SCALE)))
    draw_h = max(1, int(round(ready_img.get_height() * ARENA_STAGE_READY_SCALE)))
    ready_draw = pygame.transform.scale(ready_img, (draw_w, draw_h))
    player_rect = arena_player.rect()
    player_center_x = arena_x + int(round((player_rect.centerx - render_scroll[0]) * arena_scale))
    player_top_y = arena_y + int(round((player_rect.top - render_scroll[1]) * arena_scale))
    ready_center_y = player_top_y - int(round(draw_h * 0.78))
    ready_center_y = max((draw_h // 2) + 12, ready_center_y)
    ready_rect = ready_draw.get_rect(center=(player_center_x, ready_center_y))
    game_surface.blit(ready_draw, ready_rect)


def _activate_pause_confirmation():
    global pause_confirm_active, pause_confirm_choice, pause_confirm_action
    option = _pause_option_label(pause_selected_index)
    if option == "SKIP INTRO STAGE":
        pause_confirm_active = True
        pause_confirm_choice = 0
        pause_confirm_action = "skip_intro_stage"


def _resolve_pause_confirmation(accepted):
    global pause_confirm_active, pause_confirm_choice, pause_confirm_action, pause_slide
    action = pause_confirm_action
    pause_confirm_active = False
    pause_confirm_choice = 0
    pause_confirm_action = None
    if not accepted:
        return
    if action == "skip_intro_stage":
        _set_paused(False)
        pause_slide = 0.0
        _finish_intro_stage_to_stage_select()


def _activate_pause_option():
    global paused, pause_slide

    option = _pause_option_label(pause_selected_index)
    if option == "RESUME GAME":
        _set_paused(False)
        return
    if option == "SKIP INTRO STAGE":
        _activate_pause_confirmation()
        return
    if option == "RETURN TO STAGE SELECT":
        _set_paused(False)
        pause_slide = 0.0
        _begin_arena_result("success", destination="stage_select")
        return
    if option == "RETURN TO TITLE SCREEN":
        _set_paused(False)
        pause_slide = 0.0
        if current_stage == "intro_stage":
            _return_to_title_screen()
        else:
            _begin_arena_result("success", destination="title")

frame_index = 0
frame_timer = 0
ANIMATION_SPEED = 8

capcom_logo_sheet = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "capcom_logo.png")
).convert_alpha()
LOGO_SCALE = 5
dt = 0
reset_next_dt = False
arena_perf_overlay_enabled = False
arena_perf_metrics = {
    "fps": 0.0,
    "frame_ms": 0.0,
    "update_ms": 0.0,
    "draw_ms": 0.0,
    "setup_ms": 0.0,
}
capcom_frame_index = 0
capcom_frame_timer = 0
CAPCOM_DURATION = 7
capcom_hold_timer = 0
CAPCOM_HOLD_DURATION = 1.0

preview_anim_time = 0
PREVIEW_ANIM_DURATION = 0.8

preview_start_pos = (0, 0)

preview_start_scale = 0.5

preview_animating = False

current_music = None
music_intro_playing = False
music_loop_path = None

ui_sheet = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "ui_elements.png")
).convert_alpha()

with open(os.path.join(ASSETS_DIR, "menu_and_ui", "ui_elements.json")) as f:
    ui_data = json.load(f)

ui_frames = ui_data["frames"]

def get_ui_frame(frame_name):
    if frame_name not in ui_frames:
        return None

    frame = ui_frames[frame_name]["frame"]
    rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])
    return ui_sheet.subsurface(rect)

# ---- STAGE ICONS & PREVIEWS ----
# NOTE: "northern" was renamed from "north_pole" to match the spritesheet
stage_icons = {
    "northern":  "ui_elements #northern_area_icon.ase",
    "magma":     "ui_elements #magma_area_icon.ase",
    "airbase":   "ui_elements #airbase_area_icon.ase",
    "amazon":    "ui_elements #amazon_area_icon.ase",
    "seabase":   "ui_elements #seabase_area_icon.ase",
    "wepcenter": "ui_elements #wepcenter_area_icon.ase",
    "game_icon": "ui_elements #game_icon.ase",
}

preview_frames = {
    "northern":  "ui_elements #northern_area_preview.ase",
    "magma":     "ui_elements #magma_area_preview.ase",
    "airbase":   "ui_elements #airbase_area_preview.ase",
    "amazon":    "ui_elements #amazon_area_preview.ase",
    "seabase":   "ui_elements #seabase_area_preview.ase",
    "wepcenter": "ui_elements #wepcenter_area_preview.ase",
}

stage_info = {
    "northern":  {"stage": "Northern Area",      "overseer": "Chill Penguin"},
    "magma":     {"stage": "Magma Area",          "overseer": "Blaze Heatnix"},
    "airbase":   {"stage": "Airbase Area",        "overseer": "Gravity Beetle"},
    "amazon":    {"stage": "Amazon Area",         "overseer": "Web Spider"},
    "seabase":   {"stage": "Seabase Area",        "overseer": "Bubble Crab"},
    "wepcenter": {"stage": "Weapons Center Area", "overseer": "Infinity Mijinion"},
}

marker_frame_index = 0
marker_timer = 0
MARKER_SPEED = 0.08

map_marker_frames = []

for i in range(6):
    frame_name = f"ui_elements #map_location_indicator {i}.ase"
    if frame_name in ui_frames:
        frame = ui_frames[frame_name]["frame"]
        rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])
        image = ui_sheet.subsurface(rect)
        map_marker_frames.append(image)



# music loader supports optional intro+loop pairs so stage tracks can feel more polished
def play_music(intro_path, loop_path=None):
    global current_music, music_intro_playing, music_loop_path

    if current_music == intro_path:
        return

    pygame.mixer.music.stop()
    pygame.mixer.music.set_volume(_music_volume_for(intro_path))
    pygame.mixer.music.load(intro_path)
    pygame.mixer.music.play()

    current_music = intro_path
    music_intro_playing = True
    music_loop_path = loop_path


def stop_music(fade_time=500):
    pygame.mixer.music.fadeout(fade_time)


def _stop_all_audio_immediately():
    global current_music, music_intro_playing, music_loop_path
    try:
        pygame.mixer.stop()
    except Exception:
        pass
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass
    current_music = None
    music_intro_playing = False
    music_loop_path = None


# title intro update/draw flow stays here because it shares a lot of menu globals
def draw_intro(dt):
    global capcom_intro_phase
    global capcom_frame_index, capcom_frame_timer
    global sound_started, fade_alpha
    global capcom_hold_timer

    game_surface.fill((0, 0, 0))

    draw_text_centered("INSPIRED BY", HEIGHT // 2 - 170, highlighted=False)

    if not sound_started:
        capcom_sound.play()
        sound_started = True

    capcom_frame_timer += dt

    if capcom_frame_timer >= 1 / CAPCOM_FPS:
        capcom_frame_timer = 0
        capcom_frame_index += 1

    if capcom_frame_index >= len(capcom_frames):
        capcom_frame_index = len(capcom_frames) - 1
        capcom_intro_phase = 2

    frame = capcom_frames[capcom_frame_index]

    scaled_frame = pygame.transform.scale(
        frame,
        (
            int(frame.get_width() * LOGO_SCALE),
            int(frame.get_height() * LOGO_SCALE)
        )
    )

    game_surface.blit(
        scaled_frame,
        (
            WIDTH // 2 - scaled_frame.get_width() // 2,
            HEIGHT // 2 - scaled_frame.get_height() // 2 - 50
        )
    )

    if capcom_intro_phase == 2:
        capcom_hold_timer += dt

        if capcom_hold_timer >= CAPCOM_HOLD_DURATION:
            fade_alpha += 150 * dt
            if fade_alpha > 255:
                fade_alpha = 255

            fade_surface.set_alpha(int(fade_alpha))
            game_surface.blit(fade_surface, (0, 0))

            if fade_alpha >= 255:
                if ui_major_transition is None:
                    _begin_ui_major_transition("capcom_to_menu")


sound_started = False
fade_alpha = 0


with open(os.path.join(ASSETS_DIR, "menu_and_ui", "capcom_logo.json"), encoding="utf-8") as f:
    capcom_data = cast(dict[str, Any], json.load(f))

capcom_frames_data = cast(dict[str, dict[str, dict[str, int]]], capcom_data["frames"])

capcom_frames = []

valid_keys = [
    key for key in capcom_frames_data.keys()
    if "#capcom_logo" in key
]

sorted_keys = sorted(
    valid_keys,
    key=lambda k: int(k.split(" ")[-1].replace(".ase", "")))

for key in sorted_keys:
    frame = capcom_frames_data[key]["frame"]
    rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])
    image = capcom_logo_sheet.subsurface(rect)
    capcom_frames.append(image)

CAPCOM_DURATION = 7
CAPCOM_FPS = (len(capcom_frames) / CAPCOM_DURATION) * 1.9


with open(os.path.join(ASSETS_DIR, "menu_and_ui", "font.json")) as f:
    font_data = json.load(f)
font_frames = font_data["frames"]


def measure_real_width(surface):
    """Scan from right to find the last column with any non-transparent pixel."""
    w, h = surface.get_size()
    for x in range(w - 1, -1, -1):
        for y in range(h):
            if surface.get_at((x, y))[3] > 0:
                return x + 1
    return 1

# Build a real-width lookup for every font frame at native (1x) resolution
font_real_widths = {}
for key, data in font_frames.items():
    frame = data["frame"]
    rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])
    glyph = font_sheet.subsurface(rect)
    font_real_widths[key] = measure_real_width(glyph)


clock = pygame.time.Clock()
BASE_FPS = 60
paused = False
debug_freeze = False
frame_step = False
pause_selected_index = 0
pause_slide = 0.0
pause_confirm_active = False
pause_confirm_choice = 0
pause_confirm_action = None
arena_result_data = None
ui_major_transition = None
menu_root_drawn_once = False
PAUSE_MENU_RIGHT_MARGIN = 24
PAUSE_MENU_SLIDE_SPEED = 0.22
PAUSE_DIM_ALPHA = 132
PAUSE_MINIMAP_TILE_SIZE = 8
PAUSE_STATUS_BARS_X_OFFSET = 8
PAUSE_FACE_X_OFFSET = 22
PAUSE_FACE_SCALE_MULTIPLIER = 1.2
PAUSE_MENU_REFERENCE_PANEL_SCALE = min(
    (HEIGHT - 24) / pause_menu_panel_raw.get_height(),
    (WIDTH * 0.44) / pause_menu_panel_raw.get_width(),
)
pause_zero_face_anim = None
if pause_zero_face_source and pause_zero_face_source.images:
    pause_face_images = pause_zero_face_source.images
    base_face = pause_face_images[0]
    blink_face_a = _compose_face_frame(base_face, pause_face_images[1]) if len(pause_face_images) > 1 else _compose_face_frame(base_face)
    blink_face_b = _compose_face_frame(base_face, pause_face_images[2]) if len(pause_face_images) > 2 else blink_face_a
    pause_zero_face_anim = Animation(
        [
            _compose_face_frame(base_face),
            _compose_face_frame(base_face),
            blink_face_a,
            blink_face_b,
            blink_face_a,
            _compose_face_frame(base_face),
            blink_face_a,
            blink_face_b,
            blink_face_a,
            _compose_face_frame(base_face),
        ],
        img_dur=[56, 52, 4, 4, 4, 10, 4, 4, 4, 64],
        loop=True,
    )

intro_zero_face_bank = _build_dialogue_face_bank(pause_zero_face_source)
intro_x_face_bank = _build_dialogue_face_bank(pause_x_face_source)

stage_intro_sheet_frames, stage_intro_tag_ranges, STAGE_INTRO_CANVAS_SIZE = [], {}, (0, 0)
stage_intro_frame_crops = []
stage_intro_frame_rects = []
stage_intro_assets_signature = None


# rebuild stage-preview art when the selected stage changes
def _refresh_stage_intro_assets():
    global stage_intro_sheet_frames, stage_intro_tag_ranges, STAGE_INTRO_CANVAS_SIZE
    global stage_intro_frame_crops, stage_intro_frame_rects
    global stage_intro_assets_signature

    png_path = os.path.join(ASSETS_DIR, "menu_and_ui", "intro_and_bosses.png")
    json_path = os.path.join(ASSETS_DIR, "menu_and_ui", "intro_and_bosses.json")
    try:
        signature = (
            os.path.getmtime(png_path),
            os.path.getmtime(json_path),
            os.path.getsize(png_path),
            os.path.getsize(json_path),
        )
    except OSError:
        signature = None

    if signature == stage_intro_assets_signature and stage_intro_sheet_frames:
        return

    stage_intro_sheet_frames, stage_intro_tag_ranges, STAGE_INTRO_CANVAS_SIZE = _load_intro_boss_sheet()
    stage_intro_frame_crops = []
    stage_intro_frame_rects = []
    for _frame in stage_intro_sheet_frames:
        _rect = _frame.get_bounding_rect() if _frame is not None else None
        _cropped = _crop_alpha_surface(_frame) if _frame is not None else None
        stage_intro_frame_crops.append(_cropped)
        stage_intro_frame_rects.append(_rect)
    stage_intro_assets_signature = signature


STAGE_BOSS_TAGS = {
    "northern": "chill_penguin",
    "airbase": "gravity_beetle",
    "seabase": "bubble_crab",
    "wepcenter": "infinity_mijinion",
    "amazon": "web_spider",
    "magma": "blaze_heatnix",
}
STAGE_BOSS_FRAME_DUR = 5
STAGE_INTRO_FINAL_HOLD = 0.55
STAGE_INTRO_BAR_SLIDE = 1.35
STAGE_INTRO_TRIANGLE_SLIDE = 1.15
STAGE_INTRO_SIGMA_SLIDE = 1.15
STAGE_INTRO_STEP_HOLD = 0.35
STAGE_INTRO_LIGHTNING_ONLY = 0.42
STAGE_INTRO_SUMMON = 1.05
STAGE_INTRO_STAR_INDEX = 0
STAGE_INTRO_BAR_INDEX = 1
STAGE_INTRO_TRIANGLE_INDEX = 2
STAGE_INTRO_SIGMA_FRAMES = (3,)
STAGE_INTRO_LIGHTNING_FRAMES = (5, 4)
STAGE_START_MUSIC_DURATION = 7.38
stage_intro_boss_anim = None
stage_intro_phase = "idle"
stage_intro_hold_timer = 0.0
stage_intro_timer = 0.0
stage_intro_total_time = 0.0
stage_intro_boss_tag = None
stage_intro_skip_update_once = False
stage_intro_skip_update_frames = 0
stage_intro_pending_music = False
STAGE_BOSS_HEIGHT_FACTORS = {
    "northern": 0.15,
    "airbase": 0.25,
    "seabase": 0.25,
    "wepcenter": 0.24,
    "amazon": 0.25,
    "magma": 0.30,
}
# Fine-tune boss summon alignment here in raw game-surface pixels.
STAGE_BOSS_DRAW_OFFSETS = {
    "northern": (0, 50),
    "airbase": (0, 0),
    "seabase": (-3, 0),
    "wepcenter": (-10, 0),
    "amazon": (0, 15),
    "magma": (0, 0),
}
STAGE_BOSS_NAME_TEXT = {
    "northern": "CHILL PENGUIN",
    "airbase": "GRAVITY BEETLE",
    "seabase": "BUBBLE CRAB",
    "wepcenter": "INFINITY MIJINION",
    "amazon": "WEB SPIDER",
    "magma": "BLAZE HEATNIX",
}
STAGE_BOSS_NAME_OFFSETS = {
    "northern": (0, 250),
    "airbase": (0, 250),
    "seabase": (0, 250),
    "wepcenter": (0, 250),
    "amazon": (0, 250),
    "magma": (0, 250),
}
STAGE_BOSS_NAME_SCALE = 4.0

# game state
state = "capcom_intro"
capcom_intro_timer = 0
capcom_intro_phase = 0

# menu data
menu_root_options = ["Game Start", "Leaderboard", "Options", "Credits"]
menu_game_start_options = ["Guided", "Normal", "Back"]
menu_options_keyboard = [
    ("MOVE LEFT", "A"),
    ("MOVE RIGHT", "D"),
    ("JUMP", "SPACE"),
    ("ATTACK", "J / LEFT CLICK"),
    ("DASH", "K / MOUSE SIDE"),
    ("GIGA ATTACK", "X"),
    ("PAUSE", "ESC / ENTER"),
    ("CONFIRM", "ENTER / SPACE"),
]
menu_options_controller = [
    ("MOVE", "DPAD / LEFT STICK"),
    ("JUMP", "B"),
    ("ATTACK", "Y"),
    ("DASH", "A"),
    ("GIGA ATTACK", "X"),
    ("PAUSE", "START"),
    ("CONFIRM", "A / START"),
    ("BACK", "B"),
]
menu_credits_lines = [
    "ARENA SURVIVOR IS A COLLEGE PROJECT.",
    "",
    "SPRITES: DEVIANTART, THE SPRITERS RESOURCE,",
    "AND SPRITES INC.",
    "",
    "SOUNDS: THE SOUNDS RESOURCE",
    "AND SELECT GAME RIPS.",
    "",
    "BACKGROUNDS: THE BACKGROUNDS HQ",
    "AND SELECT GAME RIPS.",
    "",
    "MEGA MAN X AND RELATED ASSETS",
    "COPYRIGHT CAPCOM CO., LTD.",
    "ALL RIGHTS RESERVED.",
    "",
    "LEADERBOARD RECORDS ARE SAVED",
    "LOCALLY ON THIS DEVICE.",
]
selected_index = 0
FONT_SCALE = 3
LETTER_SPACING = -18
MENU_LOGO_SCALE = 0.7
MENU_LOGO_Y = -70
MENU_TEXT_START_Y = 600
MENU_TEXT_SPACING = 80
MENU_CURSOR_SCALE = 3
MENU_CURSOR_X_OFFSET = 105
MENU_CURSOR_Y_OFFSET = -180
MENU_THUMBS_SCALE = 3
MENU_CONFIRM_HOLD_FRAME = 6
MENU_CONFIRM_HOLD_DELAY = 0.35  # seconds to pause on thumbs-up before fading
MENU_CONFIRM_FADE_DURATION = 1  # seconds to reach full black (≈20 alpha/sec)
MENU_CONFIRM_BLACK_HOLD = 0.1  # seconds to hold black before switching state

menu_zero_anims = assets_load_spritesheet(
    ASSETS_DIR,
    "playable_characters/zero/zero_final_spritesheet.png",
    "playable_characters/zero/zero_final_spritesheet.json"
)
menu_zero_idle_anim = menu_zero_anims.get("zero_idle", None)
menu_zero_thumbs_anim = menu_zero_anims.get("zero_exiting", None) or menu_zero_idle_anim

menu_confirming = False
menu_current_view = None
menu_submenu_scroll = 0
menu_confirm_anim = None
menu_confirm_target = None
menu_confirm_guided = True
menu_confirm_timer = 0
menu_confirm_sound_played = False
menu_confirm_hold_reached = False
menu_confirm_fade_alpha = 0
menu_confirm_hold_timer = 0.0
menu_confirm_black_timer = 0.0
menu_confirm_fade_frame = 0
menu_confirm_music_stopped = False


def _get_menu_options():
    if menu_current_view == "game_mode":
        return menu_game_start_options
    return menu_root_options


def _play_menu_start_sound():
    try:
        menu_start_sound.play()
    except Exception:
        pass


# helper for switching submenu panels while keeping their scroll state predictable
def _open_menu_view(name):
    global menu_current_view, menu_submenu_scroll, selected_index
    menu_current_view = name
    menu_submenu_scroll = 0
    selected_index = 0


def _close_menu_view():
    global menu_current_view, menu_submenu_scroll, selected_index
    menu_current_view = None
    menu_submenu_scroll = 0
    selected_index = 0


def _leaderboard_sorted_records():
    records = _load_leaderboard_records()
    return sorted(
        records,
        key=lambda rec: (-int(rec.get("score", 0)), int(rec.get("elapsed_seconds", 0)), str(rec.get("name", ""))),
    )


def _menu_submenu_max_scroll(name):
    if name == "leaderboards":
        visible_rows = 8
        return max(0, len(_leaderboard_sorted_records()) - visible_rows)
    if name == "credits":
        return 0
    return 0


def _scroll_menu_view(delta):
    global menu_submenu_scroll
    if menu_current_view not in {"leaderboards", "credits"}:
        return False
    max_scroll = _menu_submenu_max_scroll(menu_current_view)
    new_scroll = max(0, min(max_scroll, menu_submenu_scroll + delta))
    if new_scroll == menu_submenu_scroll:
        return False
    menu_submenu_scroll = new_scroll
    return True
intro_stage_respawn_via_spawn = False
intro_stage_checkpoint_index = -1
intro_stage_checkpoint_spawn = None
intro_stage_black_transition = None
INTRO_STAGE_BLACK_FADE_DURATION = MENU_CONFIRM_FADE_DURATION
INTRO_STAGE_BLACK_HOLD = 3.0
UI_MAJOR_FADE_DURATION = 1.35
UI_MAJOR_BLACK_HOLD = 0.08

# ---- STAGE SELECT STRUCTURE ----
# Layout (2 top, 5 bottom):
#
#          [northern]          [magma]
#  [airbase] [amazon] [game_icon] [seabase] [wepcenter]
#

map_image = pygame.image.load(
    os.path.join(ASSETS_DIR, "menu_and_ui", "stage_select_background.png")
).convert_alpha()

# ---- STAGE SLOT POSITIONS ----
# Top row: 2 stages spread across upper portion
# Bottom row: 5 stages evenly spaced
# Map marker positions are placeholder — adjust once background art is finalised

TOP_Y = 162
BOT_Y = 820

# Bottom row: 5 stages evenly spaced, pulled in slightly so wepcenter doesn't clip
BOT_POSITIONS = [
    int(WIDTH * 0.11),  # airbase
    int(WIDTH * 0.30),  # amazon
    int(WIDTH * 0.50),  # game_icon (center)
    int(WIDTH * 0.70),  # seabase
    int(WIDTH * 0.89),  # wepcenter
]

# Top row: align directly above the outermost bottom icons
TOP_LEFT_X  = BOT_POSITIONS[0]  # same x as airbase
TOP_RIGHT_X = BOT_POSITIONS[4]  # same x as wepcenter

stage_slots = {
    "northern":  {"center": (TOP_LEFT_X,       TOP_Y),       "map_marker_pos": (620, 330)},
    "magma":     {"center": (TOP_RIGHT_X,      TOP_Y),       "map_marker_pos": (1180, 400)},
    "airbase":   {"center": (BOT_POSITIONS[0], BOT_Y),       "map_marker_pos": (250, 440)},
    "amazon":    {"center": (BOT_POSITIONS[1], BOT_Y),       "map_marker_pos": (900, 515)},
    "game_icon": {"center": (BOT_POSITIONS[2], BOT_Y),       "map_marker_pos": None},
    "seabase":   {"center": (BOT_POSITIONS[3], BOT_Y),       "map_marker_pos": (1309, 580)},
    "wepcenter": {"center": (BOT_POSITIONS[4], BOT_Y),       "map_marker_pos": (600, 448)},
}

# Preview settles in the dead sea space at the top, above the island
preview_target_pos = (((WIDTH // 3) - 40), 165)

cursor_index = 0
cursor_timer = 0
CURSOR_SPEED = 0.07

ICON_SCALE = 3.5
PREVIEW_SCALE = 4
CURSOR_SCALE = 3.5
MARKER_SCALE = 3

# ---- STAGE SELECT CURSOR ANIMATION ----
cursor_frames = []

for i in range(5):
    frame_name = f"ui_elements #stage_select_cursor {i}.ase"
    if frame_name in ui_frames:
        frame = ui_frames[frame_name]["frame"]
        rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])
        image = ui_sheet.subsurface(rect)
        cursor_frames.append(image)

# ---- NAVIGATION MAP ----
# Top row:    northern <-> magma
# Bottom row: airbase <-> amazon <-> game_icon <-> seabase <-> wepcenter
# Vertical:   northern above airbase/amazon, magma above seabase/wepcenter
#             game_icon connects up to whichever top stage is closest (none — stays bottom only)

navigation = {
    "northern":  {"right": "magma",    "down": "airbase"},
    "magma":     {"left":  "northern", "down": "wepcenter"},
    "airbase":   {"up": "northern", "right": "amazon"},
    "amazon":    {"up": "northern", "left": "airbase",  "right": "game_icon"},
    "game_icon": {"left": "amazon",   "right": "seabase"},
    "seabase":   {"up": "magma",    "left": "game_icon", "right": "wepcenter"},
    "wepcenter": {"up": "magma",    "left": "seabase"},
}

current_selection = "game_icon"
stage_select_transition_active = False
stage_select_transition_alpha = 0.0
stage_select_transition_timer = 0.0
stage_select_transition_fade_frame = 0
stage_select_transition_black_timer = 0.0
stage_select_transition_music_stopped = False
stage_select_transition_stage = None
stage_select_confirm_active = False
stage_select_confirm_choice = 0
stage_select_return_transition = None
STAGE_SELECT_TO_INTRO_FADE_DUR = 1.2
STAGE_SELECT_TO_INTRO_BLACK_HOLD = 0.2

preview_target_scale = PREVIEW_SCALE
previous_selection = current_selection

# ---- TEXT REVEAL ----
text_reveal_chars = 0
text_reveal_timer = 0
TEXT_REVEAL_SPEED = 0.04  # seconds per character — lower = faster


def get_frame_key(char, highlighted=False):
    if char == " ":
        return None

    prefix_color = "o_" if highlighted else "b_"

    if char.isupper():
        index = ord(char) - ord('A')
        return f"font #{prefix_color}capsletters {index}.ase"

    if char.islower():
        index = ord(char) - ord('a')
        return f"font #{prefix_color}lowerletters {index}.ase"

    if char.isdigit():
        index = int(char)
        return f"font #{prefix_color}numbers {index}.ase"

    symbols = ["!", ",", ".", "?", "_", "'", ":"]
    if char in symbols:
        index = symbols.index(char)
        return f"font #{prefix_color}symbols {index}.ase"

    return None


def calculate_text_width(text, highlighted=False, scale=None, force_upper=True, letter_spacing=None):
    return calculate_text_width_ex(text, highlighted=highlighted, scale=scale, force_upper=force_upper, letter_spacing=letter_spacing, space_width=None)


def calculate_text_width_ex(text, highlighted=False, scale=None, force_upper=True, letter_spacing=None, space_width=None):
    if scale is None:
        scale = FONT_SCALE
    if letter_spacing is None:
        letter_spacing = LETTER_SPACING
    if space_width is None:
        space_width = 30
    if force_upper:
        text = text.upper()
    width = 0

    for char in text:
        if char == " ":
            width += space_width
            continue

        key = get_frame_key(char, highlighted)
        if key and key in font_frames:
            frame_width = font_frames[key]["frame"]["w"]
            width += int(frame_width * scale) + letter_spacing

    return width


def draw_text_centered(text, y, highlighted=False, space_width=None):
    text = text.upper()
    text_width = calculate_text_width_ex(text, highlighted, space_width=space_width)
    x = WIDTH // 2 - text_width // 2

    offset_x = 0

    for char in text:
        if char == " ":
            offset_x += 30 if space_width is None else space_width
            continue

        key = get_frame_key(char, highlighted)
        if not key or key not in font_frames:
            continue

        frame = font_frames[key]["frame"]
        rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])

        letter = font_sheet.subsurface(rect)
        scaled_letter = pygame.transform.scale(letter, (rect.width * FONT_SCALE, rect.height * FONT_SCALE))
        game_surface.blit(scaled_letter, (x + offset_x, y))

        offset_x += rect.width * FONT_SCALE + LETTER_SPACING


# title menu renderer, including submenu panes and leaderboard view
def draw_menu():
    global menu_root_drawn_once
    game_surface.fill((0, 0, 0))

    if menu_current_view in {"leaderboards", "options", "credits"}:
        _draw_menu_subscreen(menu_current_view)
        if menu_confirming and menu_confirm_fade_alpha > 0:
            fade_surface.set_alpha(int(menu_confirm_fade_alpha))
            game_surface.blit(fade_surface, (0, 0))
        menu_root_drawn_once = True
        return

    logo_scaled = pygame.transform.scale(
        game_logo,
        (int(game_logo.get_width() * MENU_LOGO_SCALE), int(game_logo.get_height() * MENU_LOGO_SCALE))
    )

    game_surface.blit(
        logo_scaled,
        (WIDTH // 2 - logo_scaled.get_width() // 2, MENU_LOGO_Y)
    )

    visible_options = _get_menu_options()
    max_width = 0
    for option in menu_root_options:
        w = calculate_text_width(option, highlighted=False)
        if w > max_width:
            max_width = w

    start_x = WIDTH // 2 - max_width // 2

    for i, option in enumerate(visible_options):
        y_position = MENU_TEXT_START_Y + i * MENU_TEXT_SPACING
        draw_text_left(option, start_x, y_position, highlighted=(i == selected_index))
        if i == selected_index:
            cursor_img = None
            cursor_scale = MENU_CURSOR_SCALE
            if menu_confirming and menu_confirm_anim:
                cursor_img = menu_confirm_anim.img()
                cursor_scale = MENU_THUMBS_SCALE
            elif menu_zero_idle_anim and menu_zero_idle_anim.images:
                cursor_img = menu_zero_idle_anim.images[0]
            if cursor_img:
                w = int(cursor_img.get_width() * cursor_scale)
                h = int(cursor_img.get_height() * cursor_scale)
                if w > 0 and h > 0:
                    icon = pygame.transform.scale(cursor_img, (w, h))
                    icon_x = start_x + MENU_CURSOR_X_OFFSET - w
                    icon_y = y_position + MENU_CURSOR_Y_OFFSET
                    game_surface.blit(icon, (icon_x, icon_y))

    if menu_confirming and menu_confirm_fade_alpha > 0:
        fade_surface.set_alpha(int(menu_confirm_fade_alpha))
        game_surface.blit(fade_surface, (0, 0))
    menu_root_drawn_once = True


def _draw_menu_subscreen(name):
    title_map = {
        "leaderboards": "LEADERBOARD",
        "options": "OPTIONS",
        "credits": "CREDITS",
    }
    draw_text_centered_on(game_surface, title_map.get(name, ""), 60, highlighted=True, scale=3.5, letter_spacing=-18)

    if name == "leaderboards":
        records = _leaderboard_sorted_records()
        headers = [
            ("RANK", 110),
            ("NAME", 300),
            ("STAGE", 550),
            ("SCORE", 850),
            ("TIME", 1080),
        ]
        for label, x in headers:
            draw_text_left_on(game_surface, label, x, 160, highlighted=True, scale=2.3, letter_spacing=-18)

        start = menu_submenu_scroll
        visible_rows = 7
        row_y = 200
        row_step = 85
        if not records:
            draw_text_centered_on(game_surface, "NO RECORDS YET", 400, scale=2.5, letter_spacing=-18)
        for idx, record in enumerate(records[start:start + visible_rows], start=start + 1):
            y = row_y + ((idx - start) * row_step)
            draw_text_left_on(game_surface, str(idx), 110, y, scale=2.0, letter_spacing=-18)
            draw_text_left_on(game_surface, str(record.get("name", ""))[:12], 300, y, scale=2.0, letter_spacing=-18)
            draw_text_left_on(game_surface, str(record.get("stage_label", ""))[:11], 550, y, scale=2.0, letter_spacing=-18)
            draw_text_left_on(game_surface, f"{int(record.get('score', 0)):06d}", 850, y, scale=2.0, letter_spacing=-18)
            draw_text_left_on(game_surface, str(record.get("elapsed_label", "")), 1080, y, scale=2.0, letter_spacing=-18)

    elif name == "options":
        left_title_x = 140
        right_title_x = 100
        draw_text_left_on(game_surface, "KEYBOARD", left_title_x, 160, highlighted=True, scale=2.5, letter_spacing=-18)
        draw_text_left_on(game_surface, "CONTROLLER", right_title_x + WIDTH // 2, 160, highlighted=True, scale=2.5, letter_spacing=-18)

        row_y = 250
        row_step = 75
        for idx, (label, value) in enumerate(menu_options_keyboard):
            y = row_y + idx * row_step
            draw_text_left_on(game_surface, f"{label}:", left_title_x, y, scale=2.1, letter_spacing=-18)
            draw_text_left_on(game_surface, value, left_title_x + 350, y, scale=2.1, letter_spacing=-18)
        for idx, (label, value) in enumerate(menu_options_controller):
            y = row_y + idx * row_step
            draw_text_left_on(game_surface, f"{label}:", right_title_x + WIDTH // 2, y, scale=2.1, letter_spacing=-18)
            draw_text_left_on(game_surface, value, right_title_x + WIDTH // 2 + 330, y, scale=2.1, letter_spacing=-18)

    elif name == "credits":
        row_y = 140
        line_gap = 44
        section_gap = 24
        current_y = row_y
        for line in menu_credits_lines:
            if not line:
                current_y += section_gap
                continue
            draw_text_centered_on(
                game_surface,
                line,
                current_y,
                scale=2.0,
                letter_spacing=-18,
            )
            current_y += line_gap

    back_y = HEIGHT - 110
    draw_text_centered_on(game_surface, "BACK TO TITLE", back_y, highlighted=True, scale=2.7, letter_spacing=-18)


def draw_text_left(text, x, y, highlighted=False, scale=None, force_upper=True, space_width=None):
    if scale is None:
        scale = FONT_SCALE
    if space_width is None:
        space_width = 30
    if force_upper:
        text = text.upper()
    offset_x = 0

    for char in text:
        if char == " ":
            offset_x += space_width
            continue

        key = get_frame_key(char, highlighted)
        if not key or key not in font_frames:
            continue

        frame = font_frames[key]["frame"]
        rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])

        letter = font_sheet.subsurface(rect)
        target_w = int(rect.width * scale)
        target_h = int(rect.height * scale)
        scaled_letter = pygame.transform.scale(letter, (target_w, target_h))
        game_surface.blit(scaled_letter, (x + offset_x, y))

        offset_x += target_w + LETTER_SPACING


def draw_text_left_on(surface, text, x, y, highlighted=False, scale=None, force_upper=True, letter_spacing=None, space_width=None):
    if scale is None:
        scale = FONT_SCALE
    if letter_spacing is None:
        letter_spacing = LETTER_SPACING
    if space_width is None:
        space_width = 30
    if force_upper:
        text = text.upper()
    offset_x = 0

    for char in text:
        if char == " ":
            offset_x += space_width
            continue

        key = get_frame_key(char, highlighted)
        if not key or key not in font_frames:
            continue

        frame = font_frames[key]["frame"]
        rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])

        letter = font_sheet.subsurface(rect)
        target_w = int(rect.width * scale)
        target_h = int(rect.height * scale)
        scaled_letter = pygame.transform.scale(letter, (target_w, target_h))
        scaled_letter.set_colorkey((0, 0, 0))
        surface.blit(scaled_letter, (x + offset_x, y))

        offset_x += target_w + letter_spacing


def draw_text_centered_on(surface, text, y, highlighted=False, scale=None, force_upper=True, letter_spacing=None):
    text_width = calculate_text_width_ex(
        text,
        highlighted=highlighted,
        scale=scale,
        force_upper=force_upper,
        letter_spacing=letter_spacing,
        space_width=None,
    )
    x = (surface.get_width() // 2) - (text_width // 2)
    draw_text_left_on(
        surface,
        text,
        x,
        y,
        highlighted=highlighted,
        scale=scale,
        force_upper=force_upper,
        letter_spacing=letter_spacing,
    )


def _record_perf_metric(name, seconds, blend=0.18):
    sample_ms = max(0.0, float(seconds) * 1000.0)
    previous = float(arena_perf_metrics.get(name, 0.0))
    if previous <= 0.0:
        arena_perf_metrics[name] = sample_ms
    else:
        arena_perf_metrics[name] = previous + ((sample_ms - previous) * blend)


def _record_perf_value(name, value, blend=0.18):
    sample = max(0.0, float(value))
    previous = float(arena_perf_metrics.get(name, 0.0))
    if previous <= 0.0:
        arena_perf_metrics[name] = sample
    else:
        arena_perf_metrics[name] = previous + ((sample - previous) * blend)


# lightweight perf overlay for profiling without a separate debug ui
def _draw_perf_overlay(surface, ctx):
    if not arena_perf_overlay_enabled:
        return
    lines = [
        f"FPS {int(round(arena_perf_metrics.get('fps', 0.0)))}",
        f"FRAME {arena_perf_metrics.get('frame_ms', 0.0):.1f}MS",
        f"UPDATE {arena_perf_metrics.get('update_ms', 0.0):.1f}MS",
        f"DRAW {arena_perf_metrics.get('draw_ms', 0.0):.1f}MS",
    ]
    setup_ms = arena_perf_metrics.get('setup_ms', 0.0)
    if setup_ms > 0.0:
        lines.append(f"SETUP {setup_ms:.1f}MS")
    if ctx is not None:
        lines.extend(
            [
                f"ENEMY {len(arena_copters)}",
                f"TARGET {int(getattr(ctx, 'dynamic_enemy_target', 0) or 0)}",
                f"ACTIVE {int(getattr(ctx, 'perf_active_enemies', 0) or 0)}",
                f"THROTTLED {int(getattr(ctx, 'perf_throttled_enemies', 0) or 0)}",
                f"DORMANT {int(getattr(ctx, 'perf_dormant_enemies', 0) or 0)}",
                f"PROJECTILES {len(arena_enemy_projectiles)}",
            ]
        )
    scale = 1.35
    letter_spacing = -8
    line_height = 18
    padding = 10
    text_width = 0
    for line in lines:
        text_width = max(
            text_width,
            calculate_text_width_ex(
                line,
                highlighted=False,
                scale=scale,
                force_upper=True,
                letter_spacing=letter_spacing,
                space_width=14,
            ),
        )
    box = pygame.Rect(14, 14, text_width + (padding * 2), padding + (len(lines) * line_height) + 6)
    shadow = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
    shadow.fill((0, 0, 0, 180))
    surface.blit(shadow, box.topleft)
    pygame.draw.rect(surface, (214, 214, 214), box, 2)
    y = box.top + padding
    for line in lines:
        draw_text_left_on(
            surface,
            line,
            box.left + padding,
            y,
            highlighted=False,
            scale=scale,
            letter_spacing=letter_spacing,
            space_width=14,
        )
        y += line_height


# stage select screen draw pass, including icons, preview, and map cursor
def draw_stage_select():
    global preview_anim_time, preview_animating
    global text_reveal_chars, text_reveal_timer
    game_surface.fill((0, 0, 0))
    game_surface.blit(map_image, (0, 0))

    # ---- DRAW STAGE ICONS ----
    for key, data in stage_slots.items():
        icon = get_ui_frame(stage_icons[key])

        if icon:
            scaled_icon = pygame.transform.scale(
                icon,
                (
                    int(icon.get_width() * ICON_SCALE),
                    int(icon.get_height() * ICON_SCALE)
                )
            )

            rect = scaled_icon.get_rect()
            rect.center = data["center"]
            game_surface.blit(scaled_icon, rect)

    # ---- STAGE PREVIEW ----
    preview = None

    if current_selection in preview_frames:
        preview = get_ui_frame(preview_frames[current_selection])

    if preview is not None:

        if preview_animating:
            preview_anim_time += dt
            t = min(preview_anim_time / PREVIEW_ANIM_DURATION, 1)
            t = 1 - (1 - t) ** 3  # ease-out

            current_x = lerp(preview_start_pos[0], preview_target_pos[0], t)
            current_y = lerp(preview_start_pos[1], preview_target_pos[1], t)
            current_scale = lerp(preview_start_scale, preview_target_scale, t)

            if t >= 1:
                preview_animating = False
                text_reveal_chars = 0
                text_reveal_timer = 0
        else:
            current_x, current_y = preview_target_pos
            current_scale = preview_target_scale

        scaled_preview = pygame.transform.scale(
            preview,
            (
                int(preview.get_width() * current_scale),
                int(preview.get_height() * current_scale)
            )
        )

        preview_rect = scaled_preview.get_rect()
        preview_rect.center = (int(current_x), int(current_y))
        game_surface.blit(scaled_preview, preview_rect)

    # ---- STAGE INFO TEXT ----
    if not preview_animating:
        text_reveal_timer += dt
        if text_reveal_timer >= TEXT_REVEAL_SPEED:
            text_reveal_timer = 0
            text_reveal_chars += 1
        draw_stage_info(current_selection, text_reveal_chars)

    if stage_select_confirm_active:
        box = pygame.Rect(0, 0, 560, 160)
        box.center = (WIDTH // 2, HEIGHT // 2 + 24)
        shadow = box.move(6, 6)
        pygame.draw.rect(game_surface, (0, 0, 0), shadow, border_radius=8)
        pygame.draw.rect(game_surface, (34, 42, 58), box, border_radius=8)
        pygame.draw.rect(game_surface, (214, 224, 242), box, width=4, border_radius=8)
        draw_text_centered_on(game_surface, "RETURN TO TITLE SCREEN?", box.top + 26, scale=2.0, letter_spacing=-15)
        options = ("YES", "NO")
        option_y = box.top + 90
        left_x = box.centerx - 104
        right_x = box.centerx + 24
        for idx, label in enumerate(options):
            x = left_x if idx == 0 else right_x
            highlighted = idx == stage_select_confirm_choice
            draw_text_left_on(game_surface, label, x, option_y, highlighted=highlighted, scale=2.3, letter_spacing=-15)


# info card draw helper for the currently selected stage
def draw_stage_info(selection, visible_chars=9999):
    if selection not in stage_info:
        return

    info = stage_info[selection]

    preview = get_ui_frame(preview_frames.get(selection, ""))
    if preview is None:
        return

    text_x = 620
    text_y = preview_target_pos[1] - 25

    INFO_SCALE = 3
    LETTER_GAP = -4.5   # small fixed gap between letters at native res
    SPACE_WIDTH = 5  # space character width at native res
    LINE_HEIGHT = 56

    def info_char_w(char):
        if char == " ":
            return SPACE_WIDTH * INFO_SCALE
        key = get_frame_key(char, highlighted=False)
        if key and key in font_real_widths:
            return font_real_widths[key] * INFO_SCALE + LETTER_GAP * INFO_SCALE
        return 0

    def info_text_w(text):
        return sum(info_char_w(c) for c in text)

    def draw_info_text(text, x, y):
        offset_x = 0
        for char in text:
            if char == " ":
                offset_x += SPACE_WIDTH * INFO_SCALE
                continue
            key = get_frame_key(char, highlighted=False)
            if not key or key not in font_frames:
                continue
            frame = font_frames[key]["frame"]
            rect = pygame.Rect(frame["x"], frame["y"], frame["w"], frame["h"])
            letter = font_sheet.subsurface(rect)
            tw = int(rect.width * INFO_SCALE)
            th = int(rect.height * INFO_SCALE)
            scaled_letter = pygame.transform.scale(letter, (tw, th))
            game_surface.blit(scaled_letter, (x + offset_x, y))
            offset_x += font_real_widths[key] * INFO_SCALE + LETTER_GAP * INFO_SCALE

    label1 = "Stage : "
    label2 = "Arena Overseer : "

    full_line1 = label1 + info["stage"]
    full_line2 = label2 + info["overseer"]

    label1_w = info_text_w(label1)
    label2_w = info_text_w(label2)

    # Line 1 reveals first, then line 2 starts after line 1 is done
    line1_visible = min(visible_chars, len(full_line1))
    line2_visible = max(0, visible_chars - len(full_line1))

    draw_info_text(full_line1[:line1_visible], text_x, text_y)

    if line2_visible > 0:
        line2_text = full_line2[:line2_visible]
        # Split at label boundary for correct x positioning
        if line2_visible <= len(label2):
            draw_info_text(line2_text, text_x, text_y + LINE_HEIGHT)
        else:
            draw_info_text(label2, text_x, text_y + LINE_HEIGHT)
            draw_info_text(full_line2[len(label2):line2_visible], text_x + label2_w, text_y + LINE_HEIGHT)



def _begin_stage_intro_transition(selected_stage):
    global stage_select_transition_active, stage_select_transition_alpha, stage_select_transition_timer
    global stage_select_transition_fade_frame, stage_select_transition_black_timer
    global stage_select_transition_music_stopped
    global stage_select_transition_stage

    if selected_stage not in stage_music or stage_select_transition_active:
        return
    try:
        cursor_select_sound.play()
    except Exception:
        pass
    stage_select_transition_active = True
    stage_select_transition_alpha = 0.0
    stage_select_transition_timer = 0.0
    stage_select_transition_fade_frame = 0
    stage_select_transition_black_timer = 0.0
    stage_select_transition_music_stopped = False
    stage_select_transition_stage = selected_stage


def _begin_stage_select_return_transition():
    global stage_select_return_transition
    global current_music, music_intro_playing, music_loop_path
    stage_select_return_transition = None
    pygame.mixer.music.stop()
    current_music = None
    music_intro_playing = False
    music_loop_path = None
    _begin_ui_major_transition("stage_select_to_menu", play_start_sound=True)


def _activate_stage_select_confirmation():
    global stage_select_confirm_active, stage_select_confirm_choice
    if stage_select_transition_active:
        return
    stage_select_confirm_active = True
    stage_select_confirm_choice = 0
    _play_menu_start_sound()


def _resolve_stage_select_confirmation(accepted):
    global stage_select_confirm_active, stage_select_confirm_choice
    stage_select_confirm_active = False
    _play_menu_start_sound()
    if accepted:
        _begin_stage_select_return_transition()
    else:
        stage_select_confirm_choice = 0


def lerp(a, b, t):
    return a + (b - a) * t


# ---- STAGE VIEWER DRAW ----
# static stage viewer screen used before the animated intro takes over
def draw_stage_viewer():
    global frame_index, frame_timer
    global snow_index, snow_timer
    global airbase_x, clouds_x
    global seabase_x

    if current_stage == "intro_stage":
        game_surface.fill((0, 0, 0))
        return

    if current_stage == "amazon":
        background_assets = _load_stage_view_backgrounds("amazon")
        frames = background_assets.get("frames") or []
        if not frames:
            game_surface.fill((0, 0, 0))
            return
        frame_timer += 1
        if frame_timer >= ANIMATION_SPEED:
            frame_timer = 0
            frame_index = (frame_index + 1) % len(frames)
        game_surface.blit(frames[frame_index % len(frames)], (0, 0))

    elif current_stage == "magma":
        background_assets = _load_stage_view_backgrounds("magma")
        frames = background_assets.get("frames") or []
        if not frames:
            game_surface.fill((0, 0, 0))
            return
        frame_timer += 1
        if frame_timer >= ANIMATION_SPEED:
            frame_timer = 0
            frame_index = (frame_index + 1) % len(frames)
        game_surface.blit(frames[frame_index % len(frames)], (0, 0))

    elif current_stage == "northern":
        background_assets = _load_stage_view_backgrounds("northern")
        north_pole = background_assets.get("background")
        snow_frames = background_assets.get("snow_frames") or []
        if north_pole is None:
            game_surface.fill((0, 0, 0))
            return
        game_surface.blit(north_pole, (0, 0))
        if not snow_frames:
            return
        snow_timer += 1
        if snow_timer >= SNOW_ANIMATION_SPEED:
            snow_timer = 0
            snow_index = (snow_index + 1) % len(snow_frames)
        game_surface.blit(snow_frames[snow_index % len(snow_frames)], (0, 0))

    elif current_stage == "airbase":
        background_assets = _load_stage_view_backgrounds("airbase")
        airbase = background_assets.get("airbase")
        clouds_raw = background_assets.get("clouds")
        airbase_width = max(1, int(background_assets.get("airbase_width", 1)))
        clouds_width = max(1, int(background_assets.get("clouds_width", 1)))
        if airbase is None or clouds_raw is None:
            game_surface.fill((0, 0, 0))
            return
        airbase_x = (airbase_x - AIRBASE_SCROLL_SPEED) % airbase_width
        draw_x = int(airbase_x)
        game_surface.blit(airbase, (-draw_x, 0))
        game_surface.blit(airbase, (airbase_width - draw_x, 0))

        clouds_x = (clouds_x - CLOUDS_SCROLL_SPEED) % clouds_width
        draw_cx = int(clouds_x)
        game_surface.blit(clouds_raw, (-draw_cx, 0))
        game_surface.blit(clouds_raw, (clouds_width - draw_cx, 0))

    elif current_stage == "seabase":
        background_assets = _load_stage_view_backgrounds("seabase")
        seabase_bg = background_assets.get("background")
        seabase_width = max(1, int(background_assets.get("width", 1)))
        if seabase_bg is None:
            game_surface.fill((0, 0, 0))
            return
        seabase_x = (seabase_x - SEABASE_SCROLL_SPEED) % seabase_width
        draw_x = int(seabase_x)
        game_surface.blit(seabase_bg, (draw_x, 0))
        game_surface.blit(seabase_bg, (draw_x - seabase_width, 0))

    elif current_stage == "wepcenter":
        background_assets = _load_stage_view_backgrounds("wepcenter")
        frames = background_assets.get("frames") or []
        if frames:
            frame_timer += 1
            if frame_timer >= ANIMATION_SPEED:
                frame_timer = 0
                frame_index = (frame_index + 1) % len(frames)
            game_surface.blit(frames[frame_index % len(frames)], (0, 0))


def _build_stage_intro_animation(tag_name, frame_dur, final_hold=0):
    tag = stage_intro_tag_ranges.get(tag_name)
    if not tag or not stage_intro_sheet_frames:
        return None
    start = max(0, min(tag["from"], len(stage_intro_sheet_frames) - 1))
    end = max(0, min(tag["to"], len(stage_intro_sheet_frames) - 1))
    if end < start:
        start, end = end, start
    source_images = [img for img in stage_intro_sheet_frames[start:end + 1] if img is not None]
    rects = [img.get_bounding_rect() for img in source_images if img is not None]
    rects = [rect for rect in rects if rect.width > 0 and rect.height > 0]
    if not rects:
        return None
    crop_rect = rects[0].copy()
    for rect in rects[1:]:
        crop_rect.union_ip(rect)

    cropped_images = []
    for img in source_images:
        if img is None:
            continue
        frame = pygame.Surface((crop_rect.width, crop_rect.height), pygame.SRCALPHA).convert_alpha()
        frame.blit(img, (0, 0), crop_rect)
        cropped_images.append(frame)
    if not cropped_images:
        return None

    def sequence_and_durations_for_tag(name, count):
        if count <= 0:
            return [], []
        if name == "chill_penguin":
            seq = list(range(count))
            durs = [frame_dur] * len(seq)
            return seq, durs
        if name == "gravity_beetle":
            seq = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            seq = [idx for idx in seq if idx < count]
            durs = [frame_dur] * len(seq)
            if len(durs) >= 5:
                durs[4] = frame_dur * 3
            return seq, durs
        if name == "bubble_crab":
            seq = [0, 1, 2, 3, 2, 3, 2, 3, 4, 5, 6]
            seq = [idx for idx in seq if idx < count]
            durs = [frame_dur] * len(seq)
            return seq, durs
        if name == "infinity_mijinion":
            forward = list(range(max(0, count - 1)))
            backward = list(reversed(forward))
            seq = backward + forward + [count - 1]
            durs = [frame_dur] * len(seq)
            return seq, durs
        if name == "web_spider":
            seq = [0, 1, 0, 1, 0, 1, 2, 3]
            seq = [idx for idx in seq if idx < count]
            durs = [frame_dur] * len(seq)
            for i, idx in enumerate(seq[:-2]):
                if idx in (0, 1):
                    durs[i] = int(round(frame_dur * 1.5))
            return seq, durs
        if name == "blaze_heatnix":
            seq = [0, 1, 0, 1, 2, 3, 4, 5, 6, 7]
            seq = [idx for idx in seq if idx < count]
            durs = [frame_dur] * len(seq)
            for i, idx in enumerate(seq[:4]):
                if idx in (0, 1):
                    durs[i] = int(round(frame_dur * 1.5))
            return seq, durs
        seq = list(range(count))
        durs = [frame_dur] * len(seq)
        return seq, durs

    sequence, durations = sequence_and_durations_for_tag(tag_name, len(cropped_images))
    if not sequence:
        sequence = list(range(len(cropped_images)))
        durations = [frame_dur] * len(sequence)

    images = [cropped_images[idx] for idx in sequence]
    if final_hold > 0:
        durations[-1] += final_hold
    return Animation(images, durations, loop=False)


# begin the selected stage's intro animation and reset its reveal timers
def start_stage_intro():
    global state, stage_intro_boss_anim
    global stage_intro_phase, stage_intro_hold_timer, stage_intro_timer, stage_intro_total_time, stage_intro_boss_tag
    global frame_index, frame_timer, stage_intro_skip_update_once, stage_intro_skip_update_frames
    global stage_intro_pending_music

    _refresh_stage_intro_assets()
    arena_setup_start = time.perf_counter()
    init_arena_gameplay()
    _record_perf_metric("setup_ms", time.perf_counter() - arena_setup_start, blend=1.0)
    frame_index = 0
    frame_timer = 0
    stage_intro_hold_timer = 0.0
    stage_intro_boss_tag = STAGE_BOSS_TAGS.get(current_stage)
    stage_intro_timer = 0.0
    stage_intro_total_time = 0.0
    boss_hold_frames = max(1, int(round(STAGE_INTRO_FINAL_HOLD * BASE_FPS)))
    stage_intro_boss_anim = _build_stage_intro_animation(stage_intro_boss_tag, STAGE_BOSS_FRAME_DUR, final_hold=boss_hold_frames)
    stage_intro_phase = "bar"
    stage_intro_skip_update_once = True
    stage_intro_skip_update_frames = 2
    stage_intro_pending_music = True
    state = "stage_intro"


# advance the stage intro timing, text reveal, and transition handoff
def update_stage_intro():
    global state, stage_intro_phase, stage_intro_hold_timer, stage_intro_timer, stage_intro_total_time
    global stage_intro_boss_anim
    global stage_intro_skip_update_once, stage_intro_skip_update_frames

    if stage_intro_skip_update_once:
        stage_intro_skip_update_once = False
        return
    if stage_intro_skip_update_frames > 0:
        stage_intro_skip_update_frames -= 1
        return

    intro_dt = min(dt, 1 / 30)
    stage_intro_timer += intro_dt
    stage_intro_total_time += intro_dt

    if stage_intro_phase == "bar":
        if stage_intro_timer >= STAGE_INTRO_BAR_SLIDE + STAGE_INTRO_STEP_HOLD:
            stage_intro_phase = "triangle"
            stage_intro_timer = 0.0
        return

    if stage_intro_phase == "triangle":
        if stage_intro_timer >= STAGE_INTRO_TRIANGLE_SLIDE + STAGE_INTRO_STEP_HOLD:
            stage_intro_phase = "sigma"
            stage_intro_timer = 0.0
        return

    if stage_intro_phase == "sigma":
        if stage_intro_timer >= STAGE_INTRO_SIGMA_SLIDE + STAGE_INTRO_STEP_HOLD:
            stage_intro_phase = "summon"
            stage_intro_timer = 0.0
        return

    if stage_intro_phase == "summon":
        if stage_intro_boss_anim and stage_intro_timer >= STAGE_INTRO_LIGHTNING_ONLY:
            stage_intro_boss_anim.update()
        if stage_intro_timer >= STAGE_INTRO_SUMMON:
            stage_intro_phase = "hold"
            stage_intro_timer = 0.0
        return

    if stage_intro_phase == "hold":
        if stage_intro_boss_anim:
            stage_intro_boss_anim.update()
        stage_intro_hold_timer += dt
        audio_finished = not pygame.mixer.music.get_busy()
        if stage_intro_hold_timer >= STAGE_INTRO_FINAL_HOLD and stage_intro_total_time >= STAGE_START_MUSIC_DURATION and audio_finished:
            play_music(
                stage_music[current_stage]["intro"],
                stage_music[current_stage]["loop"]
            )
            state = "stage_viewer"


# render the stage intro once the update step has built the current frame state
def draw_stage_intro():
    game_surface.fill((0, 0, 0))

    def draw_intro_surface(surf, center, target_h, alpha=255, lightning=False):
        if surf is None:
            return None
        scale = target_h / max(1, surf.get_height())
        draw_size = (
            max(1, int(round(surf.get_width() * scale))),
            max(1, int(round(target_h))),
        )
        img = pygame.transform.scale(surf, draw_size)
        if lightning:
            img = _clean_lightning_draw_surface(img)
        if alpha < 255:
            img = img.copy()
            img.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        rect = img.get_rect(center=(int(round(center[0])), int(round(center[1]))))
        game_surface.blit(img, rect)
        return rect

    def draw_intro_asset(index, center, target_h, alpha=255):
        if not (0 <= index < len(stage_intro_frame_crops)):
            return None
        return draw_intro_surface(
            stage_intro_frame_crops[index],
            center,
            target_h,
            alpha=alpha,
            lightning=index in STAGE_INTRO_LIGHTNING_FRAMES,
        )

    bg = stage_intro_frame_crops[STAGE_INTRO_STAR_INDEX] if STAGE_INTRO_STAR_INDEX < len(stage_intro_frame_crops) else None
    if bg is not None:
        bg_draw = pygame.transform.scale(bg, (WIDTH, HEIGHT))
        game_surface.blit(bg_draw, (0, 0))

    ui_scale = min(WIDTH / 1280.0, HEIGHT / 720.0)
    center_x = WIDTH * 0.5
    bar_center_y = HEIGHT * 0.5
    triangle_target_y = bar_center_y - (10 * ui_scale)
    sigma_target_y = bar_center_y - (36 * ui_scale)
    triangle_target_h = HEIGHT * 0.38
    sigma_target_h = HEIGHT * 0.36
    boss_target_h = HEIGHT * STAGE_BOSS_HEIGHT_FACTORS.get(current_stage, 0.27)
    lightning_target_h = HEIGHT * 0.44

    bar_progress = 1.0 if stage_intro_phase in ("triangle", "sigma", "summon", "hold") else min(1.0, stage_intro_timer / max(0.001, STAGE_INTRO_BAR_SLIDE))
    triangle_progress = 1.0 if stage_intro_phase in ("sigma", "summon", "hold") else (0.0 if stage_intro_phase == "bar" else min(1.0, stage_intro_timer / max(0.001, STAGE_INTRO_TRIANGLE_SLIDE)))
    sigma_progress = 1.0 if stage_intro_phase in ("summon", "hold") else (0.0 if stage_intro_phase in ("bar", "triangle") else min(1.0, stage_intro_timer / max(0.001, STAGE_INTRO_SIGMA_SLIDE)))

    bar_ease = 1.0 - ((1.0 - bar_progress) ** 3)
    triangle_ease = 1.0 - ((1.0 - triangle_progress) ** 3)
    sigma_ease = 1.0 - ((1.0 - sigma_progress) ** 3)

    bar_width = WIDTH
    bar_x = lerp(-(bar_width * 0.5), center_x, bar_ease)
    triangle_y = lerp(-HEIGHT * 0.40, triangle_target_y, triangle_ease)
    sigma_y = lerp(HEIGHT + (HEIGHT * 0.28), sigma_target_y, sigma_ease)

    if bar_progress > 0.0:
        bar_surf = stage_intro_frame_crops[STAGE_INTRO_BAR_INDEX]
        if bar_surf is not None:
            target_h = max(1, int(round(bar_surf.get_height() * max(2, round(HEIGHT / 240)))))
            bar_img = pygame.transform.scale(bar_surf, (bar_width, target_h))
            bar_rect = bar_img.get_rect(center=(int(round(bar_x)), int(round(bar_center_y))))
            game_surface.blit(bar_img, bar_rect)
    if triangle_progress > 0.0:
        draw_intro_asset(STAGE_INTRO_TRIANGLE_INDEX, (center_x, triangle_y), triangle_target_h)
    sigma_rect = None
    if sigma_progress > 0.0:
        sigma_index = STAGE_INTRO_SIGMA_FRAMES[0]
        if stage_intro_phase in ("summon", "hold"):
            sigma_index = STAGE_INTRO_SIGMA_FRAMES[(pygame.time.get_ticks() // 180) % len(STAGE_INTRO_SIGMA_FRAMES)]
        sigma_rect = draw_intro_asset(sigma_index, (center_x, sigma_y), sigma_target_h)
    sigma_center = sigma_rect.center if sigma_rect else (center_x, sigma_target_y)
    boss_offset = STAGE_BOSS_DRAW_OFFSETS.get(current_stage, (0, 0))
    boss_center = (
        sigma_center[0] + boss_offset[0],
        sigma_center[1] + boss_offset[1],
    )

    if stage_intro_phase in ("summon", "hold"):
        lightning_only_time = STAGE_INTRO_LIGHTNING_ONLY
        if stage_intro_phase == "summon":
            summon_progress = min(1.0, max(0.0, stage_intro_timer / max(0.001, lightning_only_time)))
            boss_visible = stage_intro_timer >= lightning_only_time
        else:
            summon_progress = 1.0
            boss_visible = True

        if not boss_visible:
            lightning_index = STAGE_INTRO_LIGHTNING_FRAMES[int((pygame.time.get_ticks() // 85) % len(STAGE_INTRO_LIGHTNING_FRAMES))]
            lightning_alpha = int(255 * min(1.0, summon_progress * 1.2))
            draw_intro_asset(lightning_index, sigma_center, lightning_target_h, alpha=lightning_alpha)

        if boss_visible and stage_intro_boss_anim:
            boss_alpha = 255
            boss_img = stage_intro_boss_anim.img()
            boss_h = max(1, int(round(boss_target_h)))
            boss_scale = boss_h / max(1, boss_img.get_height())
            boss_size = (
                max(1, int(round(boss_img.get_width() * boss_scale))),
                boss_h,
            )
            boss_draw = pygame.transform.scale(boss_img, boss_size)
            if boss_alpha < 255:
                boss_draw = boss_draw.copy()
                boss_draw.set_alpha(boss_alpha)
            boss_rect = boss_draw.get_rect(center=(int(round(boss_center[0])), int(round(boss_center[1]))))
            game_surface.blit(boss_draw, boss_rect)

            if stage_intro_phase == "hold" or stage_intro_timer >= (STAGE_INTRO_SUMMON * 0.7):
                boss_name = STAGE_BOSS_NAME_TEXT.get(current_stage, "")
                if boss_name:
                    name_offset = STAGE_BOSS_NAME_OFFSETS.get(current_stage, (0, 96))
                    name_x = int(round(boss_center[0] + name_offset[0] - (calculate_text_width(boss_name, highlighted=False, scale=STAGE_BOSS_NAME_SCALE) / 2)))
                    name_y = int(round(boss_center[1] + name_offset[1]))
                    draw_text_left(
                        boss_name,
                        name_x,
                        name_y,
                        highlighted=False,
                        scale=STAGE_BOSS_NAME_SCALE,
                    )


# ---- SHARED NAVIGATION HANDLER ----
# shared navigation helper so keyboard, dpad, and stick input all move the cursor the same way
def handle_stage_select_move(direction):
    global current_selection, previous_selection
    global preview_anim_time, preview_animating, preview_start_pos
    global text_reveal_chars, text_reveal_timer

    if direction in navigation[current_selection]:
        current_selection = navigation[current_selection][direction]
        cursor_move_sound.play()

        preview_anim_time = 0
        preview_animating = True
        text_reveal_chars = 0
        text_reveal_timer = 0

        marker_pos = stage_slots[current_selection]["map_marker_pos"]
        if marker_pos:
            preview_start_pos = marker_pos

        previous_selection = current_selection


_prewarm_intro_stage_startup_blocking()


while True:
    frame_perf_start = time.perf_counter()
    if ui_major_transition is not None:
        transition_dt = min(dt, 1.0 / BASE_FPS)
        ui_major_transition["timer"] += transition_dt
        fade_p = min(1.0, ui_major_transition["timer"] / max(0.0001, UI_MAJOR_FADE_DURATION))
        ui_major_transition["alpha"] = fade_p * 255.0
        if ui_major_transition["timer"] >= UI_MAJOR_FADE_DURATION + UI_MAJOR_BLACK_HOLD:
            transition = ui_major_transition
            ui_major_transition = None
            _complete_ui_major_transition(transition)
    ui_transition_blocking = ui_major_transition is not None
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        if event.type == pygame.JOYDEVICEADDED:
            detect_controller()
            continue

        if ui_transition_blocking:
            continue

        if event.type == pygame.KEYDOWN:

            if state == "arena_result":
                if arena_result_data:
                    step = arena_result_data.get("step", "banner")
                    if step == "banner" and event.key in (
                        pygame.K_RETURN,
                        pygame.K_SPACE,
                        pygame.K_j,
                        pygame.K_k,
                        pygame.K_x,
                        pygame.K_ESCAPE,
                    ):
                        _play_menu_start_sound()
                        _confirm_arena_result()
                        continue
                    if step == "save_prompt":
                        if event.key in (pygame.K_a, pygame.K_w):
                            if arena_result_data.get("save_choice", 0) != 0:
                                arena_result_data["save_choice"] = 0
                                cursor_move_sound.play()
                        elif event.key in (pygame.K_d, pygame.K_s):
                            if arena_result_data.get("save_choice", 0) != 1:
                                arena_result_data["save_choice"] = 1
                                cursor_move_sound.play()
                    if step == "name_input":
                        if event.key == pygame.K_RETURN:
                            _play_menu_start_sound()
                            _confirm_arena_result()
                        elif event.key == pygame.K_ESCAPE:
                            _play_menu_start_sound()
                            _cancel_arena_result()
                        elif event.key == pygame.K_BACKSPACE:
                            arena_result_data["name_input"] = str(arena_result_data.get("name_input", ""))[:-1]
                        else:
                            char = event.unicode
                            if char and len(str(arena_result_data.get("name_input", ""))) < 12:
                                if re.match(r"[A-Za-z0-9 _.-]", char):
                                    arena_result_data["name_input"] = str(arena_result_data.get("name_input", "")) + char.upper()
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_j):
                        _play_menu_start_sound()
                        _confirm_arena_result()
                    elif event.key == pygame.K_ESCAPE:
                        _play_menu_start_sound()
                        _cancel_arena_result()
                continue

            if state == "stage_select":
                if stage_select_transition_active or stage_select_return_transition is not None:
                    continue
                if stage_select_confirm_active:
                    if event.key in (pygame.K_a,):
                        if stage_select_confirm_choice != 0:
                            stage_select_confirm_choice = 0
                            cursor_move_sound.play()
                    if event.key in (pygame.K_d,):
                        if stage_select_confirm_choice != 1:
                            stage_select_confirm_choice = 1
                            cursor_move_sound.play()
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        _resolve_stage_select_confirmation(stage_select_confirm_choice == 0)
                    if event.key == pygame.K_ESCAPE:
                        _resolve_stage_select_confirmation(False)
                    continue
                if event.key in (pygame.K_d,):
                    handle_stage_select_move("right")
                if event.key in (pygame.K_a,):
                    handle_stage_select_move("left")
                if event.key in (pygame.K_w,):
                    handle_stage_select_move("up")
                if event.key in (pygame.K_s,):
                    handle_stage_select_move("down")

                if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                    if current_selection == "game_icon":
                        _activate_stage_select_confirmation()
                    elif current_selection in stage_music:
                        _begin_stage_intro_transition(current_selection)

            if state == "menu":
                if not menu_confirming:
                    if menu_current_view in {"leaderboards", "options", "credits"}:
                        if event.key in (pygame.K_s,):
                            if _scroll_menu_view(1):
                                cursor_move_sound.play()
                        elif event.key in (pygame.K_w,):
                            if _scroll_menu_view(-1):
                                cursor_move_sound.play()
                        elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE or event.key == pygame.K_j:
                            _play_menu_start_sound()
                            _close_menu_view()
                        elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                            _play_menu_start_sound()
                            _close_menu_view()
                    else:
                        current_menu_options = _get_menu_options()
                        if event.key in (pygame.K_s,):
                            selected_index = (selected_index + 1) % len(current_menu_options)
                            cursor_move_sound.play()
                        if event.key in (pygame.K_w,):
                            selected_index = (selected_index - 1) % len(current_menu_options)
                            cursor_move_sound.play()
                        if event.key == pygame.K_RETURN:
                            option = current_menu_options[selected_index]
                            if option == "Game Start":
                                _play_menu_start_sound()
                                _open_menu_view("game_mode")
                            elif option == "Back":
                                _play_menu_start_sound()
                                _close_menu_view()
                            elif option in ("Guided", "Normal"):
                                menu_confirm_guided = option == "Guided"
                                menu_confirming = True
                                menu_confirm_target = "intro_stage"
                                menu_confirm_anim = menu_zero_thumbs_anim.copy() if menu_zero_thumbs_anim else None
                                if menu_confirm_anim:
                                    menu_confirm_anim.loop = False
                                    menu_confirm_timer = menu_confirm_anim._total
                                else:
                                    menu_confirm_timer = 18
                                menu_confirm_sound_played = False
                                menu_confirm_hold_reached = False
                                menu_confirm_fade_alpha = 0
                                menu_confirm_hold_timer = 0.0
                                menu_confirm_black_timer = 0.0
                                menu_confirm_fade_frame = 0
                                menu_confirm_music_stopped = False
                            elif option == "Leaderboard":
                                _play_menu_start_sound()
                                _open_menu_view("leaderboards")
                            elif option == "Options":
                                _play_menu_start_sound()
                                _open_menu_view("options")
                            elif option == "Credits":
                                _play_menu_start_sound()
                                _open_menu_view("credits")

            if state == "stage_viewer":
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                    if paused and pause_confirm_active and event.key == pygame.K_ESCAPE:
                        _resolve_pause_confirmation(False)
                        continue
                    _set_paused(not paused, from_input=True)
                    continue
                if paused:
                    if pause_confirm_active:
                        if event.key in (pygame.K_a,):
                            if pause_confirm_choice != 0:
                                pause_confirm_choice = 0
                                cursor_move_sound.play()
                        if event.key in (pygame.K_d,):
                            if pause_confirm_choice != 1:
                                pause_confirm_choice = 1
                                cursor_move_sound.play()
                        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            _play_menu_start_sound()
                            _resolve_pause_confirmation(pause_confirm_choice == 0)
                        if event.key == pygame.K_ESCAPE:
                            _resolve_pause_confirmation(False)
                    else:
                        option_count = len(_get_pause_menu_options())
                        if event.key in (pygame.K_w,):
                            pause_selected_index = (pause_selected_index - 1) % option_count
                            cursor_move_sound.play()
                        if event.key in (pygame.K_s,):
                            pause_selected_index = (pause_selected_index + 1) % option_count
                            cursor_move_sound.play()
                        if event.key in (pygame.K_RETURN, pygame.K_j, pygame.K_SPACE):
                            _play_menu_start_sound()
                            _activate_pause_option()
                    continue
                if _arena_scripted_input_locked(arena_ctx) and not getattr(arena_ctx, "cutscene_active", False):
                    continue
                if arena_ctx and getattr(arena_ctx, "cutscene_active", False):
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_j, pygame.K_k, pygame.K_x) and _cutscene_line_fully_revealed(arena_ctx):
                        _advance_arena_cutscene(arena_ctx, source="keyboard")
                    continue
                if event.key == pygame.K_8:
                    arena_perf_overlay_enabled = not arena_perf_overlay_enabled
                    continue
                if arena_stage_start_active:
                    continue
                if event.key in (pygame.K_a,):
                    arena_key_movement[0] = True
                if event.key in (pygame.K_d,):
                    arena_key_movement[1] = True
                if event.key == pygame.K_SPACE:
                    arena_player.set_jump_hold(True)
                    arena_player.jump(input_dir=_current_arena_input_dir())
                if event.key == pygame.K_j:
                    arena_player.attack(input_dir=_current_arena_input_dir())
                if event.key in (pygame.K_k,):
                    arena_player.set_dash_hold(True)
                    arena_player.start_dash(_current_arena_input_dir())
                if event.key == pygame.K_x:
                    arena_player.start_giga_attack()
                if event.key == pygame.K_p:
                    debug_freeze = not debug_freeze
                if event.key == pygame.K_h:
                    arena_debug_hitboxes = not arena_debug_hitboxes
                if event.key == pygame.K_0:
                    if debug_freeze:
                        frame_step = True

        if event.type == pygame.MOUSEBUTTONDOWN and state == "stage_viewer":
            if _arena_scripted_input_locked(arena_ctx) and not getattr(arena_ctx, "cutscene_active", False):
                continue
            if arena_ctx and getattr(arena_ctx, "cutscene_active", False):
                if _cutscene_line_fully_revealed(arena_ctx):
                    _advance_arena_cutscene(arena_ctx, source="mouse")
                continue
            if paused:
                continue
            if arena_stage_start_active:
                continue
            if event.button == MOUSE_ATTACK_BUTTON:
                arena_player.attack(input_dir=_current_arena_input_dir())
            if event.button == MOUSE_GIGA_BUTTON:
                arena_player.start_giga_attack()
            if event.button in MOUSE_DASH_BUTTONS:
                arena_player.set_dash_hold(True)
                arena_player.start_dash(_current_arena_input_dir())

        if event.type == pygame.JOYBUTTONDOWN:

            if state == "arena_result":
                if arena_result_data and arena_result_data.get("step", "banner") == "banner":
                    if event.button in (BTN_A, BTN_B, BTN_X, BTN_Y, BTN_START):
                        _play_menu_start_sound()
                        _confirm_arena_result()
                        continue
                if event.button in (BTN_A, BTN_Y, BTN_START, BTN_X):
                    _play_menu_start_sound()
                    _confirm_arena_result()
                elif event.button == BTN_B:
                    _play_menu_start_sound()
                    _cancel_arena_result()
                continue

            if state == "menu":
                if event.button in (BTN_A, BTN_START) and not menu_confirming:
                    if menu_current_view in {"leaderboards", "options", "credits"}:
                        _play_menu_start_sound()
                        _close_menu_view()
                    else:
                        current_menu_options = _get_menu_options()
                        option = current_menu_options[selected_index]
                        if option == "Game Start":
                            _play_menu_start_sound()
                            _open_menu_view("game_mode")
                        elif option == "Back":
                            _play_menu_start_sound()
                            _close_menu_view()
                        elif option in ("Guided", "Normal"):
                            menu_confirm_guided = option == "Guided"
                            menu_confirming = True
                            menu_confirm_target = "intro_stage"
                            menu_confirm_anim = menu_zero_thumbs_anim.copy() if menu_zero_thumbs_anim else None
                            if menu_confirm_anim:
                                menu_confirm_anim.loop = False
                                menu_confirm_timer = menu_confirm_anim._total
                            else:
                                menu_confirm_timer = 18
                            menu_confirm_sound_played = False
                            menu_confirm_hold_reached = False
                            menu_confirm_fade_alpha = 0
                            menu_confirm_hold_timer = 0.0
                            menu_confirm_black_timer = 0.0
                            menu_confirm_fade_frame = 0
                            menu_confirm_music_stopped = False
                        elif option == "Leaderboard":
                            _play_menu_start_sound()
                            _open_menu_view("leaderboards")
                        elif option == "Options":
                            _play_menu_start_sound()
                            _open_menu_view("options")
                        elif option == "Credits":
                            _play_menu_start_sound()
                            _open_menu_view("credits")
                elif event.button == BTN_B and state == "menu" and not menu_confirming and menu_current_view in {"leaderboards", "options", "credits"}:
                    _play_menu_start_sound()
                    _close_menu_view()

            elif state == "stage_select":
                if stage_select_transition_active or stage_select_return_transition is not None:
                    continue
                if stage_select_confirm_active:
                    if event.button in (BTN_A, BTN_START):
                        _resolve_stage_select_confirmation(stage_select_confirm_choice == 0)
                    elif event.button == BTN_B:
                        _resolve_stage_select_confirmation(False)
                    continue
                if event.button == BTN_START:
                    _activate_stage_select_confirmation()
                    continue
                if event.button in (BTN_A, BTN_Y):
                    if current_selection == "game_icon":
                        _activate_stage_select_confirmation()
                    elif current_selection in stage_music:
                        _begin_stage_intro_transition(current_selection)

            if state == "stage_viewer":
                if event.button == BTN_START:
                    _set_paused(not paused, from_input=True)
                    continue
                if paused:
                    if pause_confirm_active:
                        if event.button in (BTN_A, BTN_START):
                            _play_menu_start_sound()
                            _resolve_pause_confirmation(pause_confirm_choice == 0)
                        elif event.button == BTN_B:
                            _resolve_pause_confirmation(False)
                    else:
                        if event.button == BTN_A:
                            _play_menu_start_sound()
                            _activate_pause_option()
                    continue
                if _arena_scripted_input_locked(arena_ctx) and not getattr(arena_ctx, "cutscene_active", False):
                    continue
                if arena_ctx and getattr(arena_ctx, "cutscene_active", False):
                    if event.button >= 0 and _cutscene_line_fully_revealed(arena_ctx):
                        _advance_arena_cutscene(arena_ctx, source="controller")
                    continue
                if arena_stage_start_active:
                    continue
                if event.button == BTN_B:
                    arena_player.set_jump_hold(True)
                    arena_player.jump(input_dir=_current_arena_input_dir())
                if event.button == BTN_Y:
                    arena_player.attack(input_dir=_current_arena_input_dir())
                if event.button == BTN_A:
                    arena_player.set_dash_hold(True)
                    arena_player.start_dash(_current_arena_input_dir())
                if event.button == BTN_X:
                    arena_player.start_giga_attack()

        if event.type == pygame.JOYBUTTONUP and state == "stage_viewer":
            if _arena_scripted_input_locked(arena_ctx):
                arena_player.set_jump_hold(False)
                arena_player.set_dash_hold(False)
                continue
            if event.button == BTN_B:
                arena_player.set_jump_hold(False)
            if event.button == BTN_A:
                arena_player.set_dash_hold(False)

        if event.type == pygame.MOUSEBUTTONUP and state == "stage_viewer":
            if _arena_scripted_input_locked(arena_ctx):
                arena_player.set_dash_hold(False)
                continue
            if event.button in MOUSE_DASH_BUTTONS:
                arena_player.set_dash_hold(False)

        if event.type == pygame.KEYUP and state == "stage_viewer":
            if _arena_scripted_input_locked(arena_ctx):
                arena_key_movement[0] = False
                arena_key_movement[1] = False
                arena_player.set_jump_hold(False)
                arena_player.set_dash_hold(False)
                continue
            if event.key in (pygame.K_a,):
                arena_key_movement[0] = False
            if event.key in (pygame.K_d,):
                arena_key_movement[1] = False
            if event.key == pygame.K_SPACE:
                arena_player.set_jump_hold(False)
            if event.key in (pygame.K_k,):
                arena_player.set_dash_hold(False)


    if music_intro_playing and not pygame.mixer.music.get_busy() and not (state == "menu" and menu_confirming):
        if music_loop_path:
            pygame.mixer.music.set_volume(_music_volume_for(music_loop_path))
            pygame.mixer.music.load(music_loop_path)
            pygame.mixer.music.play(-1)
        music_intro_playing = False


    # ---- DPAD NAVIGATION ----
    if joystick:
        dpad_cooldown -= dt

        axis_x = joystick.get_axis(AXIS_HORIZONTAL)
        axis_y = -joystick.get_axis(AXIS_VERTICAL)

        if dpad_cooldown <= 0:

            if state == "menu":
                if not menu_confirming:
                    if menu_current_view in {"leaderboards", "options", "credits"}:
                        if axis_y > AXIS_DEADZONE:
                            if _scroll_menu_view(1):
                                cursor_move_sound.play()
                                dpad_cooldown = DPAD_DELAY
                        elif axis_y < -AXIS_DEADZONE:
                            if _scroll_menu_view(-1):
                                cursor_move_sound.play()
                                dpad_cooldown = DPAD_DELAY
                    else:
                        current_menu_options = _get_menu_options()
                        if axis_y > AXIS_DEADZONE:
                            selected_index = (selected_index + 1) % len(current_menu_options)
                            cursor_move_sound.play()
                            dpad_cooldown = DPAD_DELAY
                        elif axis_y < -AXIS_DEADZONE:
                            selected_index = (selected_index - 1) % len(current_menu_options)
                            cursor_move_sound.play()
                            dpad_cooldown = DPAD_DELAY

            elif state == "stage_select" and not stage_select_transition_active and stage_select_return_transition is None:
                if stage_select_confirm_active:
                    if axis_x < -AXIS_DEADZONE:
                        if stage_select_confirm_choice != 0:
                            stage_select_confirm_choice = 0
                            cursor_move_sound.play()
                            dpad_cooldown = DPAD_DELAY
                    elif axis_x > AXIS_DEADZONE:
                        if stage_select_confirm_choice != 1:
                            stage_select_confirm_choice = 1
                            cursor_move_sound.play()
                            dpad_cooldown = DPAD_DELAY
                else:
                    if axis_x > AXIS_DEADZONE:
                        handle_stage_select_move("right")
                        dpad_cooldown = DPAD_DELAY
                    elif axis_x < -AXIS_DEADZONE:
                        handle_stage_select_move("left")
                        dpad_cooldown = DPAD_DELAY
                    elif axis_y > AXIS_DEADZONE:
                        handle_stage_select_move("down")
                        dpad_cooldown = DPAD_DELAY
                    elif axis_y < -AXIS_DEADZONE:
                        handle_stage_select_move("up")
                        dpad_cooldown = DPAD_DELAY
            elif state == "arena_result" and arena_result_data and arena_result_data.get("step") == "save_prompt":
                if axis_x < -AXIS_DEADZONE or axis_y < -AXIS_DEADZONE:
                    if arena_result_data.get("save_choice", 0) != 0:
                        arena_result_data["save_choice"] = 0
                        cursor_move_sound.play()
                        dpad_cooldown = DPAD_DELAY
                elif axis_x > AXIS_DEADZONE or axis_y > AXIS_DEADZONE:
                    if arena_result_data.get("save_choice", 0) != 1:
                        arena_result_data["save_choice"] = 1
                        cursor_move_sound.play()
                        dpad_cooldown = DPAD_DELAY

        if state == "stage_viewer":
            hat_x = joystick.get_hat(0)[0] if joystick.get_numhats() > 0 else 0
            hat_y = joystick.get_hat(0)[1] if joystick.get_numhats() > 0 else 0
            if paused:
                arena_joy_dir = 0
                if dpad_cooldown <= 0:
                    if pause_confirm_active:
                        if hat_x < -AXIS_DEADZONE or axis_x < -AXIS_DEADZONE:
                            if pause_confirm_choice != 0:
                                pause_confirm_choice = 0
                                cursor_move_sound.play()
                                dpad_cooldown = DPAD_DELAY
                        elif hat_x > AXIS_DEADZONE or axis_x > AXIS_DEADZONE:
                            if pause_confirm_choice != 1:
                                pause_confirm_choice = 1
                                cursor_move_sound.play()
                                dpad_cooldown = DPAD_DELAY
                    else:
                        option_count = len(_get_pause_menu_options())
                        if hat_y > AXIS_DEADZONE or axis_y < -AXIS_DEADZONE:
                            pause_selected_index = (pause_selected_index - 1) % option_count
                            cursor_move_sound.play()
                            dpad_cooldown = DPAD_DELAY
                        elif hat_y < -AXIS_DEADZONE or axis_y > AXIS_DEADZONE:
                            pause_selected_index = (pause_selected_index + 1) % option_count
                            cursor_move_sound.play()
                            dpad_cooldown = DPAD_DELAY
            elif _arena_scripted_input_locked(arena_ctx):
                arena_joy_dir = 0
            elif hat_x < -AXIS_DEADZONE or axis_x < -AXIS_DEADZONE:
                arena_joy_dir = -1
            elif hat_x > AXIS_DEADZONE or axis_x > AXIS_DEADZONE:
                arena_joy_dir = 1
            else:
                arena_joy_dir = 0

    if state == "menu" and menu_confirming:
        if menu_confirm_anim and not menu_confirm_hold_reached:
            menu_confirm_anim.update()
            hold_idx = min(MENU_CONFIRM_HOLD_FRAME, len(menu_confirm_anim.images) - 1)
            if menu_confirm_anim.frame_index() >= hold_idx:
                menu_confirm_hold_reached = True
                start_tick = 0 if hold_idx == 0 else menu_confirm_anim._boundaries[hold_idx - 1]
                menu_confirm_anim.frame = start_tick
                menu_confirm_anim.done = False
        elif not menu_confirm_anim:
            menu_confirm_hold_reached = True

        if menu_confirm_hold_reached:
            if not menu_confirm_sound_played:
                try:
                    thumbs_up_sound.play()
                except Exception:
                    pass
                menu_confirm_sound_played = True
            menu_confirm_hold_timer += dt
            if menu_confirm_hold_timer >= MENU_CONFIRM_HOLD_DELAY:
                if not menu_confirm_music_stopped:
                    pygame.mixer.music.stop()
                    music_intro_playing = False
                    music_loop_path = None
                    current_music = None
                    menu_confirm_music_stopped = True
                fade_frames = max(1, int(MENU_CONFIRM_FADE_DURATION * BASE_FPS))
                if menu_confirm_fade_alpha < 255:
                    menu_confirm_fade_frame = min(fade_frames, menu_confirm_fade_frame + 1)
                    menu_confirm_fade_alpha = min(255, (menu_confirm_fade_frame / fade_frames) * 255)
                if menu_confirm_fade_alpha >= 255:
                    menu_confirm_black_timer += dt
                    if menu_confirm_black_timer >= MENU_CONFIRM_BLACK_HOLD and menu_confirm_target:
                        if menu_confirm_target == "stage_select":
                            play_music(stage_select_intro, stage_select_loop)
                            state = menu_confirm_target
                        elif menu_confirm_target == "intro_stage":
                            intro_stage_guided_mode_selected = menu_confirm_guided
                            current_stage = "intro_stage"
                            init_arena_gameplay()
                            intro_path, loop_path = _current_intro_stage_music_pair()
                            play_music(intro_path, loop_path)
                            state = "stage_viewer"
                        else:
                            state = menu_confirm_target
                        menu_confirming = False
                        menu_current_view = None
                        menu_confirm_target = None
                        menu_confirm_anim = None

    if not ui_transition_blocking and state == "stage_select" and stage_select_transition_active:
        fade_frames = max(1, int(STAGE_SELECT_TO_INTRO_FADE_DUR * BASE_FPS))
        if stage_select_transition_alpha < 255:
            stage_select_transition_fade_frame = min(fade_frames, stage_select_transition_fade_frame + 1)
            stage_select_transition_alpha = min(255, (stage_select_transition_fade_frame / fade_frames) * 255)
        if stage_select_transition_alpha >= 255:
            if not stage_select_transition_music_stopped:
                pygame.mixer.music.stop()
                music_intro_playing = False
                music_loop_path = None
                current_music = None
                stage_select_transition_music_stopped = True
            stage_select_transition_black_timer += dt
            if stage_select_transition_black_timer >= STAGE_SELECT_TO_INTRO_BLACK_HOLD and stage_select_transition_stage:
                current_stage = stage_select_transition_stage
                stage_select_transition_active = False
                stage_select_transition_alpha = 0.0
                stage_select_transition_timer = 0.0
                stage_select_transition_fade_frame = 0
                stage_select_transition_black_timer = 0.0
                stage_select_transition_music_stopped = False
                stage_select_transition_stage = None
                start_stage_intro()

    if not ui_transition_blocking and state == "stage_select" and stage_select_return_transition is not None:
        stage_select_return_transition["timer"] += dt
        fade_p = min(1.0, stage_select_return_transition["timer"] / max(0.0001, INTRO_STAGE_BLACK_FADE_DURATION))
        stage_select_return_transition["alpha"] = fade_p * 255.0
        if stage_select_return_transition["timer"] >= INTRO_STAGE_BLACK_FADE_DURATION + INTRO_STAGE_BLACK_HOLD:
            stage_select_return_transition = None
            _return_to_title_screen()

    if not ui_transition_blocking and state == "stage_viewer":
        arena_movement[0] = arena_key_movement[0] or (arena_joy_dir < 0)
        arena_movement[1] = arena_key_movement[1] or (arena_joy_dir > 0)

    if not ui_transition_blocking and state == "stage_intro":
        update_stage_intro()

    pause_target = 1.0 if (state == "stage_viewer" and paused) else 0.0
    pause_slide += (pause_target - pause_slide) * PAUSE_MENU_SLIDE_SPEED
    if abs(pause_target - pause_slide) < 0.001:
        pause_slide = pause_target
    if not ui_transition_blocking and state == "stage_viewer" and paused and pause_zero_face_anim:
        pause_zero_face_anim.update()

    if not ui_transition_blocking and state == "stage_viewer" and (arena_player is None or arena_tilemap is None):
        init_arena_gameplay()

    if not ui_transition_blocking and state == "stage_viewer" and arena_player and arena_tilemap:
        do_step = (not paused and not debug_freeze) or frame_step
        if do_step:
            if current_stage == "intro_stage" and intro_stage_black_transition is not None:
                intro_stage_black_transition["timer"] += dt
                fade_p = min(1.0, intro_stage_black_transition["timer"] / max(0.0001, INTRO_STAGE_BLACK_FADE_DURATION))
                intro_stage_black_transition["alpha"] = fade_p * 255.0
                if intro_stage_black_transition["timer"] >= INTRO_STAGE_BLACK_FADE_DURATION + INTRO_STAGE_BLACK_HOLD:
                    action = intro_stage_black_transition.get("action")
                    intro_stage_black_transition = None
                    if action == "respawn":
                        _restart_current_stage()
                    else:
                        _complete_intro_stage_to_stage_select()
                if frame_step:
                    frame_step = False
                continue
            intro_opening_active = bool(arena_ctx and getattr(arena_ctx, "intro_opening_active", False))
            intro_vile_active = bool(arena_ctx and getattr(arena_ctx, "intro_vile_sequence_active", False))
            intro_vile_scripted = bool(intro_vile_active and not _intro_vile_player_control_enabled(arena_ctx))
            if arena_ctx and not arena_stage_start_active and not intro_opening_active:
                arena_ctx.elapsed_time = getattr(arena_ctx, "elapsed_time", 0.0) + dt
                _sync_dynamic_arena_enemy_population()
            if intro_opening_active:
                _update_intro_stage_opening(arena_ctx, arena_player, dt)
            elif intro_vile_scripted:
                _update_intro_vile_sequence(arena_ctx, arena_player, dt)
            elif arena_ctx and getattr(arena_ctx, "cutscene_active", False):
                _update_arena_cutscene(arena_ctx, dt)
            elif arena_stage_start_active:
                arena_player.update(arena_tilemap, (0, 0))
                if arena_stage_ready_anim:
                    arena_stage_ready_anim.update()
                ready_done = arena_stage_ready_anim is None or arena_stage_ready_anim.done
                if ready_done and arena_player.spawn_timer > 0:
                    arena_player.finish_spawn_sequence()
                if ready_done and arena_player.spawn_timer <= 0:
                    arena_stage_start_active = False
            elif arena_player.pickup_refill_active():
                arena_player.update_pickup_refill()
            elif arena_ctx and getattr(arena_ctx, "intro_post_cutscene_hold", 0.0) > 0.0:
                arena_ctx.intro_post_cutscene_hold = max(0.0, arena_ctx.intro_post_cutscene_hold - dt)
                arena_player.velocity = [0, 0]
                arena_player.hspeed = 0
                arena_player.air_hspeed = 0
            else:
                if arena_ctx:
                    arena_ctx.performance_frame = int(getattr(arena_ctx, "performance_frame", 0)) + 1
                if current_stage == "intro_stage":
                    _maybe_trigger_intro_guidance(arena_ctx, arena_player)
                    _maybe_trigger_intro_command_room_swarm(arena_ctx, arena_player)
                    _update_intro_pending_swarm_spawns(arena_ctx)
                arena_player.update(arena_tilemap, ((arena_movement[1] - arena_movement[0]) * 1.4, 0))
                if current_stage == "intro_stage":
                    _maybe_update_intro_stage_checkpoint(arena_ctx, arena_player)
                sword_hitboxes = arena_player.get_sword_hitboxes()
                if arena_copters:
                    active_view_rect = _get_arena_view_rect()
                    perf_active_enemies = 0
                    perf_throttled_enemies = 0
                    perf_dormant_enemies = 0
                    alive_copters = []
                    for enemy in arena_copters:
                        enemy_rect = enemy.rect()
                        if not arena_player.giga_active:
                            update_divisor = _arena_enemy_update_divisor(enemy, active_view_rect)
                            if update_divisor <= 0:
                                _tick_dormant_enemy(enemy)
                                perf_dormant_enemies += 1
                                alive_copters.append(enemy)
                                continue
                            if update_divisor > 1 and (getattr(arena_ctx, "performance_frame", 0) % update_divisor) != 0:
                                _tick_dormant_enemy(enemy)
                                perf_throttled_enemies += 1
                                alive_copters.append(enemy)
                                continue
                            perf_active_enemies += 1
                            enemy.update(arena_player, arena_bounds, tilemap=arena_tilemap, projectiles=arena_enemy_projectiles)
                            if getattr(enemy, "expired", False):
                                continue
                            enemy_rect = enemy.rect()
                            if enemy.spawn_delay <= 0 and enemy_rect.colliderect(arena_player.rect()):
                                if arena_player.take_enemy_hit(enemy_rect.centerx):
                                    enemy.on_hit_player(arena_player)
                        destroyed = False
                        if sword_hitboxes and any(hitbox.colliderect(enemy_rect) for hitbox in sword_hitboxes):
                            if enemy.take_sword_hit(arena_player):
                                destroy_enemy(arena_ctx, enemy, enemy_rect)
                                destroyed = True
                        if not destroyed:
                            alive_copters.append(enemy)
                    arena_copters = alive_copters
                    if arena_ctx:
                        arena_ctx.perf_active_enemies = perf_active_enemies
                        arena_ctx.perf_throttled_enemies = perf_throttled_enemies
                        arena_ctx.perf_dormant_enemies = perf_dormant_enemies
                elif arena_ctx:
                    arena_ctx.perf_active_enemies = 0
                    arena_ctx.perf_throttled_enemies = 0
                    arena_ctx.perf_dormant_enemies = 0
                if arena_enemy_projectiles:
                    alive_projectiles = []
                    for projectile in arena_enemy_projectiles:
                        destroyed = not projectile.update(arena_tilemap, player=arena_player)
                        if not destroyed:
                            alive_projectiles.append(projectile)
                    arena_enemy_projectiles = alive_projectiles
                if intro_vile_active and _intro_vile_player_control_enabled(arena_ctx):
                    boss = getattr(arena_ctx, "intro_vile_boss", None)
                    if boss is not None and not getattr(boss, "expired", False):
                        boss.update(arena_player, arena_bounds, tilemap=arena_tilemap)
                        boss_rect = boss.rect()
                        if sword_hitboxes and any(hitbox.colliderect(boss_rect) for hitbox in sword_hitboxes):
                            boss.take_sword_hit(arena_player)
                    if arena_player.health <= 1:
                        _begin_intro_vile_rescue(arena_ctx, arena_player)
                if arena_ctx and getattr(arena_ctx, "giga_beams", None):
                    max_y = arena_render_scroll[1] + ARENA_H + 200
                    alive_beams = []
                    for beam in arena_ctx.giga_beams:
                        if beam.update(max_y):
                            alive_beams.append(beam)
                    arena_ctx.giga_beams = alive_beams
                if arena_ctx:
                    if arena_player and arena_player.giga_active:
                        bg = getattr(arena_ctx, "assets", {}).get("giga_attack_background")
                        if bg is not None and bg.get_height() > 0:
                            next_scroll = getattr(arena_ctx, "giga_background_scroll", 0.0) + (dt * ARENA_GIGA_BACKGROUND_SCROLL_SPEED)
                            arena_ctx.giga_background_scroll = next_scroll % bg.get_height()
                    else:
                        arena_ctx.giga_background_scroll = 0.0
                if arena_copters and arena_player and arena_player.giga_active and arena_ctx and getattr(arena_ctx, "giga_beams", None):
                    giga_view_rect = _get_arena_view_rect().inflate(ARENA_RENDER_CULL_MARGIN * 2, ARENA_RENDER_CULL_MARGIN * 2)
                    beam_hitboxes = [
                        beam.hitbox_rect(
                            width_factor=arena_player.giga_beam_hitbox_width_factor,
                            height_factor=arena_player.giga_beam_hitbox_height_factor,
                        )
                        for beam in arena_ctx.giga_beams
                        if _arena_render_visible(beam.rect(), arena_render_scroll, margin=ARENA_RENDER_CULL_MARGIN)
                    ]
                    if beam_hitboxes:
                        beam_union = beam_hitboxes[0].copy()
                        for hitbox in beam_hitboxes[1:]:
                            beam_union.union_ip(hitbox)
                        surviving_copters = []
                        for enemy in arena_copters:
                            enemy_rect = enemy.rect()
                            destroyed = False
                            if (
                                enemy.spawn_delay <= 0
                                and enemy_rect.colliderect(giga_view_rect)
                                and enemy_rect.colliderect(beam_union)
                                and any(hitbox.colliderect(enemy_rect) for hitbox in beam_hitboxes)
                            ):
                                giga_hit = getattr(enemy, "take_giga_hit", None)
                                destroyed = giga_hit() if callable(giga_hit) else True
                                if destroyed:
                                    destroy_enemy(arena_ctx, enemy, enemy_rect)
                            if not destroyed:
                                surviving_copters.append(enemy)
                        arena_copters = surviving_copters
                _update_pending_enemy_respawns()
                if arena_ctx and getattr(arena_ctx, "effects", None):
                    alive_effects = []
                    for eff in arena_ctx.effects:
                        if eff.update():
                            alive_effects.append(eff)
                    arena_ctx.effects = alive_effects
                if arena_ctx and getattr(arena_ctx, "pickups", None):
                    alive_pickups = []
                    for pickup in arena_ctx.pickups:
                        if pickup.update(arena_tilemap, arena_player):
                            alive_pickups.append(pickup)
                    arena_ctx.pickups = alive_pickups
                if (
                    current_stage == "intro_stage"
                    and arena_ctx
                    and not getattr(arena_ctx, "secret_foxy_triggered", False)
                    and getattr(arena_tilemap, "secret_roof_floor", None) is not None
                    and getattr(arena_tilemap, "secret_roof_wall", None) is not None
                ):
                    secret_floor = arena_tilemap.secret_roof_floor
                    secret_wall = arena_tilemap.secret_roof_wall
                    player_rect = arena_player.rect()
                    at_secret_roof_height = (
                        player_rect.bottom >= secret_floor.top - 12
                        and player_rect.bottom <= secret_floor.bottom + 20
                    )
                    inside_secret_wall_trigger = pygame.Rect(
                        secret_wall.left - 10,
                        secret_floor.top - 32,
                        secret_wall.width + 28,
                        max(48, secret_wall.bottom - secret_floor.top + 32),
                    )
                    on_secret_roof_run = (
                        player_rect.centerx >= secret_floor.left - 8
                        and player_rect.centerx <= secret_wall.right + 20
                    )
                    if (
                        at_secret_roof_height
                        and on_secret_roof_run
                        and player_rect.colliderect(inside_secret_wall_trigger)
                    ):
                        _trigger_secret_foxy(arena_ctx)
                if arena_ctx:
                    _update_secret_foxy(arena_ctx, dt)
                if (
                    current_stage == "intro_stage"
                    and arena_ctx
                    and not getattr(arena_ctx, "intro_vile_triggered", False)
                    and getattr(arena_tilemap, "_camera_mode", "") == "z5_upper"
                    and getattr(arena_tilemap, "second_shaft_top_floor", None) is not None
                ):
                    balcony_floor = arena_tilemap.second_shaft_top_floor
                    trigger_x = balcony_floor.left + INTRO_VILE_BALCONY_TRIGGER_OFFSET
                    if arena_player.rect().centerx >= trigger_x:
                        _start_intro_vile_sequence(arena_ctx, arena_player)
            if intro_opening_active and arena_ctx:
                arena_render_scroll = tuple(getattr(arena_ctx, "intro_opening_scroll", arena_render_scroll))
                arena_ctx.render_scroll = arena_render_scroll
            elif arena_player and arena_bounds:
                ox, oy, w, h = arena_bounds
                cam_cx, cam_cy = arena_player.camera_center()
                target_x = cam_cx - ARENA_W / 2
                target_y = cam_cy - ARENA_H / 2
                min_x = ox
                max_x = ox + w - ARENA_W
                min_y = oy
                max_y = oy + h - ARENA_H
                if max_x < min_x:
                    target_x = ox + (w / 2) - (ARENA_W / 2)
                    max_x = min_x = target_x
                if max_y < min_y:
                    target_y = oy + (h / 2) - (ARENA_H / 2)
                    max_y = min_y = target_y
                camera_lock = None
                if arena_tilemap and hasattr(arena_tilemap, "get_camera_lock"):
                    try:
                        camera_lock = arena_tilemap.get_camera_lock(arena_player.rect(), ARENA_W, ARENA_H, arena_bounds)
                    except Exception:
                        camera_lock = None
                if camera_lock:
                    if "scroll_x" in camera_lock:
                        target_x = camera_lock["scroll_x"]
                    if "scroll_y" in camera_lock:
                        target_y = camera_lock["scroll_y"]
                if arena_ctx and getattr(arena_ctx, "intro_locked_camera_scroll", None) is not None:
                    target_x, target_y = arena_ctx.intro_locked_camera_scroll
                if arena_ctx and getattr(arena_ctx, "intro_post_camera_min_x", None) is not None:
                    target_x = max(target_x, arena_ctx.intro_post_camera_min_x)
                # Add a tiny deadzone at clamp boundaries to avoid 1-frame pops
                # when transitioning from clamped to free camera movement.
                if target_x <= min_x + 1:
                    scroll_x = min_x
                elif target_x >= max_x - 1:
                    scroll_x = max_x
                else:
                    scroll_x = target_x
                clamped_target_y = max(min_y, min(target_y, max_y))
                if (
                    current_stage == "intro_stage"
                    and camera_lock
                    and camera_lock.get("mode") in {"z3_to_z4"}
                ):
                    prev_scroll_y = arena_render_scroll[1] if arena_render_scroll else clamped_target_y
                    smooth_factor = 0.18
                    scroll_y = prev_scroll_y + ((clamped_target_y - prev_scroll_y) * smooth_factor)
                    if abs(scroll_y - clamped_target_y) < 0.5:
                        scroll_y = clamped_target_y
                else:
                    scroll_y = clamped_target_y
                arena_render_scroll = (scroll_x, scroll_y)
                if arena_ctx:
                    arena_ctx.render_scroll = arena_render_scroll
                    if current_stage == "intro_stage" and arena_player and arena_tilemap:
                        try:
                            shaft_rect = arena_tilemap.get_shaft_zone() if hasattr(arena_tilemap, "get_shaft_zone") else None
                            pit_trigger_y = arena_tilemap.get_shaft_pit_trigger_y() if hasattr(arena_tilemap, "get_shaft_pit_trigger_y") else None
                        except Exception:
                            shaft_rect = None
                            pit_trigger_y = None
                        if shaft_rect and pit_trigger_y is not None:
                            in_shaft_x = (
                                arena_player.rect().centerx >= shaft_rect.left - 24
                                and arena_player.rect().centerx <= shaft_rect.right + 24
                            )
                            below_pit = arena_player.rect().top >= pit_trigger_y
                            below_screen = arena_player.rect().top >= (arena_render_scroll[1] + ARENA_H)
                            if in_shaft_x and below_pit:
                                # Keep the shaft camera stable while falling into
                                # the pit and only kill Zero if he remains below
                                # the visible screen long enough.
                                arena_render_scroll = (arena_render_scroll[0], min(arena_render_scroll[1], pit_trigger_y - ARENA_H + 120))
                                arena_ctx.render_scroll = arena_render_scroll
                                if below_screen and not arena_player.dead:
                                    arena_ctx.intro_shaft_offscreen_timer += 1
                                    if arena_ctx.intro_shaft_offscreen_timer >= 90:
                                        arena_player.dead = True
                                        arena_player.death_timer = arena_player.death_time
                                        try:
                                            death_sound = getattr(arena_ctx, "sfx_death", None)
                                            if death_sound:
                                                death_sound.play()
                                        except Exception:
                                            pass
                                else:
                                    arena_ctx.intro_shaft_offscreen_timer = 0
                            else:
                                arena_ctx.intro_shaft_offscreen_timer = 0
            if arena_player and arena_player.dead and arena_player.death_timer <= 0:
                if current_stage == "intro_stage":
                    if intro_stage_black_transition is None:
                        _begin_intro_stage_black_transition("respawn")
                else:
                    _begin_arena_result("failed", destination="stage_select")
        if frame_step:
            frame_step = False


    update_perf_end = time.perf_counter()
    _record_perf_metric("update_ms", update_perf_end - frame_perf_start)

    # ---- DRAW ----
    draw_perf_start = time.perf_counter()
    if state == "capcom_intro":
        draw_intro(dt)

    elif state == "menu":
        draw_menu()

    elif state == "stage_select":
        draw_stage_select()

        # Marker animation
        marker_timer += dt
        if marker_timer >= MARKER_SPEED:
            marker_timer = 0
            marker_frame_index = (marker_frame_index + 1) % len(map_marker_frames)

        marker_pos = stage_slots[current_selection]["map_marker_pos"]
        if marker_pos and map_marker_frames:
            raw_marker = map_marker_frames[marker_frame_index]
            current_frame = pygame.transform.scale(
                raw_marker,
                (
                    int(raw_marker.get_width() * MARKER_SCALE),
                    int(raw_marker.get_height() * MARKER_SCALE)
                )
            )
            marker_rect = current_frame.get_rect()
            marker_rect.center = marker_pos
            game_surface.blit(current_frame, marker_rect)

        # Cursor animation
        cursor_timer += dt
        if cursor_timer >= CURSOR_SPEED:
            cursor_timer = 0
            cursor_index = (cursor_index + 1) % len(cursor_frames)

        if cursor_frames:
            raw_cursor = cursor_frames[cursor_index]
            current_cursor = pygame.transform.scale(
                raw_cursor,
                (
                    int(raw_cursor.get_width() * CURSOR_SCALE),
                    int(raw_cursor.get_height() * CURSOR_SCALE)
                )
            )
            cursor_rect = current_cursor.get_rect()
            cursor_rect.center = stage_slots[current_selection]["center"]
            game_surface.blit(current_cursor, cursor_rect)

        if stage_select_transition_alpha > 0:
            fade_surface = pygame.Surface((WIDTH, HEIGHT))
            fade_surface.fill((0, 0, 0))
            fade_surface.set_alpha(int(stage_select_transition_alpha))
            game_surface.blit(fade_surface, (0, 0))
        if stage_select_return_transition is not None:
            fade_surface = pygame.Surface((WIDTH, HEIGHT))
            fade_surface.fill((0, 0, 0))
            fade_surface.set_alpha(int(max(0, min(255, round(stage_select_return_transition.get("alpha", 0.0))))))
            game_surface.blit(fade_surface, (0, 0))

    elif state == "stage_intro":
        draw_stage_intro()

    elif state == "stage_viewer":
        draw_stage_viewer()
        if arena_tilemap and arena_player and arena_surface:
            arena_surface.fill((0, 0, 0, 0))
            render_scroll = arena_render_scroll
            arena_tilemap.render(arena_surface, offset=render_scroll)
            giga_bg_active = _should_draw_giga_background(
                arena_ctx,
                arena_player,
                render_scroll,
                (ARENA_W, ARENA_H),
            )
            if giga_bg_active:
                if hasattr(arena_tilemap, "render_foreground"):
                    arena_tilemap.render_foreground(arena_surface, offset=render_scroll)
                _draw_giga_attack_background(arena_surface, arena_ctx)
            if arena_ctx and getattr(arena_ctx, "effects", None):
                for eff in arena_ctx.effects:
                    if eff.layer < 0:
                        eff.render(arena_surface, offset=render_scroll)
            if arena_ctx and getattr(arena_ctx, "pickups", None):
                for pickup in arena_ctx.pickups:
                    pickup.render(arena_surface, offset=render_scroll)
            if current_stage == "intro_stage":
                _draw_intro_stage_placement_overlay(arena_surface, arena_ctx, render_scroll)
            if arena_copters and not arena_stage_start_active:
                for enemy in arena_copters:
                    if not _arena_render_visible(enemy.rect(), render_scroll, margin=ARENA_RENDER_CULL_MARGIN):
                        continue
                    if arena_debug_hitboxes:
                        enemy.render_debug(arena_surface, offset=render_scroll)
                    else:
                        enemy.render(arena_surface, offset=render_scroll)
            intro_vile_boss = getattr(arena_ctx, "intro_vile_boss", None) if arena_ctx else None
            if arena_ctx and _intro_vile_use_held_zero_overlay(arena_ctx):
                _draw_intro_vile_held_zero(arena_surface, arena_ctx, render_scroll)
            if intro_vile_boss is not None and not getattr(intro_vile_boss, "expired", False):
                if arena_debug_hitboxes:
                    intro_vile_boss.render_debug(arena_surface, offset=render_scroll)
                else:
                    intro_vile_boss.render(arena_surface, offset=render_scroll)
            if arena_enemy_projectiles and not arena_stage_start_active and not (arena_ctx and getattr(arena_ctx, "intro_opening_active", False)):
                for projectile in arena_enemy_projectiles:
                    if not _arena_render_visible(projectile.rect(), render_scroll, margin=ARENA_RENDER_CULL_MARGIN):
                        continue
                    projectile.render(arena_surface, offset=render_scroll)
            if arena_ctx and getattr(arena_ctx, "intro_opening_active", False):
                _draw_intro_stage_opening(arena_surface, arena_ctx, render_scroll, arena_player)
            else:
                hide_player_for_vile_grab = bool(arena_ctx and _intro_vile_hide_player_sprite(arena_ctx))
                if not hide_player_for_vile_grab:
                    if arena_debug_hitboxes:
                        arena_player.render_debug(arena_surface, offset=render_scroll)
                    else:
                        arena_player.render(arena_surface, offset=render_scroll)
                if arena_ctx and getattr(arena_ctx, "intro_vile_shot", None):
                    _draw_intro_vile_shot(arena_surface, arena_ctx, render_scroll)
                if arena_ctx and getattr(arena_ctx, "intro_vile_explosion", None):
                    _draw_intro_vile_explosion(arena_surface, arena_ctx, render_scroll)
                if arena_ctx and getattr(arena_ctx, "intro_vile_arm_effect", None):
                    _draw_intro_vile_arm_effect(arena_surface, arena_ctx, render_scroll)
                if arena_ctx and getattr(arena_ctx, "intro_vile_x_actor", None):
                    _draw_intro_vile_x_actor(arena_surface, arena_ctx, render_scroll)
                if arena_ctx:
                    _draw_intro_vile_zero_end(arena_surface, arena_ctx, render_scroll)
            if arena_ctx and getattr(arena_ctx, "effects", None):
                for eff in arena_ctx.effects:
                    eff_rect = getattr(eff, "rect", None)
                    if callable(eff_rect):
                        try:
                            if not _arena_render_visible(eff_rect(), render_scroll, margin=ARENA_RENDER_CULL_MARGIN):
                                continue
                        except Exception:
                            pass
                    if eff.layer >= 0:
                        eff.render(arena_surface, offset=render_scroll)
            if hasattr(arena_tilemap, "render_foreground") and not giga_bg_active:
                arena_tilemap.render_foreground(arena_surface, offset=render_scroll)
            if arena_ctx and getattr(arena_ctx, "giga_beams", None):
                for beam in arena_ctx.giga_beams:
                    if not _arena_render_visible(beam.rect(), render_scroll, margin=ARENA_RENDER_CULL_MARGIN):
                        continue
                    beam.render(arena_surface, offset=render_scroll)
                if arena_debug_hitboxes and arena_player:
                    for beam in arena_ctx.giga_beams:
                        r = beam.hitbox_rect(
                            width_factor=arena_player.giga_beam_hitbox_width_factor,
                            height_factor=arena_player.giga_beam_hitbox_height_factor
                        )
                        pygame.draw.rect(
                            arena_surface,
                            (255, 255, 0),
                            (r.x - render_scroll[0], r.y - render_scroll[1],
                             r.w, r.h),
                            1
                        )

            arena_scale = max(WIDTH / ARENA_W, HEIGHT / ARENA_H)
            # Use integer scale for arena to avoid shimmer during camera movement.
            arena_scale = int(round(min(WIDTH / ARENA_W, HEIGHT / ARENA_H))) or 1
            arena_scaled_w = int(ARENA_W * arena_scale)
            arena_scaled_h = int(ARENA_H * arena_scale)
            arena_scaled = pygame.transform.scale(arena_surface, (arena_scaled_w, arena_scaled_h))
            arena_x = (WIDTH - arena_scaled_w) // 2
            arena_y = (HEIGHT - arena_scaled_h) // 2
            game_surface.blit(arena_scaled, (arena_x, arena_y))
            if arena_stage_start_active:
                _draw_arena_stage_ready(arena_x, arena_y, arena_scale, render_scroll)
            if arena_ctx and getattr(arena_ctx, "secret_foxy_active", False):
                _draw_secret_foxy_overlay(game_surface, arena_ctx)
            if arena_ctx and getattr(arena_ctx, "cutscene_active", False):
                _draw_arena_cutscene(game_surface, arena_ctx)
            if arena_ctx and getattr(arena_ctx, "intro_vile_fade_alpha", 0.0) > 0.0:
                fade_surface = pygame.Surface((WIDTH, HEIGHT))
                fade_surface.fill((0, 0, 0))
                fade_surface.set_alpha(int(max(0, min(255, round(arena_ctx.intro_vile_fade_alpha)))))
                game_surface.blit(fade_surface, (0, 0))
            if current_stage == "intro_stage" and intro_stage_black_transition is not None:
                fade_surface = pygame.Surface((WIDTH, HEIGHT))
                fade_surface.fill((0, 0, 0))
                fade_surface.set_alpha(int(max(0, min(255, round(intro_stage_black_transition.get("alpha", 0.0))))))
                game_surface.blit(fade_surface, (0, 0))
            if paused or pause_slide > 0.001:
                draw_pause_menu()

    elif state == "arena_result":
        draw_arena_result()


    # ---- SCALE TO WINDOW ----
    window_w, window_h = screen.get_size()
    scale = min(window_w / WIDTH, window_h / HEIGHT)
    if PIXEL_PERFECT_SCALE and scale >= 1:
        scale = int(scale)
    scaled_w = int(WIDTH * scale)
    scaled_h = int(HEIGHT * scale)

    scaled_surface = pygame.transform.scale(game_surface, (scaled_w, scaled_h))

    x_offset = (window_w - scaled_w) // 2
    y_offset = (window_h - scaled_h) // 2

    screen.fill((0, 0, 0))
    screen.blit(scaled_surface, (x_offset, y_offset))

    if state == "stage_viewer" and (paused or pause_slide > 0.001):
        draw_pause_menu_overlay(screen, x_offset, y_offset, scale)

    if (
        state == "stage_viewer"
        and ui_major_transition is None
        and arena_ctx
        and arena_player
        and arena_tilemap
        and pause_slide <= 0.001
        and not getattr(arena_ctx, "intro_opening_active", False)
        and not getattr(arena_ctx, "cutscene_active", False)
    ):
        viewport_rect = pygame.Rect(
            x_offset,
            y_offset,
            scaled_w,
            scaled_h,
        )
        arena_screen_rect = pygame.Rect(
            x_offset + int(round(arena_x * scale)),
            y_offset + int(round(arena_y * scale)),
            int(round(arena_scaled_w * scale)),
            int(round(arena_scaled_h * scale)),
        )
        _draw_status_bars(
            screen,
            arena_ctx,
            arena_player,
            arena_tilemap,
            arena_bounds,
            arena_render_scroll,
            arena_screen_rect,
            viewport_rect,
            arena_scale,
            scale,
        )
        if current_stage != "intro_stage":
            _draw_minimap(
                screen,
                arena_ctx,
                arena_player,
                arena_tilemap,
                arena_bounds,
                arena_render_scroll,
                arena_screen_rect,
                viewport_rect,
            )
        _draw_perf_overlay(screen, arena_ctx)

    elif state == "stage_intro":
        _draw_perf_overlay(screen, arena_ctx)

    if ui_major_transition is not None:
        transition_overlay = pygame.Surface((window_w, window_h))
        transition_overlay.fill((0, 0, 0))
        transition_overlay.set_alpha(int(max(0, min(255, round(ui_major_transition.get("alpha", 0.0))))))
        screen.blit(transition_overlay, (0, 0))

    pygame.display.flip()
    draw_perf_end = time.perf_counter()
    _record_perf_metric("draw_ms", draw_perf_end - draw_perf_start)
    _record_perf_metric("frame_ms", draw_perf_end - frame_perf_start)
    if state == "stage_intro" and stage_intro_pending_music:
        stage_intro_pending_music = False
        play_music(stage_intro_music_intro, None)
    dt = clock.tick(BASE_FPS) / 1000
    _record_perf_value("fps", clock.get_fps())
    if reset_next_dt:
        dt = 0
        reset_next_dt = False
