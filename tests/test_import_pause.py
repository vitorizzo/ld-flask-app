import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch, Mock

from tools.import_pause import IMPORT_TASKS, PAUSE_ENV, task_paused


class ImportPauseTests(unittest.TestCase):
    def load(self, path, name):
        spec = importlib.util.spec_from_file_location(name, Path(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_switch_targets_only_matrix_and_file_tasks(self):
        with patch.dict(os.environ, {PAUSE_ENV: " true "}):
            self.assertTrue(all(task_paused(name) for name in IMPORT_TASKS))
            self.assertFalse(task_paused("config.tasks.import_poleepo_orders_task"))
            self.assertFalse(task_paused("config.tasks.send_mailing_campaign_task"))
        with patch.dict(os.environ, {PAUSE_ENV: "false"}):
            self.assertFalse(any(task_paused(name) for name in IMPORT_TASKS))

    def test_scheduler_retains_other_tasks_and_restores_imports(self):
        log = types.ModuleType("tools.log_utils")
        log.get_logger = lambda name: Mock()
        with patch.dict(sys.modules, {"tools.log_utils": log}):
            with patch.dict(os.environ, {PAUSE_ENV: "false"}):
                normal = self.load("config/celeryconfig.py", "normal_schedule").beat_schedule
            with patch.dict(os.environ, {PAUSE_ENV: "true"}):
                paused = self.load("config/celeryconfig.py", "paused_schedule").beat_schedule
        removed = set(normal) - set(paused)
        self.assertEqual(len(removed), 5)
        self.assertTrue(all(normal[name]["task"] in IMPORT_TASKS for name in removed))
        self.assertTrue(all(paused[name] == normal[name] for name in paused))

    def test_queued_task_skips_before_running_callback(self):
        log = types.ModuleType("tools.log_utils")
        log.get_logger = lambda name: Mock()
        redis_utils = types.ModuleType("tools.redis_utils")
        redis_utils.clear_task_status = Mock()
        with patch.dict(sys.modules, {"tools.log_utils": log, "tools.redis_utils": redis_utils}):
            module = self.load("config/celery_app.py", "pause_test_celery")
            module.FlaskContextTask.bind(module.celery)
            task = module.FlaskContextTask()
            task.name = "config.tasks.import_articoli_task"
            task.push_request(id="queued-import")
            task.run = Mock(return_value="executed")
            try:
                with patch.dict(os.environ, {PAUSE_ENV: "true"}):
                    self.assertEqual(task()["reason"], "imports_paused")
                    task.run.assert_not_called()
                    redis_utils.clear_task_status.assert_called_once_with("queued-import")
                    task.name = "config.tasks.import_poleepo_orders_task"
                    self.assertEqual(task(), "executed")
                task.name = "config.tasks.import_articoli_task"
                with patch.dict(os.environ, {PAUSE_ENV: "false"}):
                    self.assertEqual(task(), "executed")
            finally:
                task.pop_request()


if __name__ == "__main__":
    unittest.main()
