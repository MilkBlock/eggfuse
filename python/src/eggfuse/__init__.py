"""Offline EggFuse compiler and post-inference source-semantic verifier."""
from .compiler import compile_projection, projection_recipe
from .verify import verify_crossrun

__all__ = ["compile_projection", "projection_recipe", "verify_crossrun"]
