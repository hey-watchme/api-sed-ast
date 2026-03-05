from __future__ import annotations

import os
from typing import Dict, List

import numpy as np
import torch
from transformers import ASTForAudioClassification, AutoFeatureExtractor

from .base import BaseSedBackend


class AstHfBackend(BaseSedBackend):
    """AST backend using Hugging Face checkpoints."""

    def __init__(self) -> None:
        self._model_name = os.getenv(
            "SED_MODEL_NAME",
            "MIT/ast-finetuned-audioset-10-10-0.4593",
        )
        self._model = None
        self._feature_extractor = None
        self._id2label = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    @property
    def backend_id(self) -> str:
        return "ast_hf"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def sample_rate(self) -> int:
        if self._feature_extractor is None:
            return 16000
        return int(self._feature_extractor.sampling_rate)

    def load(self) -> None:
        print(f"🔄 Loading model backend={self.backend_id}, model={self._model_name}")
        self._feature_extractor = AutoFeatureExtractor.from_pretrained(self._model_name)
        self._model = ASTForAudioClassification.from_pretrained(self._model_name)
        self._id2label = self._model.config.id2label
        self._model.to(self._device)
        self._model.eval()

        print("✅ Model loaded successfully")
        print(f"   - Backend: {self.backend_id}")
        print(f"   - Model: {self._model_name}")
        print(f"   - Device: {self._device}")
        print(f"   - Classes: {len(self._id2label)}")
        print(f"   - Sampling Rate: {self.sample_rate} Hz")

    def predict_events(
        self,
        audio_data: np.ndarray,
        top_k: int,
        threshold: float,
    ) -> List[Dict]:
        if self._model is None or self._feature_extractor is None or self._id2label is None:
            raise RuntimeError("Model backend is not loaded")

        inputs = self._feature_extractor(
            audio_data,
            sampling_rate=self.sample_rate,
            return_tensors="pt",
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits

        probs = torch.nn.functional.softmax(logits, dim=-1)[0]
        top_probs, top_indices = torch.topk(probs, min(top_k, len(probs)))

        predictions: List[Dict] = []
        for prob, idx in zip(top_probs.cpu(), top_indices.cpu()):
            score = prob.item()
            if score < threshold:
                continue

            label_id = idx.item()
            label = (
                self._id2label.get(label_id)
                or self._id2label.get(str(label_id))
                or f"Event_{label_id}"
            )
            predictions.append(
                {
                    "label": label,
                    "score": round(score, 4),
                }
            )

        return predictions

