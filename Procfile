# FastMCP's session_manager is process-local state. Pinning --workers 1 is
# required: multiple workers would each run their own session manager and
# clients would get inconsistent responses depending on which worker
# happened to handle a request.
web: uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-graceful-shutdown 30
