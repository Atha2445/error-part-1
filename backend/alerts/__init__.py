"""
alerts/ — Unified Multi-Threat Safety Detection Package.
"""
from .fire.detector import FireSmokeDetector
from .dog.detector import DogAttackDetector
from .fight.detector import FightDetector

__all__ = ["FireSmokeDetector", "DogAttackDetector", "FightDetector"]

