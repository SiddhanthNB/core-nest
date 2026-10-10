from __future__ import annotations

import logging

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanKind, StatusCode

from app.config.logger import _TraceContextFilter
from app.config.logger import logger as app_logger
from app.config.tracing import TRACER_NAME, LogSpanProcessor, configure_tracing


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _span_logger(level: int) -> tuple[logging.Logger, _ListHandler]:
    span_logger = logging.getLogger(f"test-spans-{level}")
    span_logger.handlers.clear()
    span_logger.propagate = False
    span_logger.setLevel(level)
    handler = _ListHandler()
    span_logger.addHandler(handler)
    return span_logger, handler


def _provider(span_logger: logging.Logger) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(LogSpanProcessor(span_logger))
    return provider


def test_span_processor_writes_one_flat_line_per_span_with_level_split() -> None:
    span_logger, handler = _span_logger(logging.DEBUG)
    provider = _provider(span_logger)
    app_tracer = provider.get_tracer(TRACER_NAME)
    redis_tracer = provider.get_tracer("opentelemetry.instrumentation.redis")

    with provider.get_tracer("opentelemetry.instrumentation.asgi").start_as_current_span("POST /v1/chat/completions", kind=SpanKind.SERVER) as request_span:  # fmt: skip
        with redis_tracer.start_as_current_span("INCRBY", kind=SpanKind.CLIENT):
            pass
        with app_tracer.start_as_current_span("chat mistral/small", attributes={"gen_ai.provider.name": "mistral", "outcome": "failed", "error.type": "RateLimitError"}) as attempt_span:  # fmt: skip
            attempt_span.set_status(StatusCode.ERROR)

    by_name = {record.getMessage().split("]", 1)[0]: record for record in handler.records}
    assert len(handler.records) == 3
    redis_record = by_name["[name: INCRBY"]
    attempt_record = by_name["[name: chat mistral/small"]
    request_record = by_name["[name: POST /v1/chat/completions"]

    assert redis_record.levelno == logging.DEBUG
    assert attempt_record.levelno == logging.INFO
    assert request_record.levelno == logging.INFO

    request_context = request_span.get_span_context()
    trace_id = format(request_context.trace_id, "032x")
    assert {record.otelTraceID for record in handler.records} == {trace_id}
    assert request_record.otelSpanID == format(request_context.span_id, "016x")
    assert attempt_record.otelSpanID == format(attempt_span.get_span_context().span_id, "016x")

    message = attempt_record.getMessage()
    assert "\n" not in message and "{" not in message
    assert f"[parent: {request_record.otelSpanID}]" in message
    assert "[status: ERROR]" in message
    assert "[gen_ai.provider.name: mistral]" in message
    assert "[outcome: failed]" in message
    assert "[error.type: RateLimitError]" in message
    assert "[duration_ms: " in message
    assert "[parent: -]" in request_record.getMessage()


def test_span_processor_skips_debug_spans_at_info_level() -> None:
    span_logger, handler = _span_logger(logging.INFO)
    provider = _provider(span_logger)

    with provider.get_tracer("opentelemetry.instrumentation.sqlalchemy").start_as_current_span("SELECT", kind=SpanKind.CLIENT):  # fmt: skip
        pass
    with provider.get_tracer(TRACER_NAME).start_as_current_span("embeddings google/text-embedding"):
        pass

    assert [record.getMessage().split("]", 1)[0] for record in handler.records] == ["[name: embeddings google/text-embedding"]  # fmt: skip


def _formatted_handler() -> logging.Handler:
    return next(handler for handler in logging.getLogger().handlers if any(isinstance(item, _TraceContextFilter) for item in handler.filters))  # fmt: skip


def test_formatted_records_carry_trace_and_span_ids() -> None:
    configure_tracing()
    configure_tracing()
    handler = _formatted_handler()
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("work") as span:
        inside = app_logger.makeRecord(app_logger.name, logging.INFO, __file__, 0, "inside", None, None)
    outside = app_logger.makeRecord(app_logger.name, logging.INFO, __file__, 0, "outside", None, None)

    for record in (inside, outside):
        handler.filter(record)
    context = span.get_span_context()
    assert f"[trace: {format(context.trace_id, '032x')}] [span: {format(context.span_id, '016x')}] : inside" in handler.format(inside)  # fmt: skip
    assert "[trace: -] [span: -] : outside" in handler.format(outside)


def test_formatter_tolerates_records_without_trace_fields() -> None:
    handler = _formatted_handler()
    record = logging.LogRecord(app_logger.name, logging.INFO, __file__, 0, "plain", None, None)

    handler.filter(record)

    assert "[trace: -] [span: -] : plain" in handler.format(record)
