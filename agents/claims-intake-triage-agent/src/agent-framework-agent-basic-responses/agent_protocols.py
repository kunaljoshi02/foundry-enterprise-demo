from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _text_from_parts(parts: object) -> list[str]:
    if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)):
        return []

    texts = []
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        if part.get("kind") == "text" or part.get("type") in {"text", "output_text"}:
            text = part.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
    return texts


def extract_a2a_text(result: object) -> str | None:
    if not isinstance(result, Mapping):
        return None

    texts = []
    artifacts = result.get("artifacts")
    if isinstance(artifacts, Sequence) and not isinstance(artifacts, (str, bytes)):
        for artifact in artifacts:
            if isinstance(artifact, Mapping):
                texts.extend(_text_from_parts(artifact.get("parts")))
    if texts:
        return "\n".join(texts)

    texts.extend(_text_from_parts(result.get("parts")))
    if texts:
        return "\n".join(texts)

    status = result.get("status")
    if isinstance(status, Mapping):
        message = status.get("message")
        if isinstance(message, Mapping):
            texts.extend(_text_from_parts(message.get("parts")))
    if texts:
        return "\n".join(texts)

    history = result.get("history")
    if isinstance(history, Sequence) and not isinstance(history, (str, bytes)):
        for message in reversed(history):
            if isinstance(message, Mapping) and message.get("role") == "agent":
                texts.extend(_text_from_parts(message.get("parts")))
                if texts:
                    return "\n".join(texts)
    return None


def extract_responses_text(response: object) -> str | None:
    if not isinstance(response, Mapping):
        return None

    texts = []
    output = response.get("output")
    if isinstance(output, Sequence) and not isinstance(output, (str, bytes)):
        for item in output:
            if not isinstance(item, Mapping) or item.get("type") != "message":
                continue
            texts.extend(_text_from_parts(item.get("content")))
    return "\n".join(texts) if texts else None


def is_hosted_agent_a2a_unsupported(error: object) -> bool:
    if not isinstance(error, Mapping):
        return False
    data = error.get("data")
    return (
        isinstance(data, Mapping)
        and data.get("code") == "HostedAgentNotSupported"
    )


def responses_url_from_a2a_url(a2a_url: str) -> str:
    parsed = urlsplit(a2a_url)
    marker = "/endpoint/protocols/a2a"
    if marker not in parsed.path:
        raise ValueError("The adjudicator A2A URL does not have the expected protocol path.")

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["api-version"] = "v1"
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.replace(
                marker,
                "/endpoint/protocols/openai/responses",
                1,
            ),
            urlencode(query),
            parsed.fragment,
        )
    )
