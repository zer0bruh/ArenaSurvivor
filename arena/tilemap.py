import random
import re
from collections import defaultdict

import pygame

# offsets used when sampling neighboring tiles for collision and decoration logic
NEIGHBOR_OFFSETS = [
    (-2, -1), (-1, -1), (0, -1), (1, -1), (2, -1),
    (-2,  0), (-1,  0), (0,  0), (1,  0), (2,  0),
    (-2,  1), (-1,  1), (0,  1), (1,  1), (2,  1),
    (-2,  2), (-1,  2), (0,  2), (1,  2), (2,  2),
    (-2,  3), (-1,  3), (0,  3), (1,  3), (2,  3),
]
PHYSICS_TILES = {'grass', 'stone'}
ARENA_TILEMAP_BUCKET = 96


STAGE_LAYOUT_SPANS = {
    # these spans rebuild the arena platforms in code from the stage-select artwork layout
    # Mapped from arena_layout1-6.png in Downloads, in the game's existing
    # stage order: amazon, magma, northern, airbase, seabase, wepcenter.
    'amazon': [
        (6, 10, 4),
        (14, 15, 4),
        (25, 28, 4),
        (31, 36, 6),
        (17, 25, 7),
        (1, 7, 8),
        (14, 16, 8),
        (29, 35, 10),
        (6, 10, 12),
        (16, 23, 14),
        (4, 12, 16),
        (27, 34, 16),
        (16, 23, 19),
        (3, 12, 20),
        (37, 38, 20),
        (15, 20, 24),
        (27, 35, 24),
        (5, 10, 25),
    ],
    'magma': [
        (1, 2, 4),
        (32, 35, 5),
        (6, 8, 6),
        (12, 18, 6),
        (22, 28, 6),
        (1, 3, 8),
        (35, 38, 9),
        (6, 9, 10),
        (17, 22, 11),
        (29, 32, 11),
        (11, 14, 14),
        (25, 27, 14),
        (4, 7, 15),
        (32, 35, 15),
        (19, 20, 16),
        (10, 15, 18),
        (24, 28, 18),
        (16, 23, 19),
        (3, 6, 20),
        (35, 38, 20),
        (5, 10, 24),
        (28, 33, 24),
        (17, 21, 25),
    ],
    'northern': [
        (14, 28, 5),
        (33, 38, 5),
        (3, 9, 7),
        (33, 38, 9),
        (15, 19, 10),
        (1, 3, 11),
        (20, 24, 11),
        (10, 12, 12),
        (25, 29, 12),
        (34, 38, 13),
        (3, 9, 15),
        (17, 23, 15),
        (29, 30, 16),
        (31, 35, 17),
        (6, 11, 19),
        (16, 25, 19),
        (29, 35, 22),
        (6, 12, 24),
        (19, 22, 24),
        (26, 28, 25),
    ],
    'airbase': [
        (5, 10, 4),
        (15, 22, 5),
        (28, 34, 5),
        (1, 9, 8),
        (29, 35, 9),
        (15, 24, 10),
        (1, 5, 13),
        (10, 12, 14),
        (27, 30, 14),
        (18, 22, 15),
        (33, 36, 15),
        (4, 7, 18),
        (13, 15, 18),
        (24, 26, 18),
        (16, 23, 19),
        (32, 35, 19),
        (26, 30, 22),
        (4, 14, 23),
        (19, 22, 24),
        (29, 36, 25),
    ],
    'seabase': [
        (1, 5, 4),
        (31, 38, 4),
        (11, 25, 5),
        (30, 33, 8),
        (1, 8, 9),
        (13, 18, 10),
        (22, 27, 10),
        (35, 38, 11),
        (1, 3, 14),
        (9, 19, 14),
        (25, 30, 15),
        (4, 7, 17),
        (36, 38, 17),
        (16, 23, 19),
        (10, 15, 20),
        (24, 29, 20),
        (1, 5, 21),
        (34, 38, 21),
        (11, 15, 24),
        (1, 6, 25),
        (19, 22, 25),
        (27, 33, 25),
    ],
    'wepcenter': [
        (13, 15, 4),
        (26, 29, 4),
        (1, 3, 5),
        (33, 36, 6),
        (8, 12, 7),
        (17, 24, 7),
        (6, 7, 8),
        (27, 28, 10),
        (32, 36, 10),
        (13, 14, 11),
        (1, 7, 12),
        (11, 12, 12),
        (26, 29, 13),
        (17, 22, 14),
        (33, 38, 14),
        (9, 11, 16),
        (25, 30, 18),
        (1, 2, 19),
        (7, 13, 19),
        (17, 22, 20),
        (34, 36, 20),
        (33, 33, 21),
        (4, 11, 23),
        (25, 27, 23),
        (15, 16, 24),
        (17, 21, 25),
        (30, 35, 25),
    ],
}


class ArenaTilemap:
    def __init__(self, game, tile_size=16):
        # build a tile-driven arena shell plus some hand-authored platform spans for combat
        self.game = game
        self.tile_size = tile_size
        self.tilemap = {}
        self.offgrid_tiles = []
        self.platform_spans = []
        self.collision_rects = []
        self._physics_buckets = defaultdict(list)
        self._physics_bucket_size = ARENA_TILEMAP_BUCKET

        self.start_x = 5
        self.start_y = 5
        base_w = 80
        base_h = 60
        if self.tile_size >= 32:
            base_w //= 2
            base_h //= 2
        self.width = base_w
        self.height = base_h

        # pull tile variant indices out of the loaded stage art maps once so placement stays cheap
        stone_map = getattr(self.game, 'assets', {}).get('stone_map', {})
        decor_map = getattr(self.game, 'assets', {}).get('decor_map', {})
        stage_key = getattr(self.game, 'stage_key', None)
        use_floor_for_ceiling = bool(getattr(self.game, 'ceiling_from_floor', False))
        stone_variants = len(getattr(self.game, 'assets', {}).get('stone', []))
        if stone_variants <= 0:
            stone_variants = 1

        def collect_variants(prefix, mapping):
            # keep numbered variants in order like floor_1, floor_2, floor_3, ...
            items = []
            pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
            for key, value in mapping.items():
                match = pattern.match(key)
                if not match:
                    continue
                idx = int(match.group(1))
                items.append((idx, value))
            items.sort(key=lambda item: item[0])
            return [value for _, value in items]

        floor_seq = collect_variants('floor_', stone_map) or None
        ceiling_seq = collect_variants('ceiling_', stone_map) or None
        floor_decor_seq = collect_variants('floor_decor_', decor_map) or None
        top_floor_decor_var = decor_map.get('top_floor_decor', None)
        top_floor_decor_vars = [decor_map[k] for k in sorted(decor_map.keys()) if k.startswith('top_floor_decor_')]

        floor_var = stone_map.get('floor_1', 0)
        floor_var_alt = stone_map.get('floor_2', floor_var)
        wall_var = stone_map.get('wall', 0)
        wall_variants = [stone_map[k] for k in sorted(stone_map.keys()) if k.startswith('wall_')]
        if not wall_variants:
            wall_variants = [wall_var]
        wall_decor_variants = [decor_map[k] for k in sorted(decor_map.keys()) if k.startswith('wall_decor_')]
        if not wall_decor_variants:
            wall_decor_variants = [decor_map[k] for k in sorted(decor_map.keys()) if k.startswith('wall_decor') and not k.startswith('wall_decor_')]
        wall_decor_var = decor_map.get('wall_decor', None)
        ceiling_var = stone_map.get('ceiling', floor_var)
        platform_var = stone_map.get('platform', floor_var)
        platform_edge_var = stone_map.get('platform_edge', platform_var)
        platform_decor_var = decor_map.get('platform_decor', stone_map.get('platform_decor', None))
        platform_edge_decor_var = decor_map.get('platform_edge_decor', stone_map.get('platform_edge_decor', platform_decor_var))
        platform_decor_type = 'decor' if 'platform_decor' in decor_map else ('stone' if 'platform_decor' in stone_map else None)
        platform_edge_decor_type = 'decor' if 'platform_edge_decor' in decor_map else ('stone' if 'platform_edge_decor' in stone_map else platform_decor_type)

        if stage_key == 'seabase':
            ceiling_var = wall_variants[0] if wall_variants else wall_var

        # lay in the arena shell first, then decorate it with stage-specific extras
        for x in range(self.width):
            if stage_key == 'seabase':
                top_variant = ceiling_var
                top_flip_y = False
            elif use_floor_for_ceiling and floor_seq:
                floor_idx = x % len(floor_seq)
                top_variant = floor_seq[floor_idx]
                top_flip_y = True
            else:
                top_variant = ceiling_seq[(x % len(ceiling_seq))] if ceiling_seq else ceiling_var
                top_flip_y = False
            self.tilemap[f'{self.start_x + x};{self.start_y}'] = {
                'type': 'stone', 'variant': top_variant, 'pos': (self.start_x + x, self.start_y), 'flip_y': top_flip_y
            }
            if floor_seq:
                floor_idx = x % len(floor_seq)
                bottom_variant = floor_seq[floor_idx]
                is_edge = (x == 0 or x == self.width - 1)
                if floor_decor_seq and not is_edge:
                    decor_variant = floor_decor_seq[floor_idx % len(floor_decor_seq)]
                    self.offgrid_tiles.append({'type': 'decor', 'variant': decor_variant, 'pos': (self.start_x + x, self.start_y + self.height - 2), 'layer': 'front'})
                if (top_floor_decor_var is not None or top_floor_decor_vars) and not is_edge:
                    pair_top = getattr(self.game, 'top_floor_decor_pair', False)
                    if pair_top:
                        if x % 2 == 0 and (x + 1) < self.width and top_floor_decor_var is not None:
                            base_x = self.start_x + x
                            self.offgrid_tiles.append({'type': 'decor', 'variant': top_floor_decor_var, 'pos': (base_x, self.start_y + self.height - 3), 'flip': False, 'layer': 'front'})
                            self.offgrid_tiles.append({'type': 'decor', 'variant': top_floor_decor_var, 'pos': (base_x + 1, self.start_y + self.height - 3), 'flip': True, 'layer': 'front'})
                    else:
                        if top_floor_decor_vars:
                            if len(top_floor_decor_vars) >= 3:
                                seq = [0, 1, 2, 2, 1, 0]
                                flip_seq = [False, False, False, True, True, True]
                                idx = floor_idx % len(seq)
                                top_variant = top_floor_decor_vars[seq[idx]]
                                top_flip = flip_seq[idx]
                            else:
                                top_variant = top_floor_decor_vars[floor_idx % len(top_floor_decor_vars)]
                                top_flip = (floor_idx % 2 == 1)
                        else:
                            top_variant = top_floor_decor_var
                            top_flip = (floor_idx % 2 == 1)
                        self.offgrid_tiles.append({'type': 'decor', 'variant': top_variant, 'pos': (self.start_x + x, self.start_y + self.height - 3), 'flip': top_flip, 'layer': 'front'})
            else:
                bottom_variant = floor_var_alt if random.random() < 0.5 else floor_var
            self.tilemap[f'{self.start_x + x};{self.start_y + self.height - 1}'] = {
                'type': 'stone', 'variant': bottom_variant, 'pos': (self.start_x + x, self.start_y + self.height - 1)
            }

        def wall_pattern_index(y):
            # some stages want a deliberate wall sequence instead of full randomness
            if stage_key == 'amazon':
                seq = [0, 1, 2]
                return seq[y % len(seq)]
            if stage_key == 'seabase':
                seq = [0, 1, 2, 1, 2, 1, 2]
                return seq[y % len(seq)]
            return None

        for y in range(self.height):
            pattern_idx = wall_pattern_index(y)
            if pattern_idx is None:
                left_variant = random.choice(wall_variants)
                right_variant = random.choice(wall_variants)
            else:
                left_variant = wall_variants[pattern_idx % len(wall_variants)]
                right_variant = left_variant
            self.tilemap[f'{self.start_x};{self.start_y + y}'] = {
                'type': 'stone', 'variant': left_variant, 'pos': (self.start_x, self.start_y + y)
            }
            self.tilemap[f'{self.start_x + self.width - 1};{self.start_y + y}'] = {
                'type': 'stone', 'variant': right_variant, 'pos': (self.start_x + self.width - 1, self.start_y + y), 'flip': True
            }
            if wall_decor_variants or wall_decor_var is not None:
                if pattern_idx is None:
                    decor_variant = wall_decor_variants[y % len(wall_decor_variants)] if wall_decor_variants else wall_decor_var
                else:
                    if wall_decor_variants:
                        decor_variant = wall_decor_variants[pattern_idx % len(wall_decor_variants)]
                    else:
                        decor_variant = wall_decor_var
                left_decor_x = self.start_x + 1
                right_decor_x = self.start_x + self.width - 2
                self.offgrid_tiles.append({'type': 'decor', 'variant': decor_variant, 'pos': (left_decor_x, self.start_y + y), 'flip': True, 'layer': 'front'})
                self.offgrid_tiles.append({'type': 'decor', 'variant': decor_variant, 'pos': (right_decor_x, self.start_y + y), 'flip': False, 'layer': 'front'})

        if stage_key == 'seabase':
            bottom_y = self.start_y + self.height - 1
            left_x = self.start_x
            right_x = self.start_x + self.width - 1
            if floor_seq:
                left_variant = floor_seq[left_x % len(floor_seq)]
                right_variant = floor_seq[right_x % len(floor_seq)]
            else:
                left_variant = floor_var_alt
                right_variant = floor_var_alt
            self.tilemap[f'{left_x};{bottom_y}'] = {'type': 'stone', 'variant': left_variant, 'pos': (left_x, bottom_y)}
            self.tilemap[f'{right_x};{bottom_y}'] = {'type': 'stone', 'variant': right_variant, 'pos': (right_x, bottom_y)}

        platform_scale = 0.2 if self.tile_size >= 32 else 1.0
        line_length = 6 if self.tile_size >= 32 else max(6, int((self.width // 6) * platform_scale))
        spawn_tile_x = self.start_x + self.width // 2
        spawn_tile_y = self.start_y + self.height // 2
        line_start_x = spawn_tile_x - line_length // 2
        line_y = spawn_tile_y + 2

        def add_platform(x0, y, length):
            # register both the visual tiles and the collision span for each floating platform
            x0 = max(self.start_x + 1, min(x0, self.start_x + self.width - 2))
            x1 = min(self.start_x + self.width - 1, x0 + length)
            if y <= self.start_y or y >= self.start_y + self.height - 1:
                return
            for x in range(x0 - 1, x1 + 1):
                if x == self.start_x or x == self.start_x + self.width - 1:
                    continue
                loc = f'{x};{y}'
                if loc in self.tilemap:
                    return
            self.platform_spans.append((x0, x1, y))
            for x in range(x0, x1):
                is_left = (x == x0)
                is_right = (x == x1 - 1)
                if is_left or is_right:
                    tile = {'type': 'stone', 'variant': platform_edge_var, 'pos': (x, y)}
                    if is_right:
                        tile['flip'] = True
                    self.tilemap[f'{x};{y}'] = tile
                    if stage_key in ('seabase', 'amazon') and platform_edge_decor_var is not None and platform_edge_decor_type is not None:
                        decor_tile = {'type': platform_edge_decor_type, 'variant': platform_edge_decor_var, 'pos': (x, y - 1), 'layer': 'front'}
                        if is_right:
                            decor_tile['flip'] = True
                        self.offgrid_tiles.append(decor_tile)
                    continue
                self.tilemap[f'{x};{y}'] = {'type': 'stone', 'variant': platform_var, 'pos': (x, y)}
                if stage_key in ('seabase', 'amazon') and platform_decor_var is not None and platform_decor_type is not None:
                    self.offgrid_tiles.append({'type': platform_decor_type, 'variant': platform_decor_var, 'pos': (x, y - 1), 'layer': 'front'})

        custom_layout = STAGE_LAYOUT_SPANS.get(stage_key)
        if custom_layout:
            for x0, x1, y in custom_layout:
                add_platform(self.start_x + x0, self.start_y + y, (x1 - x0) + 1)
        else:
            add_platform(line_start_x, line_y, line_length)

            floor_y = self.start_y + self.height - 1
            row_offsets = [3, 6, 9, 12, 15]
            base_len = 5 if self.tile_size >= 32 else max(6, int((self.width // 7) * platform_scale))
            for off in row_offsets:
                y = floor_y - off
                if y <= self.start_y + 2:
                    continue
                jitter = random.randint(-2, 2) if self.tile_size >= 32 else random.randint(-3, 3)
                left_len = base_len
                right_len = max(4, base_len - 1)
                left_x = self.start_x + 3 + jitter
                right_x = self.start_x + self.width - right_len - 3 - jitter
                add_platform(left_x, y, left_len)
                add_platform(right_x, y, right_len)

        support_var = decor_map.get('platform_support', None)
        if support_var is not None:
            floor_y = self.start_y + self.height - 1
            for x0, x1, y in self.platform_spans:
                length = x1 - x0
                if length < 3:
                    continue
                support_xs = [x0 + 1, x1 - 2]
                support_y = y + 1
                if support_y >= floor_y:
                    continue
                for sx in support_xs:
                    for sy in range(support_y, floor_y):
                        loc = f'{sx};{sy}'
                        if loc in self.tilemap:
                            break
                        self.offgrid_tiles.append({'type': 'decor', 'variant': support_var, 'pos': (sx, sy)})

        railing_var = decor_map.get('railing_decor', None)
        if railing_var is not None:
            floor_y = self.start_y + self.height - 1
            x = self.start_x + 2
            max_x = self.start_x + self.width - 4
            while x <= max_x:
                if random.random() < 0.45:
                    self.offgrid_tiles.append({'type': 'decor', 'variant': railing_var, 'pos': (x, floor_y - 1), 'flip': False, 'layer': 'front'})
                    self.offgrid_tiles.append({'type': 'decor', 'variant': railing_var, 'pos': (x + 1, floor_y - 1), 'flip': True, 'layer': 'front'})
                    x += 3
                else:
                    x += random.randint(2, 6)

        self._rebuild_collision_cache()

    def _rebuild_collision_cache(self):
        # bucket collision rects so nearby lookups stay fast during movement and spawning
        self.collision_rects = []
        self._physics_buckets = defaultdict(list)
        bucket = max(self.tile_size * 4, ARENA_TILEMAP_BUCKET)
        self._physics_bucket_size = bucket
        for tile in self.tilemap.values():
            if tile.get('type') not in PHYSICS_TILES:
                continue
            rect = pygame.Rect(
                tile['pos'][0] * self.tile_size,
                tile['pos'][1] * self.tile_size,
                self.tile_size,
                self.tile_size,
            )
            self.collision_rects.append(rect)
            bx0 = rect.left // bucket
            bx1 = max(rect.left, rect.right - 1) // bucket
            by0 = rect.top // bucket
            by1 = max(rect.top, rect.bottom - 1) // bucket
            for by in range(by0, by1 + 1):
                for bx in range(bx0, bx1 + 1):
                    self._physics_buckets[(bx, by)].append(rect)

    def tiles_around(self, pos):
        tiles = []
        tile_loc = (int(pos[0] // self.tile_size), int(pos[1] // self.tile_size))
        for offset in NEIGHBOR_OFFSETS:
            check_loc = str(tile_loc[0] + offset[0]) + ';' + str(tile_loc[1] + offset[1])
            if check_loc in self.tilemap:
                tiles.append(self.tilemap[check_loc])
        return tiles

    def physics_rects_around(self, pos, size=(34, 43)):
        # query only the buckets touched by a local search rect instead of scanning every tile
        query = pygame.Rect(pos[0], pos[1], size[0], size[1]).inflate(ARENA_TILEMAP_BUCKET, ARENA_TILEMAP_BUCKET)
        bucket = max(1, int(self._physics_bucket_size))
        bx0 = query.left // bucket
        bx1 = max(query.left, query.right - 1) // bucket
        by0 = query.top // bucket
        by1 = max(query.top, query.bottom - 1) // bucket
        rects = []
        seen = set()
        for by in range(by0, by1 + 1):
            for bx in range(bx0, bx1 + 1):
                for rect in self._physics_buckets.get((bx, by), ()):
                    key = (rect.x, rect.y)
                    if key in seen:
                        continue
                    seen.add(key)
                    rects.append(rect)
        return rects

    def get_center_spawn_platform(self):
        # pick a stable center platform for arena spawns and camera framing
        if not self.platform_spans:
            return None
        arena_center_x = self.start_x + (self.width / 2)
        arena_center_y = self.start_y + (self.height / 2)

        def sort_key(span):
            x0, x1, y = span
            span_center_x = x0 + ((x1 - x0) / 2)
            span_len = x1 - x0
            return (
                abs(span_center_x - arena_center_x),
                abs(y - arena_center_y),
                -span_len,
                y,
            )

        return min(self.platform_spans, key=sort_key)

    def render(self, surf, offset=(0, 0)):
        # draw back-layer decor first, then tiles, then front-layer decor
        for tile in self.offgrid_tiles:
            if tile.get('layer') == 'front':
                continue
            img = self.game.assets[tile['type']][tile['variant']]
            if tile.get('flip') or tile.get('flip_y'):
                img = pygame.transform.flip(img, tile.get('flip', False), tile.get('flip_y', False))
            surf.blit(img, (tile['pos'][0] * self.tile_size - offset[0], tile['pos'][1] * self.tile_size - offset[1]))

        start_x = int(offset[0] // self.tile_size) - 1
        end_x = int((offset[0] + surf.get_width()) // self.tile_size) + 2
        start_y = int(offset[1] // self.tile_size) - 1
        end_y = int((offset[1] + surf.get_height()) // self.tile_size) + 2
        for x in range(start_x, end_x):
            for y in range(start_y, end_y):
                loc = str(x) + ';' + str(y)
                if loc in self.tilemap:
                    tile = self.tilemap[loc]
                    img = self.game.assets[tile['type']][tile['variant']]
                    if tile.get('flip') or tile.get('flip_y'):
                        img = pygame.transform.flip(img, tile.get('flip', False), tile.get('flip_y', False))
                    surf.blit(img, (tile['pos'][0] * self.tile_size - offset[0], tile['pos'][1] * self.tile_size - offset[1]))

        for tile in self.offgrid_tiles:
            if tile.get('layer') != 'front':
                continue
            img = self.game.assets[tile['type']][tile['variant']]
            if tile.get('flip') or tile.get('flip_y'):
                img = pygame.transform.flip(img, tile.get('flip', False), tile.get('flip_y', False))
            surf.blit(img, (tile['pos'][0] * self.tile_size - offset[0], tile['pos'][1] * self.tile_size - offset[1]))
