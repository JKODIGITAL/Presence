"""
Utility functions for the presence application
"""

import numpy as np
from typing import Any


def make_json_serializable(obj: Any) -> Any:
    """
    Convert numpy types and other non-JSON-serializable types to JSON-serializable Python types.
    
    This function recursively processes dictionaries, lists, and tuples to ensure all
    nested values are JSON-serializable.
    
    Args:
        obj: The object to convert
        
    Returns:
        A JSON-serializable version of the object
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    else:
        return obj


def convert_bbox_to_python_ints(bbox) -> tuple:
    """
    Convert bounding box coordinates to Python ints.
    
    Args:
        bbox: Bounding box as list or tuple (x, y, width, height)
        
    Returns:
        Tuple with Python int values
    """
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        return tuple(int(x) for x in bbox[:4])
    else:
        return (0, 0, 0, 0)


def safe_float_conversion(value, default: float = 0.0) -> float:
    """
    Safely convert a value to float, handling numpy types.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value
    """
    try:
        if isinstance(value, (np.floating, np.integer)):
            return float(value)
        elif value is not None:
            return float(value)
        else:
            return default
    except (ValueError, TypeError):
        return default


def safe_int_conversion(value, default: int = 0) -> int:
    """
    Safely convert a value to int, handling numpy types.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Int value
    """
    try:
        if isinstance(value, (np.integer, np.floating)):
            return int(value)
        elif value is not None:
            return int(value)
        else:
            return default
    except (ValueError, TypeError):
        return default