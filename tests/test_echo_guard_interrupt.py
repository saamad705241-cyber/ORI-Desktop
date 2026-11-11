from core.echo import EchoGuard


def test_echo_guard_reset_candidate_clears_only_streak():
    guard = EchoGuard()
    guard._run = 5
    guard._last_sim = 0.7
    guard.reset_candidate()
    assert guard._run == 0
    assert guard._last_sim == 0.7


def test_echo_guard_reset_clears_output_history_and_run():
    guard = EchoGuard()
    guard._run = 4
    guard._hist.append((1.0, [0.1, 0.2], 0.5))
    guard.reset()
    assert guard._run == 0
    assert guard._hist == []
