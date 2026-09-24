import unittest

from agent_protocols import (
    extract_a2a_text,
    extract_responses_text,
    is_hosted_agent_a2a_unsupported,
    responses_url_from_a2a_url,
)


class AgentProtocolTests(unittest.TestCase):
    def test_extracts_a2a_artifact_text(self):
        result = {
            "artifacts": [
                {"parts": [{"kind": "text", "text": "final decision"}]}
            ]
        }

        self.assertEqual(extract_a2a_text(result), "final decision")

    def test_extracts_direct_a2a_message_text(self):
        result = {"kind": "message", "parts": [{"kind": "text", "text": "reply"}]}

        self.assertEqual(extract_a2a_text(result), "reply")

    def test_extracts_a2a_status_message_text(self):
        result = {
            "status": {
                "state": "completed",
                "message": {"parts": [{"kind": "text", "text": "status reply"}]},
            }
        }

        self.assertEqual(extract_a2a_text(result), "status reply")

    def test_extracts_latest_agent_history_message(self):
        result = {
            "history": [
                {"role": "agent", "parts": [{"kind": "text", "text": "older"}]},
                {"role": "user", "parts": [{"kind": "text", "text": "question"}]},
                {"role": "agent", "parts": [{"kind": "text", "text": "latest"}]},
            ]
        }

        self.assertEqual(extract_a2a_text(result), "latest")

    def test_extracts_responses_assistant_output(self):
        response = {
            "output": [
                {"type": "tool_call", "name": "search"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "covered"}],
                },
            ]
        }

        self.assertEqual(extract_responses_text(response), "covered")

    def test_identifies_hosted_agent_a2a_error(self):
        error = {
            "code": -32099,
            "data": {"code": "HostedAgentNotSupported"},
        }

        self.assertTrue(is_hosted_agent_a2a_unsupported(error))

    def test_builds_responses_url(self):
        a2a_url = (
            "https://example.test/api/projects/demo/agents/adjudicator/"
            "endpoint/protocols/a2a?api-version=v1"
        )

        self.assertEqual(
            responses_url_from_a2a_url(a2a_url),
            "https://example.test/api/projects/demo/agents/adjudicator/"
            "endpoint/protocols/openai/responses?api-version=v1",
        )


if __name__ == "__main__":
    unittest.main()
