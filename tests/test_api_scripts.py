import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import tests.check_models as check_models
import tests.test_prompt as test_prompt


class APIScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config.json"
        self.config.write_text(json.dumps({"BASE_URL": "https://example.invalid/v1/", "API_KEY": "secret-key", "MODEL": "test"}))

    def run_script(self, module, response=None, error=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(module, "urlopen", side_effect=error, return_value=io.BytesIO(json.dumps(response).encode())) as request:
            with redirect_stdout(output), redirect_stderr(errors):
                result = module.main(["--config", str(self.config)])
        return result, output.getvalue(), errors.getvalue(), request

    def test_default_config_is_at_repository_root(self):
        root = Path(__file__).resolve().parents[1]
        for module in (check_models, test_prompt):
            with patch.object(module.argparse.ArgumentParser, "parse_args", side_effect=RuntimeError("stop")), patch.object(module.argparse.ArgumentParser, "add_argument") as add:
                with self.assertRaises(RuntimeError):
                    module.main([])
            self.assertEqual(add.call_args.kwargs["default"], root / "config.json")

    def test_models_needs_no_model_and_uses_custom_url_and_user_agent(self):
        self.config.write_text(json.dumps({"BASE_URL": "https://example.invalid/v1/", "API_KEY": "secret-key"}))
        result, output, errors, mock = self.run_script(check_models, {"data": [{"id": "one"}]})
        self.assertEqual((result, output, errors), (0, "one\n", ""))
        request = mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.invalid/v1/models")
        self.assertEqual(request.get_header("User-agent"), "learn-vocab/1.0")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")

    def test_prompt_sends_hello_and_redacts_key(self):
        result, output, errors, mock = self.run_script(test_prompt, {"choices": [{"message": {"content": "Hello secret-key"}}]})
        self.assertEqual((result, output, errors), (0, "Hello [REDACTED]\n", ""))
        request = mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(json.loads(request.data), {"model": "test", "messages": [{"role": "user", "content": "Hello"}]})
        self.assertEqual(request.get_header("User-agent"), "learn-vocab/1.0")

    def test_invalid_config_fails_before_request(self):
        for module in (check_models, test_prompt):
            for config in ([], {}, {"BASE_URL": "file:///tmp/key", "API_KEY": "secret", "MODEL": "x"}):
                self.config.write_text(json.dumps(config))
                result, _, errors, mock = self.run_script(module)
                self.assertEqual(result, 1)
                self.assertTrue(errors)
                mock.assert_not_called()

    def test_bad_responses_and_network_failures(self):
        for module in (check_models, test_prompt):
            for response in ([], {}, {"data": [None]}, {"choices": []}):
                result, _, errors, _ = self.run_script(module, response)
                self.assertEqual(result, 1)
                self.assertNotIn("Traceback", errors)
            for error in (HTTPError("url", 403, "secret-key", {}, None), URLError("secret-key"), TimeoutError("secret-key")):
                result, _, errors, mock = self.run_script(module, error=error)
                self.assertEqual(result, 1)
                self.assertNotIn("secret-key", errors)
                self.assertEqual(mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
