HITBOX_H = 43
DASH_H = 30
# Keep airborne flip/curl actions on the full normal terrain body so they cannot
# physically enter undersides/corners that the standard airborne body would never fit.
COMPACT_AIR_H = HITBOX_H

# raw body sizes for player and enemy actions
HITBOX_SIZES = {
    'zero_idle':             (22, HITBOX_H),
    'zero_idle_blinking':    (22, HITBOX_H),
    'zero_sprinting':        (22, HITBOX_H),
    'zero_spawning':         (22, HITBOX_H),
    'zero_dashing':          (42, DASH_H),
    'zero_dashing_startloop':(42, DASH_H),
    'zero_dashing_restart':  (42, DASH_H),
    'zero_dashing_end_idle': (42, DASH_H),
    'zero_dashing_end_move': (42, DASH_H),
    'zero_dashing_wallstop': (42, DASH_H),
    'zero_jumping':          (22, HITBOX_H),
    'zero_double_jump':      (22, COMPACT_AIR_H),
    'zero_falling':          (22, HITBOX_H),
    'zero_falling_compact':  (22, COMPACT_AIR_H),
    'zero_landing':          (22, HITBOX_H),
    'zero_wallkick_jump':    (22, HITBOX_H),
    'zero_wall_land':        (22, HITBOX_H),
    'zero_wall_slide':       (22, HITBOX_H),
    'zero_hurt':             (22, HITBOX_H),
    'zero_saber_slash1':     (22, HITBOX_H),
    'zero_saber_slash2':     (22, HITBOX_H),
    'zero_saber_slash3':     (22, HITBOX_H),
    'zero_saber_sheathe1':   (22, HITBOX_H),
    'zero_saber_sheathe3':   (22, HITBOX_H),
    'zero_air_saber_slash':  (22, HITBOX_H),
    'zero_double_jump_slash': (22, COMPACT_AIR_H),
    'zero_wall_saber_slash': (22, HITBOX_H),
    'zero_giga_attack':      (22, HITBOX_H),
    'zero_climbing':         (18, HITBOX_H),
    'giga_attack':           (0, HITBOX_H),
    'copter_flying':         (31, 32),
    'copter_after_hit':      (31, 32),
    'met_idle':              (22, 18),
    'met_walking':           (22, 18),
    'met_hide':              (22, 18),
    'cannon_idle':           (26, 26),
    'cannon_jump_land':      (26, 26),
    'cannon_shoot_1':        (26, 26),
    'cannon_shoot_2':        (26, 26),
    'cannon_shoot_3':        (26, 26),
    'cannon_shoot_4':        (26, 26),
    'heli_rocket_idle_moving': (28, 30),
    'heli_rocket_reloading':   (28, 30),
    'heavy_idle':            (34, 40),
    'heavy_prepare_attack':  (34, 40),
    'heavy_imminent_attack': (34, 40),
    'heavy_attack':          (34, 40),
    'bird_flying':           (30, 14),
    'wheel_moving':          (26, 26),
    'spike_idle':            (23, 40),
    'spike_move':            (23, 40),
    'spike_attack':          (23, 40),
    'vile_idle':             (52, 70),
    'vile_laughing':         (52, 70),
    'vile_walking':          (52, 70),
    'vile_punching':         (52, 70),
    'vile_disarmed':         (52, 70),
}

# hand-tuned sword contact boxes per animation frame
SWORD_HITBOXES = {
    'zero_saber_slash1': {
        0: [],
        1: [(25, 68, 20, 14)],
        2: [(38, 68, 58, 15)],
        3: [(40, 77, 10, 5), (50, 48, 24, 34), (74, 53, 12, 28), (86, 58, 12, 20)],
        4: [(40, 77, 10, 5), (50, 48, 24, 34), (74, 53, 12, 28), (86, 58, 12, 20)],
        5: [(50, 52, 31, 10), (50, 47, 16, 6)],
        6: [(50, 47, 16, 6)],
        7: [(50, 47, 16, 6)],
    },
    'zero_saber_slash2': {
        0: [(50, 47, 16, 6)],
        1: [(26, 73, 8, 11), (34, 67, 70, 22), (64, 44, 26, 28), (103, 64, 5, 18), (90, 58, 16, 16), (90, 55, 14, 5), (89, 49, 10, 8)],
        2: [(26, 73, 8, 11), (34, 67, 52, 21), (34, 88, 52, 4), (84, 80, 8, 11)],
        3: [(28, 73, 5, 9), (32, 66, 18, 22)],
        4: [(28, 76, 15, 9), (32, 68, 15, 9)],
        5: [(28, 74, 5, 7), (33, 72, 5, 7), (38, 68, 5, 7), (42, 66, 5, 7)],
    },
    'zero_saber_slash3': {
        0: [(31, 83, 3, 4), (34, 81, 3, 4), (37, 80, 3, 4), (40, 78, 3, 4), (43, 77, 3, 4), (46, 76, 3, 4), (49, 75, 3, 4), (52, 73, 3, 4)],
        1: [(28, 74, 5, 7), (57, 62, 10, 5), (33, 66, 55, 17), (66, 25, 28, 55), (88, 22, 22, 44), (93, 66, 10, 10), (74, 18, 20, 10), (83, 18, 20, 10), (77, 11, 23, 10), (81, 6, 11, 5)],
        2: [(45, 66, 34, 17), (57, 62, 10, 5), (66, 25, 28, 55), (88, 22, 22, 44), (93, 66, 10, 10), (74, 18, 20, 10), (83, 18, 20, 10), (77, 11, 23, 10), (81, 6, 11, 5)],
        3: [(65, 34, 13, 13), (69, 30, 13, 13), (72, 24, 15, 15), (76, 21, 15, 15), (74, 18, 15, 15), (77, 12, 15, 15), (80, 18, 15, 15), (84, 14, 15, 15), (81, 8, 10, 7), (97, 17, 6, 11), (86, 10, 10, 7)],
        4: [(66, 36, 8, 8), (69, 32, 8, 8), (71, 29, 8, 8), (73, 26, 8, 8), (74, 23, 9, 9), (74, 20, 10, 10), (75, 17, 10, 10), (77, 15, 11, 11), (79, 10, 11, 11), (81, 6, 11, 11), (84, 9, 11, 11)],
        5: [(66, 37, 5, 6), (68, 34, 5, 6), (70, 31, 5, 6), (70, 29, 5, 6), (72, 27, 5, 6), (73, 25, 5, 6), (74, 24, 5, 6), (75, 22, 5, 6), (76, 20, 5, 6), (77, 16, 5, 6), (80, 12, 5, 6)],
        6: [(66, 37, 5, 6), (68, 34, 5, 6), (70, 31, 5, 6), (70, 29, 5, 6), (72, 27, 5, 6), (73, 25, 5, 6), (74, 24, 5, 6), (75, 22, 5, 6), (76, 20, 5, 6)],
        7: [(66, 37, 5, 6), (68, 34, 5, 6), (70, 31, 5, 6), (70, 29, 5, 6), (72, 27, 5, 6)],
        8: [],
    },
    'zero_air_saber_slash': {
        0: [(33, 39, 26, 16)],
        1: [(72, 50, 40, 30), (64, 79, 30, 10), (80, 89, 22, 8), (94, 79, 20, 10), (110, 53, 6, 30), (50, 30, 40, 20), (83, 37, 25, 25), (39, 30, 15, 15)],
        2: [(72, 50, 40, 30), (64, 79, 30, 10), (80, 89, 22, 8), (94, 79, 20, 10), (110, 53, 6, 30), (50, 30, 40, 20), (83, 37, 25, 25), (39, 30, 15, 15)],
        3: [(67, 79, 44, 17)],
        4: [(64, 82, 4, 4), (67, 84, 4, 4), (70, 85, 4, 4), (73, 86, 4, 4), (76, 88, 4, 4), (79, 89, 4, 4), (82, 90, 4, 5), (85, 92, 4, 4), (88, 93, 4, 4)],
    },
    'zero_double_jump_slash': {
        0: [],
        1: [],
        2: [(48, 30, 36, 12), (24, 36, 48, 24), (69, 36, 28, 36), (36, 60, 36, 12)],
        3: [(54, 31, 24, 44), (72, 34, 24, 24), (72, 58, 24, 24), (80, 44, 24, 24), (96, 68, 12, 12), (84, 76, 12, 12), (72, 84, 12, 12)],
        4: [(86, 40, 12, 75), (70, 60, 12, 36), (74, 57, 12, 44), (60, 80, 12, 12), (60, 92, 12, 12), (74, 96, 12, 12), (98, 50, 12, 56), (110, 71, 2, 20)],
        5: [(66, 67, 48, 36), (66, 96, 16, 24), (78, 102, 24, 16), (54, 84, 12, 20)],
        6: [(55, 86, 36, 38), (40, 80, 16, 38), (88, 98, 18, 20)],
        7: [(24, 80, 24, 36), (38, 68, 36, 36), (46, 100, 12, 24), (50, 98, 24, 30)],
        8: [(24, 55, 12, 60), (36, 96, 12, 24), (36, 56, 24, 48), (60, 60, 12, 12), (17, 60, 12, 48)],
        9: [(34, 40, 24, 12), (30, 46, 24, 40), (60, 48, 12, 24), (22, 54, 12, 36), (60, 72, 12, 12), (14, 56, 12, 36), (54, 46, 8, 40  )],
    },
    'zero_wall_saber_slash': {
        0: [(51, 54, 23, 33)],
        1: [(46, 41, 28, 46), (51, 35, 6, 6)],
        2: [(18, 51, 56, 46), (12, 70, 6, 20), (12, 64, 6, 20), (22, 94, 25, 10), (30, 45, 22, 10)],
        3: [(19, 80, 51, 22)],
        4: [(40, 83, 35, 20), (35, 96, 7, 7)],
        5: [(42, 86, 30, 11)],
    },
}


def ensure_sword_hitbox_frames(anims):
    # backfill any missing frames so attack lookups can stay simple everywhere else
    for action in SWORD_HITBOXES:
        if action not in anims:
            continue
        frames = len(anims[action].images)
        action_map = SWORD_HITBOXES.setdefault(action, {})
        for i in range(frames):
            action_map.setdefault(i, [])


DASH_OFFSET_R = -8
DASH_OFFSET_L = -16
# dashes use a wider, lower body and need per-facing offsets to stay centered visually
HITBOX_OFFSETS = {
    'zero_dashing':          (DASH_OFFSET_R, DASH_OFFSET_L),
    'zero_dashing_startloop':(DASH_OFFSET_R, DASH_OFFSET_L),
    'zero_dashing_restart':  (DASH_OFFSET_R, DASH_OFFSET_L),
    'zero_dashing_end_idle': (DASH_OFFSET_R, DASH_OFFSET_L),
    'zero_dashing_end_move': (DASH_OFFSET_R, DASH_OFFSET_L),
    'zero_dashing_wallstop': (DASH_OFFSET_R, DASH_OFFSET_L),
}

# some actions borrow another animation's anchor data so the body does not pop around
HITBOX_ALIGN_TO_ANIM = {
    'zero_double_jump': 'zero_jumping',
    'zero_double_jump_slash': {
        0: 'zero_falling',
        1: 'zero_falling',
        2: 'zero_jumping',
        3: 'zero_jumping',
        4: 'zero_jumping',
        5: 'zero_jumping',
        6: 'zero_jumping',
        7: 'zero_jumping',
        8: 'zero_jumping',
        9: 'zero_jumping',
    },
}

OY_GROUND = -46

# sprite draw offsets from the hitbox origin
ANIM_OFFSETS = {
    'zero_idle':             (-55, -54, OY_GROUND),
    'zero_idle_blinking':    (-54, -52, OY_GROUND),
    'zero_sprinting':        (-54, -52, OY_GROUND),
    'zero_spawning':         (-54, -52, OY_GROUND),
    'zero_jumping':          (-54, -52, OY_GROUND),
    'zero_double_jump':      (-52, -52, (OY_GROUND - 12)),
    'zero_falling':          (-54, -52, OY_GROUND),
    'zero_falling_compact':  (-54, -52, OY_GROUND),
    'zero_landing':          (-54, -52, OY_GROUND),
    'zero_wallkick_jump':    (-53, -63, OY_GROUND),
    'zero_wall_land':        (-53, -63, OY_GROUND),
    'zero_wall_slide':       (-53, -53, OY_GROUND),
    'zero_dashing':          (-51, -57, OY_GROUND),
    'zero_dashing_startloop':(-51, -57, OY_GROUND),
    'zero_dashing_end_idle': (-65, -67, OY_GROUND),
    'zero_dashing_end_move': (-69, -67, OY_GROUND),
    'zero_dashing_wallstop': (-51, -57, OY_GROUND),
    'zero_hurt':             (-51, -60, OY_GROUND),
    'zero_saber_slash1':     (-52, -55, OY_GROUND),
    'zero_saber_slash2':     (-52, -51, OY_GROUND),
    'zero_saber_slash3':     (-49, -79, (OY_GROUND - 1)),
    'zero_saber_sheathe1':   (-51, -55, OY_GROUND),
    'zero_saber_sheathe3':   (-51, -55, OY_GROUND),
    'zero_air_saber_slash':  (-50, -56, OY_GROUND),
    'zero_double_jump_slash': (-52, -52, (OY_GROUND - 12)),
    'zero_wall_saber_slash': (-53, -53, OY_GROUND),
    'zero_giga_attack':      (-55, -54, OY_GROUND),
    'zero_climbing':         (-58, -66, OY_GROUND),
    'giga_attack':           (0, 0, OY_GROUND),
    'copter_flying':         (-46, -46, -24),
    'copter_after_hit':      (-46, -46, -24),
}

DEFAULT_ACTION = 'zero_idle'
