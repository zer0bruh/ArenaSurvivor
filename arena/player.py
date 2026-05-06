import random

import pygame

from .combat_data import DASH_H, HITBOX_H, HITBOX_SIZES, SWORD_HITBOXES
from .core import Animation, Effect
from .entities import ArenaPhysicsEntity, GigaBeam


# zero-specific movement, combat, and survivability logic lives here
class ArenaPlayer(ArenaPhysicsEntity):
    def __init__(self, game, pos, size):
        super().__init__(game, 'player', pos, size)
        # movement and dash state
        self.air_time      = 0
        self.landing_timer = 0
        self.was_ascending = False
        self.dash_timer    = 0
        self.dash_cooldown = 0
        self.dash_dir      = 1
        self.dash_speed    = 4
        self.dash_input_boost = 1.4
        self.dash_buffer   = 0
        self.dash_input_dir = 0
        self.grounded      = False
        self.dash_hold     = False
        self.dash_time     = 0
        self.dash_min      = 6
        self.dash_max      = 30
        self.dash_air_timer = 0
        self.dash_air_max   = 8
        self.dash_air_speed = self.dash_speed
        self.dash_air_min   = 6
        self.dash_air_max_hold = 24
        self.dash_air_full = False
        self.max_air_jumps  = 1
        self.air_jumps      = self.max_air_jumps
        self.dash_ending    = False
        self.coyote_max     = 6
        self.coyote_timer   = 0
        self.hspeed         = 0.0
        self.hspeed_ground_decay = 0.70
        self.hspeed_air_decay    = 0.84
        self.air_control   = 1.0
        self.dash_just_jump = False
        self.dash_jump_used = False
        self.air_hspeed    = 0.0
        self.air_accel     = 0.56
        self.dash_restart  = False
        self.dash_end_move = False
        self.dash_in_air   = False
        self.air_dash_used = False
        self.jump_pressed  = False
        self.dash_jump_queued = False
        self.jump_hold = False
        self.jump_is_air = False
        self.jump_cut_velocity = -2.0
        self.wall_slide = False
        self.wall_dir = 0
        self.wall_slide_speed = 1.2
        self.wall_jump_speed_y = -4.0
        self.wall_jump_speed_x = 2.8
        self.wall_dash_jump_speed_y = -4.05
        self.wall_dash_jump_speed_x = 3.0
        self.wall_dash_jump_wall_speed_y = -4.25
        self.wall_dash_jump_wall_speed_x = 3.15
        self.wall_jump_lock = 0
        self.wall_jump_lock_time = 10
        self.wall_jump_dir = 0
        self.wall_jump_timer = 0
        self.wall_jump_anim_time = 10
        self.wall_stick_timer = 0
        self.wall_stick_time = 6
        self.wall_jump_no_cling_timer = 0
        self.wall_jump_no_cling_time = 12
        self.wall_land_timer = 0
        self.wall_land_time = 10
        self.force_short = False
        self.wall_cling_delay = 0
        self.wall_cling_delay_time = 2
        self.wall_slide_grace_timer = 0
        self.wall_slide_grace_time = 8
        self.dash_stop_timer = 0
        self.dash_stop_time = 6
        self.last_input_dir = 0
        self.current_input_dir = 0
        self.wall_dash_lock_timer = 0
        self.wall_dash_lock_time = 8
        self.wall_dash_lock_speed = 0.0
        self.wall_kick_dash_cooldown_timer = 0
        self.wall_kick_dash_cooldown_time = 20
        self.wall_contact_timer = 0
        self.wall_contact_time = 8
        self.wall_contact_dir = 0
        self.wall_contact_edge = 0
        self.land_face_timer = 0
        self.land_face_time = 6
        self.land_face_dir = 0
        self.flip_lock_timer = 0
        self.flip_lock_dir = 0
        self.ignore_auto_flip = True
        self._last_tilemap = None
        self._last_rect = None
        self._last_safe_rect = None
        self._deferred_hitbox_size = None
        self._air_dash_release_size = None
        self._air_dash_release_pending = False
        self.air_stuck_frames = 0
        self.air_stuck_last_center = None
        self.dash_press_buffer = 0
        self.dash_press_time = 6
        # saber combo state
        self.attack_active = False
        self.attack_action = ''
        self.attack_kind = None
        self.attack_combo_step = 0
        self.attack_combo_timer = 0
        self.attack_combo_window = 28
        self.attack_combo_queued = False
        self.attack_combo_speedup_min = 0.60
        self.attack_combo_speedup_applied = False
        self.attack_buffer = 0
        self.attack_buffer_time = 6
        self.attack_buffer_dir = 0
        self.attack_timer = 0
        self.attack_instance_id = 0
        self.attack_cancel_time = 2
        self.attack_air_cooldown = 0
        self.attack_wall_cooldown = 0
        self.attack_air_cooldown_time = 12
        self.attack_wall_cooldown_time = 12
        self.attack_end_timer = 0
        self.attack_end_time = 10
        self.attack_end_action = ''
        # giga attack sequencing
        self.giga_active = False
        self.giga_timer = 0
        self.giga_beam_queue = []
        self.giga_beam_index = 0
        self.giga_beam_timer = 0
        self.giga_beam_start_delay = 8
        self.giga_beam_interval = 5
        self.giga_beam_height_step = 12
        self.giga_beam_speed = 8
        self.giga_beam_scale = 1.6
        self.giga_beam_fall_delay = 6
        self.giga_beam_size = (0, 0)
        self.giga_beam_hitbox_width_factor = 0.3
        self.giga_beam_hitbox_height_factor = 0.9
        self.giga_request_timer = 0
        self.giga_request_time = 8
        # cosmetic effect timers
        self.dash_smoke_timer = 0
        self.dash_smoke_interval = 3
        self.dash_booster_timer = 0
        self.dash_booster_interval = 1
        self.dash_booster_back_offset = 12
        self.dash_booster_x_offset = 20
        self.dash_booster_y_offset = 0
        self.dash_smoke_x_offset = + 15
        self.dash_smoke_y_offset = 13
        self.dash_booster_scale = 0.8
        self.dash_booster_anim = None
        self.wall_kick_spark_x_offset = 0
        self.wall_kick_spark_y_offset = 0
        # Only draw booster on "fully leaned" dash frames (tweak sets as needed).
        self.dash_booster_action_frames = {
            'zero_dashing_startloop': {2, 3},
            'zero_dashing_restart': {1, 2},
            'zero_dashing': {2, 3},
            'zero_dashing_wallstop': {0},
        }
        self.dash_booster_default_frames = {2, 3}
        if hasattr(self.game, "effect_images"):
            imgs = self.game.effect_images.get('dash_booster', None)
            if imgs:
                if self.dash_booster_scale != 1.0:
                    scaled = []
                    for img in imgs:
                        scaled.append(pygame.transform.scale(
                            img,
                            (int(img.get_width() * self.dash_booster_scale),
                             int(img.get_height() * self.dash_booster_scale))
                        ))
                    imgs = scaled
                self.dash_booster_anim = Animation(imgs, img_dur=2, loop=True)
        self.wall_slide_smoke_timer = 0
        self.wall_slide_smoke_interval = 6
        self.spawn_timer = 0
        self.spawn_time = 0
        self.spawn_sound_played = False
        self.landing_sound_suppressed_frames = 0
        self.sfx_attack_channel = None
        self.sfx_dash_channel = None
        self.sfx_spawn_channel = None
        self.sfx_jump_channel = None
        self.sfx_giga_channel = None
        self.sfx_gain_channel = None
        self.sfx_gain_channel_ready = False
        self.jump_sound_index = 0
        # player resources and damage state
        self.max_health = 32
        self.health = self.max_health
        self.max_giga_energy = 16
        self.giga_energy = self.max_giga_energy
        self.pickup_refill_kind = None
        self.pickup_refill_remaining = 0
        self.pickup_refill_step_time = 2
        self.pickup_refill_step_timer = 0
        self.invuln_time = 120
        self.invuln_timer = 0
        self.hurt_time = 18
        self.hurt_timer = 0
        self.death_time = 45
        self.death_timer = 0
        self.dead = False
        self.hurt_knockback_x = 2.5
        self.hurt_knockback_y = -2.0
        if 'zero_spawning' in self.game.assets:
            anim = self.game.assets['zero_spawning']
            total = getattr(anim, "_total", 0)
            if total <= 0:
                total = max(1, len(anim.images))
            self.spawn_time = total
            self.spawn_timer = total
            self.set_action('zero_spawning', force=True)

    def render(self, surf, offset=(0, 0)):
        # render the dash booster first when that frame should show it, then the player sprite itself
        if self.dash_timer > 0 and self.dash_booster_anim:
            allowed = self.dash_booster_action_frames.get(self.action, self.dash_booster_default_frames)
            if allowed is not None:
                frame_idx = self.animation.frame_index()
                if frame_idx not in allowed:
                    return self._render_self(surf, offset)
            r = self.rect()
            foot_y = r.bottom + 44 + self.dash_booster_y_offset
            back_x = r.centerx - (self.dash_dir * self.dash_booster_back_offset)
            dir_sign = -1 if self.dash_dir > 0 else 1
            booster_x = back_x + (self.dash_booster_x_offset * dir_sign)
            img = self.dash_booster_anim.img()
            if self.dash_dir < 0:
                img = pygame.transform.flip(img, True, False)
            draw_x = booster_x - (img.get_width() // 2)
            draw_y = foot_y - img.get_height()
            surf.blit(img, (draw_x - offset[0], draw_y - offset[1]))
        self._render_self(surf, offset)

    def _hurt_render_alpha(self):
        if self.invuln_timer <= 0:
            return 255
        # Match the X-series style invulnerability blink: the sprite pops
        # between fully visible and fully transparent rather than darkening.
        return 0 if (self.invuln_timer // 3) % 2 == 0 else 255

    def _spawn_intro_draw_y_offset(self):
        if self.action != 'zero_spawning' or self.spawn_timer <= 0 or not hasattr(self, 'animation'):
            return 0
        base_nudge = 1
        frame_idx = self.animation.frame_index()
        if frame_idx != 0 or not getattr(self.animation, "durations", None):
            return base_nudge
        first_dur = max(1, int(self.animation.durations[0]))
        ticks_into = min(first_dur - 1, int(self.animation.frame))
        progress = ticks_into / max(1, first_dur - 1)
        # Drop the opening beam/materialization frame in from above the platform.
        start_offset = -160
        return base_nudge + int(round(start_offset * (1.0 - progress)))

    def _render_self(self, surf, offset=(0, 0)):
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        tx, ty = self.transition_render_nudge if self.transition_render_nudge_timer > 0 else (0, 0)
        draw_x = int(self.pos[0] - offset[0]) + int(ox) + tx
        draw_y = (
            int(self.pos[1] - offset[1])
            + int(oy)
            + self._spawn_intro_draw_y_offset()
            + ty
        )
        frame = pygame.transform.flip(img, self.flip, False)
        alpha = self._hurt_render_alpha()
        if alpha <= 0:
            return
        if alpha < 255:
            # Scale only the sprite's per-pixel alpha. Surface-wide alpha causes the
            # whole 128x128 canvas to behave like a translucent rectangle.
            frame = frame.copy()
            alpha_mask = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            alpha_mask.fill((255, 255, 255, alpha))
            frame.blit(alpha_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(frame, (draw_x, draw_y))

    def get_sword_hitboxes(self):
        if not self.attack_active:
            return []
        action = self.attack_action
        if action not in SWORD_HITBOXES:
            return []
        frame_idx = self.animation.frame_index()
        boxes = SWORD_HITBOXES[action].get(frame_idx, [])
        if not boxes:
            return []
        img = self.animation.img()
        ox, oy = self._draw_offset(img)
        draw_x = self.pos[0] + ox
        draw_y = self.pos[1] + oy
        rects = []
        for x, y, w, h in boxes:
            if self.flip:
                x = img.get_width() - x - w
            rects.append(pygame.Rect(int(draw_x + x), int(draw_y + y), int(w), int(h)))
        return rects

    def _spawn_effect(self, name, pos, img_dur=4, loop=False, vel=(0, 0), accel=(0, 0), damp=(1.0, 1.0),
                      life=None, layer=0, flip=False, anchor="topleft", scale=1.0):
        if not hasattr(self.game, "effects"):
            self.game.effects = []
        images = getattr(self.game, "effect_images", {}).get(name)
        if not images:
            return
        x, y = pos
        if images:
            w = int(images[0].get_width() * scale)
            h = int(images[0].get_height() * scale)
            if anchor == "bottomcenter":
                x -= w / 2
                y -= h
            elif anchor == "bottomleft":
                y -= h
            elif anchor == "bottomright":
                x -= w
                y -= h
            elif anchor == "center":
                x -= w / 2
                y -= h / 2
        self.game.effects.append(Effect(images, (x, y), img_dur=img_dur, loop=loop,
                                        vel=vel, accel=accel, damp=damp,
                                        life=life, layer=layer, flip=flip, scale=scale))

    def finish_spawn_sequence(self):
        if self.spawn_timer <= 0 or self.action != 'zero_spawning':
            return
        if not hasattr(self, 'animation') or not getattr(self.animation, 'durations', None):
            self.spawn_timer = 0
            return
        last_dur = max(1, int(self.animation.durations[-1]))
        self.animation.frame = max(0, self.animation._total - last_dur)
        self.spawn_timer = min(self.spawn_timer, last_dur)

    def _set_animation_frame_index(self, frame_index):
        if not hasattr(self, "animation") or self.animation is None or not getattr(self.animation, "images", None):
            return
        target = max(0, min(int(frame_index), len(self.animation.images) - 1))
        frame_tick = 0
        durations = getattr(self.animation, "durations", None) or []
        for i in range(target):
            if i < len(durations):
                frame_tick += max(1, int(durations[i]))
            else:
                frame_tick += 1
        self.animation.frame = frame_tick
        self.animation.done = False

    def _handoff_finished_air_slash_to_fall(self, tilemap):
        self.was_ascending = False
        can_use_full_fall = self._can_expand_airborne_hitbox(tilemap, 'zero_falling')
        if not can_use_full_fall and 'zero_falling_compact' in self.game.assets:
            self.set_action('zero_falling_compact', force=True)
        else:
            self.set_action('zero_falling', force=True)
        if self.action in ('zero_falling', 'zero_falling_compact'):
            self._set_animation_frame_index(0)

    def render_debug(self, surf, offset=(0, 0)):
        super().render_debug(surf, offset)
        action = self.attack_action if self.attack_active else self.action
        if action in SWORD_HITBOXES:
            frame_idx = self.animation.frame_index()
            boxes = SWORD_HITBOXES[action].get(frame_idx, [])
            if boxes:
                img = self.animation.img()
                ox, oy = self._draw_offset(img)
                draw_x = int(self.pos[0] - offset[0] + ox)
                draw_y = int(self.pos[1] - offset[1] + oy)
                for x, y, w, h in boxes:
                    if self.flip:
                        x = img.get_width() - x - w
                    pygame.draw.rect(
                        surf,
                        (0, 128, 255),
                        (draw_x + int(x), draw_y + int(y), int(w), int(h)),
                        1
                    )

    def take_enemy_hit(self, enemy_x, allow_knockback=True):
        # central damage entry point so every enemy hit respects invulnerability and death flow
        if self.spawn_timer > 0 or self.dead or self.invuln_timer > 0 or self.giga_active:
            return False
        damage_floor = max(0, int(getattr(self.game, "damage_health_floor", 0) or 0))
        self.health = max(damage_floor, self.health - 4)
        self.invuln_timer = self.invuln_time
        self.hurt_timer = self.hurt_time
        self.attack_active = False
        self.attack_action = ''
        self.attack_kind = None
        self.attack_combo_step = 0
        self.attack_combo_timer = 0
        self.attack_combo_queued = False
        self.attack_timer = 0
        self.attack_end_timer = 0
        self.attack_end_action = ''
        self.dash_timer = 0
        self.dash_time = 0
        self.dash_ending = False
        self.dash_in_air = False
        self.dash_air_timer = 0
        self.dash_air_full = False
        self.dash_jump_queued = False
        if allow_knockback:
            hurt_vx, hurt_vy = self._safe_hurt_launch(enemy_x)
        else:
            hurt_vx, hurt_vy = 0.0, 0.0
        self.hspeed = hurt_vx
        self.air_hspeed = self.hspeed
        self.velocity[1] = hurt_vy
        try:
            hurt_sounds = getattr(self.game, 'sfx_hurt_sounds', [])
            if hurt_sounds:
                random.choice(hurt_sounds).play()
        except Exception:
            pass
        self.set_action('zero_hurt', force=True)
        if self.health <= 0:
            self.dead = True
            self.death_timer = self.death_time
            try:
                death_sound = getattr(self.game, 'sfx_death', None)
                if death_sound:
                    death_sound.play()
            except Exception:
                pass
        return True

    def _safe_hurt_knockback_x(self, enemy_x):
        desired = -self.hurt_knockback_x if self.rect().centerx < enemy_x else self.hurt_knockback_x
        tilemap = self._last_tilemap
        rect = self._last_rect if self._last_rect else self.rect()
        if not tilemap or desired == 0:
            return desired
        step_dir = -1 if desired < 0 else 1
        max_push = abs(desired)
        safe_push = max_push
        probe_steps = max(1, int(max_push * 4))
        for step in range(1, probe_steps + 1):
            test_push = (step / probe_steps) * max_push
            test_rect = rect.move(step_dir * test_push, 0)
            blocked = False
            for wall in tilemap.physics_rects_around(test_rect.topleft, test_rect.size):
                if test_rect.colliderect(wall):
                    blocked = True
                    break
            if blocked:
                safe_push = (step - 1) / probe_steps * max_push
                break
        return step_dir * safe_push

    def _safe_hurt_launch(self, enemy_x):
        desired_x = -self.hurt_knockback_x if self.rect().centerx < enemy_x else self.hurt_knockback_x
        desired_y = self.hurt_knockback_y
        tilemap = self._last_tilemap
        rect = self._last_rect if self._last_rect else self.rect()
        if not tilemap:
            return desired_x, desired_y
        steps = max(1, int(max(abs(desired_x), abs(desired_y)) * 6))
        safe_x = 0.0
        safe_y = 0.0
        for step in range(1, steps + 1):
            frac = step / steps
            test_x = desired_x * frac
            test_y = desired_y * frac
            test_rect = rect.move(test_x, test_y)
            blocked = False
            for wall in tilemap.physics_rects_around(test_rect.topleft, test_rect.size):
                if test_rect.colliderect(wall):
                    blocked = True
                    break
            if blocked:
                break
            safe_x = test_x
            safe_y = test_y
        # If horizontal launch is heavily constrained while grounded, avoid popping
        # upward into slope seams and letting the next frame resolve badly.
        if self.grounded and abs(safe_x) < abs(desired_x) * 0.5:
            safe_y = min(0.0, safe_y)
        # On slope-capable stages, keep grounded hurt knockback horizontal only.
        # This preserves the knockback feel without letting the upward launch
        # push Zero into floor seams and intermittently drop through terrain.
        if (
            self.grounded
            and getattr(tilemap, "allow_step_up", False)
            and self._has_ground_support(tilemap, rect)
        ):
            safe_y = max(0.0, safe_y)
        return safe_x, safe_y

    def restore_health(self, amount):
        if amount <= 0 or self.dead:
            return False
        prev = self.health
        self.health = min(self.max_health, self.health + amount)
        return self.health > prev

    def restore_giga_energy(self, amount):
        if amount <= 0 or self.dead or self.giga_active:
            return False
        prev = self.giga_energy
        self.giga_energy = min(self.max_giga_energy, self.giga_energy + amount)
        return self.giga_energy > prev

    def pickup_refill_active(self):
        return self.pickup_refill_kind is not None and self.pickup_refill_remaining > 0

    def start_pickup_refill(self, kind, amount):
        # pickups refill over time on purpose so the ui has a chance to sell the reward
        if amount <= 0 or self.dead or self.pickup_refill_active():
            return False
        if kind == "health":
            gain = min(amount, self.max_health - self.health)
        else:
            gain = min(amount, self.max_giga_energy - self.giga_energy)
        if gain <= 0:
            return False
        self.pickup_refill_kind = kind
        self.pickup_refill_remaining = gain
        self.pickup_refill_step_timer = self.pickup_refill_step_time
        try:
            if self.sfx_gain_channel:
                self.sfx_gain_channel.stop()
            gain_sound = getattr(self.game, "sfx_life_energy_gain", None)
            if gain_sound:
                gain_channel = getattr(self.game, "sfx_gain_channel", None)
                if gain_channel:
                    gain_channel.play(gain_sound, loops=-1)
                self.sfx_gain_channel = gain_channel
            else:
                self.sfx_gain_channel = None
        except Exception:
            self.sfx_gain_channel = None
        return True

    def update_pickup_refill(self):
        # tick one refill step at a time until the queued amount is gone
        if not self.pickup_refill_active():
            return False
        if self.pickup_refill_step_timer > 0:
            self.pickup_refill_step_timer -= 1
            return True
        if self.pickup_refill_kind == "health":
            self.health = min(self.max_health, self.health + 1)
        else:
            self.giga_energy = min(self.max_giga_energy, self.giga_energy + 1)
        self.pickup_refill_remaining -= 1
        if self.pickup_refill_remaining <= 0:
            self.pickup_refill_kind = None
            self.pickup_refill_remaining = 0
            self.pickup_refill_step_timer = 0
            if self.sfx_gain_channel:
                try:
                    self.sfx_gain_channel.stop()
                except Exception:
                    pass
                self.sfx_gain_channel = None
            return False
        self.pickup_refill_step_timer = self.pickup_refill_step_time
        return True

    def start_dash(self, input_dir=0):
        # decide whether the input should become a grounded dash, air dash, or buffered retry
        tilemap = self._last_tilemap
        slope_dash_ok = bool(tilemap and getattr(tilemap, "allow_step_up", False) and self.grounded)
        if self.spawn_timer > 0:
            return
        if self.dead or self.hurt_timer > 0:
            return
        if self.giga_active:
            return
        if self.dash_cooldown > 0:
            return
        if self.wall_kick_dash_cooldown_timer > 0:
            return
        if self.wall_slide and not self.grounded:
            return
        if (not slope_dash_ok) and ((self.collisions['left'] and input_dir < 0) or (self.collisions['right'] and input_dir > 0)):
            return
        if input_dir == 0:
            if (not slope_dash_ok) and ((self.collisions['left'] and self.flip) or (self.collisions['right'] and not self.flip)):
                return
        if input_dir < 0 and getattr(self, "wall_contact_dir", 0) < 0 and getattr(self, "wall_contact_timer", 0) > 0:
            return
        if input_dir > 0 and getattr(self, "wall_contact_dir", 0) > 0 and getattr(self, "wall_contact_timer", 0) > 0:
            return
        dash_dir = 0
        if input_dir != 0:
            dash_dir = -1 if input_dir < 0 else 1
        else:
            dash_dir = -1 if self.flip else 1
        if self._dash_blocked_by_wall(dash_dir, treat_as_dash=self.grounded):
            return
        if (not slope_dash_ok) and self._is_wall_adjacent(dash_dir):
            return
        if not self.grounded:
            if self.jump_pressed:
                return
            allow_wall_dash = self.wall_slide or self.wall_jump_timer > 0
            if (not allow_wall_dash) and (self.air_dash_used or self.air_jumps < self.max_air_jumps or self.dash_jump_used):
                return
        if self.attack_end_timer > 0:
            self.attack_end_timer = 0
            self.attack_end_action = ''
        if self.attack_active and self.attack_kind in ('air', 'wall'):
            # Apply cooldown when canceling air/wall slashes via dash to prevent rapid re-slash spam.
            if self.attack_kind == 'air':
                self.attack_air_cooldown = self.attack_air_cooldown_time
            elif self.attack_kind == 'wall':
                self.attack_wall_cooldown = self.attack_wall_cooldown_time
            if self.sfx_attack_channel:
                try:
                    self.sfx_attack_channel.stop()
                except Exception:
                    pass
                self.sfx_attack_channel = None
            self.attack_active = False
            self.attack_action = ''
            self.attack_kind = None
            self.attack_combo_step = 0
            self.attack_combo_timer = 0
            self.attack_combo_queued = False
            self.attack_timer = 0
        if self.attack_active and self.attack_kind == 'ground':
            if self.attack_timer >= self.attack_cancel_time:
                if self.sfx_attack_channel:
                    try:
                        self.sfx_attack_channel.stop()
                    except Exception:
                        pass
                    self.sfx_attack_channel = None
                self.attack_active = False
                self.attack_action = ''
                self.attack_kind = None
                self.attack_combo_step = 0
                self.attack_combo_timer = 0
                self.attack_combo_queued = False
                self.attack_timer = 0
            else:
                return
        self.dash_press_buffer = self.dash_press_time
        self.dash_input_dir = input_dir
        if self.jump_pressed and (self.grounded or self.coyote_timer > 0):
            if input_dir != 0:
                self.dash_dir = -1 if input_dir < 0 else 1
            else:
                self.dash_dir = -1 if self.flip else 1
            self.dash_jump_queued = True
            return
        if self.dash_timer > 0:
            self.dash_restart = True
            self.dash_time = 0
            self.dash_ending = False
            return
        if not self.grounded:
            self._begin_dash(input_dir, in_air=True)
            return
        self._begin_dash(input_dir, in_air=False)

    def _begin_dash(self, input_dir=0, in_air=False):
        # actual dash startup lives here once the caller has already decided it is allowed
        if input_dir != 0:
            self.dash_dir = -1 if input_dir < 0 else 1
        else:
            self.dash_dir = -1 if self.flip else 1
        self.dash_timer = 1
        self.dash_time = 0
        self.dash_cooldown = 20
        self.dash_in_air = in_air
        self.dash_air_full = in_air and input_dir != 0
        try:
            if self.sfx_dash_channel:
                self.sfx_dash_channel.stop()
            dash_sound = getattr(self.game, 'sfx_dash', None)
            self.sfx_dash_channel = dash_sound.play() if dash_sound else None
        except Exception:
            self.sfx_dash_channel = None
        if in_air:
            self.air_dash_used = True

    def end_dash(self, moving=False):
        was_air = self.dash_in_air
        self.dash_timer = 0
        self.dash_time = 0
        self.dash_end_move = moving
        self.dash_air_full = False
        if self.sfx_dash_channel:
            try:
                self.sfx_dash_channel.stop()
            except Exception:
                pass
            self.sfx_dash_channel = None
        if self.dash_in_air:
            self.dash_in_air = False
            self.hspeed = 0.0
            self.was_ascending = False
            self.jump_hold = False
            target_size = HITBOX_SIZES.get('zero_falling', (self.size[0], HITBOX_H))
            self._air_dash_release_size = target_size
            self._air_dash_release_pending = True
            self.velocity[1] = max(self.velocity[1], 0.6)
            self.dash_ending = False
            return
        if moving:
            self.dash_ending = False
            return
        self.hspeed = 0.0
        self.dash_ending = False
        self.set_action('zero_idle', force=True)

    def set_dash_hold(self, is_held):
        self.dash_hold = is_held
        if is_held:
            self.dash_press_buffer = self.dash_press_time

    def attack(self, input_dir=None):
        # queue combo followups when possible, otherwise start the most appropriate attack now
        if self.spawn_timer > 0:
            return
        if self.dead or self.hurt_timer > 0:
            return
        if self.giga_active:
            return
        # If jump and slash are pressed on the same frame, let jump win so we
        # do not start a grounded saber combo before the player has actually
        # left the floor.
        if self.jump_pressed and self._can_start_jump_from_current_state():
            return
        if self.dash_timer > 0 or self.dash_air_timer != 0 or self.dash_in_air or self.dash_ending:
            if not self.grounded:
                # Allow air slash to interrupt air dash, but not dash-jump momentum.
                if self.dash_in_air:
                    self.dash_timer = 0
                    self.dash_time = 0
                    self.dash_in_air = False
                    self.dash_ending = False
                    self.dash_air_full = False
                    self.dash_just_jump = False
                    self.air_hspeed = self.hspeed
            else:
                if self.dash_timer > 0 or self.dash_ending:
                    self.dash_timer = 0
                    self.dash_time = 0
                    self.dash_in_air = False
                    self.dash_ending = False
                    self.hspeed = 0.0
                    self.air_hspeed = 0.0
                else:
                    self.attack_buffer = self.attack_buffer_time
                    self.attack_buffer_dir = 0 if input_dir is None else input_dir
                    return
        if self.attack_active:
            if self.attack_kind == 'ground' and self.attack_combo_timer > 0 and self.attack_combo_step < 3:
                self.attack_combo_queued = True
                if not self.attack_combo_speedup_applied:
                    ratio = 0.0
                    if self.attack_combo_window > 0:
                        ratio = max(0.0, min(1.0, self.attack_combo_timer / self.attack_combo_window))
                    # Earlier inputs reduce the remaining frame durations (no frame skipping).
                    factor = self.attack_combo_speedup_min + (1.0 - self.attack_combo_speedup_min) * (1.0 - ratio)
                    self.animation.accelerate_remaining(factor=factor, min_dur=1)
                    self.attack_combo_speedup_applied = True
            return
        if self.grounded and self.attack_combo_timer > 0 and self.attack_combo_step in (1, 2):
            next_action = 'zero_saber_slash2' if self.attack_combo_step == 1 else 'zero_saber_slash3'
            self.attack_end_timer = 0
            self.attack_end_action = ''
            self._start_attack(next_action, 'ground', step=self.attack_combo_step + 1)
            return
        if self.wall_slide and not self.grounded:
            if self.attack_wall_cooldown > 0:
                return
            self.attack_end_timer = 0
            self.attack_end_action = ''
            self._start_attack('zero_wall_saber_slash', 'wall')
            return
        if not self.grounded:
            if self.attack_air_cooldown > 0:
                return
            self.attack_end_timer = 0
            self.attack_end_action = ''
            air_slash_action = 'zero_double_jump_slash' if (
                self.jump_is_air and 'zero_double_jump_slash' in self.game.assets
            ) else 'zero_air_saber_slash'
            self._start_attack(air_slash_action, 'air')
            return
        self.attack_end_timer = 0
        self.attack_end_action = ''
        self._start_attack('zero_saber_slash1', 'ground', step=1)

    def _start_attack(self, action, kind, step=0):
        # reset the shared attack state in one place so grounded, air, and wall attacks stay consistent
        self.attack_active = True
        self.attack_instance_id += 1
        self.attack_action = action
        self.attack_kind = kind
        self.attack_combo_step = step
        self.attack_combo_timer = self.attack_combo_window if kind == 'ground' else 0
        self.attack_combo_queued = False
        self.attack_combo_speedup_applied = False
        self.attack_timer = 0
        if kind == 'ground':
            self.hspeed = 0.0
            self.air_hspeed = 0.0
        if action in ('zero_saber_slash1', 'zero_saber_slash2', 'zero_saber_slash3',
                      'zero_air_saber_slash', 'zero_double_jump_slash', 'zero_wall_saber_slash'):
            try:
                if self.sfx_attack_channel:
                    self.sfx_attack_channel.stop()
                if action == 'zero_saber_slash1':
                    ground_slash1 = getattr(self.game, 'sfx_ground_slash1', [])
                    self.sfx_attack_channel = random.choice(ground_slash1).play() if ground_slash1 else None
                elif action == 'zero_saber_slash2':
                    ground_slash2 = getattr(self.game, 'sfx_ground_slash2', [])
                    self.sfx_attack_channel = random.choice(ground_slash2).play() if ground_slash2 else None
                elif action == 'zero_saber_slash3':
                    ground_slash3 = getattr(self.game, 'sfx_ground_slash3', None)
                    self.sfx_attack_channel = ground_slash3.play() if ground_slash3 else None
                else:
                    air_wall_slash = getattr(self.game, 'sfx_air_wall_slash', None)
                    self.sfx_attack_channel = air_wall_slash.play() if air_wall_slash else None
            except Exception:
                self.sfx_attack_channel = None
        self.set_action(action, force=True)

    def _action_total_duration(self, action):
        anim = getattr(self.game, "assets", {}).get(action)
        if not anim:
            return self.attack_end_time
        total = getattr(anim, "_total", 0)
        return max(1, int(total) if total else self.attack_end_time)

    def _build_giga_beam_queue(self):
        # precompute the staggered beam groups so the update loop only has to pop them in order
        if 'giga_attack_beam' not in self.game.assets:
            return []
        beam_img = self.game.assets['giga_attack_beam'].images[0]
        beam_w = int(beam_img.get_width() * self.giga_beam_scale)
        beam_h = int(beam_img.get_height() * self.giga_beam_scale)
        self.giga_beam_size = (beam_w, beam_h)
        center_x = self.pos[0] + self._hw / 2.0
        scroll_x, _ = getattr(self.game, 'render_scroll', (0, 0))
        left_bound = scroll_x - beam_w
        right_bound = scroll_x + getattr(self.game, 'arena_view_width', 0) + beam_w
        step = max(int(beam_w * 0.275), 8)
        queue = []
        level = 0
        while True:
            if level == 0:
                xs = [center_x] if left_bound <= center_x <= right_bound else []
            else:
                xs = []
                left_x = center_x - level * step
                right_x = center_x + level * step
                if left_bound <= left_x <= right_bound:
                    xs.append(left_x)
                if left_bound <= right_x <= right_bound:
                    xs.append(right_x)
            if xs:
                queue.append((xs, level))
            if center_x - level * step <= left_bound and center_x + level * step >= right_bound:
                break
            level += 1
            if level > 60:
                break
        return queue

    def _spawn_giga_beam_group(self, group):
        if not group:
            return
        if not hasattr(self.game, "giga_beams"):
            self.game.giga_beams = []
        xs, level = group
        beam_w, beam_h = self.giga_beam_size
        _, scroll_y = getattr(self.game, 'render_scroll', (0, 0))
        start_y = scroll_y - beam_h - (level * self.giga_beam_height_step)
        for x in xs:
            beam_x = int(x - beam_w / 2)
            self.game.giga_beams.append(GigaBeam(
                self.game,
                beam_x,
                start_y,
                speed=self.giga_beam_speed,
                scale=self.giga_beam_scale,
                delay=self.giga_beam_fall_delay
            ))

    def _do_giga_attack(self):
        if self.spawn_timer > 0:
            return
        if self.giga_active:
            return
        if not self._giga_attack_unlocked():
            return
        if 'zero_giga_attack' not in self.game.assets:
            return
        if self.giga_energy < self.max_giga_energy:
            return

        self.attack_active = False
        self.attack_action = ''
        self.attack_kind = None
        self.attack_combo_step = 0
        self.attack_combo_timer = 0
        self.attack_combo_queued = False
        self.attack_timer = 0
        self.attack_end_timer = 0
        self.attack_end_action = ''
        self.dash_timer = 0
        self.dash_time = 0
        self.dash_ending = False
        self.dash_in_air = False
        self.dash_air_timer = 0
        self.hspeed = 0.0
        self.air_hspeed = 0.0
        self.velocity[0] = 0
        self.giga_energy = 0

        self.giga_active = True
        self.giga_timer = 0
        self.giga_beam_queue = self._build_giga_beam_queue()
        self.giga_beam_index = 0
        self.giga_beam_timer = self.giga_beam_start_delay
        self.giga_request_timer = 0
        if hasattr(self.game, "giga_background_scroll"):
            self.game.giga_background_scroll = 0.0
        if hasattr(self.game, "giga_background_beam_seen"):
            self.game.giga_background_beam_seen = False
        try:
            if self.sfx_giga_channel:
                self.sfx_giga_channel.stop()
            giga_sound = getattr(self.game, 'sfx_giga_attack', None)
            self.sfx_giga_channel = giga_sound.play() if giga_sound else None
        except Exception:
            self.sfx_giga_channel = None
        self.set_action('zero_giga_attack', force=True)

    def _giga_attack_unlocked(self):
        if getattr(self.game, "stage_key", "") != "intro_stage":
            return True
        if not getattr(self.game, "intro_stage_guided", False):
            return True
        return bool(getattr(self.game, "intro_guided_giga_unlocked", False))

    def start_giga_attack(self):
        # begin the request animation first, then the real beam logic takes over a few frames later
        if self.spawn_timer > 0:
            return
        if self.dead or self.hurt_timer > 0:
            return
        if self.giga_active:
            return
        if not self._giga_attack_unlocked():
            return
        if self.giga_energy < self.max_giga_energy:
            return
        if self.grounded:
            self._do_giga_attack()
            return
        self.giga_request_timer = self.giga_request_time

    def _can_start_jump_from_current_state(self):
        if self.wall_slide and not self.grounded:
            return True
        if self.grounded or self.coyote_timer > 0:
            return True
        if self.air_jumps > 0 and not self.dash_jump_used and not self.air_dash_used:
            return True
        return False

    def jump(self, input_dir=None):
        # choose between ground jump, air jump, and wall jump based on the current contact state
        self.jump_pressed = True
        if self.spawn_timer > 0:
            return
        if self.dead or self.hurt_timer > 0:
            return
        if self.giga_active:
            return
        if not self._can_start_jump_from_current_state():
            return
        if self.attack_end_timer > 0:
            self.attack_end_timer = 0
            self.attack_end_action = ''
        if self.attack_active and self.attack_kind == 'air' and not self.grounded:
            self.attack_air_cooldown = self.attack_air_cooldown_time
            if self.sfx_attack_channel:
                try:
                    self.sfx_attack_channel.stop()
                except Exception:
                    pass
                self.sfx_attack_channel = None
            self.attack_active = False
            self.attack_action = ''
            self.attack_kind = None
            self.attack_combo_step = 0
            self.attack_combo_timer = 0
            self.attack_combo_queued = False
            self.attack_timer = 0
        if self.attack_active and self.attack_kind == 'ground':
            if self.sfx_attack_channel:
                try:
                    self.sfx_attack_channel.stop()
                except Exception:
                    pass
                self.sfx_attack_channel = None
            self.attack_active = False
            self.attack_action = ''
            self.attack_kind = None
            self.attack_combo_step = 0
            self.attack_combo_timer = 0
            self.attack_combo_queued = False
            self.attack_timer = 0
        if self.wall_slide and not self.grounded:
            dash_boost = self.dash_hold or self.dash_press_buffer > 0
            self._do_wall_jump(dash_boost=dash_boost, input_dir=input_dir)
            if dash_boost:
                self.dash_press_buffer = 0
            return
        if self.grounded or self.coyote_timer > 0:
            self._do_jump(is_air_jump=False)
            if self.dash_jump_queued or self.dash_hold:
                self.dash_air_timer = -1
                self.dash_air_speed = self.dash_speed * 0.53
                self.dash_jump_used = True
                self.air_hspeed = self.dash_dir * self.dash_air_speed
                self.dash_jump_queued = False
            return
        if self.air_jumps > 0 and not self.dash_jump_used and not self.air_dash_used:
            self._do_jump(is_air_jump=True)
            return

    def _do_jump(self, is_air_jump):
        # shared vertical launch logic for regular jumps and air jumps
        self.velocity[1] = -4.0
        self.jump_is_air = is_air_jump
        if is_air_jump:
            self._play_jump_sound(force_index=1)
        else:
            self._play_jump_sound(force_sound1=False)
        if is_air_jump:
            self.air_jumps -= 1
            self.air_dash_used = True
        else:
            self.coyote_timer = 0
            self.air_jumps = self.max_air_jumps
            self.wall_slide_grace_timer = self.wall_slide_grace_time
        self.air_time = 5
        self.was_ascending = True
        jump_action = 'zero_double_jump' if (is_air_jump and 'zero_double_jump' in self.game.assets) else 'zero_jumping'
        self.set_action(jump_action, force=True)
        if self.dash_timer > 0:
            self.dash_air_timer = -1
            self.dash_air_speed = self.dash_speed * 0.53
            self.dash_timer = 0
            self.dash_time = 0
            self.dash_ending = False
            self.dash_just_jump = True
            self.dash_jump_used = True
            self.air_hspeed = self.dash_dir * self.dash_air_speed

    def _do_wall_jump(self, dash_boost=False, input_dir=None):
        # wall jumps get their own launch tuning because they also need to peel the player off the wall
        self.wall_slide = False
        self.jump_is_air = False
        self.coyote_timer = 0
        self.air_jumps = self.max_air_jumps
        self.air_dash_used = False
        self.dash_jump_used = False
        self.dash_jump_queued = False
        self.dash_timer = 0
        self.dash_time = 0
        self.dash_ending = False
        self.dash_in_air = False
        self.dash_air_timer = 0
        self.dash_just_jump = False
        self.air_time = 5
        self.was_ascending = True
        self.wall_jump_dir = -self.wall_dir if self.wall_dir != 0 else (-1 if self.flip else 1)
        use_dir = self.current_input_dir if input_dir is None else input_dir
        facing_wall = False
        if self.wall_dir != 0:
            if use_dir != 0:
                facing_wall = (use_dir == self.wall_dir)
            else:
                facing_wall = (self.wall_dir < 0 and self.flip) or (self.wall_dir > 0 and not self.flip)
        if facing_wall and self.wall_dir != 0:
            self.flip = self.wall_dir < 0
            self.flip_lock_dir = self.wall_dir
        else:
            self.flip = self.wall_jump_dir < 0
            self.flip_lock_dir = self.wall_jump_dir
        self.flip_lock_timer = max(self.flip_lock_timer, 6)
        if dash_boost:
            self.velocity[1] = self.wall_dash_jump_wall_speed_y if facing_wall else self.wall_dash_jump_speed_y
            self.dash_air_timer = -1
            self.dash_air_speed = self.dash_speed * 0.53
            dash_jump_x = self.wall_dash_jump_wall_speed_x if facing_wall else self.wall_dash_jump_speed_x
            self.hspeed = self.wall_jump_dir * dash_jump_x
            self.air_hspeed = self.hspeed
            self.dash_jump_used = True
            self.wall_dash_lock_timer = self.wall_dash_lock_time
            self.wall_dash_lock_speed = self.dash_air_speed
        else:
            self.velocity[1] = self.wall_jump_speed_y
            self.hspeed = self.wall_jump_dir * self.wall_jump_speed_x
            self.air_hspeed = self.hspeed
        if self.wall_dir != 0:
            self.pos[0] += self.wall_jump_dir * 2
            r = self.rect()
            spark_y = r.bottom + 45 + self.wall_kick_spark_y_offset
            if self.wall_dir < 0:
                spark_x = r.left + 59 + self.wall_kick_spark_x_offset
                self._spawn_effect('wall_kick_spark', (spark_x, spark_y),
                                   img_dur=3, life=8, layer=1, anchor="bottomright")
            else:
                spark_x = r.right - 59 - self.wall_kick_spark_x_offset
                self._spawn_effect('wall_kick_spark', (spark_x, spark_y),
                                   img_dur=3, life=8, layer=1, anchor="bottomleft")
        self.wall_jump_lock = self.wall_jump_lock_time
        self.wall_jump_no_cling_timer = self.wall_jump_no_cling_time
        self.wall_jump_timer = self.wall_jump_anim_time
        self.wall_kick_dash_cooldown_timer = self.wall_kick_dash_cooldown_time
        try:
            wall_jump_sound = getattr(self.game, 'sfx_wall_jump', None)
            if wall_jump_sound:
                wall_jump_sound.play()
        except Exception:
            pass
        self.set_action('zero_wallkick_jump', force=True)

    def _interrupt_dash(self, facing_dir=0, hit_wall=False):
        was_air = self.dash_in_air
        self.dash_timer = 0
        self.dash_time = 0
        self.dash_ending = False
        self.dash_in_air = False
        self.hspeed = 0.0
        self.air_hspeed = 0.0
        self.dash_air_timer = 0
        if self.sfx_dash_channel:
            try:
                self.sfx_dash_channel.stop()
            except Exception:
                pass
            self.sfx_dash_channel = None
        if was_air:
            self.was_ascending = False
            self.jump_hold = False
            target_size = HITBOX_SIZES.get('zero_falling', (self.size[0], HITBOX_H))
            self._air_dash_release_size = target_size
            self._air_dash_release_pending = True
            self.velocity[1] = max(self.velocity[1], 0.6)
        if hit_wall and self.grounded:
            self.dash_stop_timer = self.dash_stop_time
        if facing_dir == 0 and hit_wall:
            facing_dir = self.dash_dir
        if facing_dir != 0:
            self.flip = facing_dir < 0
            self.flip_lock_dir = facing_dir
            self.flip_lock_timer = max(self.flip_lock_timer, self.dash_stop_time)

    def _is_wall_adjacent(self, dir_sign):
        tilemap = self._last_tilemap
        rect = self._last_rect if self._last_rect else self.rect()
        if not tilemap or dir_sign == 0:
            return False
        if dir_sign < 0:
            edge = rect.left
            for r in tilemap.physics_rects_around(rect.topleft, (rect.w, rect.h)):
                if r.top < rect.bottom and r.bottom > rect.top:
                    if 0 <= edge - r.right <= 1:
                        return True
                    if r.left < edge < r.right:
                        return True
        else:
            edge = rect.right
            for r in tilemap.physics_rects_around(rect.topleft, (rect.w, rect.h)):
                if r.top < rect.bottom and r.bottom > rect.top:
                    if 0 <= r.left - edge <= 1:
                        return True
                    if r.left < edge < r.right:
                        return True
        return False

    def _dash_blocked_by_wall(self, dir_sign, treat_as_dash=False):
        tilemap = self._last_tilemap
        rect = self._last_rect if self._last_rect else self.rect()
        if not tilemap or dir_sign == 0:
            return False
        max_step = self._step_up_height_for_motion(tilemap, dx=0, treat_as_dash=treat_as_dash)
        edge_x = rect.left if dir_sign < 0 else rect.right
        for wall in tilemap.physics_rects_around(rect.topleft, (rect.w, rect.h)):
            if wall.top >= rect.bottom or wall.bottom <= rect.top:
                continue
            if dir_sign < 0:
                touching = 0 <= edge_x - wall.right <= 1 or (wall.left < edge_x < wall.right)
            else:
                touching = 0 <= wall.left - edge_x <= 1 or (wall.left < edge_x < wall.right)
            if not touching:
                continue
            if wall.top < (rect.bottom - max_step):
                return True
        return False

    def _has_ground_support(self, tilemap, rect=None):
        if not tilemap:
            return False
        rect = rect if rect is not None else self.rect()
        probe = pygame.Rect(rect.left + 2, rect.bottom, max(1, rect.w - 4), 2)
        for ground in tilemap.physics_rects_around(probe.topleft, (probe.w, probe.h)):
            if ground.left < probe.right and ground.right > probe.left:
                if probe.colliderect(ground):
                    return True
                if 0 <= ground.top - rect.bottom <= 1:
                    return True
        return False

    def _set_rect_position(self, rect):
        ox, oy = self._hitbox_offsets()
        self.pos[0] = rect.x - ox
        self.pos[1] = rect.y - oy

    def _can_expand_airborne_hitbox(self, tilemap, action):
        if not tilemap:
            return True
        desired_w, desired_h = HITBOX_SIZES.get(action, (self.size[0], HITBOX_H))
        if desired_h <= self._hh and desired_w <= self._hw:
            return True
        rect = self.rect()
        test_rect = pygame.Rect(0, 0, desired_w, desired_h)
        test_rect.centerx = rect.centerx
        test_rect.bottom = rect.bottom
        test_rect = self._clamp_rect_to_arena(test_rect)
        if self._rect_outside_arena(test_rect):
            return False
        for wall in tilemap.physics_rects_around(test_rect.topleft, (test_rect.w, test_rect.h)):
            if test_rect.colliderect(wall):
                return False
        return True

    def _can_fit_hitbox_size(self, tilemap, width, height):
        if not tilemap:
            return True
        rect = self.rect()
        test_rect = pygame.Rect(0, 0, width, height)
        test_rect.centerx = rect.centerx
        test_rect.bottom = rect.bottom
        test_rect = self._clamp_rect_to_arena(test_rect)
        if self._rect_outside_arena(test_rect):
            return False
        return not self._rect_overlaps_solid(tilemap, test_rect)

    def _apply_hitbox_size(self, width, height):
        rect = self.rect()
        new_rect = pygame.Rect(0, 0, width, height)
        new_rect.centerx = rect.centerx
        new_rect.bottom = rect.bottom
        self._hw = width
        self._hh = height
        self._set_rect_position(new_rect)

    def _resolve_air_dash_end_clearance(self, tilemap, target_size, dash_dir=0):
        if not tilemap:
            return False
        start_rect = self.rect()
        target_w, target_h = target_size
        dx_candidates = [0]
        away = -1 if dash_dir > 0 else 1 if dash_dir < 0 else 0
        if away:
            dx_candidates.extend([away, away * 2, away * 3, -away])
        else:
            dx_candidates.extend([-1, 1, -2, 2])
        for dy in range(1, HITBOX_H + 25):
            for dx in dx_candidates:
                candidate = self._clamp_rect_to_arena(start_rect.move(dx, dy))
                if not self._is_safe_recovery_rect(tilemap, candidate):
                    continue
                target_rect = pygame.Rect(0, 0, target_w, target_h)
                target_rect.centerx = candidate.centerx
                target_rect.bottom = candidate.bottom
                target_rect = self._clamp_rect_to_arena(target_rect)
                if self._rect_outside_arena(target_rect) or self._rect_overlaps_solid(tilemap, target_rect):
                    continue
                self._set_rect_position(candidate)
                self._last_safe_rect = candidate.copy()
                return True
        return False

    def _rect_overlaps_solid(self, tilemap, rect=None):
        if not tilemap:
            return False
        rect = rect if rect is not None else self.rect()
        for wall in tilemap.physics_rects_around(rect.topleft, (rect.w, rect.h)):
            if rect.colliderect(wall):
                return True
        return False

    def _rect_has_ceiling_contact(self, tilemap, rect=None):
        if not tilemap:
            return False
        rect = rect if rect is not None else self.rect()
        for wall in tilemap.physics_rects_around(rect.topleft, (rect.w, rect.h)):
            if wall.left < rect.right and wall.right > rect.left:
                if 0 <= rect.top - wall.bottom <= 1:
                    return True
        return False

    def _rect_has_overhead_blocker(self, tilemap, rect=None, distance=12):
        if not tilemap:
            return False
        rect = rect if rect is not None else self.rect()
        max_gap = max(1, int(distance))
        for wall in tilemap.physics_rects_around((rect.left, rect.top - max_gap), (rect.w, rect.h + max_gap)):
            if wall.left < rect.right and wall.right > rect.left:
                gap = rect.top - wall.bottom
                if 0 <= gap <= max_gap:
                    return True
        return False

    def _has_blocked_deferred_expansion(self, tilemap, rect=None):
        if not tilemap or (self._deferred_hitbox_size is None and self._air_dash_release_size is None):
            return False
        rect = rect if rect is not None else self.rect()
        return self._rect_has_overhead_blocker(tilemap, rect, distance=3)

    def _rect_outside_arena(self, rect=None):
        rect = rect if rect is not None else self.rect()
        arena_bounds = getattr(self.game, "arena_bounds", None)
        if not arena_bounds:
            return False
        ox, _, w, _ = arena_bounds
        return rect.left < ox or rect.right > (ox + w)

    def _clamp_rect_to_arena(self, rect):
        clamped = rect.copy()
        arena_bounds = getattr(self.game, "arena_bounds", None)
        if not arena_bounds:
            return clamped
        ox, _, w, _ = arena_bounds
        if clamped.width >= w:
            clamped.centerx = ox + (w // 2)
            return clamped
        if clamped.left < ox:
            clamped.left = ox
        if clamped.right > (ox + w):
            clamped.right = ox + w
        return clamped

    def _is_safe_recovery_rect(self, tilemap, rect):
        if rect is None:
            return False
        rect = self._clamp_rect_to_arena(rect)
        return (not self._rect_outside_arena(rect)) and (not self._rect_overlaps_solid(tilemap, rect))

    def _refresh_contact_flags(self, tilemap):
        # recompute the lightweight wall/ground flags that a lot of movement code branches on
        rect = self.rect()
        contacts = {'up': False, 'down': False, 'right': False, 'left': False}
        for wall in tilemap.physics_rects_around(rect.topleft, (rect.w, rect.h)):
            if wall.top < rect.bottom and wall.bottom > rect.top:
                if 0 <= rect.left - wall.right <= 1:
                    contacts['left'] = True
                if 0 <= wall.left - rect.right <= 1:
                    contacts['right'] = True
            if wall.left < rect.right and wall.right > rect.left:
                if 0 <= rect.top - wall.bottom <= 1:
                    contacts['up'] = True
                if 0 <= wall.top - rect.bottom <= 1:
                    contacts['down'] = True
        if not contacts['down'] and self._has_ground_support(tilemap, rect):
            contacts['down'] = True
        self.collisions = contacts
        self.grounded = contacts['down']

    def _attempt_position_recovery(self, tilemap, fallback_rect=None):
        # if the player ever gets stuck in solids, search nearby safe spots before giving up
        if not tilemap:
            return False
        current_rect = self.rect()
        invalid = self._rect_outside_arena(current_rect) or self._rect_overlaps_solid(tilemap, current_rect)
        if not invalid:
            self._last_safe_rect = current_rect.copy()
            return False

        candidates = []
        for rect in (fallback_rect, self._last_safe_rect, self._last_rect, current_rect):
            if rect is None:
                continue
            candidates.append(self._clamp_rect_to_arena(rect.copy()))

        anchor = candidates[0].copy() if candidates else self._clamp_rect_to_arena(current_rect.copy())
        for radius in range(2, 25, 2):
            candidates.extend([
                anchor.move(0, -radius),
                anchor.move(0, radius),
                anchor.move(-radius, 0),
                anchor.move(radius, 0),
                anchor.move(-radius, -radius),
                anchor.move(radius, -radius),
                anchor.move(-radius, radius),
                anchor.move(radius, radius),
            ])

        recovery_rect = None
        for candidate in candidates:
            clamped = self._clamp_rect_to_arena(candidate)
            if self._is_safe_recovery_rect(tilemap, clamped):
                recovery_rect = clamped
                break

        if recovery_rect is None:
            return False

        self._set_rect_position(recovery_rect)
        self.hspeed = 0.0
        self.air_hspeed = 0.0
        self.velocity[0] = 0.0
        self.velocity[1] = min(0.0, self.velocity[1])
        self.dash_timer = 0
        self.dash_time = 0
        self.dash_ending = False
        self.dash_in_air = False
        self.wall_slide = False
        self.wall_dir = 0
        self.wall_stick_timer = 0
        self.wall_contact_timer = 0
        self._refresh_contact_flags(tilemap)
        if self.grounded:
            self.velocity[1] = 0
        self._last_safe_rect = recovery_rect.copy()
        return True

    def _prevent_compact_air_phase(self, tilemap, fallback_rect=None):
        if not tilemap or self.grounded:
            return False
        if self.action not in ('zero_double_jump', 'zero_double_jump_slash', 'zero_falling_compact'):
            return False
        compact_rect = self.rect()
        full_w, full_h = HITBOX_SIZES.get('zero_falling', (self.size[0], HITBOX_H))
        probe_rect = pygame.Rect(0, 0, full_w, full_h)
        probe_rect.centerx = compact_rect.centerx
        probe_rect.bottom = compact_rect.bottom
        if not self._rect_outside_arena(probe_rect) and not self._rect_overlaps_solid(tilemap, probe_rect):
            return False

        safe_rect = None
        for candidate in (fallback_rect, self._last_safe_rect, self._last_rect):
            if candidate is None:
                continue
            candidate = candidate.copy()
            if self._is_safe_recovery_rect(tilemap, candidate):
                safe_rect = candidate
                break
        if safe_rect is None:
            return False

        self._set_rect_position(safe_rect)
        self.hspeed = 0.0
        self.air_hspeed = 0.0
        self.velocity[0] = 0.0
        if self.velocity[1] < 0:
            self.velocity[1] = 0.0
        self._refresh_contact_flags(tilemap)
        return True

    def _resolve_air_corner_stick(self, tilemap):
        if not tilemap or self.grounded:
            return False
        if self.action not in ('zero_jumping', 'zero_double_jump', 'zero_air_saber_slash', 'zero_double_jump_slash', 'zero_falling_compact', 'zero_falling'):
            return False
        if not self.collisions.get('up'):
            return False
        if not (self.collisions.get('left') or self.collisions.get('right')):
            return False

        start_rect = self.rect()
        for dy in range(1, HITBOX_H + 1):
            candidate = self._clamp_rect_to_arena(start_rect.move(0, dy))
            if self._is_safe_recovery_rect(tilemap, candidate):
                self._set_rect_position(candidate)
                self.was_ascending = False
                self.jump_hold = False
                self.velocity[1] = max(self.velocity[1], 0.6)
                self._refresh_contact_flags(tilemap)
                self._last_safe_rect = candidate.copy()
                return True
        return False

    def _resolve_air_solid_embed(self, tilemap, fallback_rect=None):
        if not tilemap or self.grounded:
            return False
        start_rect = self.rect()
        if not self._rect_overlaps_solid(tilemap, start_rect):
            return False

        candidates = []
        for dy in range(1, HITBOX_H + 17):
            candidates.append(self._clamp_rect_to_arena(start_rect.move(0, dy)))
        for rect in (fallback_rect, self._last_safe_rect, self._last_rect):
            if rect is not None:
                candidates.append(self._clamp_rect_to_arena(rect.copy()))

        for candidate in candidates:
            if not self._is_safe_recovery_rect(tilemap, candidate):
                continue
            self._set_rect_position(candidate)
            self.was_ascending = False
            self.jump_hold = False
            self.hspeed = 0.0
            self.air_hspeed = 0.0
            self.velocity[0] = 0.0
            self.velocity[1] = max(self.velocity[1], 0.75)
            self._refresh_contact_flags(tilemap)
            self._last_safe_rect = candidate.copy()
            return True
        return False

    def _force_release_from_ceiling(self, tilemap, fallback_rect=None):
        if not tilemap or self.grounded:
            return False

        start_rect = self.rect()
        pinned = (
            self.collisions.get('up')
            or self._rect_has_ceiling_contact(tilemap, start_rect)
            or self._rect_overlaps_solid(tilemap, start_rect)
            or self._has_blocked_deferred_expansion(tilemap, start_rect)
        )
        if not pinned:
            return False

        candidates = []
        for dy in range(1, HITBOX_H + 25):
            candidates.append(self._clamp_rect_to_arena(start_rect.move(0, dy)))
            candidates.append(self._clamp_rect_to_arena(start_rect.move(-1, dy)))
            candidates.append(self._clamp_rect_to_arena(start_rect.move(1, dy)))
        for rect in (fallback_rect, self._last_safe_rect, self._last_rect):
            if rect is not None:
                candidates.append(self._clamp_rect_to_arena(rect.copy()))

        for candidate in candidates:
            if not self._is_safe_recovery_rect(tilemap, candidate):
                continue
            if self._rect_has_ceiling_contact(tilemap, candidate):
                continue
            self._set_rect_position(candidate)
            self.was_ascending = False
            self.jump_hold = False
            self.wall_slide = False
            self.wall_dir = 0
            self.hspeed = 0.0
            self.air_hspeed = 0.0
            self.velocity[0] = 0.0
            self.velocity[1] = max(self.velocity[1], 0.9)
            self._refresh_contact_flags(tilemap)
            self._last_safe_rect = candidate.copy()
            return True

        if fallback_rect is not None:
            fallback = self._clamp_rect_to_arena(fallback_rect.copy())
            if self._is_safe_recovery_rect(tilemap, fallback):
                self._set_rect_position(fallback)
                self.was_ascending = False
                self.jump_hold = False
                self.wall_slide = False
                self.wall_dir = 0
                self.hspeed = 0.0
                self.air_hspeed = 0.0
                self.velocity[0] = 0.0
                self.velocity[1] = max(self.velocity[1], 0.9)
                self._refresh_contact_flags(tilemap)
                self._last_safe_rect = fallback.copy()
                return True
        return False

    def set_jump_hold(self, is_held):
        self.jump_hold = is_held
        if not is_held and not self.jump_is_air:
            if self.velocity[1] < self.jump_cut_velocity:
                self.velocity[1] = self.jump_cut_velocity
                if self.jump_sound_index != 0:
                    self._play_jump_sound(force_sound1=True)

    def _play_jump_sound(self, force_sound1=False, force_index=None):
        jump_sounds = getattr(self.game, 'sfx_jump_sounds', [])
        if not jump_sounds:
            return
        try:
            if self.sfx_jump_channel:
                self.sfx_jump_channel.stop()
        except Exception:
            pass
        if force_index is not None:
            idx = max(0, min(force_index, len(jump_sounds) - 1))
        elif force_sound1:
            idx = 0
        else:
            weights = [0.40, 0.20, 0.20, 0.20]
            weights = weights[:len(jump_sounds)]
            idx = random.choices(range(len(jump_sounds)), weights=weights, k=1)[0]
        self.jump_sound_index = idx
        try:
            self.sfx_jump_channel = jump_sounds[idx].play()
        except Exception:
            self.sfx_jump_channel = None

    def update(self, tilemap, movement=(0, 0)):
        # one full player tick: inputs are already resolved, so this handles state, movement, combat, and fx
        prev_wall_slide = self.wall_slide
        recovery_rect = self._last_safe_rect or self._last_rect or self.rect().copy()
        if self._last_safe_rect is None and tilemap and not self._rect_overlaps_solid(tilemap, recovery_rect):
            self._last_safe_rect = self._clamp_rect_to_arena(recovery_rect.copy())
        if self.invuln_timer > 0:
            self.invuln_timer -= 1
        if self.hurt_timer > 0:
            self.hurt_timer -= 1
        if self.landing_sound_suppressed_frames > 0:
            self.landing_sound_suppressed_frames -= 1
        if self.dead:
            self.death_timer = max(0, self.death_timer - 1)
            self.hspeed *= 0.85
            self.air_hspeed *= 0.85
            self.velocity[0] = 0
            self.velocity[1] = 0
            if self.action != 'zero_hurt':
                self.set_action('zero_hurt', force=True)
            self.animation.update()
            return
        if self.spawn_timer > 0:
            if not self.spawn_sound_played:
                try:
                    spawn_sound = getattr(self.game, 'sfx_spawn', None)
                    if spawn_sound:
                        spawn_sound.play()
                except Exception:
                    pass
                self.spawn_sound_played = True
            self.spawn_timer -= 1
            self.hspeed = 0.0
            self.air_hspeed = 0.0
            self.velocity[0] = 0
            self.velocity[1] = 0
            self.dash_timer = 0
            self.dash_time = 0
            self.dash_ending = False
            self.dash_in_air = False
            if self.action != 'zero_spawning':
                self.set_action('zero_spawning', force=True)
            super().update(tilemap, movement=(0, 0))

            prev_grounded = self.grounded
            self.grounded = self.collisions['down']
            if self.grounded:
                self.air_time = 0
                self.air_jumps = self.max_air_jumps
                self.dash_air_timer = 0
                self.coyote_timer = self.coyote_max
                self.dash_jump_used = False
                self.air_dash_used = False
                self.air_hspeed = 0.0
                self.jump_is_air = False
                self.wall_slide = False
                self.wall_dir = 0
                self.wall_jump_timer = 0
                self.wall_stick_timer = 0
                self.wall_land_timer = 0

            self._attempt_position_recovery(tilemap, recovery_rect)

            self._last_tilemap = tilemap
            self._last_rect = self.rect()

            if self.animation.done or self.spawn_timer <= 0:
                self.spawn_timer = 0
                self.spawn_sound_played = False
                self.set_action('zero_idle', force=True)
            return

        if self.giga_active:
            prev_grounded = self.grounded
            self.hspeed = 0.0
            self.air_hspeed = 0.0
            self.velocity[0] = 0
            if prev_grounded and self.velocity[1] <= 0:
                # Keep a tiny downward push so ground collision stays registered.
                self.velocity[1] = 0.2
            if self.action != 'zero_giga_attack':
                self.set_action('zero_giga_attack', force=True)

            if self.giga_beam_timer > 0:
                self.giga_beam_timer -= 1
            elif self.giga_beam_index < len(self.giga_beam_queue):
                self._spawn_giga_beam_group(self.giga_beam_queue[self.giga_beam_index])
                self.giga_beam_index += 1
                self.giga_beam_timer = self.giga_beam_interval

            super().update(tilemap, movement=(0, 0))
            if not self.collisions['down'] and self.velocity[1] >= 0:
                entity_rect = self.rect()
                for rect in tilemap.physics_rects_around(entity_rect.topleft, (self._hw, self._hh)):
                    if rect.left < entity_rect.right and rect.right > entity_rect.left:
                        if rect.top - 1 <= entity_rect.bottom <= rect.top + 1 and entity_rect.top < rect.top:
                            ox, oy = self._hitbox_offsets()
                            self.pos[1] = rect.top - self._hh - oy
                            self.collisions['down'] = True
                            self.velocity[1] = 0
                            break
            self.grounded = self.collisions['down']
            self._attempt_position_recovery(tilemap, recovery_rect)
            self._last_tilemap = tilemap
            self._last_rect = self.rect()

            if (self.giga_beam_index >= len(self.giga_beam_queue)
                    and not getattr(self.game, "giga_beams", [])):
                self.giga_active = False
                if self.sfx_giga_channel:
                    try:
                        self.sfx_giga_channel.stop()
                    except Exception:
                        pass
                    self.sfx_giga_channel = None
                if self.grounded:
                    self.set_action('zero_idle', force=True)
                else:
                    self.set_action('zero_falling', force=True)
                return

            if not self.grounded:
                self.giga_active = False
                if self.sfx_giga_channel:
                    try:
                        self.sfx_giga_channel.stop()
                    except Exception:
                        pass
                    self.sfx_giga_channel = None
                if not self.grounded:
                    self.set_action('zero_falling', force=True)
                else:
                    self.set_action('zero_idle', force=True)
            return

        if self.dash_cooldown > 0:
            self.dash_cooldown -= 1

        if self.dash_buffer > 0:
            self.dash_buffer -= 1
            if self.grounded and self.dash_timer == 0 and self.dash_cooldown == 0:
                self._begin_dash(self.dash_input_dir)

        input_dir = movement[0]
        if self.hurt_timer > 0:
            movement = (0, movement[1])
            input_dir = 0
        if input_dir != 0:
            self.last_input_dir = 1 if input_dir > 0 else -1
            self.current_input_dir = self.last_input_dir
        else:
            self.current_input_dir = 0
        if self.flip_lock_timer > 0:
            self.flip_lock_timer -= 1
            if self.flip_lock_dir != 0:
                self.flip = self.flip_lock_dir < 0
        if self.wall_slide_grace_timer > 0:
            self.wall_slide_grace_timer -= 1
        if self.wall_jump_lock > 0:
            self.wall_jump_lock -= 1
        if self.wall_jump_no_cling_timer > 0:
            self.wall_jump_no_cling_timer -= 1
        if self.wall_dash_lock_timer > 0:
            self.wall_dash_lock_timer -= 1
        if self.wall_kick_dash_cooldown_timer > 0:
            self.wall_kick_dash_cooldown_timer -= 1
        if self.dash_smoke_timer > 0:
            self.dash_smoke_timer -= 1
        if self.dash_booster_timer > 0:
            self.dash_booster_timer -= 1
        if self.wall_slide_smoke_timer > 0:
            self.wall_slide_smoke_timer -= 1
        if self.dash_press_buffer > 0:
            self.dash_press_buffer -= 1
        if self.wall_contact_timer > 0:
            self.wall_contact_timer -= 1
        if self.dash_timer > 0:
            self.dash_time += 1
            self.flip = self.dash_dir < 0
            self.flip_lock_dir = -1 if self.flip else 1
            self.flip_lock_timer = max(self.flip_lock_timer, 1)
            if input_dir != 0 and (input_dir > 0) != (self.dash_dir > 0) and self.dash_time >= self.dash_min:
                self._interrupt_dash(facing_dir=input_dir)
            if self.dash_in_air:
                self.velocity[1] = 0
                hold_like = self.dash_hold or self.dash_air_full
                if (not hold_like and self.dash_time >= self.dash_air_min) or self.dash_time >= self.dash_air_max_hold:
                    self.end_dash(moving=False)
                else:
                    self.hspeed = self.dash_dir * ((self.dash_speed * 0.9) + self.dash_input_boost)
            else:
                if (not self.dash_hold and self.dash_time >= self.dash_min) or self.dash_time >= self.dash_max:
                    self.end_dash(moving=input_dir != 0)
                else:
                    self.hspeed = self.dash_dir * (self.dash_speed + self.dash_input_boost)

        if self.dash_air_timer != 0:
            if self.dash_air_timer > 0:
                self.dash_air_timer -= 1
            if input_dir != 0:
                target = input_dir * (self.dash_air_speed * 0.6)
            else:
                target = 0.0
            self.air_hspeed += (target - self.air_hspeed) * self.air_accel
            self.hspeed = self.air_hspeed
        if self.dash_air_timer == 0:
            self.dash_just_jump = False

        if self.wall_dash_lock_timer > 0:
            self.hspeed = self.wall_jump_dir * self.wall_dash_lock_speed
            self.air_hspeed = self.hspeed

        if self.attack_buffer > 0:
            self.attack_buffer -= 1
            if (not self.attack_active and self.dash_timer == 0 and self.dash_air_timer == 0
                    and not self.dash_in_air and not self.dash_ending):
                buffered_dir = self.attack_buffer_dir
                self.attack_buffer = 0
                self.attack_buffer_dir = 0
                self.attack(input_dir=buffered_dir)

        if self.attack_combo_timer > 0:
            self.attack_combo_timer -= 1
        if self.attack_active:
            self.attack_timer += 1
        if self.attack_combo_timer == 0 and not self.attack_active:
            self.attack_combo_step = 0
        if self.attack_air_cooldown > 0:
            self.attack_air_cooldown -= 1
        if self.attack_wall_cooldown > 0:
            self.attack_wall_cooldown -= 1


        if self.dash_timer > 0:
            movement = (self.hspeed, movement[1])
        elif self.wall_jump_lock > 0:
            movement = (self.hspeed, movement[1])
        else:
            if self.dash_air_timer != 0:
                movement = (self.hspeed + movement[0] * self.air_control, movement[1])
            else:
                movement = (movement[0] + self.hspeed, movement[1])

        if self.attack_active and self.attack_kind == 'ground':
            self.hspeed = 0.0
            self.air_hspeed = 0.0
            movement = (0, movement[1])
        if self.attack_end_timer > 0:
            self.hspeed = 0.0
            self.air_hspeed = 0.0
            movement = (0, movement[1])

        self.force_short = False
        desired_w, desired_h = HITBOX_SIZES.get(self.action, (self.size[0], HITBOX_H))
        desired_size = (desired_w, desired_h)
        if self._air_dash_release_size is not None:
            if self._can_fit_hitbox_size(tilemap, *self._air_dash_release_size):
                self._air_dash_release_size = None
            else:
                desired_size = (self._hw, self._hh)
        if self._deferred_hitbox_size is not None and self._deferred_hitbox_size != desired_size:
            self._deferred_hitbox_size = None
        if self._deferred_hitbox_size is not None:
            if self._can_fit_hitbox_size(tilemap, *self._deferred_hitbox_size):
                self._apply_hitbox_size(*self._deferred_hitbox_size)
                self._deferred_hitbox_size = None
        elif (self._hw, self._hh) != desired_size:
            larger = desired_w > self._hw or desired_h > self._hh
            if (not larger) or self._can_fit_hitbox_size(tilemap, desired_w, desired_h):
                self._apply_hitbox_size(desired_w, desired_h)
            else:
                self._deferred_hitbox_size = desired_size

        super().update(tilemap, movement=movement)

        if self._air_dash_release_pending and self._air_dash_release_size is not None:
            if self._can_fit_hitbox_size(tilemap, *self._air_dash_release_size):
                self._air_dash_release_size = None
            else:
                if self._resolve_air_dash_end_clearance(tilemap, self._air_dash_release_size, dash_dir=self.dash_dir):
                    self._refresh_contact_flags(tilemap)
                self.velocity[1] = max(self.velocity[1], 0.6)
            self._air_dash_release_pending = False

        self._prevent_compact_air_phase(tilemap, recovery_rect)

        best_rect = None
        if not self.collisions['down'] and self.velocity[1] >= 0:
            entity_rect = self.rect()
            snap_height = int(getattr(tilemap, "ground_snap_height", 1))
            if self.dash_timer > 0:
                snap_height = int(getattr(tilemap, "ground_snap_dash_height", snap_height))
            best_distance = None
            for rect in tilemap.physics_rects_around(entity_rect.topleft, (self._hw, self._hh)):
                if rect.left < entity_rect.right and rect.right > entity_rect.left:
                    if rect.top - 1 <= entity_rect.bottom <= rect.top + snap_height and entity_rect.top < rect.top:
                        distance = rect.top - entity_rect.bottom
                        if best_distance is None or distance < best_distance:
                            best_distance = distance
                            best_rect = rect
        if best_rect is not None:
            ox, oy = self._hitbox_offsets()
            self.pos[1] = best_rect.top - self._hh - oy
            self.collisions['down'] = True
            self.velocity[1] = 0

        self._attempt_position_recovery(tilemap, recovery_rect)
        self._resolve_air_solid_embed(tilemap, recovery_rect)
        self._force_release_from_ceiling(tilemap, recovery_rect)

        prev_grounded = self.grounded
        self.grounded = self.collisions['down']
        if not self.grounded and self.collisions['up']:
            self.was_ascending = False
            self.jump_hold = False
            if self.velocity[1] <= 0:
                self.velocity[1] = 0.35
        self._resolve_air_corner_stick(tilemap)
        self.grounded = self.collisions['down']
        current_rect = self.rect()
        if not self.grounded:
            current_center = (float(current_rect.centerx), float(current_rect.centery))
            pinned_now = (
                self.collisions.get('up')
                or self.collisions.get('left')
                or self.collisions.get('right')
                or self._rect_has_ceiling_contact(tilemap, current_rect)
                or self._rect_overlaps_solid(tilemap, current_rect)
                or self._has_blocked_deferred_expansion(tilemap, current_rect)
            )
            if (
                pinned_now
                and self.air_stuck_last_center is not None
                and abs(current_center[0] - self.air_stuck_last_center[0]) <= 0.5
                and abs(current_center[1] - self.air_stuck_last_center[1]) <= 0.5
            ):
                self.air_stuck_frames += 1
            else:
                self.air_stuck_frames = 0
            self.air_stuck_last_center = current_center
            if self.air_stuck_frames >= 2:
                self._force_release_from_ceiling(tilemap, recovery_rect)
                self.air_stuck_frames = 0
                self.air_stuck_last_center = (
                    float(self.rect().centerx),
                    float(self.rect().centery),
                )
                self.grounded = self.collisions['down']
        else:
            self.air_stuck_frames = 0
            self.air_stuck_last_center = None
        self.render_y_nudge = 0
        if self.grounded and self.dash_timer > 0 and getattr(tilemap, "allow_step_up", False):
            self.render_y_nudge = int(getattr(tilemap, "dash_render_y_nudge", 0))
        if self.grounded:
            self._air_dash_release_size = None
            self._air_dash_release_pending = False
            self.air_time = 0
            self.air_jumps = self.max_air_jumps
            self.dash_air_timer = 0
            self.coyote_timer = self.coyote_max
            self.dash_jump_used = False
            self.air_dash_used = False
            self.air_hspeed = 0.0
            self.jump_is_air = False
            self.wall_slide = False
            self.wall_dir = 0
            self.wall_jump_timer = 0
            self.wall_stick_timer = 0
            self.wall_land_timer = 0
            self.wall_cling_delay = 0
            self.dash_stop_timer = 0
            self.wall_kick_dash_cooldown_timer = 0
        else:
            self.air_time += 1
            if self.coyote_timer > 0:
                self.coyote_timer -= 1
        self.jump_pressed = False

        if self.giga_request_timer > 0:
            self.giga_request_timer -= 1
            if self.grounded and not self.giga_active:
                self._do_giga_attack()
                if self.giga_active:
                    return

        if self.dash_timer > 0:
            if (self.collisions['left'] and self.dash_dir < 0) or (self.collisions['right'] and self.dash_dir > 0):
                self._interrupt_dash(facing_dir=input_dir, hit_wall=True)
                if not self.grounded:
                    self.wall_cling_delay = self.wall_cling_delay_time
                else:
                    r = self.rect()
                    if self.dash_dir < 0:
                        self.wall_contact_dir = -1
                        self.wall_contact_edge = r.left
                        self.wall_contact_timer = self.wall_contact_time
                    elif self.dash_dir > 0:
                        self.wall_contact_dir = 1
                        self.wall_contact_edge = r.right
                        self.wall_contact_timer = self.wall_contact_time

        just_landed = self.grounded and not prev_grounded
        suppress_landing_feedback = self.landing_sound_suppressed_frames > 0
        if self.grounded:
            self.was_ascending = False
            self.landing_timer = 0 if (not just_landed or suppress_landing_feedback) else self.landing_timer

        if just_landed:
            if input_dir != 0:
                self.flip = input_dir < 0
            elif self.last_input_dir != 0:
                self.flip = self.last_input_dir < 0
            elif abs(self.hspeed) > 0.05:
                self.flip = self.hspeed < 0
            elif abs(self.air_hspeed) > 0.05:
                self.flip = self.air_hspeed < 0
            self.land_face_dir = -1 if self.flip else 1
            self.land_face_timer = self.land_face_time
            self.flip_lock_dir = self.land_face_dir
            self.flip_lock_timer = max(self.flip_lock_timer, self.land_face_time)
            if not suppress_landing_feedback:
                try:
                    land_sound = getattr(self.game, 'sfx_land', None)
                    if land_sound:
                        land_sound.play()
                except Exception:
                    pass

        grounded_for_anim = self.grounded or (prev_grounded and self.velocity[1] == 0)
        is_airborne = not grounded_for_anim

        if is_airborne:
            if self.velocity[1] < 0:
                self.was_ascending = True
            else:
                self.was_ascending = False

        if just_landed and not suppress_landing_feedback:
            self.landing_timer = 10

        if self.grounded:
            self.hspeed *= self.hspeed_ground_decay
            if abs(self.hspeed) < 0.05:
                self.hspeed = 0.0
        else:
            self.hspeed *= self.hspeed_air_decay

        # Dash effects (booster + ground smoke)
        if self.dash_timer > 0:
            img = self.animation.img()
            ox, oy = self._draw_offset(img)
            draw_x = self.pos[0] + ox
            draw_y = self.pos[1] + oy
            r = self.rect()
            foot_y = r.bottom + 44
            back_x = r.centerx - (self.dash_dir * self.dash_booster_back_offset)
            dir_sign = -1 if self.dash_dir > 0 else 1
            booster_x = back_x + (self.dash_booster_x_offset * dir_sign)
            booster_y = foot_y + self.dash_booster_y_offset
            smoke_x = back_x + (self.dash_smoke_x_offset * dir_sign)
            smoke_y = foot_y + self.dash_smoke_y_offset
            if self.dash_booster_anim:
                self.dash_booster_anim.update()
            if self.grounded and self.dash_smoke_timer <= 0:
                vx = -0.35 * self.dash_dir
                vy = -2.5
                self._spawn_effect('dash_smoke', (smoke_x, smoke_y),
                                   img_dur=4, life=16, vel=(vx, vy), damp=(0.9, 0.88),
                                   layer=-1, anchor="bottomcenter")
                self.dash_smoke_timer = self.dash_smoke_interval
        else:
            self.dash_smoke_timer = 0
            self.dash_booster_timer = 0
            if self.dash_booster_anim:
                self.dash_booster_anim.frame = 0
                self.dash_booster_anim.done = False

        # Wall slide smoke
        if self.wall_slide and not self.grounded:
            if self.wall_slide_smoke_timer <= 0:
                r = self.rect()
                smoke_y = r.bottom + 45
                if self.wall_dir < 0:
                    smoke_x = r.left + 59
                    anchor = "bottomright"
                else:
                    smoke_x = r.right - 59
                    anchor = "bottomleft"
                self._spawn_effect('wall_slide_smoke', (smoke_x, smoke_y),
                                   img_dur=4, life=12, vel=(0.15 * self.wall_dir, -0.05), layer=-1, anchor=anchor)
                self.wall_slide_smoke_timer = self.wall_slide_smoke_interval
        else:
            self.wall_slide_smoke_timer = 0

        if self.flip_lock_timer <= 0 and input_dir != 0:
            self.flip = input_dir < 0

        can_cling_left = self.collisions['left']
        can_cling_right = self.collisions['right']
        if hasattr(tilemap, 'wall_cling_allowed'):
            if can_cling_left:
                can_cling_left = tilemap.wall_cling_allowed(self.rect(), -1)
            if can_cling_right:
                can_cling_right = tilemap.wall_cling_allowed(self.rect(), 1)

        want_left = can_cling_left and input_dir < -0.1
        want_right = can_cling_right and input_dir > 0.1
        if want_left:
            self.wall_dir = -1
            self.wall_stick_timer = self.wall_stick_time
        elif want_right:
            self.wall_dir = 1
            self.wall_stick_timer = self.wall_stick_time
        elif self.wall_stick_timer > 0:
            self.wall_stick_timer -= 1

        wall_contact = (
            not self.grounded and
            self.wall_jump_lock == 0 and
            self.dash_timer == 0 and
            (can_cling_left or can_cling_right)
        )
        wall_slide_possible = (
            wall_contact and
            (want_left or want_right or prev_wall_slide or self.wall_stick_timer > 0) and
            (self.wall_slide_grace_timer == 0 or self.velocity[1] >= 0) and
            self.wall_jump_no_cling_timer == 0
        )

        blocked_by_wall = self.grounded and (
            (self.collisions['left'] and input_dir < -0.1) or
            (self.collisions['right'] and input_dir > 0.1)
        )

        if wall_slide_possible:
            self.wall_slide = True
            if self.velocity[1] < 0:
                self.velocity[1] = 0
            elif self.velocity[1] > self.wall_slide_speed:
                self.velocity[1] = self.wall_slide_speed
            self.hspeed = 0.0
            self.air_hspeed = 0.0
            if self.wall_dir == 0:
                if can_cling_left and not can_cling_right:
                    self.wall_dir = -1
                elif can_cling_right and not can_cling_left:
                    self.wall_dir = 1
            if not prev_wall_slide:
                self.wall_land_timer = self.wall_land_time
                try:
                    wall_land_sound = getattr(self.game, 'sfx_wall_land', None)
                    if wall_land_sound:
                        wall_land_sound.play()
                except Exception:
                    pass
        else:
            self.wall_slide = False
            if not can_cling_left and not can_cling_right:
                self.wall_dir = 0
            self.wall_cling_delay = 0
            if prev_wall_slide and not self.jump_pressed:
                self.dash_press_buffer = 0
                self.dash_air_timer = 0
                self.dash_air_speed = self.dash_speed
                self.hspeed = 0.0
                self.air_hspeed = 0.0

        if self.hurt_timer > 0:
            self.attack_active = False
            self.attack_action = ''
            self.attack_kind = None
            self.attack_combo_step = 0
            self.attack_combo_timer = 0
            self.attack_combo_queued = False
            self.attack_timer = 0
            self.attack_end_timer = 0
            self.attack_end_action = ''
            self.set_action('zero_hurt')
            self._last_tilemap = tilemap
            self._last_rect = self.rect()
            return

        if self.attack_active:
            if self.attack_kind == 'air' and (self.grounded or self.wall_slide):
                self.attack_air_cooldown = self.attack_air_cooldown_time
                if self.sfx_attack_channel:
                    try:
                        self.sfx_attack_channel.stop()
                    except Exception:
                        pass
                    self.sfx_attack_channel = None
                self.attack_active = False
                self.attack_action = ''
                self.attack_kind = None
                self.attack_combo_step = 0
                self.attack_combo_timer = 0
                self.attack_combo_queued = False
                self.attack_timer = 0
            if self.attack_kind == 'wall' and not self.wall_slide:
                if self.sfx_attack_channel:
                    try:
                        self.sfx_attack_channel.stop()
                    except Exception:
                        pass
                    self.sfx_attack_channel = None
                self.attack_active = False
                self.attack_action = ''
                self.attack_kind = None
                self.attack_combo_step = 0
                self.attack_combo_timer = 0
                self.attack_combo_queued = False
                self.attack_timer = 0
            if self.attack_active:
                if self.action != self.attack_action:
                    self.set_action(self.attack_action, force=True)
                if self.animation.done:
                    if self.attack_kind == 'ground' and self.attack_combo_queued and self.attack_combo_step < 3:
                        next_action = (
                            'zero_saber_slash2' if self.attack_combo_step == 1
                            else 'zero_saber_slash3'
                        )
                        self._start_attack(next_action, 'ground', step=self.attack_combo_step + 1)
                    else:
                        if self.attack_kind == 'ground':
                            self.attack_end_action = 'zero_saber_sheathe1'
                            self.attack_end_timer = self._action_total_duration(self.attack_end_action)
                        finished_attack_action = self.attack_action
                        if self.attack_kind == 'air':
                            self.attack_air_cooldown = self.attack_air_cooldown_time
                        elif self.attack_kind == 'wall':
                            self.attack_wall_cooldown = self.attack_wall_cooldown_time
                        self.attack_active = False
                        self.attack_action = ''
                        self.attack_kind = None
                        if self.attack_end_timer == 0:
                            self.attack_combo_step = 0
                            self.attack_combo_timer = 0
                        self.attack_combo_queued = False
                        self.attack_timer = 0
                        if (
                            finished_attack_action in ('zero_air_saber_slash', 'zero_double_jump_slash')
                            and not self.grounded
                            and not self.wall_slide
                        ):
                            self._handoff_finished_air_slash_to_fall(tilemap)

        if self.attack_end_timer > 0 and is_airborne:
            self.attack_end_timer = 0
            self.attack_end_action = ''

        if not self.attack_active and not is_airborne:
            if self.attack_end_timer > 0:
                self.attack_end_timer -= 1
                if self.attack_end_action in self.game.assets:
                    if self.action != self.attack_end_action:
                        self.set_action(self.attack_end_action, force=True)
                else:
                    if self.action != 'zero_idle':
                        self.set_action('zero_idle', force=True)
                return
            if self.dash_stop_timer > 0:
                self.dash_stop_timer -= 1
                if 'zero_dashing_wallstop' in self.game.assets:
                    if self.action != 'zero_dashing_wallstop':
                        self.set_action('zero_dashing_wallstop', force=True)
                elif 'zero_dashing_startloop' in self.game.assets:
                    if self.action != 'zero_dashing_startloop':
                        self.set_action('zero_dashing_startloop', force=True)
                else:
                    if self.action != 'zero_dashing':
                        self.set_action('zero_dashing', force=True)
                return
            if self.dash_ending:
                if self.action not in ('zero_dashing_end_idle',):
                    self.dash_ending = False
                elif self.animation.done:
                    self.dash_ending = False
            elif self.dash_timer > 0:
                if 'zero_dashing_startloop' in self.game.assets:
                    if self.dash_restart and 'zero_dashing_restart' in self.game.assets:
                        self.set_action('zero_dashing_restart', force=True)
                        self.dash_restart = False
                    else:
                        self.set_action('zero_dashing_startloop', force=self.dash_restart)
                        self.dash_restart = False
                else:
                    self.set_action('zero_dashing')
            elif self.landing_timer > 0:
                self.landing_timer -= 1
                self.set_action('zero_landing')
            elif blocked_by_wall:
                self.set_action('zero_idle')
            elif abs(movement[0]) > 0.2:
                self.set_action('zero_sprinting')
            else:
                self.set_action('zero_idle')
        elif not self.attack_active:
            self.landing_timer = 0
            if self.wall_jump_timer > 0:
                if self.action != 'zero_wallkick_jump':
                    self.set_action('zero_wallkick_jump', force=True)
                self.wall_jump_timer -= 1
                if self.animation.done:
                    self.wall_jump_timer = 0
            elif self.wall_slide:
                has_wall_land = 'zero_wall_land' in self.game.assets
                has_wall_slide = 'zero_wall_slide' in self.game.assets
                if self.wall_cling_delay > 0:
                    self.wall_cling_delay -= 1
                else:
                    if self.wall_land_timer > 0 and has_wall_land:
                        self.wall_land_timer -= 1
                        if self.action != 'zero_wall_land':
                            self.set_action('zero_wall_land', force=True)
                    elif self.action == 'zero_wall_land' and self.animation.done and has_wall_slide:
                        self.set_action('zero_wall_slide', force=True)
                    elif self.action not in ('zero_wall_land', 'zero_wall_slide'):
                        if has_wall_slide:
                            self.set_action('zero_wall_slide', force=True)
                        elif has_wall_land:
                            self.set_action('zero_wall_land', force=True)
            elif self.dash_timer > 0:
                if 'zero_dashing_startloop' in self.game.assets:
                    if self.dash_restart and 'zero_dashing_restart' in self.game.assets:
                        self.set_action('zero_dashing_restart', force=True)
                        self.dash_restart = False
                    else:
                        self.set_action('zero_dashing_startloop', force=self.dash_restart)
                        self.dash_restart = False
                else:
                    self.set_action('zero_dashing')
            elif self.was_ascending:
                previous_action = self.action
                if previous_action == 'zero_air_saber_slash':
                    self.was_ascending = False
                    can_use_full_fall = self._can_expand_airborne_hitbox(tilemap, 'zero_falling')
                    if not can_use_full_fall and 'zero_falling_compact' in self.game.assets:
                        self.set_action('zero_falling_compact')
                    else:
                        self.set_action('zero_falling')
                    if self.action in ('zero_falling', 'zero_falling_compact'):
                        self._set_animation_frame_index(0)
                elif previous_action in ('zero_falling', 'zero_falling_compact'):
                    can_use_full_fall = self._can_expand_airborne_hitbox(tilemap, 'zero_falling')
                    if not can_use_full_fall and 'zero_falling_compact' in self.game.assets:
                        if self.action != 'zero_falling_compact':
                            self.set_action('zero_falling_compact')
                    else:
                        if self.action != 'zero_falling':
                            self.set_action('zero_falling')
                elif self.jump_is_air and 'zero_double_jump' in self.game.assets:
                    self.set_action('zero_double_jump')
                else:
                    self.set_action('zero_jumping')
            else:
                can_use_full_fall = self._can_expand_airborne_hitbox(tilemap, 'zero_falling')
                if not can_use_full_fall and 'zero_falling_compact' in self.game.assets:
                    self.set_action('zero_falling_compact')
                else:
                    preserved_frame = self.animation.frame if self.action == 'zero_falling_compact' else None
                    self.set_action('zero_falling')
                    if preserved_frame is not None:
                        self.animation.frame = min(preserved_frame, max(0, self.animation._total - 1))

        if self.land_face_timer > 0:
            self.land_face_timer -= 1
            self.flip = self.land_face_dir < 0

        if (
            not self.grounded
            and self.action == 'zero_falling'
            and 'zero_falling_compact' in self.game.assets
            and (self._rect_overlaps_solid(tilemap) or not self._can_expand_airborne_hitbox(tilemap, 'zero_falling'))
        ):
            self.set_action('zero_falling_compact', force=True)
            self._attempt_position_recovery(tilemap, recovery_rect)

        self._last_tilemap = tilemap
        self._last_rect = self.rect()

        if self.grounded and self.dash_timer == 0 and not self.dash_ending and self.landing_timer == 0:
            if self.action in ('zero_falling', 'zero_falling_compact', 'zero_jumping', 'zero_double_jump'):
                if abs(movement[0]) > 0.2:
                    self.set_action('zero_sprinting')
                else:
                    self.set_action('zero_idle')
