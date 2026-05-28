"""Visualization layer system.

Provides modular layer-based rendering:
- Base layer class
- Skeleton overlay layer
- Velocity vectors layer
- Motion trails layer
- Blade indicator layer
- HUD layer
- Vertical axis layer
- Joint angle layer
- Timer layer
"""

from src.visualization.layers.base import Layer, LayerContext, render_layers
from src.visualization.layers.blade_layer import BladeLayer
from src.visualization.layers.hud_layer import HUDLayer
from src.visualization.layers.joint_angle_layer import JointAngleLayer
from src.visualization.layers.skeleton_layer import SkeletonLayer
from src.visualization.layers.timer_layer import TimerLayer
from src.visualization.layers.trail_layer import TrailLayer
from src.visualization.layers.velocity_layer import VelocityLayer
from src.visualization.layers.vertical_axis_layer import VerticalAxisLayer

__all__ = [
    "BladeLayer",
    "HUDLayer",
    "JointAngleLayer",
    "Layer",
    "LayerContext",
    "SkeletonLayer",
    "TimerLayer",
    "TrailLayer",
    "VelocityLayer",
    "VerticalAxisLayer",
    "render_layers",
]
