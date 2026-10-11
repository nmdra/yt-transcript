"""Check prompt delivery and mocked output acceptance, not real-model spelling quality."""

import json

import pytest

from yt_transcript import formatter, openrouter_backend


@pytest.mark.parametrize("provider", ["pi", "openrouter"])
@pytest.mark.parametrize("mode", ["standard", "focused", "summarized"])
def test_spelling_policy_keeps_source_and_accepts_mocked_correction(
    provider, mode, monkeypatch
):
    # Deliberate misspellings test ordinary words versus protected identifiers.
    source = "Please recieve the message. Their tool is named AcmeX; run recieve_msg --count 7."
    corrected = source.replace("Please recieve", "Please receive", 1)
    calls = []
    monkeypatch.setattr(formatter, "ensure_formatter", lambda *a: "fake")

    def complete(request):
        calls.append(request)
        if mode == "summarized":
            spans = json.loads(request.source)["source_spans"]
            assert [span["text"] for span in spans] == [source]
        else:
            assert request.source == source
        assert (
            "Correct only unambiguous spelling errors in ordinary words"
            in request.system_prompt
        )
        assert (
            "Preserve names, technical terms, numbers, units, URLs"
            in request.system_prompt
        )
        assert "code, commands, and identifiers exactly" in request.system_prompt
        assert "When uncertain, keep the original spelling" in request.system_prompt
        assert "resolve homophones, or infer missing words" in request.system_prompt
        if mode == "summarized":
            return (
                f"## Summary\n\n{corrected}\n\n## Key points\n\n- Receive the message."
            )
        return f"## Edited\n\n{corrected}"

    monkeypatch.setattr(
        formatter, "_run_pi_chunk", lambda executable, request: complete(request)
    )
    monkeypatch.setattr(
        openrouter_backend, "complete", lambda request, settings=None: complete(request)
    )
    result = formatter.format_transcript(
        source,
        provider=provider,
        model="fake/model",
        editorial_mode=mode,
        max_chunks=1,
    )
    assert "Please receive the message" in result
    assert "Their tool is named AcmeX; run recieve_msg --count 7." in result
    assert len(calls) == 1
