"""Configuration path utilities for the synthetic user project.

This module provides helper functions to resolve paths to configuration,
schema, data, and output files relative to the project root directory.
"""

from pathlib import Path

from project_paths import DATA_DIR, ROOT_DIR

ROOT_FOLDER = ROOT_DIR
SYNTHETIC_USER_DIR = DATA_DIR / "synthetic_user"


def get_config_path(filename: str) -> Path:
    """Get absolute path to a config file in config/synthetic_user/.

    Parameters
    ----------
    filename : str
        Name of the configuration file (e.g., 'agents.json').

    Returns
    -------
    Path
        Absolute path to the configuration file.

    Examples
    --------
    >>> get_config_path('agents.json')
    PosixPath('/path/to/project/config/synthetic_user/agents.json')
    """
    return ROOT_FOLDER / "config" / "synthetic_user" / filename


def get_schema_path(filename: str) -> Path:
    """Get absolute path to a schema file in data/synthetic_user/schema/.

    Parameters
    ----------
    filename : str
        Name of the schema file (e.g., 'generator_schema.json').

    Returns
    -------
    Path
        Absolute path to the schema file.

    Examples
    --------
    >>> get_schema_path('user_profile.json')
    PosixPath('/path/to/project/data/synthetic_user/schema/user_profile.json')
    """
    return SYNTHETIC_USER_DIR / "schema" / filename


def get_data_path(filename: str) -> Path:
    """Get absolute path to an input data file in data/synthetic_user/input/.

    Parameters
    ----------
    filename : str
        Name of the input data file (e.g., 'users.json').

    Returns
    -------
    Path
        Absolute path to the input data file.

    Examples
    --------
    >>> get_data_path('segments.json')
    PosixPath('/path/to/project/data/synthetic_user/input/segments.json')
    """
    return SYNTHETIC_USER_DIR / "input" / filename


def get_output_path(filename: str) -> Path:
    """Get absolute path to an output file in data/synthetic_user/output/.

    Parameters
    ----------
    filename : str
        Name of the output file (e.g., 'generated_users.json').

    Returns
    -------
    Path
        Absolute path to the output file.

    Examples
    --------
    >>> get_output_path('results.json')
    PosixPath('/path/to/project/data/synthetic_user/output/results.json')
    """
    return SYNTHETIC_USER_DIR / "output" / filename


def get_db_path(filename: str) -> Path:
    """Get absolute path to a database file in data/synthetic_user/db/.

    Parameters
    ----------
    filename : str
        Name of the database file (e.g., 'jobs.db').

    Returns
    -------
    Path
        Absolute path to the database file.

    Examples
    --------
    >>> get_db_path('jobs.db')
    PosixPath('/path/to/project/data/synthetic_user/db/jobs.db')
    """
    return SYNTHETIC_USER_DIR / "db" / filename
