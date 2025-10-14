"""Configuration management for production and test environments.

This module provides centralized path configuration for database and file storage,
allowing safe separation between production and test data.
"""

from pathlib import Path
from typing import Literal

from ..utils.log import get_logger

log = get_logger(__name__)

# Environment mode type
EnvironmentMode = Literal["production", "test"]

# Default paths for production environment
_DEFAULT_PRODUCTION_PATHS = {
    "db_path": Path("data/cache/research_articles_management.db"),
    "pdf_dir": Path("data/pdfs"),
    "docx_dir": Path("data/docx"),
    "markdown_from_docx_dir": Path("data/markdown/from_docx"),
    "markdown_from_html_dir": Path("data/markdown/from_html"),
    "html_dir": Path("data/html"),
    "cache_dir": Path("data/cache"),
}

# Test paths (completely separate from production)
_DEFAULT_TEST_PATHS = {
    "db_path": Path("test_data/cache/test_research_articles.db"),
    "pdf_dir": Path("test_data/pdfs"),
    "docx_dir": Path("test_data/docx"),
    "markdown_from_docx_dir": Path("test_data/markdown/from_docx"),
    "markdown_from_html_dir": Path("test_data/markdown/from_html"),
    "html_dir": Path("test_data/html"),
    "cache_dir": Path("test_data/cache"),
}


class EnvironmentConfig:
    """Manages environment-specific paths for database and file storage.
    
    This class ensures complete separation between production and test environments
    by maintaining separate paths for all data storage.
    """
    
    def __init__(self, mode: EnvironmentMode = "production") -> None:
        """Initialize configuration with specified mode.
        
        Args:
            mode: Environment mode ('production' or 'test')
        """
        self._mode: EnvironmentMode = mode
        self._paths: dict[str, Path] = {}
        self._load_paths()
        log.debug("environment_config_initialized", mode=mode, paths=str(self._paths))
    
    def _load_paths(self) -> None:
        """Load paths based on current mode."""
        if self._mode == "test":
            self._paths = _DEFAULT_TEST_PATHS.copy()
        else:
            self._paths = _DEFAULT_PRODUCTION_PATHS.copy()
    
    @property
    def mode(self) -> EnvironmentMode:
        """Get current environment mode."""
        return self._mode
    
    @property
    def db_path(self) -> Path:
        """Get database file path."""
        return self._paths["db_path"]
    
    @property
    def pdf_dir(self) -> Path:
        """Get PDF storage directory."""
        return self._paths["pdf_dir"]
    
    @property
    def docx_dir(self) -> Path:
        """Get DOCX storage directory."""
        return self._paths["docx_dir"]
    
    @property
    def markdown_from_docx_dir(self) -> Path:
        """Get Markdown storage directory for DOCX conversions."""
        return self._paths["markdown_from_docx_dir"]
    
    @property
    def markdown_from_html_dir(self) -> Path:
        """Get Markdown storage directory for HTML conversions."""
        return self._paths["markdown_from_html_dir"]
    
    @property
    def html_dir(self) -> Path:
        """Get HTML storage directory."""
        return self._paths["html_dir"]
    
    @property
    def cache_dir(self) -> Path:
        """Get HTTP cache directory."""
        return self._paths["cache_dir"]
    
    def set_mode(self, mode: EnvironmentMode) -> None:
        """Change environment mode and reload paths.
        
        Args:
            mode: New environment mode ('production' or 'test')
        """
        if mode != self._mode:
            old_mode = self._mode
            self._mode = mode
            self._load_paths()
            log.info(
                "environment_mode_changed",
                old_mode=old_mode,
                new_mode=mode,
                new_paths=str(self._paths)
            )
    
    def ensure_directories(self) -> None:
        """Create all necessary directories if they don't exist."""
        for path_name, path in self._paths.items():
            if path_name.endswith("_dir"):
                path.mkdir(parents=True, exist_ok=True)
                log.debug("directory_ensured", path=str(path))
            elif path_name.endswith("_path"):
                # For file paths, ensure parent directory exists
                path.parent.mkdir(parents=True, exist_ok=True)
                log.debug("parent_directory_ensured", path=str(path.parent))
    
    def get_summary(self) -> dict[str, str]:
        """Get summary of current configuration.
        
        Returns:
            Dictionary with mode and all paths as strings
        """
        return {
            "mode": self._mode,
            **{k: str(v) for k, v in self._paths.items()}
        }


# Global configuration instance (lazily initialized)
_config: EnvironmentConfig | None = None


def get_config() -> EnvironmentConfig:
    """Get the global configuration instance.
    
    Lazily initializes the config on first access if not already initialized.
    
    Returns:
        Current environment configuration
    """
    global _config
    if _config is None:
        _config = EnvironmentConfig(mode="production")
    return _config


def set_test_mode() -> None:
    """Switch to test mode globally.
    
    This function should be called at the beginning of CLI commands
    when the --test flag is used, or in test fixtures.
    
    If config is not yet initialized, it will be initialized in test mode.
    """
    global _config
    if _config is None:
        _config = EnvironmentConfig(mode="test")
        log.info("initialized_in_test_mode", paths=_config.get_summary())
    else:
        _config.set_mode("test")
        log.info("switched_to_test_mode", paths=_config.get_summary())


def set_production_mode() -> None:
    """Switch to production mode globally.
    
    This is the default mode. Explicitly calling this function
    is only needed if switching from test mode.
    
    If config is not yet initialized, it will be initialized in production mode.
    """
    global _config
    if _config is None:
        _config = EnvironmentConfig(mode="production")
        log.info("initialized_in_production_mode", paths=_config.get_summary())
    else:
        _config.set_mode("production")
        log.info("switched_to_production_mode", paths=_config.get_summary())


def is_test_mode() -> bool:
    """Check if currently in test mode.
    
    Returns:
        True if in test mode, False otherwise
    """
    config = get_config()
    return config.mode == "test"
