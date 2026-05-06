import math
import random

import pygame

from .combat_data import (
    ANIM_OFFSETS,
    DEFAULT_ACTION,
    HITBOX_ALIGN_TO_ANIM,
    HITBOX_H,
    HITBOX_OFFSETS,
    HITBOX_SIZES,
    OY_GROUND,
)
from .core import Animation, Effect
from .tilemap import PHYSICS_TILES

AIRBORNE_BODY_ACTIONS = {
    'zero_jumping',
    'zero_double_jump',
    'zero_falling',
    'zero_falling_compact',
    'zero_air_saber_slash',
    'zero_double_jump_slash',
}


# shared physics body used by the player and most arena enemies
class ArenaPhysicsEntity:
    def __init__(self, game, e_type, pos, size):
        self.game = game
        self.type = e_type
        self.pos = list(pos)
        self.size = size
        self.render_x_nudge = 0
        self.render_y_nudge = 0
        self.transition_render_nudge = (0, 0)
        self.transition_render_nudge_timer = 0
        self.transition_render_nudge_duration = 0
        self.velocity = [0, 0]
        self.collisions = {'up': False, 'down': False, 'right': False, 'left': False}
        self.action = ''
        self.flip = False
        self._hw = size[0]
        self._hh = HITBOX_H
        self.set_action(DEFAULT_ACTION)

    def _hitbox_offsets(self):
        ox_r, ox_l = HITBOX_OFFSETS.get(self.action, (0, 0))
        if self.action in HITBOX_ALIGN_TO_ANIM:
            align_target = HITBOX_ALIGN_TO_ANIM[self.action]
            if isinstance(align_target, dict):
                frame_idx = self.animation.frame_index() if hasattr(self, "animation") else 0
                align_target = align_target.get(frame_idx, self.action)
            if self.action in getattr(self.game, 'anim_offsets_override', {}):
                anim_offsets = self.game.anim_offsets_override
            else:
                anim_offsets = ANIM_OFFSETS
            base = anim_offsets.get('zero_idle', (-45, -49, OY_GROUND))
            cur = anim_offsets.get(align_target, base)
            ox_r += (cur[0] - base[0])
            ox_l += (cur[1] - base[1])
        ox = ox_l if self.flip else ox_r
        oy = HITBOX_H - self._hh
        return ox, oy

    def rect(self):
        ox, oy = self._hitbox_offsets()
        return pygame.Rect(self.pos[0] + ox, self.pos[1] + oy, self._hw, self._hh)

    def camera_center(self):
        ox, oy = self._hitbox_offsets()
        body_left = self.pos[0] + ox
        body_bottom = self.pos[1] + oy + self._hh
        return (
            body_left + (self._hw / 2.0),
            body_bottom - (HITBOX_H / 2.0),
        )

    def _is_in_active_view(self, margin=32):
        scroll = getattr(self.game, "render_scroll", None)
        view_w = getattr(self.game, "arena_view_width", None)
        view_h = getattr(self.game, "arena_view_height", None)
        if scroll is None or view_w is None or view_h is None:
            return True
        rect = self.rect().inflate(margin * 2, margin * 2)
        view_rect = pygame.Rect(int(scroll[0]) - margin, int(scroll[1]) - margin, int(view_w) + margin * 2, int(view_h) + margin * 2)
        return rect.colliderect(view_rect)

    def set_action(self, action, force=False):
        # swap animations while trying to preserve collision contact and body placement
        old_rect = self.rect()
        old_action = self.action
        old_size = (self._hw, self._hh)
        old_draw_offset = None
        airborne_preserve = False
        if hasattr(self, 'animation') and getattr(self.animation, 'images', None):
            try:
                old_img = self.animation.img()
                old_draw_offset = self._draw_offset(old_img)
            except Exception:
                old_draw_offset = None
        if force or action != self.action:
            self.action = action
            self.animation = self.game.assets[action].copy()
        size = HITBOX_SIZES.get(action, (self.size[0], HITBOX_H))
        self._hw = size[0]
        self._hh = size[1]
        if (
            (force or action != old_action)
            and (old_action in AIRBORNE_BODY_ACTIONS or action in AIRBORNE_BODY_ACTIONS)
            and not getattr(self, 'grounded', False)
            and not self.collisions.get('down', False)
        ):
            airborne_preserve = True
            new_rect = self.rect()
            new_rect.centerx = old_rect.centerx
            new_rect.bottom = old_rect.bottom
            ox, oy = self._hitbox_offsets()
            self.pos[0] = new_rect.x - ox
            self.pos[1] = new_rect.y - oy
        if (force or action != old_action) and any(self.collisions.values()) and not airborne_preserve:
            new_rect = self.rect()
            if self.collisions.get('left'):
                new_rect.left = old_rect.left
            elif self.collisions.get('right'):
                new_rect.right = old_rect.right
            if self.collisions.get('down'):
                new_rect.bottom = old_rect.bottom
            elif self.collisions.get('up'):
                new_rect.top = old_rect.top
            ox, oy = self._hitbox_offsets()
            self.pos[0] = new_rect.x - ox
            self.pos[1] = new_rect.y - oy
        if (force or action != old_action) and getattr(self, 'wall_contact_timer', 0) > 0:
            new_rect = self.rect()
            if getattr(self, 'wall_contact_dir', 0) < 0:
                new_rect.left = self.wall_contact_edge
            elif getattr(self, 'wall_contact_dir', 0) > 0:
                new_rect.right = self.wall_contact_edge
            ox, oy = self._hitbox_offsets()
            self.pos[0] = new_rect.x - ox
            self.pos[1] = new_rect.y - oy
        if force or action != old_action:
            last_tilemap = getattr(self, '_last_tilemap', None)
            deferred_attr = hasattr(self, '_deferred_hitbox_size')
            if last_tilemap is not None and (self._hw > old_size[0] or self._hh > old_size[1]):
                blocked = False
                if hasattr(self, '_can_fit_hitbox_size'):
                    blocked = not self._can_fit_hitbox_size(last_tilemap, self._hw, self._hh)
                if blocked:
                    self._hw, self._hh = old_size
                    ox, oy = self._hitbox_offsets()
                    self.pos[0] = old_rect.x - ox
                    self.pos[1] = old_rect.y - oy
                    if deferred_attr:
                        self._deferred_hitbox_size = (size[0], size[1])
                elif deferred_attr:
                    self._deferred_hitbox_size = None
    def update(self, tilemap, movement=(0, 0)):
        # base physics tick: move, collide, auto-flip, gravity, then advance animation
        self.collisions = {'up': False, 'down': False, 'right': False, 'left': False}
        frame_movement = (movement[0] + self.velocity[0], movement[1] + self.velocity[1])

        self.pos[0] += frame_movement[0]
        entity_rect = self.rect()
        if frame_movement[0] and getattr(tilemap, "allow_step_up", False):
            stepped_rect = self._try_step_up(tilemap, entity_rect, frame_movement[0])
            if stepped_rect is not None:
                entity_rect = stepped_rect
                ox, oy = self._hitbox_offsets()
                self.pos[0] = entity_rect.x - ox
                self.pos[1] = entity_rect.y - oy
        for rect in tilemap.physics_rects_around(entity_rect.topleft, (self._hw, self._hh)):
            if entity_rect.colliderect(rect):
                if frame_movement[0] > 0:
                    entity_rect.right = rect.left
                    self.collisions['right'] = True
                elif frame_movement[0] < 0:
                    entity_rect.left = rect.right
                    self.collisions['left'] = True
                ox, oy = self._hitbox_offsets()
                self.pos[0] = entity_rect.x - ox

        self.pos[1] += frame_movement[1]
        entity_rect = self.rect()
        for rect in tilemap.physics_rects_around(entity_rect.topleft, (self._hw, self._hh)):
            if entity_rect.colliderect(rect):
                if frame_movement[1] > 0:
                    entity_rect.bottom = rect.top
                    self.collisions['down'] = True
                elif frame_movement[1] < 0:
                    entity_rect.top = rect.bottom
                    self.collisions['up'] = True
                ox, oy = self._hitbox_offsets()
                self.pos[1] = entity_rect.y - oy

        if not getattr(self, 'ignore_auto_flip', False) and getattr(self, 'flip_lock_timer', 0) <= 0:
            if movement[0] > 0:
                self.flip = False
            elif movement[0] < 0:
                self.flip = True

        self.velocity[1] = min(7, self.velocity[1] + 0.14)
        if self.collisions['down'] or self.collisions['up']:
            self.velocity[1] = 0

        prev_rect = self.rect()
        prev_frame_idx = self.animation.frame_index()
        self.animation.update()
        if (
            self.action in HITBOX_ALIGN_TO_ANIM
            and isinstance(HITBOX_ALIGN_TO_ANIM[self.action], dict)
            and self.animation.frame_index() != prev_frame_idx
        ):
            new_rect = self.rect()
            if new_rect.topleft != prev_rect.topleft:
                new_rect.centerx = prev_rect.centerx
                new_rect.bottom = prev_rect.bottom
                ox, oy = self._hitbox_offsets()
                self.pos[0] = new_rect.x - ox
                self.pos[1] = new_rect.y - oy
        if self.transition_render_nudge_timer > 0:
            self.transition_render_nudge_timer -= 1
            if self.transition_render_nudge_timer <= 0:
                self.transition_render_nudge = (0, 0)
                self.transition_render_nudge_duration = 0

    def _step_up_height_for_motion(self, tilemap, dx=0, treat_as_dash=False):
        max_step = int(getattr(tilemap, "step_up_height", 0))
        if max_step <= 0 or not getattr(tilemap, "allow_step_up", False):
            return 0

        dash_active = treat_as_dash or getattr(self, "dash_timer", 0) > 0
        if getattr(self, "grounded", False) and dash_active:
            dash_step = getattr(tilemap, "dash_step_up_height", None)
            if dash_step is None:
                dash_step = max_step + int(math.ceil(abs(dx)))
            max_step = max(max_step, int(dash_step))
        return max_step

    def _try_step_up(self, tilemap, entity_rect, dx):
        # let grounded bodies step up short lips instead of feeling sticky on tiny edges
        max_step = self._step_up_height_for_motion(tilemap, dx=dx)
        if max_step <= 0 or self.velocity[1] < 0:
            return None

        query_rects = tilemap.physics_rects_around(entity_rect.topleft, (self._hw, self._hh))
        if not any(entity_rect.colliderect(rect) for rect in query_rects):
            return None

        test_rect = entity_rect.copy()
        for step in range(1, max_step + 1):
            test_rect.y -= 1
            nearby = tilemap.physics_rects_around(test_rect.topleft, (self._hw, self._hh))
            if any(test_rect.colliderect(rect) for rect in nearby):
                continue
            return test_rect.copy()

        return None

    def _draw_offset(self, img):
        # draw offsets keep authored sprite anchors lined up with the gameplay hitbox
        anchored = {
            'zero_idle',
            'zero_dashing_end_idle', 'zero_dashing_end_move',
        }
        anchor_tweak = {
            'zero_idle': (0, 1),
        }
        if self.action in anchored:
            mask = pygame.mask.from_surface(img)
            rects = mask.get_bounding_rects()
            if rects:
                min_x = min(r.x for r in rects)
                max_x = max(r.x + r.w for r in rects)
                max_y = max(r.y + r.h for r in rects)
                anchor_x = (min_x + max_x) / 2.0
                anchor_y = max_y
                if self.flip:
                    anchor_x = img.get_width() - anchor_x
                ox = self._hw / 2.0 - anchor_x
                oy = self._hh - anchor_y
                tx, ty = anchor_tweak.get(self.action, (0, 0))
                return int(ox + tx), int(oy + ty)

        draw_offsets_override = getattr(self.game, 'anim_draw_offsets_override', {})
        if self.action in draw_offsets_override:
            ox_r, ox_l, oy = draw_offsets_override[self.action]
        elif self.action in self.game.anim_offsets_override:
            ox_r, ox_l, oy = self.game.anim_offsets_override[self.action]
        else:
            ox_r, ox_l, oy = ANIM_OFFSETS.get(self.action, (-45, -49, OY_GROUND))
        frame_offsets = getattr(self.game, 'anim_frame_offsets', {})
        dx = 0
        dy = 0
        if self.action in frame_offsets:
            idx = self.animation.frame_index()
            offsets = frame_offsets[self.action]
            if offsets:
                dx, dy = offsets[min(idx, len(offsets) - 1)]
        return (ox_l if self.flip else ox_r) + dx, oy + dy

    def render(self, surf, offset=(0, 0)):
        # render uses the current animation frame plus any temporary transition nudge
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        tx, ty = self._transition_render_offset()
        draw_x = int(self.pos[0] - offset[0]) + int(ox) + int(getattr(self, 'render_x_nudge', 0)) + tx
        draw_y = int(self.pos[1] - offset[1]) + int(oy) + int(getattr(self, 'render_y_nudge', 0)) + ty
        surf.blit(pygame.transform.flip(img, self.flip, False), (draw_x, draw_y))

    def sprite_focus_point(self):
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        tx, ty = self._transition_render_offset()
        return (
            self.pos[0] + ox + tx + (img.get_width() / 2.0),
            self.pos[1] + oy + ty + (img.get_height() / 2.0),
        )

    def render_debug(self, surf, offset=(0, 0)):
        self.render(surf, offset)
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        hb_ox, hb_oy = self._hitbox_offsets()
        tx, ty = self._transition_render_offset()
        draw_x = int(self.pos[0] - offset[0]) + int(ox) + int(getattr(self, 'render_x_nudge', 0)) + tx
        draw_y = int(self.pos[1] - offset[1]) + int(oy) + int(getattr(self, 'render_y_nudge', 0)) + ty
        hb_x = int(self.pos[0] - offset[0]) + int(hb_ox)
        hb_y = int(self.pos[1] - offset[1]) + int(hb_oy)
        pygame.draw.rect(surf, (0, 255, 0), (hb_x, hb_y, self._hw, self._hh), 1)
        pygame.draw.rect(surf, (255, 0, 0), (draw_x, draw_y, img.get_width(), img.get_height()), 1)

    def _transition_render_offset(self):
        if self.transition_render_nudge_timer <= 0 or self.transition_render_nudge_duration <= 0:
            return (0, 0)
        ratio = self.transition_render_nudge_timer / float(self.transition_render_nudge_duration)
        return (
            int(round(self.transition_render_nudge[0] * ratio)),
            int(round(self.transition_render_nudge[1] * ratio)),
        )


# falling giga beam columns are separate from the player so they can update/render independently
class GigaBeam:
    def __init__(self, game, x, y, speed=14, scale=1.0, delay=0):
        self.game = game
        self.pos = [x, y]
        self.speed = speed
        self.scale = scale
        self.delay = delay
        self.animation = game.assets['giga_attack_beam'].copy()
        if self.animation.images and scale != 1.0:
            scaled = []
            for img in self.animation.images:
                scaled.append(pygame.transform.scale(img, (int(img.get_width() * scale), int(img.get_height() * scale))))
            self.animation.images = scaled
        if self.animation.images:
            self.width = self.animation.images[0].get_width()
            self.height = self.animation.images[0].get_height()
        else:
            self.width = 0
            self.height = 0

    def update(self, max_y):
        if self.delay > 0:
            self.delay -= 1
        else:
            self.pos[1] += self.speed
        self.animation.update()
        return self.pos[1] <= max_y

    def render(self, surf, offset=(0, 0)):
        img = self.animation.img()
        surf.blit(img, (self.pos[0] - offset[0], self.pos[1] - offset[1]))

    def rect(self):
        return pygame.Rect(
            int(round(self.pos[0])),
            int(round(self.pos[1])),
            int(self.width),
            int(self.height),
        )

    def hitbox_rect(self, width_factor=1.0, height_factor=1.0):
        w = max(1, int(self.width * width_factor))
        h = max(1, int(self.height * height_factor))
        x = int(self.pos[0] + (self.width - w) / 2)
        y = int(self.pos[1] + (self.height - h) / 2)
        return pygame.Rect(x, y, w, h)


# simple health / giga refills with their own tiny physics and blink timing
class ArenaPickup:
    DEFAULT_VALUES = {
        "small_hp_pickup": 2,
        "large_hp_pickup": 8,
        "small_special_ammo_pickup": 4,
        "large_special_ammo_pickup": 8,
    }

    def __init__(self, game, pickup_key, pos, amount=None, vel=(0, 0), persistent=False):
        self.game = game
        self.pickup_key = pickup_key
        images = list(getattr(game, "effect_images", {}).get(pickup_key, []))
        if not images:
            raise ValueError(f"Missing pickup images for {pickup_key}")
        loop_from = 0
        if pickup_key == "small_hp_pickup":
            loop_from = max(0, len(images) - 3)
        elif pickup_key == "large_hp_pickup":
            loop_from = max(0, len(images) - 3)
        self.animation = Animation(images, img_dur=6, loop=True, loop_from=loop_from)
        self.amount = self.DEFAULT_VALUES.get(pickup_key, 1) if amount is None else amount
        self.kind = "health" if "hp" in pickup_key else "giga"
        self.pos = [float(pos[0]), float(pos[1])]
        self.velocity = [float(vel[0]), float(vel[1])]
        self.gravity = 0.16
        self.max_fall_speed = 3.4
        self.grounded = False
        self.rest_y = None
        self.collect_delay = 12
        self.ground_timer = 0
        self.persistent = bool(persistent)
        self.despawn_delay = 180
        self.blink_duration = 60
        self._compute_bounds(images)

    def _compute_bounds(self, images):
        rects = []
        self.frame_anchors = []
        for img in images:
            mask = pygame.mask.from_surface(img)
            frame_rects = mask.get_bounding_rects()
            rects.extend(frame_rects)
            if frame_rects:
                min_x = min(r.x for r in frame_rects)
                min_y = min(r.y for r in frame_rects)
                max_x = max(r.x + r.w for r in frame_rects)
                max_y = max(r.y + r.h for r in frame_rects)
                frame_bounds = pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
            else:
                frame_bounds = pygame.Rect(0, 0, img.get_width(), img.get_height())
            self.frame_anchors.append(
                (
                    frame_bounds.x + (frame_bounds.w / 2.0),
                    frame_bounds.bottom,
                )
            )
        if rects:
            min_x = min(r.x for r in rects)
            min_y = min(r.y for r in rects)
            max_x = max(r.x + r.w for r in rects)
            max_y = max(r.y + r.h for r in rects)
            self.bounds = pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
        else:
            self.bounds = pygame.Rect(0, 0, images[0].get_width(), images[0].get_height())
        self.anchor_x = self.bounds.x + (self.bounds.w / 2.0)
        self.anchor_y = self.bounds.bottom

    def rect(self):
        return pygame.Rect(
            int(round(self.pos[0] - (self.bounds.w / 2.0))),
            int(round(self.pos[1] - self.bounds.h)),
            self.bounds.w,
            self.bounds.h,
        )

    def _apply_to_player(self, player):
        if self.kind == "health":
            if player.health >= player.max_health:
                return True
        else:
            if player.giga_energy >= player.max_giga_energy:
                return True
        return player.start_pickup_refill(self.kind, self.amount)

    def _blink_alpha(self):
        if self.persistent:
            return 255
        if self.ground_timer <= self.despawn_delay:
            return 255
        blink_timer = self.ground_timer - self.despawn_delay
        return 0 if (blink_timer // 3) % 2 == 0 else 255

    def update(self, tilemap, player=None):
        if player and getattr(player, "pickup_refill_active", lambda: False)():
            return True
        self.animation.update()
        if self.collect_delay > 0:
            self.collect_delay -= 1

        if self.rest_y is None:
            self.grounded = False
            self.velocity[1] = min(self.max_fall_speed, self.velocity[1] + self.gravity)

            self.pos[0] += self.velocity[0]
            pickup_rect = self.rect()
            for rect in tilemap.physics_rects_around(pickup_rect.topleft, pickup_rect.size):
                if pickup_rect.colliderect(rect):
                    if self.velocity[0] > 0:
                        pickup_rect.right = rect.left
                    elif self.velocity[0] < 0:
                        pickup_rect.left = rect.right
                    self.pos[0] = pickup_rect.centerx
                    self.velocity[0] = 0.0

            self.pos[1] += self.velocity[1]
            pickup_rect = self.rect()
            for rect in tilemap.physics_rects_around(pickup_rect.topleft, pickup_rect.size):
                if pickup_rect.colliderect(rect):
                    if self.velocity[1] > 0:
                        pickup_rect.bottom = rect.top
                        self.grounded = True
                        self.rest_y = pickup_rect.bottom
                    elif self.velocity[1] < 0:
                        pickup_rect.top = rect.bottom
                    self.pos[1] = pickup_rect.bottom
                    self.velocity[1] = 0.0
        else:
            self.grounded = True
            self.pos[1] = self.rest_y
            self.velocity[1] = 0.0

        if self.grounded:
            self.ground_timer += 1
            self.velocity[0] *= 0.82
            if abs(self.velocity[0]) < 0.05:
                self.velocity[0] = 0.0
            if (not self.persistent) and self.ground_timer > self.despawn_delay + self.blink_duration:
                return False
        else:
            self.ground_timer = 0

        if player and self.collect_delay <= 0 and self.rect().colliderect(player.rect()):
            if self._apply_to_player(player):
                return False
        return True

    def render(self, surf, offset=(0, 0)):
        img = self.animation.img()
        frame_idx = self.animation.frame_index()
        anchor_x, anchor_y = self.frame_anchors[min(frame_idx, len(self.frame_anchors) - 1)]
        alpha = self._blink_alpha()
        if alpha <= 0:
            return
        if alpha < 255:
            img = img.copy()
            alpha_mask = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            alpha_mask.fill((255, 255, 255, alpha))
            img.blit(alpha_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        draw_x = int(round(self.pos[0] - anchor_x - offset[0]))
        draw_y = int(round(self.pos[1] - anchor_y - offset[1]))
        surf.blit(img, (draw_x, draw_y))


# flying intro/arena enemy with its own swoop and recovery behavior
class ArenaCopterEnemy(ArenaPhysicsEntity):
    def __init__(self, game, pos, spawn_delay=0):
        super().__init__(game, 'enemy', pos, (36, 24))
        self.ignore_auto_flip = False
        self.home_pos = [float(pos[0]), float(pos[1])]
        self.speed = 0.6
        self.arrive_radius = 8
        self.hover_strength = 0.45
        self.hover_frequency = 0.08
        self.hover_timer = random.uniform(0.0, math.tau)
        self.retreat_timer = 0
        self.retreat_time = 18
        self.retreat_vel = [0.0, 0.0]
        self.max_health = 2
        self.health = self.max_health
        self.hit_flash_timer = 0
        self.hit_flash_time = 30
        self.orbit_timer = 0
        self.orbit_interval = 82
        self.orbit_angle = random.uniform(0.0, math.tau)
        self.orbit_radius_x = 96
        self.orbit_radius_y = 68
        self.attack_timer = random.randint(220, 320)
        self.attack_cooldown_min = 230
        self.attack_cooldown_max = 360
        self.attack_duration = 8
        self.attack_time_left = 0
        self.attack_vector = [0.0, 0.0]
        self.attack_speed = 1.2
        self.attack_window_time = 600
        self.attack_window_timer = self.attack_window_time
        self.attacks_in_window = 0
        self.spawn_delay = spawn_delay
        self.after_hit_timer = 0
        self.after_hit_time = 60
        self.reengage_height_margin = 12
        self.reengage_hover_offset = 28
        self.notice_range_x = 240
        self.notice_range_y = 150
        self.player_hit_retreat_px = 96
        self.last_sword_attack_id = -1
        self.camera_activation_pending = True
        self.track_player_globally = getattr(game, "stage_key", None) != "intro_stage"
        if self.track_player_globally:
            self.camera_activation_pending = False
        self.entry_mode = False
        self.entry_speed_scale = 1.0
        self.drop_table = [
            (None, 64, 0),
            ("small_hp_pickup", 20, 4),
            ("large_hp_pickup", 5, 8),
            ("small_special_ammo_pickup", 9, 4),
            ("large_special_ammo_pickup", 2, 8),
        ]
        self.set_action('copter_flying', force=True)

    def _hitbox_offsets(self):
        if not hasattr(self, 'animation'):
            return 0, 0
        img = self.animation.img()
        draw_ox, draw_oy = self._draw_offset(img)
        ox = int(draw_ox + (img.get_width() - self._hw) / 2)
        oy = int(draw_oy + (img.get_height() - self._hh) / 2)
        return ox, oy

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if self.hit_flash_timer > 0:
            self.hit_flash_timer -= 1
        if self.spawn_delay > 0:
            self.spawn_delay -= 1
            self.animation.update()
            return
        if self.camera_activation_pending:
            if self._is_in_active_view(margin=24):
                self.camera_activation_pending = False
            else:
                self.animation.update()
                return
        if self.attack_window_timer > 0:
            self.attack_window_timer -= 1
        else:
            self.attack_window_timer = self.attack_window_time
            self.attacks_in_window = 0
        if not player:
            self.animation.update()
            return

        if self.retreat_timer > 0:
            self.retreat_timer -= 1
            self.pos[0] += self.retreat_vel[0]
            self.pos[1] += self.retreat_vel[1]
            self.retreat_vel[0] *= 0.93
            self.retreat_vel[1] *= 0.94
            if self.after_hit_timer > 0 and 'copter_after_hit' in self.game.assets:
                if self.action != 'copter_after_hit':
                    self.set_action('copter_after_hit', force=True)
            elif self.action != 'copter_flying':
                self.set_action('copter_flying', force=True)
            self.animation.update()
            return

        player_rect = player.rect()
        player_sprite_x, player_sprite_y = player.sprite_focus_point()
        my_rect = self.rect()
        self.hover_timer += self.hover_frequency
        player_engaged = self.track_player_globally or (
            abs(player_rect.centerx - my_rect.centerx) <= self.notice_range_x
            and abs(player_rect.centery - my_rect.centery) <= self.notice_range_y
        )

        if self.after_hit_timer > 0:
            self.after_hit_timer -= 1
            if self.after_hit_timer == self.after_hit_time - self.retreat_time:
                self.attack_time_left = 0
                self.attack_vector[0] = 0.0
                self.attack_vector[1] = 0.0
            if self.after_hit_timer > 0 and 'copter_after_hit' in self.game.assets:
                if self.action != 'copter_after_hit':
                    self.set_action('copter_after_hit', force=True)
            elif self.action != 'copter_flying':
                self.set_action('copter_flying', force=True)
            self.animation.update()
            return

        if self.entry_mode:
            target_x = self.home_pos[0]
            target_y = self.home_pos[1] + math.sin(self.hover_timer) * 8
            dx = target_x - self.pos[0]
            dy = target_y - self.pos[1]
            dist = math.hypot(dx, dy)
            move_x = 0.0
            move_y = math.sin(self.hover_timer * 1.7) * self.hover_strength * 0.6
            entry_speed = max(0.2, self.speed * self.entry_speed_scale)
            if dist > self.arrive_radius:
                scale = min(entry_speed, dist) / max(0.001, dist)
                move_x += dx * scale
                move_y += dy * scale
            self.pos[0] += move_x
            self.pos[1] += move_y
            if abs(move_x) > 0.05:
                self.flip = move_x < 0
            if dist <= self.arrive_radius + 4:
                self.entry_mode = False
            self.animation.update()
            return

        if self.attack_time_left > 0:
            self.attack_time_left -= 1
            move_x = self.attack_vector[0]
            move_y = self.attack_vector[1]
        elif not player_engaged:
            target_x = self.home_pos[0]
            target_y = self.home_pos[1] + math.sin(self.hover_timer) * 8
            dx = target_x - self.pos[0]
            dy = target_y - self.pos[1]
            dist = math.hypot(dx, dy)
            move_x = 0.0
            move_y = math.sin(self.hover_timer * 1.7) * self.hover_strength
            if dist > self.arrive_radius:
                scale = min(self.speed, dist) / dist
                move_x += dx * scale
                move_y += dy * scale
            if self.attack_timer <= 0:
                self.attack_timer = random.randint(self.attack_cooldown_min, self.attack_cooldown_max)
            self.attack_time_left = 0
            self.attack_vector[0] = 0.0
            self.attack_vector[1] = 0.0
        else:
            if self.orbit_timer <= 0:
                self.orbit_timer = self.orbit_interval + random.randint(-12, 16)
                self.orbit_angle = random.uniform(0.0, math.tau)
                self.orbit_radius_x = random.randint(84, 126)
                self.orbit_radius_y = random.randint(54, 92)
            else:
                self.orbit_timer -= 1

            target_x = player_sprite_x + math.cos(self.orbit_angle) * self.orbit_radius_x - (my_rect.width / 2)
            target_y = player_sprite_y + math.sin(self.orbit_angle) * self.orbit_radius_y - (my_rect.height / 2)
            target_y += math.sin(self.hover_timer) * 8
            preferred_top = (player_sprite_y - self.reengage_hover_offset) - (my_rect.height / 2)
            below_player = my_rect.centery > (player_rect.centery + self.reengage_height_margin)
            if below_player:
                target_y = min(target_y, preferred_top)

            dx = target_x - self.pos[0]
            dy = target_y - self.pos[1]
            dist = math.hypot(dx, dy)

            move_x = 0.0
            move_y = math.sin(self.hover_timer * 1.7) * self.hover_strength
            if dist > self.arrive_radius:
                scale = min(self.speed, dist) / dist
                move_x += dx * scale
                move_y += dy * scale

            if self.attack_timer > 0:
                self.attack_timer -= 1
            elif (not below_player) and dist > 48 and self.attacks_in_window < 4 and random.random() < 0.10:
                p_dx = player_sprite_x - my_rect.centerx
                p_dy = player_sprite_y - my_rect.centery
                p_dist = math.hypot(p_dx, p_dy)
                if p_dist > 0:
                    self.attack_vector[0] = (p_dx / p_dist) * self.attack_speed
                    self.attack_vector[1] = (p_dy / p_dist) * self.attack_speed
                    self.attack_time_left = self.attack_duration
                    self.attacks_in_window += 1
                self.attack_timer = random.randint(self.attack_cooldown_min, self.attack_cooldown_max)
            elif self.attack_timer <= 0:
                self.attack_timer = random.randint(self.attack_cooldown_min, self.attack_cooldown_max)

        self.pos[0] += move_x
        self.pos[1] += move_y

        if arena_bounds:
            ox, oy, w, h = arena_bounds
            max_x = ox + w - self._hw
            max_y = oy + h - self._hh
            self.pos[0] = max(ox, min(self.pos[0], max_x))
            self.pos[1] = max(oy, min(self.pos[1], max_y))

        if move_x > 0.05:
            self.flip = False
        elif move_x < -0.05:
            self.flip = True
        if self.after_hit_timer > 0 and 'copter_after_hit' in self.game.assets:
            if self.action != 'copter_after_hit':
                self.set_action('copter_after_hit', force=True)
        elif self.action != 'copter_flying':
            self.set_action('copter_flying', force=True)
        self.animation.update()

    def _hurt_render_alpha(self):
        if self.hit_flash_timer <= 0:
            return 255
        return 0 if (self.hit_flash_timer // 3) % 2 == 0 else 255

    def render(self, surf, offset=(0, 0)):
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        draw_x = int(self.pos[0] - offset[0]) + int(ox)
        draw_y = int(self.pos[1] - offset[1]) + int(oy)
        frame = pygame.transform.flip(img, self.flip, False)
        if self.spawn_delay > 0:
            ready_alpha = max(70, 255 - min(180, self.spawn_delay * 3))
            faded = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            faded.blit(frame, (0, 0))
            faded.fill((255, 255, 255, ready_alpha), special_flags=pygame.BLEND_RGBA_MULT)
            frame = faded
        alpha = self._hurt_render_alpha()
        if alpha < 255:
            faded = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            faded.blit(frame, (0, 0))
            faded.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            frame = faded
        surf.blit(frame, (draw_x, draw_y))

    def on_hit_player(self, player):
        player_rect = player.rect()
        my_rect = self.rect()
        dir_sign = -1 if my_rect.centerx >= player_rect.centerx else 1
        self.after_hit_timer = self.after_hit_time
        self.retreat_timer = self.retreat_time
        self.retreat_vel[0] = (self.player_hit_retreat_px / 11.2) * dir_sign
        self.retreat_vel[1] = -1.6
        self.attack_time_left = 0
        self.attack_vector[0] = 0.0
        self.attack_vector[1] = 0.0
        self.flip = dir_sign < 0

    def take_sword_hit(self, player):
        attack_id = getattr(player, "attack_instance_id", 0)
        if attack_id == self.last_sword_attack_id:
            return False
        self.last_sword_attack_id = attack_id
        self.health = max(0, self.health - 1)
        self.hit_flash_timer = self.hit_flash_time
        hitmarker_sound = getattr(self.game, 'sfx_hitmarker', None)
        if hitmarker_sound:
            try:
                hitmarker_sound.play()
            except Exception:
                pass
        player_rect = player.rect()
        my_rect = self.rect()
        dir_sign = 1 if my_rect.centerx >= player_rect.centerx else -1
        self.retreat_timer = 0
        self.retreat_vel[0] = 0.0
        self.retreat_vel[1] = 0.0
        self.flip = dir_sign < 0
        return self.health <= 0

    def take_giga_hit(self):
        if self.spawn_delay > 0:
            return False
        self.health = 0
        self.hit_flash_timer = 0
        self.after_hit_timer = 0
        self.retreat_timer = 0
        self.retreat_vel[0] = 0.0
        self.retreat_vel[1] = 0.0
        return True

    def roll_pickup_drop(self):
        if not self.drop_table:
            return None
        total_weight = sum(max(0, entry[1]) for entry in self.drop_table)
        if total_weight <= 0:
            return None
        roll = random.uniform(0, total_weight)
        upto = 0.0
        for pickup_key, weight, amount in self.drop_table:
            weight = max(0, weight)
            upto += weight
            if roll <= upto:
                if not pickup_key:
                    return None
                return {
                    "pickup_key": pickup_key,
                    "amount": amount,
                }
        return None


# base projectile wrapper for enemy shots that need animation + world collision
class ArenaEnemyProjectile:
    def __init__(self, game, action, pos, vel=(0.0, 0.0), gravity=0.0, life=180, anchor="center", flip=False):
        self.game = game
        self.action = action
        self.animation = game.assets[action].copy()
        self.pos = [float(pos[0]), float(pos[1])]
        self.vel = [float(vel[0]), float(vel[1])]
        self.gravity = float(gravity)
        self.life = int(life)
        self.anchor = anchor
        self.flip = bool(flip)
        self._bounds_cache = {}

    def _frame_bounds(self, img):
        key = id(img)
        bounds = self._bounds_cache.get(key)
        if bounds is not None:
            return bounds
        mask = pygame.mask.from_surface(img)
        rects = mask.get_bounding_rects()
        if rects:
            min_x = min(r.x for r in rects)
            min_y = min(r.y for r in rects)
            max_x = max(r.x + r.w for r in rects)
            max_y = max(r.y + r.h for r in rects)
            bounds = pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
        else:
            bounds = img.get_bounding_rect()
            if bounds.width <= 0 or bounds.height <= 0:
                bounds = pygame.Rect(0, 0, img.get_width(), img.get_height())
        self._bounds_cache[key] = bounds
        return bounds

    def rect(self):
        img = self.animation.img()
        bounds = self._frame_bounds(img)
        if self.anchor == "bottom":
            x = self.pos[0] - (bounds.w / 2.0)
            y = self.pos[1] - bounds.h
        else:
            x = self.pos[0] - (bounds.w / 2.0)
            y = self.pos[1] - (bounds.h / 2.0)
        return pygame.Rect(int(round(x)), int(round(y)), bounds.w, bounds.h)

    def _collides_with_world(self, tilemap):
        rect = self.rect()
        for wall in tilemap.physics_rects_around(rect.topleft, rect.size):
            if rect.colliderect(wall):
                return True
        return False

    def update(self, tilemap, player=None):
        if self.life <= 0:
            return False
        self.life -= 1
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]
        self.vel[1] += self.gravity
        if tilemap and self._collides_with_world(tilemap):
            return False
        if player and self.rect().colliderect(player.rect()):
            if player.take_enemy_hit(self.rect().centerx):
                return False
        self.animation.update()
        return self.life > 0

    def render(self, surf, offset=(0, 0)):
        img = self.animation.img()
        if self.flip:
            img = pygame.transform.flip(img, True, False)
        bounds = self._frame_bounds(img)
        rect = self.rect()
        surf.blit(img, (rect.x - bounds.x - offset[0], rect.y - bounds.y - offset[1]))


# rocket variant that leaves a trail and explodes on contact
class ArenaRocketProjectile(ArenaEnemyProjectile):
    def __init__(self, game, action, pos, vel=(0.0, 0.0), life=120, flip=False):
        super().__init__(game, action, pos, vel=vel, gravity=0.0, life=life, anchor="center", flip=flip)
        self.trail_timer = 0
        self.trail_interval = 3

    def _spawn_trail(self):
        trail_anim = getattr(self.game, "assets", {}).get("heavy_rocket_trail")
        if not trail_anim or not getattr(self.game, "effects", None) is not None:
            return
        img = trail_anim.images[0]
        rocket_img = self.animation.img()
        rocket_bounds = self._frame_bounds(rocket_img)
        trail_bounds = self._frame_bounds(img)
        dir_sign = -1 if self.vel[0] < 0 else 1
        rocket_rect = self.rect()
        rocket_draw_x = rocket_rect.x - rocket_bounds.x
        rocket_draw_y = rocket_rect.y - rocket_bounds.y
        if dir_sign < 0:
            tail_center_x = rocket_draw_x + rocket_bounds.right - 1
        else:
            tail_center_x = rocket_draw_x + rocket_bounds.left
        tail_center_y = rocket_draw_y + rocket_bounds.centery
        trail_anchor_x = trail_bounds.x + (trail_bounds.w / 2.0)
        if self.flip:
            trail_anchor_x = img.get_width() - trail_anchor_x
        trail_anchor_y = trail_bounds.y + (trail_bounds.h / 2.0)
        x = tail_center_x - trail_anchor_x
        y = tail_center_y - trail_anchor_y
        self.game.effects.append(
            Effect(
                trail_anim.images,
                (x, y),
                img_dur=getattr(trail_anim, "durations", 2),
                loop=False,
                vel=(-self.vel[0] * 0.14, -self.vel[1] * 0.14),
                damp=(0.92, 0.92),
                flip=self.flip,
            )
        )

    def _explode(self):
        images = getattr(self.game, "effect_images", {}).get("enemy_destroyed")
        if images:
            img = images[0]
            x = self.pos[0] - (img.get_width() / 2.0)
            y = self.pos[1] - (img.get_height() / 2.0)
            self.game.effects.append(Effect(images, (x, y), img_dur=4, loop=False))
        destroy_sound = getattr(self.game, "sfx_enemy_destroyed", None)
        if destroy_sound:
            try:
                destroy_sound.play()
            except Exception:
                pass

    def update(self, tilemap, player=None):
        if self.life <= 0:
            return False
        self.life -= 1
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]
        self.trail_timer -= 1
        if self.trail_timer <= 0:
            self._spawn_trail()
            self.trail_timer = self.trail_interval
        if tilemap and self._collides_with_world(tilemap):
            self._explode()
            return False
        if player and self.rect().colliderect(player.rect()):
            player.take_enemy_hit(self.rect().centerx)
            self._explode()
            return False
        self.animation.update()
        return self.life > 0


# thin extension point for enemy shots that just want explosion cleanup on timeout
class ArenaExplodingProjectile(ArenaEnemyProjectile):
    def _explode(self):
        images = getattr(self.game, "effect_images", {}).get("enemy_destroyed")
        if images:
            img = images[0]
            x = self.pos[0] - (img.get_width() / 2.0)
            y = self.pos[1] - (img.get_height() / 2.0)
            self.game.effects.append(Effect(images, (x, y), img_dur=4, loop=False))
        destroy_sound = getattr(self.game, "sfx_enemy_destroyed", None)
        if destroy_sound:
            try:
                destroy_sound.play()
            except Exception:
                pass

    def update(self, tilemap, player=None):
        if self.life <= 0:
            return False
        self.life -= 1
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]
        self.vel[1] += self.gravity
        if tilemap and self._collides_with_world(tilemap):
            self._explode()
            return False
        if player and self.rect().colliderect(player.rect()):
            player.take_enemy_hit(self.rect().centerx)
            self._explode()
            return False
        self.animation.update()
        return self.life > 0


# projectile that keeps a rotated sprite aligned with its launch angle
class ArenaAngledProjectile(ArenaEnemyProjectile):
    def __init__(self, game, action, pos, vel=(0.0, 0.0), gravity=0.0, life=180, angle_degrees=None, base_angle_degrees=0.0):
        super().__init__(game, action, pos, vel=vel, gravity=gravity, life=life, anchor="center")
        if angle_degrees is None:
            angle_degrees = math.degrees(-math.atan2(self.vel[1], self.vel[0])) if (self.vel[0] or self.vel[1]) else 0.0
        self.angle_degrees = float(angle_degrees)
        self.base_angle_degrees = float(base_angle_degrees)

    def _rotated_image(self):
        img = self.animation.img()
        return pygame.transform.rotate(img, self.angle_degrees - self.base_angle_degrees)

    def rect(self):
        img = self._rotated_image()
        bounds = img.get_bounding_rect()
        return pygame.Rect(
            int(round(self.pos[0] - (bounds.w / 2.0))),
            int(round(self.pos[1] - (bounds.h / 2.0))),
            bounds.w,
            bounds.h,
        )

    def render(self, surf, offset=(0, 0)):
        img = self._rotated_image()
        bounds = img.get_bounding_rect()
        rect = self.rect()
        surf.blit(img, (rect.x - bounds.x - offset[0], rect.y - bounds.y - offset[1]))


# heli-rocket shot with its own default action art
class ArenaHeliRocketProjectile(ArenaEnemyProjectile):
    def __init__(self, game, pos, vel=(0.0, 0.0), life=140, flip=False):
        super().__init__(game, 'heli_rocket_ammo_1', pos, vel=vel, gravity=0.0, life=life, anchor="center", flip=flip)
        ammo_1 = game.assets['heli_rocket_ammo_1']
        ammo_2 = game.assets['heli_rocket_ammo_2']
        self.animation = Animation(
            [ammo_1.images[0], ammo_2.images[0]],
            [4, 4],
            loop=True,
        )


# projectile that snaps down to the floor so ground enemies can fire along terrain
class ArenaGroundProjectile(ArenaEnemyProjectile):
    def __init__(self, game, action, pos, vel=(0.0, 0.0), life=180, ground_snap=8):
        super().__init__(game, action, pos, vel=vel, gravity=0.0, life=life, anchor="bottom")
        self.ground_snap = max(1, int(ground_snap))

    def _snap_to_ground(self, tilemap):
        rect = self.rect()
        support = pygame.Rect(rect.left + 2, rect.bottom, max(1, rect.w - 4), self.ground_snap + 1)
        best_rect = None
        best_distance = None
        for ground in tilemap.physics_rects_around(support.topleft, support.size):
            if ground.left >= support.right or ground.right <= support.left:
                continue
            if rect.colliderect(ground):
                return False
            distance = ground.top - rect.bottom
            if 0 <= distance <= self.ground_snap:
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_rect = ground
        if best_rect is None:
            return False
        self.pos[1] += best_rect.top - rect.bottom
        return True

    def update(self, tilemap, player=None):
        if self.life <= 0:
            return False
        self.life -= 1
        self.pos[0] += self.vel[0]
        if tilemap:
            rect = self.rect()
            for wall in tilemap.physics_rects_around(rect.topleft, rect.size):
                if rect.colliderect(wall):
                    return False
            if not self._snap_to_ground(tilemap):
                return False
        if player and self.rect().colliderect(player.rect()):
            if player.take_enemy_hit(self.rect().centerx):
                return False
        self.animation.update()
        return self.life > 0


# projectile that crawls along walls / ceilings by following nearby solid surfaces
class ArenaSurfaceCrawlerProjectile(ArenaEnemyProjectile):
    def __init__(self, game, action, pos, move_dir=1, fall_speed=2.1, crawl_speed=1.4, life=260, air_drift=0.0):
        super().__init__(game, action, pos, vel=(0.0, 0.0), gravity=0.0, life=life, anchor="center")
        self.move_dir = 1 if move_dir >= 0 else -1
        self.fall_speed = float(fall_speed)
        self.crawl_speed = float(crawl_speed)
        self.air_drift = float(air_drift)
        self.surface_normal = None
        self.surface_snap = 8
        self.detach_grace = 10

    def _rect_at(self, center):
        img = self.animation.img()
        bounds = self._frame_bounds(img)
        return pygame.Rect(
            int(round(center[0] - (bounds.w / 2.0))),
            int(round(center[1] - (bounds.h / 2.0))),
            bounds.w,
            bounds.h,
        )

    def _rect_collides(self, tilemap, rect):
        for wall in tilemap.physics_rects_around(rect.topleft, rect.size):
            if rect.colliderect(wall):
                return True
        return False

    def _snap_rect_to_surface(self, tilemap, rect, normal, max_gap=None):
        max_gap = self.surface_snap if max_gap is None else max_gap
        best_rect = None
        best_gap = None
        for wall in tilemap.physics_rects_around(rect.topleft, rect.size):
            if normal == (0, -1):
                if wall.left >= rect.right or wall.right <= rect.left:
                    continue
                gap = wall.top - rect.bottom
                if rect.colliderect(wall):
                    candidate = rect.copy()
                    candidate.bottom = wall.top
                    return candidate
                if 0 <= gap <= max_gap and (best_gap is None or gap < best_gap):
                    candidate = rect.copy()
                    candidate.y += gap
                    best_gap = gap
                    best_rect = candidate
            elif normal == (0, 1):
                if wall.left >= rect.right or wall.right <= rect.left:
                    continue
                gap = rect.top - wall.bottom
                if rect.colliderect(wall):
                    candidate = rect.copy()
                    candidate.top = wall.bottom
                    return candidate
                if 0 <= gap <= max_gap and (best_gap is None or gap < best_gap):
                    candidate = rect.copy()
                    candidate.y -= gap
                    best_gap = gap
                    best_rect = candidate
            elif normal == (1, 0):
                if wall.top >= rect.bottom or wall.bottom <= rect.top:
                    continue
                gap = rect.left - wall.right
                if rect.colliderect(wall):
                    candidate = rect.copy()
                    candidate.left = wall.right
                    return candidate
                if 0 <= gap <= max_gap and (best_gap is None or gap < best_gap):
                    candidate = rect.copy()
                    candidate.x -= gap
                    best_gap = gap
                    best_rect = candidate
            elif normal == (-1, 0):
                if wall.top >= rect.bottom or wall.bottom <= rect.top:
                    continue
                gap = wall.left - rect.right
                if rect.colliderect(wall):
                    candidate = rect.copy()
                    candidate.right = wall.left
                    return candidate
                if 0 <= gap <= max_gap and (best_gap is None or gap < best_gap):
                    candidate = rect.copy()
                    candidate.x += gap
                    best_gap = gap
                    best_rect = candidate
        return best_rect

    def _set_center_from_rect(self, rect):
        self.pos[0] = rect.centerx
        self.pos[1] = rect.centery

    def _surface_half_extents(self, center):
        rect = self._rect_at(center)
        return rect.w / 2.0, rect.h / 2.0

    def _solid_tile_at_pixel(self, tilemap, px, py):
        tile_size = getattr(tilemap, "tile_size", 16) or 16
        tx = int(math.floor(px / tile_size))
        ty = int(math.floor(py / tile_size))
        tile = getattr(tilemap, "tilemap", {}).get(f"{tx};{ty}")
        if not tile or tile.get("type") not in PHYSICS_TILES:
            return None
        return tile

    def _snap_center_to_surface(self, tilemap, center, normal):
        half_w, half_h = self._surface_half_extents(center)
        if normal == (0, -1):
            tile = self._solid_tile_at_pixel(tilemap, center[0], center[1] + half_h + 1)
            if not tile:
                return None
            return (center[0], (tile["pos"][1] * tilemap.tile_size) - half_h)
        if normal == (0, 1):
            tile = self._solid_tile_at_pixel(tilemap, center[0], center[1] - half_h - 1)
            if not tile:
                return None
            return (center[0], ((tile["pos"][1] + 1) * tilemap.tile_size) + half_h)
        if normal == (1, 0):
            tile = self._solid_tile_at_pixel(tilemap, center[0] - half_w - 1, center[1])
            if not tile:
                return None
            return (((tile["pos"][0] + 1) * tilemap.tile_size) + half_w, center[1])
        if normal == (-1, 0):
            tile = self._solid_tile_at_pixel(tilemap, center[0] + half_w + 1, center[1])
            if not tile:
                return None
            return ((tile["pos"][0] * tilemap.tile_size) - half_w, center[1])
        return None

    def _find_surface_near(self, tilemap, center, normal, radius, prefer=(0, 0)):
        radius = max(0, int(radius))
        pref_x, pref_y = prefer
        for dist in range(radius + 1):
            offsets = []
            if dist == 0:
                offsets.append((0, 0))
            else:
                for dx in range(-dist, dist + 1):
                    dy = dist - abs(dx)
                    offsets.append((dx, dy))
                    if dy != 0:
                        offsets.append((dx, -dy))
            offsets.sort(key=lambda off: -((off[0] * pref_x) + (off[1] * pref_y)))
            for dx, dy in offsets:
                snapped = self._snap_center_to_surface(tilemap, (center[0] + dx, center[1] + dy), normal)
                if snapped is not None:
                    return snapped
        return None

    def _snap_outer_corner(self, tilemap, center, new_normal):
        search = max(2, int(getattr(tilemap, "tile_size", 16)))
        tangent = self._tangent()
        old_normal = self.surface_normal if self.surface_normal is not None else (0, -1)
        prefer = (-old_normal[0] - tangent[0], -old_normal[1] - tangent[1])
        return self._find_surface_near(tilemap, center, new_normal, search, prefer=prefer)

    def _advance_freefall(self, tilemap):
        remaining_h = abs(self.air_drift)
        remaining_v = abs(self.fall_speed)
        while remaining_h > 0.0 or remaining_v > 0.0:
            step_h = min(1.0, remaining_h)
            step_v = min(1.0, remaining_v)
            if step_h > 0.0:
                self.pos[0] += self.move_dir * step_h
                remaining_h -= step_h
            if step_v > 0.0:
                self.pos[1] += step_v
                remaining_v -= step_v
            snapped_floor = self._snap_center_to_surface(tilemap, tuple(self.pos), (0, -1))
            if snapped_floor is None:
                search = max(2, int(getattr(tilemap, "tile_size", 16) // 2))
                snapped_floor = self._find_surface_near(
                    tilemap,
                    tuple(self.pos),
                    (0, -1),
                    search,
                    prefer=(-self.move_dir, 1),
                )
            snapped_wall = None
            if snapped_floor is None:
                wall_normal = (self.move_dir, 0)
                search = max(2, int(getattr(tilemap, "tile_size", 16) // 2))
                snapped_wall = self._find_surface_near(
                    tilemap,
                    tuple(self.pos),
                    wall_normal,
                    search,
                    prefer=(-self.move_dir, 1),
                )
            snapped = snapped_floor if snapped_floor is not None else snapped_wall
            if snapped is not None:
                if snapped_floor is not None:
                    self.surface_normal = (0, -1)
                else:
                    self.surface_normal = (self.move_dir, 0)
                self.pos[0], self.pos[1] = snapped
                self.detach_grace = 18
                return

    def _advance_on_surface(self, tilemap):
        remaining = abs(self.crawl_speed)
        while remaining > 0.0 and self.surface_normal is not None:
            step = min(1.0, remaining)
            tangent = self._tangent()
            next_center = (
                self.pos[0] + (tangent[0] * step),
                self.pos[1] + (tangent[1] * step),
            )
            next_rect = self._rect_at(next_center)
            if self._rect_collides(tilemap, next_rect):
                new_normal = (-tangent[0], -tangent[1])
                turned = self._snap_center_to_surface(tilemap, next_center, new_normal)
                if turned is None:
                    self.surface_normal = None
                    break
                self.surface_normal = new_normal
                self.pos[0], self.pos[1] = turned
                self.detach_grace = 18
            else:
                snapped = self._snap_center_to_surface(tilemap, next_center, self.surface_normal)
                if snapped is not None:
                    self.pos[0], self.pos[1] = snapped
                    self.detach_grace = 18
                else:
                    new_normal = tangent
                    turned = self._snap_outer_corner(tilemap, next_center, new_normal)
                    if turned is None:
                        self.surface_normal = None
                        break
                    self.surface_normal = new_normal
                    self.pos[0], self.pos[1] = turned
                    self.detach_grace = 18
            remaining -= step
        return True

    def _tangent(self):
        normal = self.surface_normal
        return (-normal[1] * self.move_dir, normal[0] * self.move_dir)

    def _freefall_tangent(self):
        return (self.move_dir, 0)

    def update(self, tilemap, player=None):
        if self.life <= 0:
            return False
        self.life -= 1
        if not tilemap:
            return False

        if self.surface_normal is None:
            self._advance_freefall(tilemap)
        else:
            if not self._advance_on_surface(tilemap):
                return False
            if self.surface_normal is None:
                self.detach_grace -= 1
                if self.detach_grace <= 0:
                    return False

        if player and self.rect().colliderect(player.rect()):
            if player.take_enemy_hit(self.rect().centerx):
                return False
        self.animation.update()
        return self.life > 0


# paired shocker bolts for the heavy enemy's floor-hugging attack
class ArenaHeavyShockerPairProjectile(ArenaSurfaceCrawlerProjectile):
    def __init__(self, game, action, pos, move_dir=1, fall_speed=2.1, crawl_speed=1.4, life=260, pair_gap=8, air_drift=0.0):
        super().__init__(
            game,
            action,
            pos,
            move_dir=move_dir,
            fall_speed=fall_speed,
            crawl_speed=crawl_speed,
            life=life,
            air_drift=air_drift,
        )
        self.pair_gap = pair_gap
        self.detach_grace = 18
        self.surface_span = None

    def _pair_normal(self):
        return self.surface_normal if self.surface_normal is not None else (0, -1)

    def _secondary_center(self):
        nx, ny = self._pair_normal()
        return (self.pos[0] - (nx * self.pair_gap), self.pos[1] - (ny * self.pair_gap))

    def rect(self):
        primary = super().rect()
        secondary = self._rect_at(self._secondary_center())
        return primary.union(secondary)

    def render(self, surf, offset=(0, 0)):
        img = self.animation.img()
        bounds = self._frame_bounds(img)
        for center in (tuple(self.pos), self._secondary_center()):
            rect = self._rect_at(center)
            surf.blit(img, (rect.x - bounds.x - offset[0], rect.y - bounds.y - offset[1]))

    def _primary_rect(self):
        return super().rect()

    def _find_support_rect(self, tilemap):
        rect = self._primary_rect()
        support = pygame.Rect(
            rect.left + 1,
            rect.bottom - 1,
            max(1, rect.w - 2),
            self.surface_snap + 3,
        )
        best_rect = None
        best_distance = None
        for ground in tilemap.physics_rects_around(support.topleft, support.size):
            if ground.left >= support.right or ground.right <= support.left:
                continue
            distance = ground.top - rect.bottom
            if rect.colliderect(ground):
                distance = 0
            if -1 <= distance <= self.surface_snap + 1:
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_rect = ground
        return best_rect.copy() if best_rect is not None else None

    def _surface_span_from_rect(self, tilemap, seed_rect):
        target_top = seed_rect.top
        tile_size = max(8, int(getattr(tilemap, "tile_size", 16) or 16))
        join_gap = max(1, tile_size // 8)
        visited = set()
        pending = [seed_rect.copy()]
        span_left = seed_rect.left
        span_right = seed_rect.right
        while pending:
            rect = pending.pop()
            key = (rect.x, rect.y, rect.w, rect.h)
            if key in visited:
                continue
            visited.add(key)
            span_left = min(span_left, rect.left)
            span_right = max(span_right, rect.right)
            query = pygame.Rect(
                rect.left - tile_size - join_gap,
                target_top - tile_size,
                rect.width + ((tile_size + join_gap) * 2),
                rect.height + (tile_size * 2),
            )
            for neighbor in tilemap.physics_rects_around(query.topleft, query.size):
                neighbor_key = (neighbor.x, neighbor.y, neighbor.w, neighbor.h)
                if neighbor_key in visited:
                    continue
                if abs(neighbor.top - target_top) > 1:
                    continue
                if neighbor.right < rect.left - join_gap or neighbor.left > rect.right + join_gap:
                    continue
                pending.append(neighbor.copy())
        return pygame.Rect(span_left, target_top, max(1, span_right - span_left), max(1, seed_rect.height))

    def _lock_surface_span(self, tilemap):
        support_rect = self._find_support_rect(tilemap)
        if support_rect is None:
            return False
        self.surface_normal = (0, -1)
        snapped = self._snap_center_to_surface(tilemap, tuple(self.pos), self.surface_normal)
        if snapped is None:
            return False
        self.pos[0], self.pos[1] = snapped
        self.surface_span = self._surface_span_from_rect(tilemap, support_rect)
        rect = self._primary_rect()
        if self.move_dir > 0:
            remaining = max(0.0, self.surface_span.right - rect.right)
        else:
            remaining = max(0.0, rect.left - self.surface_span.left)
        if self.crawl_speed > 0:
            frames_needed = int(math.ceil(remaining / self.crawl_speed)) + 2
            self.life = max(self.life, frames_needed)
        return True

    def _reached_surface_end(self):
        if self.surface_span is None:
            return False
        rect = self._primary_rect()
        if self.move_dir > 0:
            return rect.right >= self.surface_span.right
        return rect.left <= self.surface_span.left

    def _advance_across_surface(self, tilemap):
        remaining = abs(self.crawl_speed)
        while remaining > 0.0:
            step = min(1.0, remaining)
            next_center = (self.pos[0] + (self.move_dir * step), self.pos[1])
            snapped = self._snap_center_to_surface(tilemap, next_center, (0, -1))
            if snapped is None:
                return False
            self.pos[0], self.pos[1] = snapped
            if self._reached_surface_end():
                return False
            remaining -= step
        return True

    def update(self, tilemap, player=None):
        if self.life <= 0:
            return False
        self.life -= 1
        if not tilemap:
            return False

        if self.surface_span is None:
            if self.surface_normal is None:
                self._advance_freefall(tilemap)
            if self.surface_normal is not None and tuple(self.surface_normal) != (0, -1):
                return False
            if self.surface_normal == (0, -1) and not self._lock_surface_span(tilemap):
                return False
        elif not self._advance_across_surface(tilemap):
            return False

        if player and self.rect().colliderect(player.rect()):
            if player.take_enemy_hit(self.rect().centerx):
                return False
        self.animation.update()
        return self.life > 0


# common enemy health, facing, and grounded-movement helpers live here
class ArenaEnemyBase(ArenaPhysicsEntity):
    def __init__(self, game, pos, size, action, spawn_delay=0, anchor_mode="bottom"):
        self.anchor_mode = anchor_mode
        self._bounds_cache = {}
        super().__init__(game, 'enemy', pos, size)
        self.ignore_auto_flip = False
        self.spawn_delay = spawn_delay
        self.max_health = 1
        self.health = self.max_health
        self.hit_flash_timer = 0
        self.hit_flash_time = 18
        self.last_sword_attack_id = -1
        self.drop_table = [
            (None, 64, 0),
            ("small_hp_pickup", 20, 4),
            ("large_hp_pickup", 5, 8),
            ("small_special_ammo_pickup", 9, 4),
            ("large_special_ammo_pickup", 2, 8),
        ]
        self.score_value = 100
        self.camera_activation_pending = True
        self.set_action(action, force=True)

    def _frame_bounds(self, img):
        key = id(img)
        bounds = self._bounds_cache.get(key)
        if bounds is not None:
            return bounds
        mask = pygame.mask.from_surface(img)
        rects = mask.get_bounding_rects()
        if rects:
            min_x = min(r.x for r in rects)
            min_y = min(r.y for r in rects)
            max_x = max(r.x + r.w for r in rects)
            max_y = max(r.y + r.h for r in rects)
            bounds = pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
        else:
            bounds = img.get_bounding_rect()
            if bounds.width <= 0 or bounds.height <= 0:
                bounds = pygame.Rect(0, 0, img.get_width(), img.get_height())
        self._bounds_cache[key] = bounds
        return bounds

    def _draw_offset(self, img):
        if img is None:
            return 0, 0
        bounds = self._frame_bounds(img)
        anchor_x = bounds.x + (bounds.w / 2.0)
        if self.flip:
            anchor_x = img.get_width() - anchor_x
        if self.anchor_mode == "center":
            anchor_y = bounds.y + (bounds.h / 2.0)
            oy = (self._hh / 2.0) - anchor_y
        else:
            anchor_y = bounds.bottom
            oy = self._hh - anchor_y
        ox = (self._hw / 2.0) - anchor_x
        return int(round(ox)), int(round(oy))

    def _hitbox_offsets(self):
        if not hasattr(self, 'animation'):
            return 0, 0
        return 0, 0

    def _hurt_render_alpha(self):
        if self.hit_flash_timer <= 0:
            return 255
        return 0 if (self.hit_flash_timer // 3) % 2 == 0 else 255

    def _update_common(self):
        # common enemy gatekeeping: hit flash, spawn delay, and camera activation timing
        if self.hit_flash_timer > 0:
            self.hit_flash_timer -= 1
        if self.spawn_delay > 0:
            self.spawn_delay -= 1
            self.animation.update()
            return False
        if self.camera_activation_pending:
            if self._is_in_active_view(margin=24):
                self.camera_activation_pending = False
            else:
                self.animation.update()
                return False
        return True

    def _player_offset(self, player):
        if player is None:
            return None
        own_rect = self.rect()
        player_rect = player.rect()
        return (
            player_rect.centerx - own_rect.centerx,
            player_rect.centery - own_rect.centery,
        )

    def _player_in_range(self, player, *, x_range=None, y_range=None, radial_range=None):
        offset = self._player_offset(player)
        if offset is None:
            return False
        dx, dy = offset
        if x_range is not None and abs(dx) > x_range:
            return False
        if y_range is not None and abs(dy) > y_range:
            return False
        if radial_range is not None and math.hypot(dx, dy) > radial_range:
            return False
        return True

    def _snap_to_ground(self, tilemap, snap_height=3):
        if not tilemap:
            return False
        if self.velocity[1] < 0:
            return False
        rect = self.rect()
        best_rect = None
        best_distance = None
        for ground in tilemap.physics_rects_around(rect.topleft, rect.size):
            if ground.left >= rect.right or ground.right <= rect.left:
                continue
            distance = ground.top - rect.bottom
            if 0 <= distance <= snap_height:
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_rect = ground
        if best_rect is None:
            return False
        ox, oy = self._hitbox_offsets()
        self.pos[1] = best_rect.top - self._hh - oy
        self.collisions['down'] = True
        self.velocity[1] = 0
        return True

    def _has_ground_ahead(self, tilemap, dir_sign, lookahead=4, probe_depth=10):
        if not tilemap:
            return True
        rect = self.rect()
        probe_w = max(4, rect.w // 3)
        edge_inset = min(3, max(0, rect.w - probe_w))
        if dir_sign < 0:
            probe_left = rect.left + edge_inset - max(1, int(round(abs(lookahead))))
        else:
            probe_left = rect.right - probe_w - edge_inset + max(1, int(round(abs(lookahead))))
        support_probe = pygame.Rect(
            int(round(probe_left)),
            rect.bottom,
            probe_w,
            max(2, int(round(probe_depth))),
        )
        best_distance = None
        for ground in tilemap.physics_rects_around(support_probe.topleft, support_probe.size):
            if ground.left >= support_probe.right or ground.right <= support_probe.left:
                continue
            distance = ground.top - rect.bottom
            if 0 <= distance <= probe_depth:
                if best_distance is None or distance < best_distance:
                    best_distance = distance
        return best_distance is not None

    def _should_turn_at_ledge(self, tilemap, dir_sign, lookahead=4, probe_depth=10):
        if not self.collisions.get('down', False):
            return False
        return not self._has_ground_ahead(tilemap, dir_sign, lookahead=lookahead, probe_depth=probe_depth)

    def render(self, surf, offset=(0, 0)):
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        draw_x = int(self.pos[0] - offset[0]) + int(ox)
        draw_y = int(self.pos[1] - offset[1]) + int(oy)
        frame = pygame.transform.flip(img, self.flip, False)
        if self.spawn_delay > 0:
            ready_alpha = max(70, 255 - min(180, self.spawn_delay * 3))
            faded = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            faded.blit(frame, (0, 0))
            faded.fill((255, 255, 255, ready_alpha), special_flags=pygame.BLEND_RGBA_MULT)
            frame = faded
        alpha = self._hurt_render_alpha()
        if alpha < 255:
            faded = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            faded.blit(frame, (0, 0))
            faded.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            frame = faded
        surf.blit(frame, (draw_x, draw_y))

    def on_hit_player(self, player):
        return None

    def take_sword_hit(self, player):
        if self.spawn_delay > 0:
            return False
        attack_id = getattr(player, "attack_instance_id", 0)
        if attack_id == self.last_sword_attack_id:
            return False
        self.last_sword_attack_id = attack_id
        self.health = max(0, self.health - 1)
        self.hit_flash_timer = self.hit_flash_time
        hitmarker_sound = getattr(self.game, 'sfx_hitmarker', None)
        if hitmarker_sound:
            try:
                hitmarker_sound.play()
            except Exception:
                pass
        return self.health <= 0

    def take_giga_hit(self):
        if self.spawn_delay > 0:
            return False
        self.health = 0
        self.hit_flash_timer = 0
        return True

    def roll_pickup_drop(self):
        if not self.drop_table:
            return None
        total_weight = sum(max(0, entry[1]) for entry in self.drop_table)
        if total_weight <= 0:
            return None
        roll = random.uniform(0, total_weight)
        upto = 0.0
        for pickup_key, weight, amount in self.drop_table:
            weight = max(0, weight)
            upto += weight
            if roll <= upto:
                if not pickup_key:
                    return None
                return {"pickup_key": pickup_key, "amount": amount}
        return None


# lightweight flier that mostly exists to pressure the player horizontally
class ArenaBirdEnemy(ArenaEnemyBase):
    def __init__(self, game, pos, move_dir=1, flight_slope=0.0, spawn_delay=0):
        super().__init__(game, pos, (30, 14), 'bird_flying', spawn_delay=spawn_delay, anchor_mode="center")
        self.ignore_auto_flip = True
        self.max_health = 1
        self.health = self.max_health
        self.score_value = 90
        self.move_dir = 1 if move_dir >= 0 else -1
        self.flight_slope = float(flight_slope)
        self.flight_speed = 3.2
        self.sprite_anchor_x = 64
        self.sprite_anchor_y = 64
        self.expired = False
        self._set_facing_dir(self.move_dir)

    def _set_facing_dir(self, dir_sign):
        # Bird art is authored facing left by default.
        self.flip = dir_sign > 0

    def _draw_offset(self, img):
        anchor_x = self.sprite_anchor_x
        if self.flip:
            anchor_x = img.get_width() - anchor_x
        ox = int(round((self._hw / 2.0) - anchor_x))
        oy = int(round((self._hh / 2.0) - self.sprite_anchor_y))
        return ox, oy

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self._update_common():
            return
        self._set_facing_dir(self.move_dir)
        self.set_action('bird_flying')
        self.pos[0] += self.flight_speed * self.move_dir
        self.pos[1] += self.flight_slope
        if arena_bounds:
            ox, oy, w, h = arena_bounds
            margin = 72
            rect = self.rect()
            if rect.right < ox - margin or rect.left > ox + w + margin or rect.bottom < oy - margin or rect.top > oy + h + margin:
                self.expired = True
        self.animation.update()


# rolling ground threat with a compact, fast-moving body
class ArenaWheelEnemy(ArenaEnemyBase):
    def __init__(self, game, pos, spawn_delay=0):
        super().__init__(game, pos, (26, 26), 'wheel_moving', spawn_delay=spawn_delay, anchor_mode="bottom")
        self.max_health = 1
        self.health = self.max_health
        self.score_value = 110
        self.move_speed = 1.35
        self.move_dir = random.choice((-1, 1))
        self.sprite_anchor_x = 64
        self.sprite_anchor_y = 82

    def _draw_offset(self, img):
        ox = int(round((self._hw / 2.0) - self.sprite_anchor_x))
        oy = int(round(self._hh - self.sprite_anchor_y))
        return ox, oy

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self._update_common():
            return
        self.set_action('wheel_moving')
        if tilemap and self.collisions.get('down') and self._should_turn_at_ledge(tilemap, self.move_dir, lookahead=8, probe_depth=14):
            self.move_dir *= -1
        super().update(tilemap, movement=(self.move_dir * self.move_speed, 0))
        self._snap_to_ground(tilemap)
        if self.collisions['left'] or self.collisions['right']:
            self.move_dir *= -1


# wall / floor spike bot that can mount surfaces and fire from its tips
class ArenaSpikeEnemy(ArenaEnemyBase):
    def __init__(self, game, pos, surface_normal=(1, 0), move_dir=1, spawn_delay=0):
        super().__init__(game, pos, (23, 40), 'spike_move', spawn_delay=spawn_delay, anchor_mode="center")
        self.ignore_auto_flip = True
        self.max_health = 2
        self.health = self.max_health
        self.score_value = 170
        self.surface_normal = surface_normal
        self.move_dir = 1 if move_dir >= 0 else -1
        self.fall_speed = 1.8
        self.crawl_speed = 0.62
        self.surface_snap = 8
        self.detach_grace = 12
        self.state = 'move'
        self.attack_cooldown = random.randint(130, 210)
        self.attack_range = 180
        self.notice_range_x = 170
        self.notice_range_y = 110
        self.shot_fired = False
        self.expired = False
        self.can_move = True
        self.surface_mode = 'vertical' if surface_normal[0] != 0 else 'ceiling'
        self.flash_frame_start = 4
        self.flash_frame_end = 5
        self.fire_frame = 5
        base_img = self.game.assets['spike_idle'].images[0]
        bounds = self._frame_bounds(base_img)
        self.sprite_bounds = bounds
        self.sprite_center_local = (bounds.centerx, bounds.centery)
        mount_face_x = float(bounds.left)
        mask = pygame.mask.from_surface(base_img)
        face_pixels = []
        face_limit = min(base_img.get_width(), bounds.left + 5)
        for y in range(bounds.top, bounds.bottom):
            for x in range(bounds.left, face_limit):
                if mask.get_at((x, y)):
                    face_pixels.append((x, y))
        if face_pixels:
            mount_face_x = sum(x for x, _ in face_pixels) / len(face_pixels)
        self.mount_depth = self.sprite_center_local[0] - mount_face_x
        self.cross_half = max(
            self.sprite_center_local[1] - bounds.top,
            bounds.bottom - self.sprite_center_local[1],
        )
        # Tip emitter positions in the default right-facing sprite orientation.
        self.tip_offsets_local = (
            {'flash_action': 'spike_flash_diagonal_1', 'projectile_action': 'spike_projectile_diagonal_1', 'offset': (8.0, -14.0), 'base_angle': 45.0},
            {'flash_action': 'spike_flash_straight', 'projectile_action': 'spike_projectile_straight', 'offset': (11.0, 0.0), 'base_angle': 0.0},
            {'flash_action': 'spike_flash_diagonal_2', 'projectile_action': 'spike_projectile_diagonal_2', 'offset': (8.0, 14.0), 'base_angle': -45.0},
        )
        if self.can_move:
            self._set_move_animation(force=True)

    def _set_move_animation(self, force=False):
        if force or self.action != 'spike_move':
            idle_img = self.game.assets['spike_idle'].images[0]
            move_img = self.game.assets['spike_move'].images[0]
            self.action = 'spike_move'
            self.animation = Animation([idle_img, move_img], [7, 7], loop=True)
            size = HITBOX_SIZES.get('spike_move', (self.size[0], HITBOX_H))
            self._hw = size[0]
            self._hh = size[1]

    def camera_center(self):
        return (self.pos[0], self.pos[1])

    def _oriented_hitbox_size(self):
        normal = getattr(self, "surface_normal", None)
        if normal is not None and normal[0] == 0:
            return self._hh, self._hw
        return self._hw, self._hh

    def rect(self):
        rect_w, rect_h = self._oriented_hitbox_size()
        return pygame.Rect(
            int(round(self.pos[0] - (rect_w / 2.0))),
            int(round(self.pos[1] - (rect_h / 2.0))),
            rect_w,
            rect_h,
        )

    def _rect_at(self, center):
        rect_w, rect_h = self._oriented_hitbox_size()
        return pygame.Rect(
            int(round(center[0] - (rect_w / 2.0))),
            int(round(center[1] - (rect_h / 2.0))),
            rect_w,
            rect_h,
        )

    def _surface_angle(self):
        return {
            (1, 0): 0,
            (0, -1): 90,
            (-1, 0): 180,
            (0, 1): -90,
        }.get(self.surface_normal or (1, 0), 0)

    def _surface_half_extents(self, center=None):
        if self.surface_normal is None:
            return self._hw / 2.0, self._hh / 2.0
        if self.surface_normal[0] != 0:
            return self.mount_depth, self.cross_half
        return self.cross_half, self.mount_depth

    def _platform_side_visual_bias(self):
        return 0.0

    def _is_arena_boundary_side(self, tilemap, center=None, normal=None):
        edges = self._inner_arena_edges(tilemap)
        if edges is None:
            return False
        center = center if center is not None else tuple(self.pos)
        normal = normal if normal is not None else self.surface_normal
        if normal is None or normal[0] == 0:
            return False
        inner_left, inner_right, _, _ = edges
        half_w, _ = self._surface_half_extents(center)
        tolerance = 1.5
        if normal == (1, 0):
            return abs(center[0] - (inner_left + half_w)) <= tolerance
        if normal == (-1, 0):
            return abs(center[0] - (inner_right - half_w)) <= tolerance
        return False

    def _platform_side_center(self, tilemap, center, normal=None):
        normal = normal if normal is not None else self.surface_normal
        if normal is None or normal[0] == 0:
            return center
        half_w, _ = self._surface_half_extents(center)
        tile_size = getattr(tilemap, "tile_size", 16) or 16
        bias_y = self._platform_side_visual_bias()
        if normal == (1, 0):
            tile = self._solid_tile_at_pixel(tilemap, center[0] - half_w - 1, center[1])
            if tile is None:
                return center
            tile_left = tile["pos"][0] * tile_size
            tile_top = tile["pos"][1] * tile_size
            return (tile_left + tile_size + half_w, tile_top + (tile_size / 2.0) + bias_y)
        if normal == (-1, 0):
            tile = self._solid_tile_at_pixel(tilemap, center[0] + half_w + 1, center[1])
            if tile is None:
                return center
            tile_left = tile["pos"][0] * tile_size
            tile_top = tile["pos"][1] * tile_size
            return (tile_left - half_w, tile_top + (tile_size / 2.0) + bias_y)
        return center

    def _visual_center_world(self):
        img = self.animation.img()
        base_center = pygame.Vector2(img.get_width() / 2.0, img.get_height() / 2.0)
        visual_center = pygame.Vector2(self.sprite_center_local)
        delta = visual_center - base_center
        angle = -self._surface_angle()
        rotated_delta = delta.rotate(angle)
        return (self.pos[0] - rotated_delta.x, self.pos[1] - rotated_delta.y)

    def _inner_arena_edges(self, tilemap):
        arena_bounds = getattr(self.game, "arena_bounds", None)
        tile_size = getattr(tilemap, "tile_size", 0) or 0
        if not arena_bounds or tile_size <= 0:
            return None
        ox, oy, w, h = arena_bounds
        return (
            ox + tile_size,
            (ox + w) - tile_size,
            oy + tile_size,
            (oy + h) - tile_size,
        )

    def _solid_tile_at_pixel(self, tilemap, px, py):
        tile_size = getattr(tilemap, "tile_size", 16) or 16
        tx = int(math.floor(px / tile_size))
        ty = int(math.floor(py / tile_size))
        tile = getattr(tilemap, "tilemap", {}).get(f"{tx};{ty}")
        if not tile or tile.get("type") not in PHYSICS_TILES:
            return None
        return tile

    def _surface_rect_at_pixel(self, tilemap, px, py):
        tile = self._solid_tile_at_pixel(tilemap, px, py)
        if tile is not None:
            tile_size = getattr(tilemap, "tile_size", 16) or 16
            return pygame.Rect(
                tile["pos"][0] * tile_size,
                tile["pos"][1] * tile_size,
                tile_size,
                tile_size,
            )
        probe = pygame.Rect(int(math.floor(px)), int(math.floor(py)), 1, 1)
        for rect in tilemap.physics_rects_around(probe.topleft, probe.size):
            if rect.collidepoint(probe.x, probe.y):
                return rect
        return None

    def _rect_collides(self, tilemap, rect):
        for wall in tilemap.physics_rects_around(rect.topleft, rect.size):
            if rect.colliderect(wall):
                return True
        edges = self._inner_arena_edges(tilemap)
        if edges is not None:
            inner_left, inner_right, inner_top, inner_bottom = edges
            if rect.left < inner_left or rect.right > inner_right or rect.top < inner_top or rect.bottom > inner_bottom:
                return True
        return False

    def _snap_center_to_arena_surface(self, tilemap, center, normal, source_center=None):
        edges = self._inner_arena_edges(tilemap)
        if edges is None:
            return None
        inner_left, inner_right, inner_top, inner_bottom = edges
        tile_size = getattr(tilemap, "tile_size", 16) or 16
        half_w, half_h = self._surface_half_extents(center)
        src_x, src_y = source_center if source_center is not None else center
        margin = max(6.0, tile_size * 1.25)
        if normal == (0, -1):
            target_y = inner_bottom - half_h
            if abs(src_y - target_y) > margin:
                return None
            if inner_left <= center[0] <= inner_right:
                return (center[0], target_y)
        if normal == (0, 1):
            target_y = inner_top + half_h
            if abs(src_y - target_y) > margin:
                return None
            if inner_left <= center[0] <= inner_right:
                return (center[0], target_y)
        if normal == (1, 0):
            target_x = inner_left + half_w
            if abs(src_x - target_x) > margin:
                return None
            if inner_top <= center[1] <= inner_bottom:
                return (target_x, center[1])
        if normal == (-1, 0):
            target_x = inner_right - half_w
            if abs(src_x - target_x) > margin:
                return None
            if inner_top <= center[1] <= inner_bottom:
                return (target_x, center[1])
        return None

    def _snap_center_to_surface(self, tilemap, center, normal, source_center=None, allow_arena_bounds=True):
        half_w, half_h = self._surface_half_extents(center)
        if normal == (0, -1):
            surface = self._surface_rect_at_pixel(tilemap, center[0], center[1] + half_h + 1)
            if not surface:
                if allow_arena_bounds:
                    return self._snap_center_to_arena_surface(tilemap, center, normal, source_center=source_center)
                return None
            return (center[0], surface.top - half_h)
        if normal == (0, 1):
            surface = self._surface_rect_at_pixel(tilemap, center[0], center[1] - half_h - 1)
            if not surface:
                if allow_arena_bounds:
                    return self._snap_center_to_arena_surface(tilemap, center, normal, source_center=source_center)
                return None
            return (center[0], surface.bottom + half_h)
        if normal == (1, 0):
            surface = self._surface_rect_at_pixel(tilemap, center[0] - half_w - 1, center[1])
            if not surface:
                if allow_arena_bounds:
                    return self._snap_center_to_arena_surface(tilemap, center, normal, source_center=source_center)
                return None
            return (surface.right + half_w, center[1])
        if normal == (-1, 0):
            surface = self._surface_rect_at_pixel(tilemap, center[0] + half_w + 1, center[1])
            if not surface:
                if allow_arena_bounds:
                    return self._snap_center_to_arena_surface(tilemap, center, normal, source_center=source_center)
                return None
            return (surface.left - half_w, center[1])
        return None

    def _surface_support_points(self, tilemap, center, normal):
        half_w, half_h = self._surface_half_extents(center)
        tile_size = getattr(tilemap, "tile_size", 16) or 16
        support_span = max(2.0, min((self._hh / 2.0) - 1.0, (tile_size / 2.0) - 2.0))
        if normal == (1, 0):
            sample_x = center[0] - half_w - 1
            return (
                (sample_x, center[1] - support_span),
                (sample_x, center[1] + support_span),
            )
        if normal == (-1, 0):
            sample_x = center[0] + half_w + 1
            return (
                (sample_x, center[1] - support_span),
                (sample_x, center[1] + support_span),
            )
        if normal == (0, 1):
            sample_y = center[1] - half_h - 1
            return (
                (center[0] - support_span, sample_y),
                (center[0] + support_span, sample_y),
            )
        if normal == (0, -1):
            sample_y = center[1] + half_h + 1
            return (
                (center[0] - support_span, sample_y),
                (center[0] + support_span, sample_y),
            )
        return ()

    def _surface_fully_supported(self, tilemap, center, normal):
        points = self._surface_support_points(tilemap, center, normal)
        if not points:
            return True
        for px, py in points:
            if self._surface_rect_at_pixel(tilemap, px, py) is not None:
                continue
            if self._snap_center_to_arena_surface(tilemap, center, normal, source_center=center) is not None:
                continue
            return False
        return True

    def _mounted_center_is_clear(self, tilemap, center, normal=None):
        normal = normal if normal is not None else self.surface_normal
        if normal is None:
            return True
        old_normal = self.surface_normal
        self.surface_normal = normal
        try:
            if normal[0] != 0:
                return not self._vertical_outward_blocked(tilemap, center)
            rect_w, rect_h = self._oriented_hitbox_size()
            sign = 1 if normal[1] > 0 else -1
            probe_y = center[1] + (sign * ((rect_h / 2.0) + 1.0))
            probe_offsets = (0.0, -(rect_w * 0.28), rect_w * 0.28)
            for dx in probe_offsets:
                if self._solid_tile_at_pixel(tilemap, center[0] + dx, probe_y) is not None:
                    return False
            return True
        finally:
            self.surface_normal = old_normal

    def _find_surface_near(self, tilemap, center, normal, radius, prefer=(0, 0), source_center=None, allow_arena_bounds=True):
        radius = max(0, int(radius))
        pref_x, pref_y = prefer
        for dist in range(radius + 1):
            offsets = []
            if dist == 0:
                offsets.append((0, 0))
            else:
                for dx in range(-dist, dist + 1):
                    dy = dist - abs(dx)
                    offsets.append((dx, dy))
                    if dy != 0:
                        offsets.append((dx, -dy))
            offsets.sort(key=lambda off: -((off[0] * pref_x) + (off[1] * pref_y)))
            for dx, dy in offsets:
                snapped = self._snap_center_to_surface(
                    tilemap,
                    (center[0] + dx, center[1] + dy),
                    normal,
                    source_center=source_center if source_center is not None else center,
                    allow_arena_bounds=allow_arena_bounds,
                )
                if (
                    snapped is not None
                    and self._surface_fully_supported(tilemap, snapped, normal)
                    and self._mounted_center_is_clear(tilemap, snapped, normal)
                ):
                    return snapped
        return None

    def _find_vertical_branch_surface(self, tilemap, center, tangent):
        return None

    def _tangent(self):
        normal = self.surface_normal
        return (-normal[1] * self.move_dir, normal[0] * self.move_dir)

    def _vertical_outward_blocked(self, tilemap, center):
        if self.surface_normal is None or self.surface_normal[0] == 0:
            return False
        rect_w, rect_h = self._oriented_hitbox_size()
        sign = 1 if self.surface_normal[0] > 0 else -1
        probe_x = center[0] + (sign * ((rect_w / 2.0) + 1.0))
        probe_offsets = (0.0, -(rect_h * 0.28), rect_h * 0.28)
        for dy in probe_offsets:
            if self._solid_tile_at_pixel(tilemap, probe_x, center[1] + dy) is not None:
                return True
        return False

    def _body_tangent(self):
        normal = self.surface_normal
        return (-normal[1], normal[0])

    def _tip_emitters(self):
        if self.surface_normal is None:
            return ()
        out = []
        angle = -self._surface_angle()
        for spec in self.tip_offsets_local:
            off = pygame.Vector2(spec['offset']).rotate(angle)
            vec = pygame.Vector2(1.0, 0.0).rotate(-(spec['base_angle'] + self._surface_angle()))
            mag = math.hypot(vec.x, vec.y) or 1.0
            out.append({
                "flash_action": spec['flash_action'],
                "projectile_action": spec['projectile_action'],
                "pos": (self.pos[0] + off.x, self.pos[1] + off.y),
                "dir": (vec.x / mag, vec.y / mag),
                "angle": math.degrees(-math.atan2(vec.y, vec.x)),
                "base_angle": spec['base_angle'],
            })
        return out

    def _has_forward_progress(self, start, end, tangent, min_progress=0.25):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        return ((dx * tangent[0]) + (dy * tangent[1])) > min_progress

    def _advance_freefall(self, tilemap):
        remaining_v = abs(self.fall_speed)
        while remaining_v > 0.0:
            step_v = min(1.0, remaining_v)
            self.pos[1] += step_v
            remaining_v -= step_v
            snapped_floor = self._snap_center_to_surface(tilemap, tuple(self.pos), (0, -1), source_center=tuple(self.pos))
            if snapped_floor is None:
                search = max(2, int(getattr(tilemap, "tile_size", 16) // 2))
                snapped_floor = self._find_surface_near(
                    tilemap,
                    tuple(self.pos),
                    (0, -1),
                    search,
                    prefer=(-self.move_dir, 1),
                    source_center=tuple(self.pos),
                )
            if snapped_floor is not None:
                self.surface_normal = (0, -1)
                self.pos[0], self.pos[1] = snapped_floor
                self.detach_grace = 18
                return

    def _advance_on_surface(self, tilemap):
        remaining = abs(self.crawl_speed)
        while remaining > 0.0 and self.surface_normal is not None:
            step = min(1.0, remaining)
            tangent = self._tangent()
            next_center = (
                self.pos[0] + (tangent[0] * step),
                self.pos[1] + (tangent[1] * step),
            )
            if self._mounted_center_is_clear(tilemap, next_center, self.surface_normal) is False:
                self.move_dir *= -1
                break
            search = max(3, int(getattr(tilemap, "tile_size", 16) // 3))
            snapped = self._find_surface_near(
                tilemap,
                next_center,
                self.surface_normal,
                search,
                prefer=tangent,
                source_center=(self.pos[0], self.pos[1]),
            )
            if (
                snapped is not None
                and self._mounted_center_is_clear(tilemap, snapped, self.surface_normal)
                and self._has_forward_progress((self.pos[0], self.pos[1]), snapped, tangent)
            ):
                self.pos[0], self.pos[1] = snapped
                self.detach_grace = 18
                remaining -= step
                continue
            self.move_dir *= -1
            break
            remaining -= step

    def attach_to_surface(self, tilemap, center=None, preferred_normal=None):
        center = tuple(center if center is not None else self.pos)
        normals = [preferred_normal] if preferred_normal is not None else []
        if preferred_normal is not None:
            if preferred_normal[0] != 0:
                self.surface_mode = 'vertical'
                candidates = ((1, 0), (-1, 0))
            else:
                self.surface_mode = 'ceiling'
                candidates = ((0, 1),)
        elif self.surface_mode == 'vertical':
            candidates = ((1, 0), (-1, 0))
        else:
            candidates = ((0, 1),)
        for normal in candidates:
            if normal not in normals:
                normals.append(normal)
        for normal in normals:
            direct = self._snap_center_to_surface(tilemap, center, normal, source_center=center)
            if (
                direct is not None
                and self._surface_fully_supported(tilemap, direct, normal)
                and self._mounted_center_is_clear(tilemap, direct, normal)
            ):
                self.surface_normal = normal
                self.pos[0], self.pos[1] = direct
                return True
            snapped = self._find_surface_near(tilemap, center, normal, 20, prefer=normal, source_center=center)
            if snapped is not None:
                self.surface_normal = normal
                self.pos[0], self.pos[1] = snapped
                return True
        return False

    def _spawn_projectiles(self, projectiles):
        if projectiles is None or self.surface_normal is None:
            return
        for emitter in self._tip_emitters():
            vx = emitter["dir"][0] * 2.8
            vy = emitter["dir"][1] * 2.8
            projectiles.append(
                ArenaAngledProjectile(
                    self.game,
                    emitter["projectile_action"],
                    emitter["pos"],
                    vel=(vx, vy),
                    gravity=0.0,
                    life=120,
                    angle_degrees=emitter["angle"],
                    base_angle_degrees=emitter["base_angle"],
                )
            )

    def _render_attack_flashes(self, surf, offset):
        if self.state != 'attack':
            return
        frame_idx = self.animation.frame_index()
        if frame_idx < self.flash_frame_start or frame_idx > self.flash_frame_end:
            return
        for emitter in self._tip_emitters():
            anim = getattr(self.game, "assets", {}).get(emitter["flash_action"])
            if not anim or not anim.images:
                continue
            img = anim.images[0]
            rotated = pygame.transform.rotate(img, emitter["angle"] - emitter["base_angle"])
            bounds = rotated.get_bounding_rect()
            rect = pygame.Rect(
                int(round(emitter["pos"][0] - (bounds.w / 2.0) - offset[0])),
                int(round(emitter["pos"][1] - (bounds.h / 2.0) - offset[1])),
                bounds.w,
                bounds.h,
            )
            surf.blit(rotated, (rect.x - bounds.x, rect.y - bounds.y))

    def render(self, surf, offset=(0, 0)):
        if not self.can_move and self.state != 'attack':
            img = self.game.assets['spike_idle'].images[0]
        else:
            img = self.animation.img()
        frame = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        frame.blit(img, (0, 0))
        if self.spawn_delay > 0:
            ready_alpha = max(70, 255 - min(180, self.spawn_delay * 3))
            frame.fill((255, 255, 255, ready_alpha), special_flags=pygame.BLEND_RGBA_MULT)
        alpha = self._hurt_render_alpha()
        if alpha < 255:
            frame.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        rotated = pygame.transform.rotate(frame, self._surface_angle())
        visual_cx, visual_cy = self._visual_center_world()
        rect = rotated.get_rect(center=(int(round(visual_cx - offset[0])), int(round(visual_cy - offset[1]))))
        surf.blit(rotated, rect.topleft)
        self._render_attack_flashes(surf, offset)

    def render_debug(self, surf, offset=(0, 0)):
        self.render(surf, offset)
        hb_rect = self.rect().move(-offset[0], -offset[1])
        pygame.draw.rect(surf, (0, 255, 0), hb_rect, 1)

        if not self.can_move and self.state != 'attack':
            img = self.game.assets['spike_idle'].images[0]
        else:
            img = self.animation.img()
        frame = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        frame.blit(img, (0, 0))
        rotated = pygame.transform.rotate(frame, self._surface_angle())
        visual_cx, visual_cy = self._visual_center_world()
        draw_rect = rotated.get_rect(center=(int(round(visual_cx - offset[0])), int(round(visual_cy - offset[1]))))
        sprite_bounds = rotated.get_bounding_rect()
        sprite_bounds.move_ip(draw_rect.topleft)
        pygame.draw.rect(surf, (255, 0, 0), sprite_bounds, 1)

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self.can_move and self.state not in ('attack', 'guard'):
            self.state = 'guard'
        if not self.can_move and self.state != 'attack' and self.action != 'spike_idle':
            self.set_action('spike_idle', force=True)
        if not self._update_common():
            return
        if not tilemap:
            return
        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1
        if self.state in ('move', 'guard'):
            if self.can_move:
                self._set_move_animation()
            else:
                self.set_action('spike_idle')
            if self.surface_normal is None:
                self._advance_freefall(tilemap)
            elif self.can_move:
                self._advance_on_surface(tilemap)
            if (
                self.surface_normal is not None
                and self.attack_cooldown <= 0
                and self._player_in_range(
                    player,
                    x_range=self.notice_range_x,
                    y_range=self.notice_range_y,
                    radial_range=self.attack_range,
                )
            ):
                    self.state = 'attack'
                    self.shot_fired = False
                    self.set_action('spike_attack', force=True)
        elif self.state == 'attack':
            if self.action != 'spike_attack':
                self.set_action('spike_attack', force=True)
            if not self.shot_fired and self.animation.frame_index() >= self.fire_frame:
                self._spawn_projectiles(projectiles)
                self.shot_fired = True
            if self.animation.done:
                self.state = 'move' if self.can_move else 'guard'
                self.attack_cooldown = random.randint(150, 240)
                if self.can_move:
                    self._set_move_animation(force=True)
                else:
                    self.set_action('spike_idle', force=True)
        self.animation.update()


# met-style pop-up enemy with hide, peek, and block timing
class ArenaMetEnemy(ArenaEnemyBase):
    def __init__(self, game, pos, spawn_delay=0):
        super().__init__(game, pos, (22, 18), 'met_walking', spawn_delay=spawn_delay, anchor_mode="bottom")
        self.ignore_auto_flip = True
        self.max_health = 1
        self.health = self.max_health
        self.score_value = 120
        self.walk_speed = 0.68
        self.unseen_walk_speed = 0.96
        self.cautious_walk_speed = 0.32
        self.walk_dir = random.choice((-1, 1))
        self.state = 'walking'
        self.state_timer = random.randint(30, 65)
        self.hidden_hold_time = 70
        self.post_shot_hide_time = 42
        self.fire_cooldown = 0
        self.hide_cooldown = 0
        self.shot_fired = False
        self.block_sound_cooldown = 0
        self.hide_trigger_distance = 86
        self.alert_distance = 190
        self.peek_distance = 210
        self.vertical_notice_range = 56
        self.ledge_lookahead = 5
        self.ledge_probe_depth = 12
        self.hidden_extensions_remaining = 0

    def _set_closed_pose(self):
        self.set_action('met_hide', force=True)
        self.animation.frame = sum(self.animation.durations[:2])
        self.animation.done = False

    def _set_facing_dir(self, dir_sign):
        self.flip = dir_sign > 0

    def _set_walk_animation(self, force=False):
        if force or self.action != 'met_walking':
            base = self.game.assets['met_walking']
            walk_durations = [max(1, int(d * 0.58)) for d in base.durations]
            self.action = 'met_walking'
            self.animation = Animation(base.images, walk_durations, loop=True)
            size = HITBOX_SIZES.get('met_walking', (self.size[0], HITBOX_H))
            self._hw = size[0]
            self._hh = size[1]

    def _set_peek_animation(self):
        base = self.game.assets['met_hide']
        self.action = 'met_hide'
        peek_durations = list(base.durations)
        if peek_durations:
            peek_durations[0] = max(peek_durations[0], 18)
        self.animation = Animation(base.images, peek_durations, loop=False)
        size = HITBOX_SIZES.get('met_hide', (self.size[0], HITBOX_H))
        self._hw = size[0]
        self._hh = size[1]

    def _player_facing_dir(self, player):
        return -1 if getattr(player, "flip", False) else 1

    def _player_is_looking_at_me(self, player):
        if not player:
            return False
        dx = self.rect().centerx - player.rect().centerx
        if abs(dx) <= 6:
            return True
        return (1 if dx > 0 else -1) == self._player_facing_dir(player)

    def _distance_to_player(self, player):
        if not player:
            return 9999, 9999
        dx = player.rect().centerx - self.rect().centerx
        dy = player.rect().centery - self.rect().centery
        return dx, dy

    def _enter_hidden(self, hold_time=None):
        self.state = 'hidden'
        self.state_timer = self.hidden_hold_time if hold_time is None else max(1, int(hold_time))
        self.shot_fired = False
        self.hidden_extensions_remaining = 1
        self._set_closed_pose()

    def _enter_peek(self):
        self.state = 'peeking'
        self.shot_fired = False
        self._set_peek_animation()

    def _play_block_sound(self):
        if self.block_sound_cooldown > 0:
            return
        sound = getattr(self.game, 'sfx_blocked_hit', None)
        if sound is None:
            sound = getattr(self.game, 'sfx_hitmarker', None)
        if sound:
            try:
                sound.stop()
                sound.play()
            except Exception:
                pass
        self.block_sound_cooldown = 6

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self._update_common():
            return
        if self.block_sound_cooldown > 0:
            self.block_sound_cooldown -= 1
        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1
        if self.hide_cooldown > 0:
            self.hide_cooldown -= 1

        dx_to_player, dy_to_player = self._distance_to_player(player)
        player_visible = abs(dx_to_player) <= self.alert_distance and abs(dy_to_player) <= self.vertical_notice_range
        player_looking = self._player_is_looking_at_me(player)
        player_threatening = player_visible and player_looking and abs(dx_to_player) <= self.hide_trigger_distance
        player_unseen = player_visible and not player_looking
        desired_dir = -1 if dx_to_player < 0 else 1

        move_x = 0.0
        prev_grounded = self.collisions.get('down', False)
        if self.state == 'walking':
            if desired_dir != 0:
                self.walk_dir = desired_dir
            self._set_facing_dir(self.walk_dir)
            if player_threatening:
                self._enter_hidden()
                move_x = 0.0
            else:
                move_speed = self.unseen_walk_speed if player_unseen else self.walk_speed
                if player_visible and player_looking:
                    move_speed = self.cautious_walk_speed
                if self._should_turn_at_ledge(tilemap, self.walk_dir, lookahead=self.ledge_lookahead, probe_depth=self.ledge_probe_depth):
                    self.set_action('met_idle', force=True)
                    move_x = 0.0
                else:
                    self._set_walk_animation()
                    move_x = move_speed * self.walk_dir
            if self.state_timer > 0:
                self.state_timer -= 1
            elif self.state_timer <= 0:
                self.state_timer = random.randint(22, 48)
                if player_visible and abs(dx_to_player) <= self.peek_distance and self.fire_cooldown <= 0:
                    self._enter_hidden()
        elif self.state == 'hidden':
            self._set_closed_pose()
            self._set_facing_dir(desired_dir)
            if player_threatening and self.hidden_extensions_remaining > 0 and self.state_timer <= 8:
                self.state_timer = 16
                self.hidden_extensions_remaining -= 1
            if self.state_timer > 0:
                self.state_timer -= 1
            else:
                if player_threatening:
                    if self.fire_cooldown <= 0:
                        self._enter_peek()
                    else:
                        self.state_timer = random.randint(14, 24)
                        self._set_closed_pose()
                elif player_visible and abs(dx_to_player) <= self.peek_distance and self.fire_cooldown <= 0:
                    self._enter_peek()
                else:
                    self.state = 'walking'
                    self.hide_cooldown = random.randint(24, 42)
                    self.state_timer = random.randint(26, 54)
                    self.set_action('met_idle', force=True)
        elif self.state == 'peeking':
            self._set_facing_dir(desired_dir)
            if self.action != 'met_hide' or self.animation.loop:
                self._set_peek_animation()
            if not self.shot_fired and self.animation.frame_index() >= 2 and projectiles is not None and player:
                bullet_dir = -1 if player.rect().centerx < self.rect().centerx else 1
                spawn_x = self.rect().centerx + (bullet_dir * 14)
                spawn_y = self.rect().centery - 8
                shot_sound = getattr(self.game, 'sfx_met_projectile', None)
                if shot_sound:
                    try:
                        shot_sound.play()
                    except Exception:
                        pass
                projectiles.append(
                    ArenaEnemyProjectile(
                        self.game,
                        'met_projectile',
                        (spawn_x, spawn_y),
                        vel=(bullet_dir * 2.9, -0.06),
                        gravity=0.01,
                        life=160,
                    )
                )
                self.shot_fired = True
                self.fire_cooldown = random.randint(120, 170)

        super().update(tilemap, movement=(move_x, 0))
        self._snap_to_ground(tilemap)
        if self.state == 'hidden':
            self._set_closed_pose()
        elif self.state == 'peeking' and self.animation.done:
            self._enter_hidden(self.post_shot_hide_time)
        if self.collisions['left'] or self.collisions['right']:
            self.walk_dir *= -1
            self.flip = self.walk_dir < 0
        if self.state == 'walking' and not prev_grounded and self.collisions['down']:
            self.set_action('met_idle', force=True)

    def take_sword_hit(self, player):
        if self.state == 'hidden':
            attack_id = getattr(player, "attack_instance_id", 0)
            if attack_id == self.last_sword_attack_id:
                return False
            self.last_sword_attack_id = attack_id
            self._play_block_sound()
            self.state_timer = max(self.state_timer, 12)
            return False
        return super().take_sword_hit(player)


# grounded cannon that picks shot poses based on the player's position
class ArenaCannonEnemy(ArenaEnemyBase):
    def __init__(self, game, pos, spawn_delay=0):
        super().__init__(game, pos, (26, 26), 'cannon_idle', spawn_delay=spawn_delay, anchor_mode="bottom")
        self.ignore_auto_flip = True
        self.max_health = 3
        self.health = self.max_health
        self.score_value = 180
        self.hop_speed = 1.3
        self.jump_speed = -3.9
        self.state = 'idle'
        self.state_timer = random.randint(84, 132)
        self.move_dir = random.choice((-1, 1))
        self.attack_action = 'cannon_shoot_3'
        self.shot_fired = False
        self.aim_hold_time = 18
        self.aim_step_interval = 5
        self.aim_commit_hold = 22
        self.burst_size = 3
        self.burst_interval = 10
        self.sprite_anchor_x = 63
        self.sprite_anchor_y = 80
        self.ledge_pause_timer = 0
        self.current_aim_index = 1
        self.desired_aim_index = 1
        self.aim_step_timer = 0
        self.aim_commit_timer = 0
        self.attack_dir = -1
        self.burst_shots_left = 0
        self.notice_range_x = 220
        self.notice_range_y = 120
        self.engaged_hop_chance = 0.74
        self.idle_hop_chance = 0.40
        # Cannon art is authored facing left by default.
        self.attack_profiles = {
            'cannon_shoot_1': {'vel': (2.8, -2.25), 'socket': (45, 50)},
            'cannon_shoot_2': {'vel': (2.35, -3.15), 'socket': (48, 43)},
            'cannon_shoot_3': {'vel': (1.7, -4.05), 'socket': (52, 37)},
            'cannon_shoot_4': {'vel': (0.8, -4.9), 'socket': (57, 33)},
        }

    def _set_facing_dir(self, dir_sign):
        self.flip = dir_sign > 0

    def _draw_offset(self, img):
        anchor_x = self.sprite_anchor_x
        if self.flip:
            anchor_x = img.get_width() - anchor_x
        ox = int(round((self._hw / 2.0) - anchor_x))
        oy = int(round(self._hh - self.sprite_anchor_y))
        return ox, oy

    def _choose_attack_action(self, player):
        if player is None:
            return 'cannon_shoot_2', self.attack_profiles['cannon_shoot_2']['vel']
        own_rect = self.rect()
        target_rect = player.rect()
        dx = abs(target_rect.centerx - own_rect.centerx)
        dy = target_rect.centery - own_rect.centery
        gravity = 0.14
        best_action = None
        best_score = None
        for action, profile in self.attack_profiles.items():
            vx, vy = profile['vel']
            speed_x = max(0.01, abs(vx))
            travel_frames = dx / speed_x
            predicted_dy = (vy * travel_frames) + (0.5 * gravity * (travel_frames ** 2))
            score = abs(predicted_dy - dy)
            # Favor steeper shots a bit when the player is clearly above.
            if dy < -28:
                preferred_index = 4 if dy < -60 else 3
                score += abs(int(action.rsplit('_', 1)[-1]) - preferred_index) * 6
            elif dx < 56:
                score += abs(int(action.rsplit('_', 1)[-1]) - 2) * 4
            if best_score is None or score < best_score:
                best_score = score
                best_action = action
        action = best_action or 'cannon_shoot_2'
        return action, self.attack_profiles[action]['vel']

    def _aim_action_for_index(self, idx):
        idx = max(1, min(4, int(idx)))
        return f'cannon_shoot_{idx}'

    def _shot_origin(self, action):
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        draw_x = self.pos[0] + ox
        draw_y = self.pos[1] + oy
        local_x, local_y = self.attack_profiles[action]['socket']
        if self.flip:
            local_x = img.get_width() - local_x
        return draw_x + local_x, draw_y + local_y

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self._update_common():
            return
        player_engaged = bool(player) and self._player_in_range(
            player,
            x_range=self.notice_range_x,
            y_range=self.notice_range_y,
        )
        if player_engaged and self.state == 'idle':
            target_dir = -1 if player.rect().centerx < self.rect().centerx else 1
            if self.state == 'idle' and self.ledge_pause_timer <= 0:
                self.move_dir = target_dir
        if self.state == 'idle':
            self._set_facing_dir(self.move_dir)

        move_x = 0.0
        was_grounded = self.collisions['down']
        if self.ledge_pause_timer > 0:
            self.ledge_pause_timer -= 1
        if self.state == 'idle':
            self.set_action('cannon_idle')
            if tilemap and self.collisions['down'] and self._should_turn_at_ledge(tilemap, self.move_dir, lookahead=8, probe_depth=16):
                self.move_dir *= -1
                self._set_facing_dir(self.move_dir)
                self.ledge_pause_timer = 10
            if self.state_timer > 0:
                self.state_timer -= 1
            elif self.ledge_pause_timer <= 0:
                hop_roll = self.engaged_hop_chance if player_engaged else self.idle_hop_chance
                if random.random() < hop_roll:
                    self.state = 'jump'
                    self.shot_fired = False
                    self.move_dir = 1 if self.flip else -1
                    self.velocity[1] = self.jump_speed
                    self.set_action('cannon_jump_land', force=True)
                else:
                    self.state_timer = random.randint(54, 96) if player_engaged else random.randint(88, 136)
                    self.set_action('cannon_idle', force=True)
        elif self.state == 'jump':
            move_x = self.hop_speed * self.move_dir
        elif self.state == 'aim':
            self._set_facing_dir(self.attack_dir)
            if self.current_aim_index != self.desired_aim_index:
                self.aim_commit_timer = self.aim_commit_hold
                if self.aim_step_timer > 0:
                    self.aim_step_timer -= 1
                else:
                    if self.current_aim_index < self.desired_aim_index:
                        self.current_aim_index += 1
                    elif self.current_aim_index > self.desired_aim_index:
                        self.current_aim_index -= 1
                    self.attack_action = self._aim_action_for_index(self.current_aim_index)
                    self.set_action(self.attack_action, force=True)
                    self.aim_step_timer = self.aim_step_interval
            elif self.aim_commit_timer > 0:
                self.aim_commit_timer -= 1
            if self.animation.frame_index() != 0 or self.animation.done:
                self.animation.frame = 0
                self.animation.done = False
            if self.state_timer > 0:
                self.state_timer -= 1
            elif self.current_aim_index == self.desired_aim_index and self.aim_commit_timer <= 0:
                self.state = 'shoot'
                self.shot_fired = False
                self.set_action(self.attack_action, force=True)
        elif self.state == 'shoot':
            self._set_facing_dir(self.attack_dir)
            if self.action != self.attack_action:
                self.set_action(self.attack_action, force=True)
            if not self.shot_fired and self.animation.frame_index() >= 1 and projectiles is not None:
                base_vel = self.attack_profiles[self.attack_action]['vel']
                vx, vy = base_vel
                vx *= (1 if self.flip else -1)
                spawn_x, spawn_y = self._shot_origin(self.attack_action)
                shot_sound = getattr(self.game, 'sfx_cannon_shoot', None)
                if shot_sound:
                    try:
                        shot_sound.play()
                    except Exception:
                        pass
                projectiles.append(
                    ArenaExplodingProjectile(
                        self.game,
                        'cannon_projectile',
                        (spawn_x, spawn_y),
                        vel=(vx, vy),
                        gravity=0.14,
                        life=180,
                    )
                )
                self.shot_fired = True
            if self.animation.done:
                self.burst_shots_left -= 1
                if self.burst_shots_left > 0:
                    self.state = 'burst_wait'
                    self.state_timer = self.burst_interval
                    self.set_action(self.attack_action, force=True)
                else:
                    self.state = 'idle'
                    self.state_timer = random.randint(118, 176)
                    self.set_action('cannon_idle', force=True)
        elif self.state == 'burst_wait':
            self._set_facing_dir(self.attack_dir)
            if self.action != self.attack_action:
                self.set_action(self.attack_action, force=True)
            if self.state_timer > 0:
                self.state_timer -= 1
            else:
                self.state = 'shoot'
                self.shot_fired = False
                self.set_action(self.attack_action, force=True)

        super().update(tilemap, movement=(move_x, 0))
        if self.state == 'jump':
            if self.collisions['down']:
                self.animation.frame = min(1, max(0, self.animation._total - 1))
            else:
                self.animation.frame = max(0, self.animation._total - 1)
            self.animation.done = False
        if self.state == 'aim':
            self.animation.frame = 0
            self.animation.done = False
        if self.state == 'burst_wait':
            self.animation.frame = 0
            self.animation.done = False
        self._snap_to_ground(tilemap)
        if self.collisions['left'] or self.collisions['right']:
            self.move_dir *= -1
            if self.state == 'idle':
                self._set_facing_dir(self.move_dir)
            self.ledge_pause_timer = 8
        if self.state == 'jump' and self.collisions['down'] and not was_grounded:
            if player_engaged:
                self.attack_dir = -1 if player.rect().centerx < self.rect().centerx else 1
            else:
                self.attack_dir = -1 if not self.flip else 1
            if player_engaged:
                self.attack_action, _ = self._choose_attack_action(player)
                self.desired_aim_index = int(self.attack_action.rsplit('_', 1)[-1])
                self.attack_action = self._aim_action_for_index(self.current_aim_index)
                self.state = 'aim'
                self.state_timer = self.aim_hold_time
                self.aim_step_timer = 0
                self.aim_commit_timer = self.aim_commit_hold
                self.shot_fired = False
                self.burst_shots_left = self.burst_size
                self.set_action(self.attack_action, force=True)
            else:
                self.state = 'idle'
                self.state_timer = random.randint(96, 152)
                self.set_action('cannon_idle', force=True)


# hovering launcher that tracks the player and spits out rockets
class ArenaHeliRocketEnemy(ArenaEnemyBase):
    def __init__(self, game, pos, spawn_delay=0):
        super().__init__(game, pos, (28, 30), 'heli_rocket_idle_moving', spawn_delay=spawn_delay, anchor_mode="center")
        self.ignore_auto_flip = True
        self.max_health = 2
        self.health = self.max_health
        self.score_value = 160
        self.base_pos = [float(pos[0]), float(pos[1])]
        self.hover_timer = random.uniform(0.0, math.tau)
        self.state = 'patrol'
        self.state_timer = random.randint(45, 75)
        self.fire_cooldown = random.randint(60, 110)
        self.shot_fired = False
        self.reload_hold = 16
        self.preferred_range = 108
        self.range_tolerance = 28
        self.notice_range_x = 260
        self.notice_range_y = 120
        self.fire_range_x = 188
        self.fire_range_y = 40
        self.move_speed = 0.75
        self.evade_speed = 1.1
        self.vertical_speed = 0.42
        self.sprite_anchor_x = 64.0
        self.sprite_anchor_y = 61.5
        self.mouth_offset_x = 0
        self.mouth_offset_y = 0
        self.face_deadzone = 18
        self.entry_mode = False
        self.entry_speed_scale = 1.0
        self.track_player_globally = getattr(game, "stage_key", None) != "intro_stage"
        if self.track_player_globally:
            self.camera_activation_pending = False
        # Authored left-facing socket at the lower loaded rocket in the mouth.
        self.rocket_socket = (60, 74)
        reload_base = self.game.assets['heli_rocket_reloading']
        self.mouth_reload_images = list(reload_base.images)
        self.mouth_flash_timer = 0
        self.mouth_flash_duration = max(8, sum(reload_base.durations))

    def _set_facing_dir(self, dir_sign):
        # Sprite art is authored facing left by default.
        self.flip = dir_sign > 0

    def _draw_offset(self, img):
        anchor_x = self.sprite_anchor_x
        if self.flip:
            anchor_x = img.get_width() - anchor_x
        ox = (self._hw / 2.0) - anchor_x
        oy = (self._hh / 2.0) - self.sprite_anchor_y
        return int(round(ox)), int(round(oy))

    def _shot_origin(self):
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        draw_x = self.pos[0] + ox
        draw_y = self.pos[1] + oy
        dir_sign = -1 if not self.flip else 1
        local_x, local_y = self.rocket_socket
        if self.flip:
            local_x = img.get_width() - local_x
        spawn_x = draw_x + local_x + (dir_sign * 4)
        spawn_y = draw_y + local_y
        return spawn_x, spawn_y, dir_sign

    def _current_mouth_image(self):
        if len(self.mouth_reload_images) < 2:
            return self.mouth_reload_images[0] if self.mouth_reload_images else None
        if self.mouth_flash_timer > max(3, self.mouth_flash_duration // 2):
            return self.mouth_reload_images[0]
        return self.mouth_reload_images[1]

    def render(self, surf, offset=(0, 0)):
        super().render(surf, offset)
        img = self._current_mouth_image()
        if img is None:
            return
        ox, oy = self._draw_offset(self.animation.img())
        draw_x = int(self.pos[0] - offset[0]) + int(ox)
        draw_y = int(self.pos[1] - offset[1]) + int(oy)
        overlay = pygame.transform.flip(img, self.flip, False)
        mouth_x = draw_x + (self.mouth_offset_x if not self.flip else -self.mouth_offset_x)
        mouth_y = draw_y + self.mouth_offset_y
        surf.blit(overlay, (mouth_x, mouth_y))

    def _spawn_projectile(self, projectiles):
        if projectiles is None:
            return
        spawn_x, spawn_y, dir_sign = self._shot_origin()
        rocket_sound = getattr(self.game, 'sfx_rocket_fired', None)
        if rocket_sound:
            try:
                rocket_sound.play()
            except Exception:
                pass
        self.mouth_flash_timer = self.mouth_flash_duration
        projectiles.append(
            ArenaRocketProjectile(
                self.game,
                'heavy_rocket_projectile',
                (spawn_x, spawn_y),
                vel=(dir_sign * 3.0, 0.0),
                life=120,
                flip=dir_sign > 0,
            )
        )

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self._update_common():
            return
        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1
        if self.mouth_flash_timer > 0:
            self.mouth_flash_timer -= 1

        if self.entry_mode:
            self.hover_timer += 0.08
            target_x = self.base_pos[0]
            target_y = self.base_pos[1] + (math.sin(self.hover_timer) * 8.0)
            dx = max(-0.28, min(0.28, (target_x - self.pos[0]) * 0.022 * max(0.2, self.entry_speed_scale)))
            dy = max(-0.22, min(0.22, (target_y - self.pos[1]) * 0.022 * max(0.2, self.entry_speed_scale)))
            self.pos[0] += dx
            self.pos[1] += dy + (math.sin(self.hover_timer) * 0.12)
            if abs(target_x - self.pos[0]) >= self.face_deadzone:
                self._set_facing_dir(-1 if target_x < self.pos[0] else 1)
            if abs(target_x - self.pos[0]) <= 10 and abs(target_y - self.pos[1]) <= 10:
                self.entry_mode = False
            self.animation.update()
            return

        dx = 0.0
        dy = 0.0
        target_dir = -1
        player_engaged = bool(player) and (
            self.track_player_globally
            or self._player_in_range(
                player,
                x_range=self.notice_range_x,
                y_range=self.notice_range_y,
            )
        )
        player_in_fire_window = self._player_in_range(
            player,
            x_range=self.fire_range_x,
            y_range=self.fire_range_y,
        )
        if player_engaged:
            player_rect = player.rect()
            own_rect = self.rect()
            x_diff = player_rect.centerx - own_rect.centerx
            y_diff = player_rect.centery - own_rect.centery
            target_dir = -1 if x_diff < 0 else 1
            target_y = player_rect.centery - 12 + (math.sin(self.hover_timer) * 10.0)
            if abs(y_diff) > 10:
                dy = max(-self.vertical_speed, min(self.vertical_speed, (target_y - own_rect.centery) * 0.045))
            dist = abs(x_diff)
            if dist < self.preferred_range - self.range_tolerance:
                dx = -target_dir * self.evade_speed
            elif dist > self.preferred_range + self.range_tolerance:
                dx = target_dir * self.move_speed
            else:
                dx = 0.0
            if abs(x_diff) >= self.face_deadzone:
                self._set_facing_dir(target_dir)
        else:
            target_x = self.base_pos[0]
            target_y = self.base_pos[1] + (math.sin(self.hover_timer) * 8.0)
            dx = max(-0.45, min(0.45, (target_x - self.pos[0]) * 0.04))
            dy = max(-0.32, min(0.32, (target_y - self.pos[1]) * 0.04))

        self.hover_timer += 0.1

        if self.state == 'patrol':
            if self.action != 'heli_rocket_idle_moving':
                self.set_action('heli_rocket_idle_moving', force=True)
            self.pos[0] += dx
            self.pos[1] += dy + (math.sin(self.hover_timer) * 0.18)
            if arena_bounds:
                ox, oy, w, h = arena_bounds
                rect = self.rect()
                left_limit = ox + 20
                right_limit = ox + w - 20
                top_limit = oy + 20
                bottom_limit = oy + h - 84
                if rect.left < left_limit:
                    self.pos[0] += left_limit - rect.left
                elif rect.right > right_limit:
                    self.pos[0] -= rect.right - right_limit
                rect = self.rect()
                if rect.top < top_limit:
                    self.pos[1] += top_limit - rect.top
                elif rect.bottom > bottom_limit:
                    self.pos[1] -= rect.bottom - bottom_limit
            if player_in_fire_window and self.fire_cooldown <= 0:
                self.state = 'reload'
                self.state_timer = self.reload_hold
                self.shot_fired = False
        elif self.state == 'reload':
            if self.action != 'heli_rocket_idle_moving':
                self.set_action('heli_rocket_idle_moving', force=True)
            self.pos[0] += dx * 0.35
            self.pos[1] += dy * 0.55 + (math.sin(self.hover_timer) * 0.14)
            if not self.shot_fired:
                self._spawn_projectile(projectiles)
                self.shot_fired = True
            if self.state_timer > 0:
                self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = 'patrol'
                self.fire_cooldown = random.randint(95, 145)
                self.set_action('heli_rocket_idle_moving', force=True)

        self.animation.update()


# heavy unit with rocket and shocker attacks plus chunkier spacing rules
class ArenaHeavyEnemy(ArenaEnemyBase):
    def __init__(self, game, pos, spawn_delay=0):
        super().__init__(game, pos, (34, 40), 'heavy_idle', spawn_delay=spawn_delay, anchor_mode="bottom")
        self.ignore_auto_flip = True
        self.max_health = 7
        self.health = self.max_health
        self.score_value = 240
        self.state = 'idle'
        self.state_timer = random.randint(42, 78)
        self.attack_kind = 'rocket'
        self.projectile_index = 0
        self.projectile_queue = ()
        self.shot_interval = 20
        self.sprite_anchor_x = 64
        self.sprite_anchor_y = 93
        self.crouch_hold_time = 16
        self.fire_recover_time = 14
        self.notice_range_x = 280
        self.notice_range_y = 128
        # Default heavy art faces left, so these are the front-side launcher sockets.
        self.rocket_holes = ((33, 57), (49, 63))
        self.shocker_origin = (35, 71)

    def _draw_offset(self, img):
        ox = int(round((self._hw / 2.0) - self.sprite_anchor_x))
        oy = int(round(self._hh - self.sprite_anchor_y))
        return ox, oy

    def _hole_world_pos(self, local_xy):
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        draw_x = self.pos[0] + ox
        draw_y = self.pos[1] + oy
        local_x, local_y = local_xy
        if self.flip:
            local_x = img.get_width() - local_x
        return (draw_x + local_x, draw_y + local_y)

    def _spawn_rocket(self, projectiles, hole):
        dir_sign = 1 if self.flip else -1
        rocket_sound = getattr(self.game, 'sfx_rocket_fired', None)
        if rocket_sound:
            try:
                rocket_sound.play()
            except Exception:
                pass
        spawn_x, spawn_y = self._hole_world_pos(hole)
        spawn_x += dir_sign * 6
        projectiles.append(
            ArenaRocketProjectile(
                self.game,
                'heavy_rocket_projectile',
                (spawn_x, spawn_y),
                vel=(dir_sign * 3.0, 0.0),
                life=120,
                flip=dir_sign > 0,
            )
        )

    def _spawn_shockers(self, projectiles):
        dir_sign = 1 if self.flip else -1
        shock_sound = getattr(self.game, 'sfx_heavy_shocker', None)
        if shock_sound:
            try:
                shock_sound.play()
            except Exception:
                pass
        spawn_x, spawn_y = self._hole_world_pos(self.shocker_origin)
        spawn_x += dir_sign * 3
        spawn_y += 1
        projectiles.append(
            ArenaHeavyShockerPairProjectile(
                self.game,
                'heavy_shocker_projectile',
                (spawn_x, spawn_y),
                move_dir=dir_sign,
                fall_speed=3,
                crawl_speed=3.5,
                life=260,
                pair_gap=8,
                air_drift=1.8,
            )
        )

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self._update_common():
            return
        player_engaged = self._player_in_range(
            player,
            x_range=self.notice_range_x,
            y_range=self.notice_range_y,
        )
        if player_engaged:
            # The heavy sheet is authored facing left by default.
            self.flip = player.rect().centerx > self.rect().centerx

        if self.state == 'idle':
            self.set_action('heavy_idle')
            if self.state_timer > 0 and player_engaged:
                self.state_timer -= 1
            elif self.state_timer <= 0 and player_engaged:
                self.state = 'prepare_anim'
                if getattr(self.game, "stage_key", "") == "intro_stage":
                    self.attack_kind = 'rocket'
                else:
                    self.attack_kind = random.choice(('rocket', 'shocker'))
                self.projectile_queue = self.rocket_holes if self.attack_kind == 'rocket' else (self.shocker_origin,)
                self.projectile_index = 0
                self.set_action('heavy_prepare_attack', force=True)
        elif self.state == 'prepare_anim':
            if self.animation.done:
                self.state = 'prepare_hold'
                self.state_timer = self.crouch_hold_time
        elif self.state == 'prepare_hold':
            if self.action != 'heavy_prepare_attack':
                self.set_action('heavy_prepare_attack', force=True)
            self.animation.frame = max(0, self.animation._total - 1)
            if self.state_timer > 0:
                self.state_timer -= 1
            else:
                self.state = 'imminent'
                self.set_action('heavy_imminent_attack', force=True)
        elif self.state == 'imminent':
            if self.animation.done:
                self.state = 'attack'
                self.set_action('heavy_attack', force=True)
        elif self.state == 'attack':
            if projectiles is not None and self.projectile_index < len(self.projectile_queue):
                if self.state_timer <= 0:
                    if self.attack_kind == 'rocket':
                        self._spawn_rocket(projectiles, self.projectile_queue[self.projectile_index])
                        self.projectile_index += 1
                        if self.projectile_index < len(self.projectile_queue):
                            self.state_timer = self.shot_interval
                        else:
                            self.state_timer = self.fire_recover_time
                    else:
                        self._spawn_shockers(projectiles)
                        self.projectile_index = len(self.projectile_queue)
                        self.state_timer = self.fire_recover_time
            if self.projectile_index >= len(self.projectile_queue) and self.state_timer <= 0:
                self.state = 'idle'
                self.state_timer = random.randint(64, 104)
                self.set_action('heavy_idle', force=True)
            elif self.state_timer > 0:
                self.state_timer -= 1

        super().update(tilemap, movement=(0, 0))
        self._snap_to_ground(tilemap)


# intro-stage boss controller with cutscene, drop-in, and fight states
class ArenaVileBoss(ArenaEnemyBase):
    def __init__(self, game, pos, spawn_delay=0):
        super().__init__(game, pos, (40, 72), 'vile_idle', spawn_delay=spawn_delay, anchor_mode="bottom")
        self.ignore_auto_flip = True
        self.max_health = 9999
        self.health = self.max_health
        self.score_value = 0
        self.drop_table = []
        self.walk_speed = 0.9
        self.punch_range = 54
        self.attack_cooldown = 0
        self.punch_hit = False
        self.contact_damage_cooldown = 0
        self.state = 'idle'
        self.state_timer = 0
        self.laugh_loops_remaining = 0
        self.land_target_y = None
        self.walk_step_frame = -1
        self.step_sound_index = 0
        self.expired = False

    def _set_facing_dir(self, dir_sign):
        self.flip = dir_sign < 0

    def _play_sound(self, name):
        sound = getattr(self.game, name, None)
        if sound:
            try:
                sound.play()
            except Exception:
                pass

    def place_midbottom(self, x, bottom_y):
        rect = self.rect()
        rect.midbottom = (int(round(x)), int(round(bottom_y)))
        ox, oy = self._hitbox_offsets()
        self.pos[0] = rect.x - ox
        self.pos[1] = rect.y - oy

    def begin_drop(self, x, bottom_y, facing_dir=-1):
        self._set_facing_dir(facing_dir)
        self.land_target_y = float(bottom_y)
        self.state = 'drop'
        self.state_timer = 0
        self.set_action('vile_idle', force=True)
        self.place_midbottom(x, bottom_y - 180)
        self.velocity[0] = 0.0
        self.velocity[1] = 1.4
        self._play_sound('sfx_vile_jump')

    def begin_laughing(self, loops=3):
        self.state = 'laugh'
        self.laugh_loops_remaining = max(1, int(loops))
        self._set_laugh_animation()

    def begin_fight(self):
        self.state = 'fight'
        self.state_timer = 0
        self.attack_cooldown = 12
        self.set_action('vile_idle', force=True)

    def begin_disarmed(self, launch_dir=1):
        self.state = 'disarmed'
        self.state_timer = 0
        self.set_action('vile_disarmed', force=True)
        self.velocity[0] = 2.9 * (1 if launch_dir >= 0 else -1)
        self.velocity[1] = -3.4

    def take_sword_hit(self, player):
        attack_id = getattr(player, "attack_instance_id", 0)
        if attack_id == self.last_sword_attack_id:
            return False
        self.last_sword_attack_id = attack_id
        self.health = max(1, self.health - 1)
        self.hit_flash_timer = self.hit_flash_time
        hit_sound = getattr(self.game, 'sfx_hitmarker', None)
        if hit_sound:
            try:
                hit_sound.play()
            except Exception:
                pass
        return False

    def take_giga_hit(self):
        self.health = max(1, self.health - 6)
        self.hit_flash_timer = self.hit_flash_time
        hit_sound = getattr(self.game, 'sfx_hitmarker', None)
        if hit_sound:
            try:
                hit_sound.play()
            except Exception:
                pass
        return False

    def _play_walk_step(self):
        sound_name = 'sfx_vile_step_land_1' if self.step_sound_index == 0 else 'sfx_vile_step_land_2'
        self.step_sound_index = 1 - self.step_sound_index
        self._play_sound(sound_name)

    def _set_laugh_animation(self):
        base = self.game.assets['vile_laughing']
        self.action = 'vile_laughing'
        self.animation = Animation(list(base.images), list(base.durations), loop=False)
        size = HITBOX_SIZES.get('vile_laughing', (self.size[0], HITBOX_H))
        self._hw = size[0]
        self._hh = size[1]

    def _update_walking_audio(self):
        if self.action != 'vile_walking':
            self.walk_step_frame = -1
            return
        frame_idx = self.animation.frame_index()
        if frame_idx != self.walk_step_frame and frame_idx in (1, 5):
            self._play_walk_step()
        self.walk_step_frame = frame_idx

    def update(self, player, arena_bounds=None, tilemap=None, projectiles=None):
        if not self._update_common():
            return
        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1
        if self.contact_damage_cooldown > 0:
            self.contact_damage_cooldown -= 1

        if self.state == 'drop':
            self.velocity[1] = min(9.0, self.velocity[1] + 0.32)
            self.pos[1] += self.velocity[1]
            rect = self.rect()
            if self.land_target_y is not None and rect.bottom >= self.land_target_y:
                rect.bottom = int(round(self.land_target_y))
                ox, oy = self._hitbox_offsets()
                self.pos[0] = rect.x - ox
                self.pos[1] = rect.y - oy
                self.velocity[1] = 0.0
                self.state = 'landing_hold'
                self.state_timer = 14
                self.set_action('vile_idle', force=True)
                self._play_walk_step()
            self.animation.update()
            return

        if self.state == 'landing_hold':
            self.set_action('vile_idle')
            if self.state_timer > 0:
                self.state_timer -= 1
            else:
                self.state = 'idle'
            self.animation.update()
            return

        if self.state == 'idle':
            self.set_action('vile_idle')
            super().update(tilemap, movement=(0, 0))
            self._snap_to_ground(tilemap, snap_height=6)
            return

        if self.state == 'laugh':
            if self.action != 'vile_laughing':
                self._set_laugh_animation()
            super().update(tilemap, movement=(0, 0))
            self._snap_to_ground(tilemap, snap_height=6)
            if self.animation.done:
                self.laugh_loops_remaining -= 1
                if self.laugh_loops_remaining > 0:
                    self._set_laugh_animation()
                else:
                    self.state = 'idle'
                    self.set_action('vile_idle', force=True)
            return

        if self.state == 'disarmed':
            self.pos[0] += self.velocity[0]
            self.pos[1] += self.velocity[1]
            self.velocity[1] = min(7.0, self.velocity[1] + 0.18)
            self.animation.update()
            if arena_bounds:
                ox, oy, w, h = arena_bounds
                if (
                    self.rect().right < ox - 80
                    or self.rect().left > (ox + w + 80)
                    or self.rect().top > (oy + h + 120)
                ):
                    self.expired = True
            return

        move_x = 0.0
        if self.state == 'fight':
            if player:
                dx = player.rect().centerx - self.rect().centerx
                dy = player.rect().centery - self.rect().centery
                current_dir = -1 if self.flip else 1
                desired_dir = current_dir if abs(dx) <= 10 else (-1 if dx < 0 else 1)
                self._set_facing_dir(desired_dir)
                touching_player = self.rect().inflate(6, 4).colliderect(player.rect())
                if touching_player and self.contact_damage_cooldown <= 0:
                    if player.take_enemy_hit(self.rect().centerx):
                        self.contact_damage_cooldown = 18
                if abs(dx) <= self.punch_range and abs(dy) <= 42 and self.attack_cooldown <= 0:
                    self.state = 'punch'
                    self.punch_hit = False
                    self.set_action('vile_punching', force=True)
                elif touching_player and abs(dy) <= 48:
                    self.set_action('vile_idle')
                    move_x = 0.0
                else:
                    self.set_action('vile_walking')
                    move_x = self.walk_speed * desired_dir
            else:
                self.set_action('vile_idle')
        elif self.state == 'punch':
            self.set_action('vile_punching')
            if (
                not self.punch_hit
                and self.animation.frame_index() >= 2
            ):
                self._play_sound('sfx_vile_punch')
                if player and abs(player.rect().centery - self.rect().centery) <= 44:
                    if abs(player.rect().centerx - self.rect().centerx) <= self.punch_range + 16:
                        player.take_enemy_hit(self.rect().centerx)
                self.punch_hit = True
            if self.animation.done:
                self.state = 'fight'
                self.attack_cooldown = 28
                self.set_action('vile_idle', force=True)

        super().update(tilemap, movement=(move_x, 0))
        self._snap_to_ground(tilemap, snap_height=6)
        self._update_walking_audio()
