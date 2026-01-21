"""
Prompt loader with fallback mechanism.
Loads prompts from /private/ if available, otherwise falls back to /private.example/
"""

import os
import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache

# Base paths
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_PRIVATE_DIR = _BASE_DIR / 'private'
_EXAMPLE_DIR = _BASE_DIR / 'private.example'

# Track which resources are using fallback (example)
_using_fallback: Dict[str, bool] = {}


def _check_fallback_status() -> Dict[str, bool]:
    """
    Proactively check if we're using fallback resources by checking directory existence.
    This doesn't require loading the modules first.
    """
    status = {}

    # Check prompts
    private_prompts = _PRIVATE_DIR / 'prompts'
    example_prompts = _EXAMPLE_DIR / 'prompts'
    if private_prompts.exists() and any(private_prompts.glob('*.py')):
        status['prompts'] = False
    elif example_prompts.exists():
        status['prompts'] = True

    # Check seed_data
    private_seed = _PRIVATE_DIR / 'seed_data'
    example_seed = _EXAMPLE_DIR / 'seed_data'
    if private_seed.exists() and any(private_seed.glob('*.md')):
        status['seed_data'] = False
    elif example_seed.exists():
        status['seed_data'] = True

    return status


def is_using_fallback(resource_type: str = None) -> bool:
    """
    Check if we're using fallback (example) resources.

    Args:
        resource_type: Optional specific resource type ('prompts', 'seed_data').
                      If None, returns True if ANY resource uses fallback.
    """
    status = _check_fallback_status()
    if resource_type:
        return status.get(resource_type, False)
    return any(status.values())


def get_fallback_warnings() -> list:
    """
    Get list of warnings about fallback usage for superadmin display.
    """
    status = _check_fallback_status()
    warnings = []
    if status.get('prompts'):
        warnings.append({
            'type': 'prompts',
            'message': "Les prompts par defaut (private.example) sont utilises. "
                      "Copiez le dossier private.example/prompts vers private/prompts "
                      "pour personnaliser les prompts."
        })
    if status.get('seed_data'):
        warnings.append({
            'type': 'seed_data',
            'message': "Les pages par defaut (private.example) sont utilisees. "
                      "Copiez le dossier private.example/seed_data vers private/seed_data "
                      "pour personnaliser les pages."
        })
    return warnings


def _load_module_from_path(module_name: str, file_path: Path):
    """Dynamically load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=32)
def _get_prompt_module(module_name: str):
    """
    Load a prompt module with fallback.
    Priority: private/prompts > private.example/prompts
    """
    private_path = _PRIVATE_DIR / 'prompts' / f'{module_name}.py'
    example_path = _EXAMPLE_DIR / 'prompts' / f'{module_name}.py'

    # Try private first
    if private_path.exists():
        _using_fallback['prompts'] = False
        return _load_module_from_path(f'private.prompts.{module_name}', private_path)

    # Fallback to example
    if example_path.exists():
        _using_fallback['prompts'] = True
        return _load_module_from_path(f'private_example.prompts.{module_name}', example_path)

    return None


def get_grading_prompts() -> Dict[str, Any]:
    """
    Get grading prompts (severity instructions, mood descriptions, template).
    Returns dict with: SEVERITY_INSTRUCTIONS, MOOD_DESCRIPTIONS, GRADING_PROMPT_TEMPLATE
    """
    module = _get_prompt_module('grading')
    if module:
        return {
            'SEVERITY_INSTRUCTIONS': getattr(module, 'SEVERITY_INSTRUCTIONS', {}),
            'MOOD_DESCRIPTIONS': getattr(module, 'MOOD_DESCRIPTIONS', {}),
            'GRADING_PROMPT_TEMPLATE': getattr(module, 'GRADING_PROMPT_TEMPLATE', ''),
        }
    return {'SEVERITY_INSTRUCTIONS': {}, 'MOOD_DESCRIPTIONS': {}, 'GRADING_PROMPT_TEMPLATE': ''}


def get_generator_prompts() -> Dict[str, Any]:
    """
    Get quiz generator prompts.
    Returns dict with: QUIZ_FORMAT, DIFFICULTY_INSTRUCTIONS, GENERATION_PROMPT_TEMPLATE
    """
    module = _get_prompt_module('generator')
    if module:
        return {
            'QUIZ_FORMAT': getattr(module, 'QUIZ_FORMAT', ''),
            'DIFFICULTY_INSTRUCTIONS': getattr(module, 'DIFFICULTY_INSTRUCTIONS', {}),
            'GENERATION_PROMPT_TEMPLATE': getattr(module, 'GENERATION_PROMPT_TEMPLATE', ''),
        }
    return {'QUIZ_FORMAT': '', 'DIFFICULTY_INSTRUCTIONS': {}, 'GENERATION_PROMPT_TEMPLATE': ''}


def get_anomaly_prompts() -> Dict[str, Any]:
    """
    Get anomaly detection prompts.
    Returns dict with: INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE, CLASS_ANALYSIS_PROMPT_TEMPLATE
    """
    module = _get_prompt_module('anomaly')
    if module:
        return {
            'INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE': getattr(module, 'INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE', ''),
            'CLASS_ANALYSIS_PROMPT_TEMPLATE': getattr(module, 'CLASS_ANALYSIS_PROMPT_TEMPLATE', ''),
        }
    return {'INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE': '', 'CLASS_ANALYSIS_PROMPT_TEMPLATE': ''}


def get_seed_data_path(filename: str) -> Optional[Path]:
    """
    Get path to a seed data file with fallback.
    Priority: private/seed_data > private.example/seed_data

    Args:
        filename: Name of the seed data file (e.g., 'a-propos.md')

    Returns:
        Path to the file, or None if not found
    """
    private_path = _PRIVATE_DIR / 'seed_data' / filename
    example_path = _EXAMPLE_DIR / 'seed_data' / filename

    # Try private first
    if private_path.exists():
        return private_path

    # Fallback to example
    if example_path.exists():
        _using_fallback['seed_data'] = True
        return example_path

    return None


def read_seed_data(filename: str) -> Optional[str]:
    """
    Read content from a seed data file with fallback.

    Args:
        filename: Name of the seed data file (e.g., 'a-propos.md')

    Returns:
        File content as string, or None if not found
    """
    path = get_seed_data_path(filename)
    if path:
        return path.read_text(encoding='utf-8')
    return None


def clear_cache():
    """Clear the prompt module cache (useful for testing or hot-reload)."""
    _get_prompt_module.cache_clear()
    global _using_fallback
    _using_fallback = {}
