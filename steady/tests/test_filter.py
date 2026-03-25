import pytest
import numpy as np
from steady.core.filter import TremorFilter, TremorProfile

class TestTremorFilter:
    def test_initial_profile_creation(self):
        """Test creating filter with predefined profiles"""
        filter_essential = TremorFilter('Essential Tremor')
        filter_parkinsons = TremorFilter('Parkinson\'s Tremor')

        assert filter_essential.current_profile.name == 'Essential Tremor'
        assert filter_parkinsons.current_profile.name == 'Parkinson\'s Tremor'

        assert 'smoothing_factor' in filter_essential.current_profile.params
        assert 'smoothing_factor' in filter_parkinsons.current_profile.params
