import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def location_block(config: str, path: str) -> str:
    match = re.search(rf"\blocation\s*=\s*{re.escape(path)}\s*\{{", config)
    if match is None:
        raise AssertionError(f"missing exact Nginx location for {path}")

    opening = config.find("{", match.start())
    depth = 0
    for index in range(opening, len(config)):
        if config[index] == "{":
            depth += 1
        elif config[index] == "}":
            depth -= 1
            if depth == 0:
                return config[match.start() : index + 1]

    raise AssertionError(f"unterminated Nginx location for {path}")


class SseNginxBufferingTests(unittest.TestCase):
    def assert_streaming_location(self, relative_path: str, endpoint: str) -> str:
        config = (ROOT / relative_path).read_text(encoding="utf-8")
        block = location_block(config, endpoint)
        self.assertRegex(block, r"(?m)^\s*proxy_buffering\s+off\s*;")
        self.assertRegex(block, r"(?m)^\s*proxy_pass\s+http://app_upstream\s*;")
        return block

    def test_backend_chat_route_disables_buffering_and_preserves_cors(self) -> None:
        block = self.assert_streaming_location(
            "deploy/backend/nginx/nginx.conf", "/v1/chat/messages"
        )
        self.assertIn("Access-Control-Allow-Origin $cors_origin", block)
        self.assertIn("Access-Control-Allow-Credentials \"true\"", block)
        self.assertIn("$request_method = OPTIONS", block)

    def test_ai_chat_route_disables_buffering(self) -> None:
        self.assert_streaming_location(
            "deploy/ai/nginx/nginx.conf", "/internal/v1/ai/chat/messages"
        )

    def test_both_services_refresh_a_stable_nginx_config_mount(self) -> None:
        for service in ("ai", "backend"):
            with self.subTest(service=service):
                compose = (ROOT / f"deploy/{service}/compose.yaml").read_text(
                    encoding="utf-8"
                )
                self.assertIn(
                    "./.runtime.nginx.conf:/etc/nginx/nginx.conf:ro", compose
                )

        deploy_script = (ROOT / "deploy/lib/deploy-blue-green.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'cat "${script_dir}/nginx/nginx.conf" > "${runtime_nginx_conf}"',
            deploy_script,
        )
        self.assertLess(
            deploy_script.index('cat "${script_dir}/nginx/nginx.conf"'),
            deploy_script.index('"${compose[@]}" up -d nginx'),
        )


if __name__ == "__main__":
    unittest.main()
