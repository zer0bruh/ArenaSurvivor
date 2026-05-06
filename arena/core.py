import pygame


class Animation:
    def __init__(self, images, img_dur=5, loop=True, loop_from=0):
        # store durations as per-frame ticks so we can mix fixed and authored timing
        self.images = images
        self.loop = loop
        self.loop_from = loop_from
        self.done = False
        self.frame = 0

        if isinstance(img_dur, (list, tuple)):
            self.durations = list(img_dur)
        else:
            self.durations = [int(img_dur)] * len(images)

        self._boundaries = []
        total = 0
        for d in self.durations:
            total += d
            self._boundaries.append(total)
        self._total = total
        self._loop_start_tick = sum(self.durations[:loop_from])

    def copy(self):
        anim = Animation.__new__(Animation)
        anim.images = self.images
        anim.loop = self.loop
        anim.loop_from = self.loop_from
        anim.done = False
        anim.frame = 0
        anim.durations = self.durations
        anim._boundaries = self._boundaries
        anim._total = self._total
        anim._loop_start_tick = self._loop_start_tick
        return anim

    def update(self):
        # advance the frame counter and then clamp or wrap depending on the animation style
        self.frame += 1
        if self.loop:
            if self.frame >= self._total:
                loop_duration = self._total - self._loop_start_tick
                if loop_duration > 0:
                    self.frame = self._loop_start_tick + (self.frame - self._loop_start_tick) % loop_duration
                else:
                    self.frame = self._loop_start_tick
        else:
            if self.frame >= self._total:
                self.frame = self._total - 1
                self.done = True

    def img(self):
        for i, boundary in enumerate(self._boundaries):
            if self.frame < boundary:
                return self.images[i]
        return self.images[-1]

    def frame_index(self):
        for i, boundary in enumerate(self._boundaries):
            if self.frame < boundary:
                return i
        return max(0, len(self.images) - 1)

    def accelerate_remaining(self, factor=0.8, min_dur=1):
        # speed up the tail end of a one-shot animation without restarting the current frame
        if self.loop or not self.durations:
            return
        if factor >= 1.0:
            return
        if factor <= 0:
            factor = 0.1
        prev_boundary = 0
        cur_index = None
        ticks_into = 0
        for i, boundary in enumerate(self._boundaries):
            if self.frame < boundary:
                cur_index = i
                ticks_into = self.frame - prev_boundary
                break
            prev_boundary = boundary
        if cur_index is None:
            return
        new_durations = list(self.durations)
        for i in range(cur_index, len(new_durations)):
            new_durations[i] = max(min_dur, int(new_durations[i] * factor))
        self.durations = new_durations
        self._boundaries = []
        total = 0
        for d in new_durations:
            total += d
            self._boundaries.append(total)
        self._total = total
        new_prev = sum(new_durations[:cur_index])
        cur_dur = new_durations[cur_index]
        self.frame = new_prev + min(ticks_into, max(cur_dur - 1, 0))
        if self.frame < 0:
            self.frame = 0
        if self.frame >= self._total:
            self.frame = self._total - 1


class Effect:
    def __init__(self, images, pos, img_dur=4, loop=False, vel=(0, 0), accel=(0, 0), damp=(1.0, 1.0),
                 life=None, layer=0, flip=False, scale=1.0):
        # effects reuse the same animation helper as gameplay sprites, just with lightweight motion
        if images and scale != 1.0:
            scaled = []
            for img in images:
                scaled.append(pygame.transform.scale(
                    img,
                    (int(img.get_width() * scale), int(img.get_height() * scale))
                ))
            images = scaled
        self.animation = Animation(images, img_dur=img_dur, loop=loop)
        self.pos = [pos[0], pos[1]]
        self.vel = [vel[0], vel[1]]
        self.accel = [accel[0], accel[1]]
        self.damp = [damp[0], damp[1]]
        self.life = life
        self.layer = layer
        self.flip = flip
        self.scale = scale

    def update(self):
        # effect motion is intentionally tiny and self-contained: accel, damp, then lifetime expiry
        self.vel[0] += self.accel[0]
        self.vel[1] += self.accel[1]
        self.vel[0] *= self.damp[0]
        self.vel[1] *= self.damp[1]
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]
        self.animation.update()
        if self.life is not None:
            self.life -= 1
            if self.life <= 0:
                return False
        else:
            if (not self.animation.loop) and self.animation.done:
                return False
        return True

    def render(self, surf, offset=(0, 0)):
        img = self.animation.img()
        if self.flip:
            img = pygame.transform.flip(img, True, False)
        surf.blit(img, (self.pos[0] - offset[0], self.pos[1] - offset[1]))
