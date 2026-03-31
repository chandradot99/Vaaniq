from vaaniq.core.state import SessionState


def test_session_state_keys() -> None:
    required = {"session_id", "agent_id", "org_id", "channel", "user_id"}
    assert required.issubset(set(SessionState.__annotations__.keys()))
