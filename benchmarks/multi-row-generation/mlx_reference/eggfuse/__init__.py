"""Python interface to the EggFuse two-Run Cell inference prototype."""
from .api import infer, load_model
from .compiler import compile_projection, projection_recipe
from .model import CrossRun, decode

__all__ = ['CrossRun', 'compile_projection', 'decode', 'infer', 'load_model', 'projection_recipe']
