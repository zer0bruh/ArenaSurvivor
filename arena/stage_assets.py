import os
import pygame


# tiny loaders for the stage-select background animations
def load_animated_stage(assets_dir, width, height, stage_key, file_prefix):
    frames = []
    stage_path = os.path.join(assets_dir, 'stages', stage_key)

    for i in range(1, 11):
        filename = f"{file_prefix} background{i}.png"
        path = os.path.join(stage_path, filename)

        if os.path.exists(path):
            img = pygame.image.load(path).convert()
            img = pygame.transform.scale(img, (width, height))
            frames.append(img)

    return frames


def load_snow_animation(assets_dir, width, height):
    # northern uses its own overlay sequence instead of the generic background naming
    frames = []
    stage_path = os.path.join(assets_dir, 'stages', 'northern')

    for i in range(1, 7):
        filename = f"northern area snow{i}.png"
        path = os.path.join(stage_path, filename)

        img = pygame.image.load(path).convert_alpha()
        img = pygame.transform.scale(img, (width, height))
        frames.append(img)

    return frames
