import unittest
from unittest.mock import Mock, patch

from tools.log_utils import log_task
from tools.matrixws_client import MatrixWSConfig, MatrixWSError, wait_for_batch_result


class TaskErrorReportingTests(unittest.TestCase):
    def test_result_classification_preserves_return_values(self):
        for result, level, label in (
            ({"success": False, "error": "HTTP 500"}, "error", "Task fallito"),
            ({"ok": False}, "error", "Task fallito"),
            ({"success": False, "skipped": True}, "error", "Task fallito"),
            ({"success": True, "skipped": True}, "info", "Task non eseguito"),
            ({"success": True}, "info", "Task completato"),
            ({"ok": True, "errors": 0}, "info", "Task completato"),
            (None, "info", "Task completato"),
        ):
            with self.subTest(result=result):
                logger = Mock()
                wrapped = log_task(logger)(lambda: result)
                self.assertIs(wrapped(), result)
                self.assertIn(label, getattr(logger, level).call_args.args[0])
                if level == "info":
                    logger.error.assert_not_called()

    def test_exception_remains_an_exception(self):
        logger = Mock()
        failure = ValueError("failed")
        @log_task(logger)
        def task():
            raise failure
        with self.assertRaises(ValueError) as caught:
            task()
        self.assertIs(caught.exception, failure)
        logger.exception.assert_called_once()

    def test_diagnostics_filter_records_and_secrets(self):
        exc = MatrixWSError("failed", kind="async_response", details={
            "status_code": 500, "batch_uuid": "batch-1",
            "response": {"error": {"Exception": "DB_BUSY", "description": "secret=hidden Bearer abc https://host/key visible-secret"},
                         "dati": {"description": "private customer record"}, "secret": "hidden"},
        })
        result = exc.log_diagnostics(secrets=("visible-secret",))
        self.assertEqual(result["status_code"], 500)
        self.assertEqual(result["messages"][0]["value"], "DB_BUSY")
        text = str(result)
        for secret in ("hidden", "abc", "https://host", "visible-secret", "private customer"):
            self.assertNotIn(secret, text)

    def test_proxy_error_heading(self):
        exc = MatrixWSError("failed", details={"status_code": 502, "response": "<title>502 Bad Gateway</title><body>private body</body>"})
        self.assertEqual(exc.log_diagnostics()["messages"], [{"field": "proxy_message", "value": "502 Bad Gateway"}])

    def test_not_finished_http_500_is_polled_then_succeeds(self):
        config = MatrixWSConfig("https://example.test", "env", "start", "app", "secret")
        responses = [
            {"ok": False, "status_code": 500, "json": {"error": {"Exception": "BATCH_NOT_FINISHED"}}},
            {"ok": True, "status_code": 200, "json": {"dati": [{"id": 1}]}},
        ]
        with patch("tools.matrixws_client.call_batch_response", side_effect=responses) as call:
            result = wait_for_batch_result(config, "batch", sleep=lambda _: None)
        self.assertTrue(result["ok"])
        self.assertEqual(call.call_count, 2)

    def test_actual_http_500_remains_an_error(self):
        config = MatrixWSConfig("https://example.test", "env", "start", "app", "secret")
        with patch("tools.matrixws_client.call_batch_response", return_value={"ok": False, "status_code": 500, "json": {"error": {"Exception": "DB_ERROR"}}}):
            with self.assertRaises(MatrixWSError) as caught:
                wait_for_batch_result(config, "batch")
        self.assertEqual(caught.exception.kind, "async_response")
        self.assertEqual(caught.exception.log_diagnostics()["messages"][0]["value"], "DB_ERROR")


if __name__ == "__main__":
    unittest.main()
