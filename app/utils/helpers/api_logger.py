import json
import time
from typing import Callable
from fastapi import Request, status
from app.config.logger import logger
from app.utils import constants
from app.db.models.api_logs import APILog
from fastapi.responses import JSONResponse
from app.config.postgres import get_async_db_session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.background import BackgroundTask

class _APILoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        start = time.perf_counter()
        request_metadata = {
            'method': request.method,
            'path': request.url.path,
        }
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

        logger.info(f"Incoming request: {request_metadata}")

        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(content="Internal Server Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        process_time = (time.perf_counter() - start) * 1000

        response_metadata = {
            'success': response.status_code < 400,
            'status_code': response.status_code,
            'process_time': f'{process_time:.2f} ms'
        }

        logger.info(f"Request to {request_metadata['path']} finished with status {response.status_code}")

        response.background = BackgroundTask(self._push_log_into_db, process_time, request_metadata, response_metadata)

        return response

    async def _push_log_into_db(self, process_time, request_metadata, response_metadata):
        try:
            payload = {
                'process_time': process_time,
                'path': request_metadata.get('path'),
                'method': request_metadata.get('method'),
                'rq_params': request_metadata.get('params'),
                'success': response_metadata.get('success'),
                'status_code': response_metadata.get('status_code'),
            }

            if (payload['path'] == '/ping') and (payload['method'].lower() == 'get'):
                return

            if constants.APP_ENV.lower() == 'development':
                return

            async with get_async_db_session() as session:
                await APILog.create_record(db_session=session, fields=payload)
        except Exception as e:
            logger.error(f'Error saving API log to database: {str(e)}', exc_info=True)

api_logger_middleware = _APILoggerMiddleware
