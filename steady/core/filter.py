import numpy as np
import json
import os
import time
from typing import List, Tuple, Dict, Any
import uuid

class TremorProfile:
    def __init__(self, name: str, initial_params: Dict[str, float]):
        self.id = str(uuid.uuid4())
        self.name = name
        self.params = initial_params
        self.learning_history: List[Dict[str, Any]] = []

class TremorFilter:
    PREDEFINED_PROFILES = {
        'Essential Tremor': {
            'smoothing_factor': 0.3,
            'frequency_range': (8, 12),
            'amplitude_threshold': 5
        },
        'Parkinson\'s Tremor': {
            'smoothing_factor': 0.5,
            'frequency_range': (4, 6),
            'amplitude_threshold': 10
        },
        'Cerebellar Tremor': {
            'smoothing_factor': 0.4,
            'frequency_range': (3, 7),
            'amplitude_threshold': 8
        }
    }

    def __init__(self, profile_name: str = 'Essential Tremor'):
        self.current_profile = self._load_or_create_profile(profile_name)
        self.x_state = None
        self.y_state = None
        self.correction_history: List[Dict[str, Any]] = []

    def _load_or_create_profile(self, profile_name: str) -> TremorProfile:
        """Load existing profile or create from predefined profiles"""
        if profile_name in self.PREDEFINED_PROFILES:
            return TremorProfile(
                profile_name,
                self.PREDEFINED_PROFILES[profile_name]
            )

        # If custom profile, try to load from persistent storage
        return self._load_custom_profile(profile_name)

    def _load_custom_profile(self, profile_name: str) -> TremorProfile:
        """Load or create a custom profile"""
        profiles_dir = os.path.join(os.path.expanduser('~'), '.steady', 'profiles')
        os.makedirs(profiles_dir, exist_ok=True)
        profile_path = os.path.join(profiles_dir, f"{profile_name}.json")

        if os.path.exists(profile_path):
            with open(profile_path, 'r') as f:
                profile_data = json.load(f)
                return TremorProfile(**profile_data)

        # If no existing profile, create a new one based on default
        return TremorProfile(
            profile_name,
            self.PREDEFINED_PROFILES['Essential Tremor']
        )

    def filter_position(self, raw_position: Tuple[float, float]) -> Tuple[float, float]:
        """
        Apply tremor filtering to raw mouse position

        Args:
            raw_position: (x, y) coordinates of mouse

        Returns:
            Filtered (x, y) coordinates
        """
        x, y = raw_position

        # Initialize states if first run
        if self.x_state is None:
            self.x_state = x
            self.y_state = y
            return raw_position

        # Apply different smoothing factors for X and Y
        smoothing_x = self.current_profile.params.get('smoothing_factor', 0.3)
        smoothing_y = smoothing_x * 1.5  # Slightly more Y-axis smoothing

        # Kalman-like filter with adaptive smoothing
        self.x_state = (1 - smoothing_x) * self.x_state + smoothing_x * x
        self.y_state = (1 - smoothing_y) * self.y_state + smoothing_y * y

        # Track correction
        correction = self._calculate_correction(raw_position, (self.x_state, self.y_state))
        self.correction_history.append(correction)

        return (self.x_state, self.y_state)

    def _calculate_correction(self, raw_position: Tuple[float, float],
                               filtered_position: Tuple[float, float]) -> Dict[str, Any]:
        dx = filtered_position[0] - raw_position[0]
        dy = filtered_position[1] - raw_position[1]
        magnitude = (dx ** 2 + dy ** 2) ** 0.5
        return {
            'timestamp': time.time(),
            'raw': raw_position,
            'filtered': filtered_position,
            'delta': (dx, dy),
            'magnitude': magnitude,
        }

    def update_params(self, delta: dict) -> None:
        """Update filter parameters in-place. Called by MLAdapter or training result."""
        self.current_profile.params.update(delta)
        self.current_profile.learning_history.append({
            'timestamp': time.time(),
            'params': dict(self.current_profile.params),
        })
        if len(self.current_profile.learning_history) > 1000:
            self.current_profile.learning_history = \
                self.current_profile.learning_history[-500:]
