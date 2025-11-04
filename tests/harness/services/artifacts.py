"""Artifact management for scenario-specific files and logs."""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class ArtifactManager:
    """Manages scenario-specific artifact directories.

    Creates temporary directories for scenario artifacts (configs, logs, etc.)
    and cleans them up based on scenario outcome.

    Attributes
    ----------
    base_dir : Path
        Base directory for all artifacts
    scenario_dir : Path | None
        Current scenario's artifact directory
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path.cwd() / "tmp" / "behave"
        self.base_dir = Path(base_dir)
        self.scenario_dir: Path | None = None

    def create_scenario_dir(self, scenario_name: str) -> Path:
        """Create a scenario-specific artifact directory.

        Parameters
        ----------
        scenario_name : str
            Name of the scenario

        Returns
        -------
        Path
            Path to created scenario directory
        """
        scenario_id = scenario_name.lower().replace(" ", "-").replace("/", "-")
        self.scenario_dir = self.base_dir / scenario_id
        self.scenario_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created artifact directory: {self.scenario_dir}")
        return self.scenario_dir

    def create_temp_file(
        self, filename: str, content: str = "", mode: str = "w"
    ) -> Path:
        """Create a temporary file in scenario directory.

        Parameters
        ----------
        filename : str
            Name of the file
        content : str, optional
            File content to write
        mode : str, optional
            File write mode (default: "w")

        Returns
        -------
        Path
            Path to created file
        """
        if self.scenario_dir is None:
            raise RuntimeError(
                "No scenario directory created. Call create_scenario_dir first."
            )

        file_path = self.scenario_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, mode) as f:
            f.write(content)

        logger.debug(f"Created temp file: {file_path}")
        return file_path

    def cleanup(self, preserve_on_failure: bool = True) -> None:
        """Cleanup scenario artifacts.

        Parameters
        ----------
        preserve_on_failure : bool, optional
            If True, preserve artifacts when scenario fails.
            If False, always delete artifacts.
        """
        if self.scenario_dir is None:
            return

        if preserve_on_failure:
            logger.debug(f"Preserving artifacts: {self.scenario_dir}")
            return

        try:
            if self.scenario_dir.exists():
                shutil.rmtree(self.scenario_dir)
                logger.debug(f"Cleaned up artifacts: {self.scenario_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup artifacts {self.scenario_dir}: {e}")
