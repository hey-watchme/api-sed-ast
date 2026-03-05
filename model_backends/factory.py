from __future__ import annotations

import os

from .base import BaseSedBackend


def create_backend() -> BaseSedBackend:
    backend_id = os.getenv("SED_MODEL_BACKEND", "ast_hf").strip().lower()

    if backend_id == "ast_hf":
        from .ast_hf_backend import AstHfBackend
        return AstHfBackend()

    raise ValueError(
        f"Unsupported SED_MODEL_BACKEND='{backend_id}'. "
        "Supported backends: ast_hf"
    )
