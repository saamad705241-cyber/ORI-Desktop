from pathlib import Path


def test_core_prompt_protects_exact_text_from_misheard_speech():
    prompt = " ".join(
        (Path(__file__).resolve().parents[1] / "core" / "prompt.txt").read_text(
            encoding="utf-8"
        ).casefold().split()
    )

    assert "automatic speech transcription can mishear" in prompt
    assert "never type, send, submit or publish a guessed transcript" in prompt
    assert "preserve the user's actual wording" in prompt
    assert "ask one concise" in prompt



def test_core_prompt_preserves_natural_hinglish_and_original_script():
    prompt = " ".join(
        (Path(__file__).resolve().parents[1] / "core" / "prompt.txt").read_text(
            encoding="utf-8"
        ).casefold().split()
    )

    assert "match the user's" in prompt
    assert "natural code-switching" in prompt
    assert "roman hindi stays roman hindi" in prompt
    assert "do not transliterate, translate or autocorrect dictated text" in prompt
