"""Synthetic two-Run provenance probes over archived, CPU-verified equivalence partitions."""
from .source import dataset, STATES, PROBES, MAKE_ROUTES, FINISH_ROUTES
from .check import audit
from .paired import paired_controls
__all__=['dataset','audit','paired_controls','STATES','PROBES','MAKE_ROUTES','FINISH_ROUTES']
