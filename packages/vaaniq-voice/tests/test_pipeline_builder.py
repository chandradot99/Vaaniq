"""
Unit tests for the pipeline builder and task runner.

These tests verify the composition logic — wiring, initial-state construction,
and the greeting trigger — without starting a real Pipecat pipeline or making
network calls.

Key changes from previous version:
- build_pipeline now returns (pipeline, llm_context, transport, memory_saver) — 4 values
- Uses get_or_compile() from vaaniq.graph.cache (not GraphBuilder directly)
- Uses create_transport() not build_twilio_transport
- Uses get_vad_analyzer() singleton (not constructing VAD inline)
- VoiceCallContext requires graph_version field
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from vaaniq.voice.pipeline.context import VoiceCallContext

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_context(**overrides) -> VoiceCallContext:
    defaults = dict(
        session_id="sess-1",
        org_id="org-1",
        agent_id="agent-1",
        agent_language="en-US",
        graph_config={"nodes": [], "edges": [], "entry_point": "start"},
        graph_version=1,
        initial_messages=[{"role": "system", "content": "You are a helpful agent."}],
        org_keys={"cartesia": "cart-key", "deepgram": "dg-key"},
        # Optional fields
        call_sid="CA-test",
        stream_sid="MZ-test",
        twilio_account_sid="AC-test",
        twilio_auth_token="auth-token",
        from_number="+19995551234",
        to_number="+18005550000",
        stt_provider="deepgram",
        tts_provider="cartesia",
        agent_voice_id=None,
    )
    defaults.update(overrides)
    return VoiceCallContext(**defaults)


def _mock_transport():
    """Build a transport mock with input/output/event_handler support."""
    t = MagicMock(name="transport")
    t.input.return_value = MagicMock(name="transport.input")
    t.output.return_value = MagicMock(name="transport.output")
    # event_handler is used as a decorator in task.py — must return a callable
    t.event_handler.return_value = lambda fn: fn
    return t


def _patch_build_pipeline(mock_transport=None, mock_graph=None, mock_memory_saver=None):
    """
    Return a context-manager stack that patches all external calls inside build_pipeline.

    Patches:
        create_transport       → mock_transport (or auto-created)
        create_stt_service     → MagicMock
        create_tts_service     → MagicMock
        get_vad_analyzer       → MagicMock
        get_or_compile         → returns (mock_graph, mock_memory_saver)
        LLMContextAggregatorPair → MagicMock with user/assistant
        Pipeline               → MagicMock (returned as pipeline)
    """
    from contextlib import ExitStack

    if mock_transport is None:
        mock_transport = _mock_transport()
    if mock_graph is None:
        mock_graph = MagicMock(name="compiled_graph")
    if mock_memory_saver is None:
        mock_memory_saver = MagicMock(name="memory_saver")

    mock_pipeline = MagicMock(name="pipeline")

    stack = ExitStack()

    patches = {
        "transport":   stack.enter_context(patch("vaaniq.voice.pipeline.builder.create_transport", return_value=mock_transport)),
        "stt":         stack.enter_context(patch("vaaniq.voice.pipeline.builder.create_stt_service", return_value=MagicMock(name="stt"))),
        "tts":         stack.enter_context(patch("vaaniq.voice.pipeline.builder.create_tts_service", return_value=MagicMock(name="tts"))),
        "vad":         stack.enter_context(patch("vaaniq.voice.pipeline.builder.get_vad_analyzer", return_value=MagicMock(name="vad"))),
        "get_or_compile": stack.enter_context(patch(
            "vaaniq.graph.cache.get_or_compile",
            new=AsyncMock(return_value=(mock_graph, mock_memory_saver)),
        )),
        "pipeline_cls": stack.enter_context(patch("vaaniq.voice.pipeline.builder.Pipeline", return_value=mock_pipeline)),
        "pair_cls":    stack.enter_context(patch("vaaniq.voice.pipeline.builder.LLMContextAggregatorPair")),
    }

    mock_pair = MagicMock(name="aggregator_pair")
    mock_pair.user.return_value = MagicMock(name="user_agg")
    mock_pair.assistant.return_value = MagicMock(name="asst_agg")
    patches["pair_cls"].return_value = mock_pair

    return stack, patches, mock_pipeline, mock_transport, mock_graph, mock_memory_saver


# ── VoiceCallContext ──────────────────────────────────────────────────────────

def test_context_requires_graph_version():
    """graph_version is a required field — missing it raises TypeError."""
    import pytest
    with pytest.raises(TypeError):
        VoiceCallContext(
            session_id="s",
            org_id="o",
            agent_id="a",
            agent_language="en-US",
            graph_config={},
            # graph_version missing
            initial_messages=[],
            org_keys={},
        )


def test_context_defaults():
    ctx = _make_context()
    assert ctx.telephony_provider == "twilio"
    assert ctx.stt_provider == "deepgram"
    assert ctx.tts_provider == "cartesia"
    assert ctx.direction == "inbound"
    assert ctx.extra_context == {}


# ── _build_initial_state ──────────────────────────────────────────────────────

def test_initial_state_has_required_fields():
    from vaaniq.voice.pipeline.builder import _build_initial_state
    state = _build_initial_state(_make_context())

    assert state["session_id"] == "sess-1"
    assert state["org_id"] == "org-1"
    assert state["agent_id"] == "agent-1"
    assert state["channel"] == "voice"
    assert state["user_id"] == "+19995551234"
    assert state["messages"] == []
    assert state["collected"] == {}
    assert state["session_ended"] is False
    assert state["transfer_initiated"] is False


def test_initial_state_start_time_is_utc_iso():
    from datetime import datetime

    from vaaniq.voice.pipeline.builder import _build_initial_state
    state = _build_initial_state(_make_context())
    dt = datetime.fromisoformat(state["start_time"])
    assert dt.tzinfo is not None


def test_initial_state_extra_context_merged():
    from vaaniq.voice.pipeline.builder import _build_initial_state
    ctx = _make_context(extra_context={"campaign_id": "cmp-1", "crm_record": {"id": "lead-99"}})
    state = _build_initial_state(ctx)
    assert state["campaign_id"] == "cmp-1"
    assert state["crm_record"] == {"id": "lead-99"}


# ── build_pipeline ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_pipeline_returns_four_values():
    """build_pipeline must return (pipeline, llm_context, transport, memory_saver)."""
    context = _make_context()
    stack, patches, mock_pipeline, mock_transport, mock_graph, mock_memory_saver = _patch_build_pipeline()

    with stack:
        from vaaniq.voice.pipeline.builder import build_pipeline
        result = await build_pipeline(MagicMock(name="ws"), context)

    assert len(result) == 4
    pipeline, llm_context, transport, memory_saver = result
    assert pipeline is mock_pipeline
    assert transport is mock_transport
    assert memory_saver is mock_memory_saver


@pytest.mark.asyncio
async def test_build_pipeline_assembles_correct_stage_order():
    """Pipeline stages must be in the correct order for audio to flow correctly."""
    context = _make_context()
    stack, patches, mock_pipeline, mock_transport, _, _ = _patch_build_pipeline()

    with stack:
        from vaaniq.voice.pipeline.builder import build_pipeline
        await build_pipeline(MagicMock(name="ws"), context)

    stages = patches["pipeline_cls"].call_args.args[0]
    # Expected order: transport.input → STT → user_agg → LangGraph → TTS → asst_agg → transport.output
    assert stages[0] is mock_transport.input.return_value
    assert stages[1] is patches["stt"].return_value
    assert stages[2] is patches["pair_cls"].return_value.user.return_value
    # stages[3] is VaaniqLangGraphService instance (not mocked)
    assert stages[4] is patches["tts"].return_value
    assert stages[5] is patches["pair_cls"].return_value.assistant.return_value
    assert stages[6] is mock_transport.output.return_value


@pytest.mark.asyncio
async def test_build_pipeline_passes_language_to_stt_and_tts():
    context = _make_context(agent_language="hi-IN", stt_provider="deepgram", tts_provider="azure")
    stack, patches, _, _, _, _ = _patch_build_pipeline()

    with stack:
        from vaaniq.voice.pipeline.builder import build_pipeline
        await build_pipeline(MagicMock(), context)

    assert patches["stt"].call_args.kwargs["language"] == "hi-IN"
    assert patches["tts"].call_args.kwargs["language"] == "hi-IN"


@pytest.mark.asyncio
async def test_build_pipeline_passes_voice_id_to_tts():
    context = _make_context(agent_voice_id="voice-xyz")
    stack, patches, _, _, _, _ = _patch_build_pipeline()

    with stack:
        from vaaniq.voice.pipeline.builder import build_pipeline
        await build_pipeline(MagicMock(), context)

    assert patches["tts"].call_args.kwargs["voice_id"] == "voice-xyz"


@pytest.mark.asyncio
async def test_build_pipeline_thread_id_format():
    """thread_id passed to VaaniqLangGraphService must be '{org_id}:{session_id}'."""
    context = _make_context(org_id="my-org", session_id="my-sess")
    captured: dict = {}

    def capture_service(**kwargs):
        captured["thread_id"] = kwargs.get("thread_id")
        return MagicMock()

    stack, patches, _, _, _, _ = _patch_build_pipeline()

    with stack:
        with patch("vaaniq.voice.pipeline.builder.VaaniqLangGraphService", side_effect=capture_service):
            from vaaniq.voice.pipeline.builder import build_pipeline
            await build_pipeline(MagicMock(), context)

    assert captured["thread_id"] == "my-org:my-sess"


@pytest.mark.asyncio
async def test_build_pipeline_calls_get_or_compile_with_correct_args():
    """get_or_compile must receive agent_id, graph_version, graph_config, org_keys."""
    context = _make_context(
        agent_id="agent-42",
        graph_version=7,
        org_keys={"openai": "key-x"},
    )
    stack, patches, _, _, _, _ = _patch_build_pipeline()

    with stack:
        from vaaniq.voice.pipeline.builder import build_pipeline
        await build_pipeline(MagicMock(), context)

    call_kwargs = patches["get_or_compile"].call_args.kwargs
    assert call_kwargs["agent_id"] == "agent-42"
    assert call_kwargs["graph_version"] == 7
    assert call_kwargs["org_keys"] == {"openai": "key-x"}


@pytest.mark.asyncio
async def test_build_pipeline_uses_vad_singleton():
    """get_vad_analyzer() must be called (not constructing SileroVADAnalyzer inline)."""
    context = _make_context()
    stack, patches, _, _, _, _ = _patch_build_pipeline()

    with stack:
        from vaaniq.voice.pipeline.builder import build_pipeline
        await build_pipeline(MagicMock(), context)

    patches["vad"].assert_called_once()


# ── run_voice_pipeline ────────────────────────────────────────────────────────

def _patch_task_runner(mock_transport=None, memory_saver=None):
    """Patch everything needed for run_voice_pipeline tests."""
    from contextlib import ExitStack

    if mock_transport is None:
        mock_transport = _mock_transport()

    mock_pipeline   = MagicMock(name="pipeline")
    mock_llm_ctx    = MagicMock(name="llm_context")
    mock_task       = AsyncMock(name="task")
    mock_task.queue_frames = AsyncMock()
    mock_runner     = AsyncMock(name="runner")
    mock_runner.run = AsyncMock()

    stack = ExitStack()
    patches = {
        "build_pipeline": stack.enter_context(patch(
            "vaaniq.voice.pipeline.task.build_pipeline",
            return_value=(mock_pipeline, mock_llm_ctx, mock_transport, memory_saver),
        )),
        "PipelineTask":   stack.enter_context(patch("vaaniq.voice.pipeline.task.PipelineTask",   return_value=mock_task)),
        "PipelineRunner": stack.enter_context(patch("vaaniq.voice.pipeline.task.PipelineRunner", return_value=mock_runner)),
        "LLMContextFrame": stack.enter_context(patch("vaaniq.voice.pipeline.task.LLMContextFrame")),
    }
    return stack, patches, mock_task, mock_runner, mock_llm_ctx


@pytest.mark.asyncio
async def test_run_pipeline_queues_initial_context_frame():
    """Greeting must be triggered by queuing an LLMContextFrame before runner.run()."""
    context = _make_context()
    stack, patches, mock_task, _, mock_llm_ctx = _patch_task_runner()

    with stack:
        from vaaniq.voice.pipeline.task import run_voice_pipeline
        await run_voice_pipeline(MagicMock(name="ws"), context)

    mock_task.queue_frames.assert_called()
    # Simpler check: LLMContextFrame was constructed once with the context
    patches["LLMContextFrame"].assert_called_once_with(context=mock_llm_ctx)


@pytest.mark.asyncio
async def test_run_pipeline_calls_runner_run():
    context = _make_context()
    stack, _, mock_task, mock_runner, _ = _patch_task_runner()

    with stack:
        from vaaniq.voice.pipeline.task import run_voice_pipeline
        await run_voice_pipeline(MagicMock(name="ws"), context)

    mock_runner.run.assert_called_once_with(mock_task)


@pytest.mark.asyncio
async def test_run_pipeline_propagates_build_exceptions():
    """Errors from build_pipeline must propagate to the caller."""
    context = _make_context()

    with patch("vaaniq.voice.pipeline.task.build_pipeline", side_effect=RuntimeError("boom")):
        from vaaniq.voice.pipeline.task import run_voice_pipeline
        with pytest.raises(RuntimeError, match="boom"):
            await run_voice_pipeline(MagicMock(), context)


@pytest.mark.asyncio
async def test_run_pipeline_finalize_called_when_memory_saver_present():
    """_finalize_session must be called after pipeline ends when memory_saver is set."""
    context = _make_context()
    mock_memory = MagicMock(name="memory_saver")
    stack, _, _, _, _ = _patch_task_runner(memory_saver=mock_memory)

    with stack:
        with patch("vaaniq.voice.pipeline.task._finalize_session", new=AsyncMock()) as mock_finalize:
            from vaaniq.voice.pipeline.task import run_voice_pipeline
            await run_voice_pipeline(MagicMock(), context)

    mock_finalize.assert_called_once()
    call_kwargs = mock_finalize.call_args.kwargs
    assert call_kwargs["session_id"] == "sess-1"
    assert call_kwargs["memory_saver"] is mock_memory


@pytest.mark.asyncio
async def test_run_pipeline_no_finalize_without_memory_saver():
    """_finalize_session must NOT be called when memory_saver is None (e.g. build failed)."""
    context = _make_context()
    stack, _, _, _, _ = _patch_task_runner(memory_saver=None)

    with stack:
        with patch("vaaniq.voice.pipeline.task._finalize_session", new=AsyncMock()) as mock_finalize:
            from vaaniq.voice.pipeline.task import run_voice_pipeline
            await run_voice_pipeline(MagicMock(), context)

    mock_finalize.assert_not_called()
