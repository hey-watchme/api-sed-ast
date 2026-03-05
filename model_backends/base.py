from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

import numpy as np


class BaseSedBackend(ABC):
    """Common interface for pluggable SED backends."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Stable backend identifier, e.g. `ast_hf`."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name or checkpoint identifier."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Input sample rate expected by this backend."""

    @abstractmethod
    def load(self) -> None:
        """Load model weights/resources."""

    @abstractmethod
    def predict_events(
        self,
        audio_data: np.ndarray,
        top_k: int,
        threshold: float,
    ) -> List[Dict]:
        """Predict events from a preprocessed audio segment."""

