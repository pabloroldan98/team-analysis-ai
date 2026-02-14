# scraping/utils/__init__.py
"""Utility functions for scraping and file management."""

from .helpers import (
    # File operations with validation and backup
    write_dict_to_json,
    load_json,
    read_dict_from_json,
    write_dict_data,  # alias
    read_dict_data,   # alias for load_json
    list_json_bases,
    is_valid_data,
    merge_with_old_data,
    overwrite_dict_data,
    delete_file,
    list_json_files,
    ensure_data_dir,
    
    # Parsing utilities
    parse_market_value,
    parse_age,
    parse_height,
    get_season_year,
    format_season,
    
    # Constants
    ROOT_DIR,
    DATA_DIR,
)

__all__ = [
    # File operations
    "load_json",
    "write_dict_to_json",
    "read_dict_from_json",
    "write_dict_data",
    "read_dict_data",
    "is_valid_data",
    "merge_with_old_data",
    "overwrite_dict_data",
    "delete_file",
    "list_json_files",
    "list_json_bases",
    "ensure_data_dir",
    
    # Parsing
    "parse_market_value",
    "parse_age",
    "parse_height",
    "get_season_year",
    "format_season",
    
    # Constants
    "ROOT_DIR",
    "DATA_DIR",
]
