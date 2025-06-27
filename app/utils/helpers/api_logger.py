import json
import time
import asyncio
from typing import Callable
from fastapi import Request
from app.config.logger import logger
from app.utils import constants
from app.db.models.api_logs import APILog
from starlette.responses import Response
from app.config.postgres import close_session
from starlette.middleware.base import BaseHTTPMiddleware

class _APILoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response            = None
        request_metadata    = {}
        response_metadata   = {}
        request_headers     = dict(request.headers)

        try:
            request_metadata['method'] = request.method
            request_metadata['path']   = request.url.path
            try:
                request_body = await request.body()
                request_metadata['params'] = {
                    'query': request.query_params._dict,
                    'body': json.loads(request_body) if request_body else {}
                }
            except Exception:
                request_metadata['params'] = {
                    'query': request.query_params._dict,
                    'body': {}
                }
            logger.info(f'Incoming request: {request_metadata}')

            # Measure processing time
            start_time = time.time()
            response = await call_next(request)
            end_time = time.time()
            process_time = round((end_time - start_time) * 1000, 2)

            # Log outgoing response
            response_metadata['success']      = response.status_code < 400
            response_metadata['status_code']  = response.status_code
            response_metadata['process_time'] = f'{process_time:.2f} ms'
            logger.info(f'Outgoing response: {response_metadata}')

            asyncio.create_task(self._push_log_into_db(process_time, request_headers, request_metadata, response_metadata))

            return response

        except Exception as e:
            logger.error(f'Error during API logging: {str(e)}', exc_info=True)
            response = await call_next(request) if response is None else response

            return response

    async def _push_log_into_db(self, process_time, request_headers, request_metadata, response_metadata):
        try:
            if constants.APP_ENV.lower() == 'development':
                return

            payload = {
                'process_time': process_time,
                'path': request_metadata.get('path'),
                'method': request_metadata.get('method'),
                'rq_params': request_metadata.get('params'),
                'success': response_metadata.get('success'),
                'status_code': response_metadata.get('status_code'),
                'auth_headers': json.loads(request_headers.get('auth', 'null')),
            }

            if (payload['path'] == '/ping') and (payload['method'].lower() == 'get'):
                return

            APILog.create_record(payload)
        finally:
            close_session()

api_logger_middleware = _APILoggerMiddleware
