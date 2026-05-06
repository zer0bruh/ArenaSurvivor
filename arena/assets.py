import json
import os

import pygame

from .combat_data import ANIM_OFFSETS, OY_GROUND, ensure_sword_hitbox_frames
from .core import Animation

_spritesheet_animation_cache = {}


# ignore finder junk and only yield real png frames
def _iter_png_files(folder_path):
    if not os.path.isdir(folder_path):
        return
    for name in sorted(os.listdir(folder_path)):
        lowered = name.lower()
        if not lowered.endswith('.png'):
            continue
        if name.startswith('._') or name == '.DS_Store':
            continue
        yield name


def parse_tagged_frame_name(key):
    # aseprite tags end up embedded in the frame name, so peel the tag + index back out
    if '#' not in key:
        return None, None

    tag_part = key.split('#', 1)[1].replace('.ase', '').rstrip('.')
    tokens = tag_part.rsplit(' ', 1)
    if len(tokens) == 2:
        frame_token = tokens[1].rstrip('.')
        if frame_token.isdigit():
            return tokens[0].rstrip('.'), int(frame_token)
    return tag_part.rstrip('.'), 0


def load_tagged_spritesheet(base_dir, png_path, json_path):
    # cache the parsed animations once, then hand out copies so callers can mutate safely
    cache_key = (os.path.abspath(base_dir), png_path, json_path)
    cached = _spritesheet_animation_cache.get(cache_key)
    if cached is not None:
        return {tag: anim.copy() for tag, anim in cached.items()}

    sheet = pygame.image.load(os.path.join(base_dir, png_path)).convert_alpha()
    with open(os.path.join(base_dir, json_path)) as f:
        data = json.load(f)

    tag_frames = {}
    for key, fdata in data['frames'].items():
        tag_name, frame_num = parse_tagged_frame_name(key)
        if tag_name is None:
            continue
        rect = fdata['frame']
        dur = fdata.get('duration', 100)
        tag_frames.setdefault(tag_name, []).append((frame_num, rect, dur))

    animations = {}
    for tag_name, frame_list in tag_frames.items():
        frame_list.sort(key=lambda x: x[0])
        images = []
        durations = []
        for _, rect, dur_ms in frame_list:
            cell = sheet.subsurface(pygame.Rect(rect['x'], rect['y'], rect['w'], rect['h']))
            images.append(cell)
            durations.append(max(1, round(dur_ms / (1000 / 60))))
        animations[tag_name] = Animation(images, durations)

    _spritesheet_animation_cache[cache_key] = animations
    return {tag: anim.copy() for tag, anim in animations.items()}


def assets_load_spritesheet(assets_dir, png_path, json_path):
    return load_tagged_spritesheet(assets_dir, png_path, json_path)


def load_tileset_folder(folder_path):
    # return both the image list and a name->index map because different callers want each form
    images = []
    names = []
    if not os.path.isdir(folder_path):
        return images, {}
    for name in _iter_png_files(folder_path):
        try:
            img = pygame.image.load(os.path.join(folder_path, name)).convert_alpha()
        except pygame.error:
            continue
        images.append(img)
        names.append(os.path.splitext(name)[0])
    return images, {n: i for i, n in enumerate(names)}


def build_arena_assets(
    assets_dir,
    stone_folder,
    auto_align_actions=False,
    frame_stabilize=False,
):
    # this is the one-stop build for gameplay art, animation timing, hitboxes, and stage tiles
    zero_anims = assets_load_spritesheet(
        assets_dir,
        'playable_characters/zero/zero_final_spritesheet.png',
        'playable_characters/zero/zero_final_spritesheet.json'
    )
    enemy_anims = {}
    for enemy_sheet in (
        'copter_enemy',
        'met',
        'cannon',
        'heli_rocket',
        'heavy',
        'bird',
        'wheel',
        'spike',
        'vile_ boss',
    ):
        enemy_anims.update(
            assets_load_spritesheet(
                assets_dir,
                f'enemies/{enemy_sheet}.png',
                f'enemies/{enemy_sheet}.json'
            )
        )

    sprint_imgs = zero_anims['zero_sprinting'].images
    # retime the authored sheets into something that feels closer to x4/x5 pacing in-game
    sprint_durs = [3.25] * len(sprint_imgs)
    zero_anims['zero_sprinting'] = Animation(sprint_imgs, sprint_durs, loop=True, loop_from=2)

    jump_imgs = zero_anims['zero_jumping'].images
    zero_anims['zero_jumping'] = Animation(jump_imgs, img_dur=4, loop=True, loop_from=1)

    fall_imgs = zero_anims['zero_falling'].images
    if len(fall_imgs) >= 8:
        zero_anims['zero_falling'] = Animation(fall_imgs[:6], img_dur=4, loop=True, loop_from=2)
        zero_anims['zero_landing'] = Animation(fall_imgs[6:8], img_dur=15, loop=False)
    else:
        zero_anims['zero_falling'] = Animation(fall_imgs[:3], img_dur=4, loop=True, loop_from=1)
        zero_anims['zero_landing'] = Animation(fall_imgs[3:5], img_dur=15, loop=False)
    zero_anims['zero_falling_compact'] = zero_anims['zero_falling'].copy()

    if 'zero_double_jump' in zero_anims:
        double_jump_imgs = zero_anims['zero_double_jump'].images
        zero_anims['zero_double_jump'] = Animation(double_jump_imgs, img_dur=3, loop=False)

    if 'zero_double_jump_slash' in zero_anims:
        double_jump_slash_imgs = zero_anims['zero_double_jump_slash'].images
        zero_anims['zero_double_jump_slash'] = Animation(double_jump_slash_imgs, img_dur=3, loop=False)

    if 'zero_wallkick_jump' in zero_anims:
        wj_imgs = zero_anims['zero_wallkick_jump'].images
        if len(wj_imgs) >= 5:
            zero_anims['zero_wallkick_jump'] = Animation(wj_imgs[0:2], img_dur=4, loop=False)
            zero_anims['zero_wall_land'] = Animation(wj_imgs[2:4], img_dur=6, loop=False)
            zero_anims['zero_wall_slide'] = Animation([wj_imgs[4]], img_dur=10, loop=True)
        elif len(wj_imgs) >= 2:
            zero_anims['zero_wallkick_jump'] = Animation(wj_imgs[0:2], img_dur=4, loop=False)
            zero_anims['zero_wall_land'] = Animation(wj_imgs[-2:-1], img_dur=6, loop=False)
            zero_anims['zero_wall_slide'] = Animation([wj_imgs[-1]], img_dur=10, loop=True)

    if 'zero_dashing' in zero_anims:
        dash_imgs = zero_anims['zero_dashing'].images
        if len(dash_imgs) >= 7:
            dash_durs = [3, 3, 4, 4]
            zero_anims['zero_dashing_startloop'] = Animation(dash_imgs[0:4], dash_durs, loop=True, loop_from=2)
            zero_anims['zero_dashing_restart'] = Animation(dash_imgs[1:4], [3, 4, 4], loop=True, loop_from=1)
            zero_anims['zero_dashing_end_idle'] = Animation(dash_imgs[4:7], img_dur=6, loop=False)
            zero_anims['zero_dashing_wallstop'] = Animation([dash_imgs[2]], img_dur=10, loop=True)
        else:
            zero_anims['zero_dashing_startloop'] = zero_anims['zero_dashing']
            if dash_imgs:
                zero_anims['zero_dashing_wallstop'] = Animation([dash_imgs[-1]], img_dur=10, loop=True)

    idle_imgs = zero_anims['zero_idle'].images
    zero_anims['zero_idle'] = Animation(idle_imgs, img_dur=40, loop=True)

    for key in list(zero_anims.keys()):
        # globally speed up the leftover zero actions that are still on raw export timing
        if key in (
            'zero_idle', 'zero_idle_blinking', 'zero_sprinting',
            'zero_jumping', 'zero_falling', 'zero_falling_compact', 'zero_landing',
            'zero_double_jump', 'zero_double_jump_slash',
            'zero_dashing_startloop', 'zero_dashing_restart',
            'zero_dashing_end_idle',
            'zero_saber_slash1', 'zero_saber_slash2', 'zero_saber_slash3',
            'zero_air_saber_slash', 'zero_wall_saber_slash',
            'zero_spawning', 'zero_giga_attack', 'giga_attack_beam'
        ):
            continue
        anim = zero_anims[key]
        fast_durs = [max(1, d // 2) for d in anim.durations]
        zero_anims[key] = Animation(anim.images, fast_durs, loop=anim.loop, loop_from=anim.loop_from)

    attack_speeds = {
        'zero_saber_slash1': 0.5,
        'zero_saber_slash2': 0.5,
        'zero_saber_slash3': 0.58,
        'zero_air_saber_slash': 0.8,
        'zero_double_jump_slash': 0.8,
        'zero_wall_saber_slash': 0.8,
    }
    for key, mult in attack_speeds.items():
        if key in zero_anims:
            anim = zero_anims[key]
            fast_durs = [max(1, int(d * mult)) for d in anim.durations]
            zero_anims[key] = Animation(anim.images, fast_durs, loop=False)

    if 'zero_saber_slash3' in zero_anims:
        anim = zero_anims['zero_saber_slash3']
        if len(anim.images) >= 2:
            # The authored slash-3 sequence ends with a recovery frame that
            # jumps forward into the sheathe pose. Let the separate sheathe
            # action handle that recovery instead of showing it here.
            zero_anims['zero_saber_slash3'] = Animation(
                list(anim.images[:-1]),
                list(anim.durations[:-1]),
                loop=False,
            )

    if 'zero_giga_attack' in zero_anims:
        # keep the beam charge snappy, then loop the last held frames while the attack is active
        anim = zero_anims['zero_giga_attack']
        giga_durs = [max(1, int(d * 0.95)) for d in anim.durations]
        if len(giga_durs) >= 2:
            giga_durs[-2] = 4
            giga_durs[-1] = 4
        zero_anims['zero_giga_attack'] = Animation(anim.images, giga_durs, loop=True, loop_from=max(0, len(anim.images) - 2))
    if 'giga_attack_beam' in zero_anims:
        anim = zero_anims['giga_attack_beam']
        beam_durs = [max(1, int(d * 0.7)) for d in anim.durations]
        zero_anims['giga_attack_beam'] = Animation(anim.images, beam_durs, loop=True)

    if 'zero_spawning' in zero_anims:
        anim = zero_anims['zero_spawning']
        base_imgs = list(anim.images)
        base_durs = list(anim.durations)
        n = len(base_durs)
        if n > 0:
            new_durs = []
            for i, d in enumerate(base_durs):
                if i == 0:
                    # Let the initial beam frame read clearly before the
                    # materialization sequence continues.
                    nd = max(10, int(d * 1.6))
                elif i == max(0, n - 2):
                    # Hold on the penultimate spawn frame briefly before
                    # the final snap to idle.
                    nd = 120
                elif i == n - 1:
                    nd = max(8, int(d * 1.2))
                else:
                    nd = max(1, int(d * 0.9))
                new_durs.append(max(1, nd))
        else:
            new_durs = base_durs
        zero_anims['zero_spawning'] = Animation(base_imgs, new_durs, loop=False)

    enemy_non_loop_actions = {
        'met_hide',
        'cannon_jump_land',
        'cannon_shoot_1',
        'cannon_shoot_2',
        'cannon_shoot_3',
        'cannon_shoot_4',
        'heli_rocket_reloading',
        'heavy_prepare_attack',
        'heavy_imminent_attack',
        'heavy_attack',
        'spike_attack',
        'vile_punching',
        'vile_disarmed',
    }
    for key in enemy_non_loop_actions:
        if key not in enemy_anims:
            continue
        anim = enemy_anims[key]
        enemy_anims[key] = Animation(anim.images, anim.durations, loop=False)

    if 'zero_saber_sheathe1' not in zero_anims and 'zero_saber_slash1' in zero_anims and zero_anims['zero_saber_slash1'].images:
        img = zero_anims['zero_saber_slash1'].images[0]
        zero_anims['zero_saber_sheathe1'] = Animation([img], img_dur=14, loop=False)

    ensure_sword_hitbox_frames(zero_anims)

    stone_images = None
    stone_map = None
    decor_images = None
    decor_map = None
    if isinstance(stone_folder, str) and stone_folder.startswith('assets:'):
        folder_name = stone_folder.split(':', 1)[1]
        tiles_path = os.path.join(assets_dir, 'tiles', folder_name)
        stone_images, stone_map = load_tileset_folder(tiles_path)
        decor_folder = None
        if folder_name.endswith('_tiles'):
            decor_candidate = folder_name.replace('_tiles', '_decor')
            decor_path = os.path.join(assets_dir, 'tiles', decor_candidate)
            if os.path.isdir(decor_path):
                decor_folder = decor_candidate
        if decor_folder:
            decor_path = os.path.join(assets_dir, 'tiles', decor_folder)
            decor_images, decor_map = load_tileset_folder(decor_path)
    if not stone_images:
        raise FileNotFoundError(f"Missing arena tileset folder for {stone_folder!r} under Assets/tiles")
    if decor_images is None:
        decor_images = []
    giga_background = None
    giga_background_path = os.path.join(assets_dir, 'playable_characters', 'zero', 'giga_attack_background.png')
    if os.path.exists(giga_background_path):
        try:
            giga_background = pygame.image.load(giga_background_path).convert_alpha()
        except pygame.error:
            giga_background = None

    assets = {
        'decor': decor_images,
        'grass': [],
        'large_decor': [],
        'stone': stone_images,
        **enemy_anims,
        **zero_anims,
    }
    if giga_background is not None:
        assets['giga_attack_background'] = giga_background
    if stone_map:
        assets['stone_map'] = stone_map
    if decor_map:
        assets['decor_map'] = decor_map

    anim_offsets = {}
    anim_frame_offsets = {}

    def bbox_anchor(img):
        mask = pygame.mask.from_surface(img)
        rects = mask.get_bounding_rects()
        if not rects:
            return (0.0, 0.0)
        min_x = min(r.x for r in rects)
        max_x = max(r.x + r.w for r in rects)
        max_y = max(r.y + r.h for r in rects)
        return ((min_x + max_x) / 2.0, max_y)

    def anchor_for_action(action, frame_index=0):
        if action not in assets:
            return None
        images = assets[action].images
        if not images:
            return None
        idx = min(frame_index, len(images) - 1)
        return bbox_anchor(images[idx])

    if auto_align_actions and 'zero_dashing_end_idle' in assets and 'zero_idle' in assets:
        a_img = assets['zero_dashing_end_idle'].images[-1]
        t_img = assets['zero_idle'].images[0]
        ax, ay = bbox_anchor(a_img)
        tx, ty = bbox_anchor(t_img)
        dx, dy = tx - ax, ty - ay
        base = ANIM_OFFSETS.get('zero_dashing_end_idle', (-45, -49, -46))
        ox_r, ox_l, oy = base
        anim_offsets['zero_dashing_end_idle'] = (int(ox_r + dx), int(ox_l + dx), int(oy + dy))

    idle_anchor = anchor_for_action('zero_idle', 0)
    jump_anchor = anchor_for_action('zero_jumping', 0) or idle_anchor
    wall_anchor = anchor_for_action('zero_wall_slide', 0) or anchor_for_action('zero_wall_land', 0) or idle_anchor

    def align_action_to_anchor(action, target_anchor):
        if not target_anchor or action not in assets:
            return
        act_anchor = anchor_for_action(action, 0)
        if not act_anchor:
            return
        dx, dy = target_anchor[0] - act_anchor[0], target_anchor[1] - act_anchor[1]
        base = ANIM_OFFSETS.get(action, (-45, -49, OY_GROUND))
        ox_r, ox_l, oy = base
        anim_offsets[action] = (int(ox_r + dx), int(ox_l + dx), int(oy + dy))

    if auto_align_actions:
        for key in ('zero_saber_slash1', 'zero_saber_slash2', 'zero_saber_slash3'):
            align_action_to_anchor(key, idle_anchor)
    else:
        align_action_to_anchor('zero_saber_slash3', idle_anchor)
    if auto_align_actions:
        align_action_to_anchor('zero_air_saber_slash', jump_anchor)
        align_action_to_anchor('zero_double_jump', jump_anchor)
        align_action_to_anchor('zero_double_jump_slash', jump_anchor)
        align_action_to_anchor('zero_wall_saber_slash', wall_anchor)
        if 'zero_air_saber_slash' in anim_offsets:
            ox_r, ox_l, oy = anim_offsets['zero_air_saber_slash']
            anim_offsets['zero_air_saber_slash'] = (ox_l, ox_l, oy)

    def compute_frame_offsets(action, use_x=False, use_y=True):
        if action not in assets:
            return
        images = assets[action].images
        if not images:
            return
        max_ys = []
        centers_x = []
        per_frame = []

        def foot_line(img):
            w, h = img.get_size()
            x0 = int(w * 0.35)
            x1 = int(w * 0.65)
            for yy in range(h - 1, -1, -1):
                for xx in range(x0, x1):
                    if img.get_at((xx, yy)).a > 0:
                        return yy + 1
            return None

        for img in images:
            mask = pygame.mask.from_surface(img)
            rects = mask.get_bounding_rects()
            if not rects:
                per_frame.append((0, 0, False))
                continue
            min_x = min(r.x for r in rects)
            max_x = max(r.x + r.w for r in rects)
            max_y = max(r.y + r.h for r in rects)
            foot_y = foot_line(img)
            centers_x.append((min_x + max_x) / 2.0)
            max_ys.append(foot_y if foot_y is not None else max_y)
            per_frame.append(((min_x + max_x) / 2.0, foot_y if foot_y is not None else max_y, True))
        if not max_ys:
            return
        target_y = sorted(max_ys)[len(max_ys) // 2]
        target_x = sorted(centers_x)[len(centers_x) // 2] if centers_x else 0
        offsets = []
        for cx, max_y, ok in per_frame:
            if not ok:
                offsets.append((0, 0))
                continue
            dx = int(round(target_x - cx)) if use_x else 0
            dy = int(round(target_y - max_y)) if use_y else 0
            offsets.append((dx, dy))
        anim_frame_offsets[action] = offsets

    if frame_stabilize:
        for action in (
            'zero_jumping', 'zero_falling', 'zero_falling_compact', 'zero_double_jump',
            'zero_wall_slide', 'zero_wall_land',
            'zero_air_saber_slash', 'zero_double_jump_slash', 'zero_wall_saber_slash',
            'zero_wallkick_jump'
        ):
            compute_frame_offsets(action, use_x=False, use_y=True)

    assets['_anim_frame_offsets'] = anim_frame_offsets
    return assets, anim_offsets


def get_stage_stone_folder(stage_key, assets_dir):
    if not stage_key:
        return 'assets:airbase_tiles'
    tiles_path = os.path.join(assets_dir, 'tiles', f'{stage_key}_tiles')
    if os.path.isdir(tiles_path):
        return f'assets:{stage_key}_tiles'
    raise FileNotFoundError(f"Missing stage tiles for {stage_key!r} under Assets/tiles")
