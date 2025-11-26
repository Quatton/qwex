"""QWP Runners

Execution engines for running jobs.
"""

from qwp.runners.base import Runner
from qwp.runners.local import LocalRunner

__all__ = ["Runner", "LocalRunner"]
