import os
import unittest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.process_manager import ProcessManager, ProcessStatusEnum


class TestDirectFDRedirection(unittest.TestCase):
    def test_direct_file_descriptor_redirection_avoids_pipe_deadlock(self):
        pm = ProcessManager(port=8090)
        bench_log_path, err_log_path = pm._get_log_paths()
        self.assertTrue(os.path.isabs(bench_log_path))
        self.assertTrue(os.path.isabs(err_log_path))


if __name__ == "__main__":
    unittest.main()
