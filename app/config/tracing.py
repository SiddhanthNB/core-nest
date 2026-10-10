from __future__ import annotations

import logging

from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagators.textmap import TextMapPropagator
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.trace import SpanKind, StatusCode

from app.config import constants
from app.config.logger import logger
from app.db import db

TRACER_NAME = constants.PROJECT_NAME
_SPAN_ATTRIBUTES = ("gen_ai.provider.name", "gen_ai.request.model", "outcome", "error.type", "http.status_code", "http.response.status_code")  # fmt: skip
_configured = False

tracer = trace.get_tracer(TRACER_NAME)


class LogSpanProcessor(SpanProcessor):
    def __init__(self, span_logger: logging.Logger = logger):
        self._logger = span_logger

    def on_end(self, span: ReadableSpan) -> None:
        level = logging.INFO if span.kind == SpanKind.SERVER or span.instrumentation_scope.name == TRACER_NAME else logging.DEBUG  # fmt: skip
        if not self._logger.isEnabledFor(level):
            return
        context = span.get_span_context()
        parent_span_id = format(span.parent.span_id, "016x") if span.parent else "-"
        duration_ms = round(((span.end_time or 0) - (span.start_time or 0)) / 1_000_000, 2)
        status = span.status.status_code.name
        fields = [f"[name: {span.name}]", f"[parent: {parent_span_id}]", f"[duration_ms: {duration_ms}]", f"[status: {status}]"]  # fmt: skip
        fields += [f"[{key}: {span.attributes[key]}]" for key in _SPAN_ATTRIBUTES if span.attributes and key in span.attributes]  # fmt: skip
        if span.status.status_code == StatusCode.ERROR and span.status.description:
            fields.append(f"[error: {span.status.description}]")
        record = self._logger.makeRecord(self._logger.name, level, __file__, 0, f"{' '.join(fields)} Span ended", None, None)  # fmt: skip
        record.otelTraceID = format(context.trace_id, "032x")
        record.otelSpanID = format(context.span_id, "016x")
        self._logger.handle(record)


class _NoopPropagator(TextMapPropagator):
    def extract(self, carrier, context: Context | None = None, getter=None) -> Context:
        return context if context is not None else Context()

    def inject(self, carrier, context: Context | None = None, setter=None) -> None:
        return None

    @property
    def fields(self) -> set[str]:
        return set()


def configure_tracing() -> None:
    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: constants.PROJECT_NAME}))
    provider.add_span_processor(LogSpanProcessor())
    trace.set_tracer_provider(provider)
    # every request starts its own trace; never accept or forward traceparent headers
    propagate.set_global_textmap(_NoopPropagator())

    LoggingInstrumentor().instrument(set_logging_format=False, inject_trace_context=True, enable_log_auto_instrumentation=False)  # fmt: skip
    RedisInstrumentor().instrument()

    if db.async_engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=db.async_engine.sync_engine)
    _configured = True


def instrument_app(app: FastAPI) -> None:
    configure_tracing()
    FastAPIInstrumentor.instrument_app(app, exclude_spans=["receive", "send"])
