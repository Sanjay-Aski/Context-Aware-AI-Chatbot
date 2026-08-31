import httpx
import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from ollama import ResponseError

from server import ollama_failure, to_ollama_messages


class OllamaFailureMappingTests(unittest.TestCase):
    def test_auth_and_access_errors_are_distinguished(self):
        self.assertEqual(ollama_failure(ResponseError("unauthorized", 401))[0], 401)
        self.assertEqual(ollama_failure(ResponseError("forbidden", 403))[0], 403)

    def test_model_and_rate_limit_errors_are_distinguished(self):
        self.assertEqual(ollama_failure(ResponseError("not found", 404))[0], 404)
        self.assertEqual(ollama_failure(ResponseError("rate limited", 429))[0], 429)

    def test_cloud_server_errors_map_to_bad_gateway(self):
        status, detail = ollama_failure(ResponseError("upstream error", 503))
        self.assertEqual(status, 502)
        self.assertIn("server error", detail)

    def test_timeout_and_connection_errors_are_distinguished(self):
        self.assertEqual(ollama_failure(httpx.ReadTimeout("timed out"))[0], 504)
        self.assertEqual(ollama_failure(httpx.ConnectError("offline"))[0], 502)


class LangChainMessageConversionTests(unittest.TestCase):
    def test_prompt_messages_convert_to_ollama_roles(self):
        converted = to_ollama_messages([
            SystemMessage(content="system"),
            HumanMessage(content="question"),
            AIMessage(content="answer"),
        ])
        self.assertEqual(converted, [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ])


if __name__ == "__main__":
    unittest.main()
