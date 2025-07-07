"""
API Endpoints module
"""

# Importações dos routers
from . import people, cameras, recognition, unknown, system

__all__ = [
    "people",
    "cameras", 
    "recognition",
    "unknown",
    "system"
]