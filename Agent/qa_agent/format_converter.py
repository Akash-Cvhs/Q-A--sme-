"""
Format Converter for Enrollment Forms
Handles conversion between nested {value, confidence} format and flat format
"""

from typing import Any, Dict, Tuple


def extract_value(data: Any) -> Any:
    """
    Recursively extract value from nested {value, confidence} structure.
    
    Args:
        data: Data that might be nested
        
    Returns:
        Extracted value (flat)
    """
    if isinstance(data, dict):
        if 'value' in data:
            # This is a {value, confidence} structure - extract the value
            return extract_value(data['value'])
        else:
            # Regular dict - recurse on all values
            return {key: extract_value(val) for key, val in data.items()}
    elif isinstance(data, list):
        # Process list items
        return [extract_value(item) for item in data]
    else:
        # Primitive value - return as-is
        return data


def is_nested_format(data: Any) -> bool:
    """
    Check if data uses nested {value, confidence} format.
    
    Args:
        data: Data to check
        
    Returns:
        bool: True if nested format detected
    """
    if not isinstance(data, dict):
        return False
    
    # Check if it has 'value' key (confidence is optional)
    if 'value' in data:
        return True
    
    # Check nested objects recursively
    for value in data.values():
        if is_nested_format(value):
            return True
    
    return False


def create_metadata(original: Any, flattened: Any, path: str = "") -> Dict:
    """
    Create metadata map to track which fields were nested.
    
    Args:
        original: Original data structure
        flattened: Flattened data structure
        path: Current path (for tracking)
        
    Returns:
        dict: Metadata for restoration
    """
    if isinstance(original, dict) and 'value' in original:
        # This was a {value, confidence} node
        return {
            'is_nested': True,
            'confidence': original.get('confidence', 1.0),
            'original_value': original.get('value')
        }
    elif isinstance(original, dict):
        # Regular dict - recurse
        metadata = {}
        for key, val in original.items():
            if key in flattened or isinstance(val, dict):
                metadata[key] = create_metadata(
                    val, 
                    flattened.get(key) if isinstance(flattened, dict) else None,
                    f"{path}.{key}" if path else key
                )
        return metadata
    elif isinstance(original, list):
        return {'is_list': True}
    else:
        return {'is_nested': False}


def restore_structure(data: Any, metadata: Any) -> Any:
    """
    Restore nested {value, confidence} format from flat format.
    
    Args:
        data: Flattened data
        metadata: Metadata from original structure
        
    Returns:
        Data with restored nested structure
    """
    if not isinstance(metadata, dict):
        return data
    
    if metadata.get('is_nested'):
        # Restore {value, confidence} structure
        return {
            'value': data,
            'confidence': metadata.get('confidence', 1.0)
        }
    elif metadata.get('is_list'):
        # Keep list as-is
        return data
    elif isinstance(data, dict) and isinstance(metadata, dict):
        # Recurse on dict
        restored = {}
        for key, val in data.items():
            if key in metadata:
                restored[key] = restore_structure(val, metadata[key])
            else:
                # New field added during processing - keep as-is
                restored[key] = val
        return restored
    else:
        # Primitive or no metadata - return as-is
        return data


def flatten_form(form_data: dict) -> Tuple[dict, dict]:
    """
    Convert nested {value, confidence} format to flat format.
    
    Args:
        form_data: Form with nested structure
        
    Returns:
        Tuple of (flattened_form, metadata_map)
    """
    # Deep flatten using extract_value
    flattened = extract_value(form_data)
    
    # Create metadata for restoration
    metadata = create_metadata(form_data, flattened)
    
    return flattened, metadata


def restore_form_structure(form_data: dict, metadata: dict) -> dict:
    """
    Restore nested {value, confidence} format from flat format.
    
    Args:
        form_data: Flattened form data
        metadata: Original structure metadata
        
    Returns:
        dict: Form with restored nested structure
    """
    return restore_structure(form_data, metadata)


def convert_input(form_data: dict) -> Tuple[dict, dict, bool]:
    """
    Convert input form to flat format if needed.
    
    Args:
        form_data: Input form data
        
    Returns:
        Tuple of (processed_form, metadata, was_nested)
    """
    # Check if form uses nested format
    if is_nested_format(form_data):
        # Convert to flat format
        flattened_form, metadata = flatten_form(form_data)
        return flattened_form, metadata, True
    else:
        # Already flat format
        return form_data, {}, False


def convert_output(form_data: dict, metadata: dict, was_nested: bool) -> dict:
    """
    Convert output form back to original format if needed.
    
    Args:
        form_data: Processed form data
        metadata: Structure metadata from input
        was_nested: Whether input was in nested format
        
    Returns:
        dict: Form in original format
    """
    if not was_nested or not metadata:
        # Was already flat, return as-is
        return form_data
    
    # Restore nested format
    return restore_form_structure(form_data, metadata)
