"""Tests of the Bedrock proxy Lambda (round 6 PR B3), without AWS.

Run: python3 deploy/aws/test_lambda_proxy.py
A fake Bedrock client stands in for boto3, so no credentials or network are used.
"""

import base64
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "lambda"))
import bedrock_proxy

MODEL = "global.amazon.nova-2-lite-v1:0"
SECRET_WORDS = "patient seven in bed twelve"


class FakeClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(f"An error occurred ({code}) with {SECRET_WORDS}")
        self.response = {"Error": {"Code": code, "Message": SECRET_WORDS}}


class FakeBedrock:
    def __init__(self, answer: Any = None, error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.answer


GOOD = {
    "output": {
        "message": {
            "role": "assistant",
            "content": [{"reasoningContent": {"text": "hidden"}}, {"text": "อันดับ 1"}],
        }
    },
    "stopReason": "end_turn",
    "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
    "ResponseMetadata": {"RequestId": "x"},
}


def event(
    body: Any, *, raw: str | None = None, base64_body: bool = False
) -> dict[str, Any]:
    text = raw if raw is not None else json.dumps(body)
    if base64_body:
        return {
            "body": base64.b64encode(text.encode()).decode(),
            "isBase64Encoded": True,
        }
    return {"body": text, "isBase64Encoded": False}


REQUEST = {"system": "s", "prompt": "p", "max_output_tokens": 100}
CONTEXT = SimpleNamespace(aws_request_id="req-1")


class ProxyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = {
            "MODEL_ID": MODEL,
            "AWS_REGION": "ap-southeast-1",
            "MAX_INPUT_BYTES": "2000",
            "MAX_OUTPUT_TOKENS": "50",
        }
        self.patch_env = mock.patch.dict(os.environ, self.env, clear=False)
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)

    def run_with(
        self, client: FakeBedrock, request_event: dict[str, Any]
    ) -> tuple[dict, str]:
        bedrock_proxy._client = client
        self.addCleanup(setattr, bedrock_proxy, "_client", None)
        logs = io.StringIO()
        with contextlib.redirect_stdout(logs):
            answer = bedrock_proxy.handler(request_event, CONTEXT)
        return answer, logs.getvalue()

    def test_success_returns_the_converse_fields_and_only_text_parts(self) -> None:
        client = FakeBedrock(GOOD)
        answer, logs = self.run_with(client, event(REQUEST))
        body = json.loads(answer["body"])
        self.assertEqual(answer["statusCode"], 200)
        self.assertEqual(body["ok"], True)
        self.assertEqual((body["model_id"], body["region"]), (MODEL, "ap-southeast-1"))
        self.assertEqual(body["output"]["message"]["content"], [{"text": "อันดับ 1"}])
        self.assertEqual(body["usage"]["inputTokens"], 10)
        self.assertNotIn("hidden", answer["body"])
        self.assertNotIn("อันดับ", logs)
        self.assertIn('"outcome": "OK"', logs)

    def test_the_model_is_fixed_and_the_answer_length_capped(self) -> None:
        client = FakeBedrock(GOOD)
        self.run_with(client, event({**REQUEST, "max_output_tokens": 4000}))
        call = client.calls[0]
        self.assertEqual(call["modelId"], MODEL)
        self.assertEqual(call["inferenceConfig"]["maxTokens"], 50)

    def test_bedrock_errors_return_only_the_code(self) -> None:
        client = FakeBedrock(error=FakeClientError("ThrottlingException"))
        answer, logs = self.run_with(client, event(REQUEST))
        body = json.loads(answer["body"])
        self.assertEqual(answer["statusCode"], 200)
        self.assertEqual(
            (body["ok"], body["error_code"]), (False, "ThrottlingException")
        )
        self.assertNotIn(SECRET_WORDS, answer["body"] + logs)

    def test_other_exceptions_return_the_class_name(self) -> None:
        client = FakeBedrock(error=TimeoutError(SECRET_WORDS))
        answer, logs = self.run_with(client, event(REQUEST))
        self.assertEqual(json.loads(answer["body"])["error_code"], "TimeoutError")
        self.assertNotIn(SECRET_WORDS, answer["body"] + logs)

    def test_bad_bodies_are_refused_without_a_call(self) -> None:
        for bad in (
            event(None, raw="not json"),
            event(["a"]),
            event({**REQUEST, "model": "other"}),
            event({"system": "s", "prompt": "p"}),
            event({**REQUEST, "max_output_tokens": 0}),
            event({**REQUEST, "max_output_tokens": True}),
            event({**REQUEST, "prompt": 3}),
        ):
            client = FakeBedrock(GOOD)
            answer, _ = self.run_with(client, bad)
            self.assertEqual(answer["statusCode"], 400)
            self.assertEqual(client.calls, [])

    def test_a_body_over_the_limit_is_413_without_a_call(self) -> None:
        client = FakeBedrock(GOOD)
        answer, _ = self.run_with(client, event({**REQUEST, "prompt": "x" * 3000}))
        self.assertEqual(answer["statusCode"], 413)
        self.assertEqual(client.calls, [])

    def test_base64_bodies_are_read(self) -> None:
        client = FakeBedrock(GOOD)
        answer, _ = self.run_with(client, event(REQUEST, base64_body=True))
        self.assertEqual(answer["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
