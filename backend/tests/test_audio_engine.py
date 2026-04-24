"""Tests for audio-engine timing helpers."""

from __future__ import annotations

from app.audio.engine import AudioEngineConfig, AudioEngineProcess


class DummyStopEvent:
	"""Simple stand-in for the multiprocessing stop event."""

	def __init__(self, *, wait_result: bool = False) -> None:
		self.wait_calls: list[float] = []
		self.wait_result = wait_result

	def is_set(self) -> bool:
		return False

	def wait(self, timeout: float) -> bool:
		self.wait_calls.append(timeout)
		return self.wait_result


def make_audio_engine(stop_event: DummyStopEvent) -> AudioEngineProcess:
	"""Create a process instance without starting a child process."""
	return AudioEngineProcess(
		AudioEngineConfig(
			buffer_path="unused.buffer",
			channels=2,
			sample_rate=48_000,
			buffer_duration_sec=300,
			block_size=480,
		),
		stop_event,
	)


def test_wait_for_next_block_accounts_for_elapsed_processing(monkeypatch) -> None:
	stop_event = DummyStopEvent()
	engine = make_audio_engine(stop_event)
	monkeypatch.setattr("app.audio.engine.time.perf_counter", lambda: 100.001)

	next_deadline = engine._wait_for_next_block(100.0, 0.01)

	assert next_deadline == 100.01
	assert len(stop_event.wait_calls) == 1
	assert 0.0089 <= stop_event.wait_calls[0] <= 0.0091


def test_wait_for_next_block_skips_sleep_when_already_behind(monkeypatch) -> None:
	stop_event = DummyStopEvent()
	engine = make_audio_engine(stop_event)
	monkeypatch.setattr("app.audio.engine.time.perf_counter", lambda: 100.015)

	next_deadline = engine._wait_for_next_block(100.0, 0.01)

	assert next_deadline == 100.01
	assert stop_event.wait_calls == []


def test_wait_for_next_block_stops_when_event_is_set(monkeypatch) -> None:
	stop_event = DummyStopEvent(wait_result=True)
	engine = make_audio_engine(stop_event)
	monkeypatch.setattr("app.audio.engine.time.perf_counter", lambda: 100.001)

	next_deadline = engine._wait_for_next_block(100.0, 0.01)

	assert next_deadline is None
	assert len(stop_event.wait_calls) == 1