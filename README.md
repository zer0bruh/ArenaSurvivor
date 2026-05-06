# Arena Survivor

Arena Survivor is a 2D action game built in Python using Pygame as part of a college final project.

The goal of the project was to recreate the feel and core mechanics of a **Mega Man X–style game**, while adapting it into a survival-based gameplay loop.

---

## 🎯 About the Project

This project was developed within a limited timeframe as a final assignment.

The main objective was to design and program a fully playable game that captures the responsiveness and movement depth of Mega Man X, while applying key programming concepts such as:

- Game loop architecture  
- Object-oriented programming  
- Collision detection  
- Game state management  
- Player and enemy systems  

---

## 🎮 Gameplay Overview

The game focuses on **fast-paced, skill-based gameplay**:

- Movement system inspired by Mega Man X (run, jump, dash, air control, wall interactions)
- Multi-state melee combat (ground, air, combos)
- Enemies that actively track and pressure the player
- Health and power systems
- Increasing difficulty over time
- Score-based survival format instead of level progression

---

## 🎨 Assets

The project uses **Mega Man X assets (sprites, animations, etc.)** to match the intended gameplay style.

These assets were used to stay consistent with the original design goal and focus development on mechanics and programming rather than asset creation.

---

## 🚧 Current State

The game is **fully playable**, but remains a prototype:

- Some bugs and edge cases are present  
- Certain systems are simplified (especially collisions)  
- Code structure could be improved  
- Overall polish is limited  

---

## 🧠 Key Focus

This project was mainly about:
- Recreating a specific game feel (Mega Man X-style movement and combat)
- Building a complete game system from scratch
- Managing complexity in a larger project
- Iterating quickly within time constraints

---

## ⚠️ Limitations

- Simplified collision system (AABB)
- Basic enemy AI (tracking behavior)
- Limited polish and balancing
- Use of non-original assets

---

## 🚀 Possible Improvements

- Replace assets with original ones
- Improve enemy AI and behaviors
- Refactor code into a cleaner architecture
- Expand combat depth and mechanics
- Transition to a full game engine (Unity / Godot) *man this would have made things simpler*

---

## ▶️ Running the Game

```bash
pip install pygame
python main.py

## 💻 Releases

A compiled version of the game is available as a standalone app for both Windows and MacOS:

-*sorry linux users*
- Windows version (.exe)
- macOS version (.app)

You can always use the build_releases.py to rebundle the game into an application when making changes. It will create an app depending on the operating system in use. Linux has not been tested.
