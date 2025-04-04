import json
import time
from config.logger import logger
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class _APILoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = None
        try:
            request_info = {
                'method': request.method,
                'path': request.url.path
            }
            try:
                request_info['params'] = {
                    'query': request.query_params._dict,
                    'body': json.loads(await request.body()) if await request.body() else {}
                }
            except Exception:
                request_info['params'] = {
                    'query': request.query_params._dict,
                    'body': {}
                }
            logger.info(f'Incoming request: {request_info}')

            # Measure processing time
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log outgoing response
            response_info = {
                'success': response.status_code < 400,
                'status_code': response.status_code,
                'process_time': f'{process_time:.2f} seconds'
            }
            logger.info(f'Outgoing response: {response_info}')

            return response

        except Exception as e:
            logger.error(f'Error during API logging: {str(e)}', exc_info=True)
            if response is None:
                response = await call_next(request)
            return response

api_logger_middleware = _APILoggerMiddleware
