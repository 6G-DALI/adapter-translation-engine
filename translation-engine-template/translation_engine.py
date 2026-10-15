"""
6G-DALI Translation Engine - common endpoints. Do not change this file;
testbed logic goes in testbed.py.

Run:
    pip install -r requirements.txt
    python translation_engine.py

Swagger UI:
    http://localhost:8000/docs

How a request flows:

    Framework --POST /6gdali/experiment/start-->  this file
        validates the body (models.StartRequest)
        calls testbed.start_experiment(exp_id, config, status_update_url)
        calls testbed.process_metadata(exp_id, metadata)   (only if start succeeded)
        replies EXPERIMENT_START_ACCEPTED

    Framework --DELETE /6gdali/experiment/stop/{experiment_id}-->  this file
        validates the experiment ID
        calls testbed.stop_experiment(exp_id)
        replies EXPERIMENT_STOP_ACCEPTED

    testbed.py --send_status_update(...)-->  Framework  (whenever state changes)

This file stores NO experiment state. Tracking experiments is up to the
testbed (testbed.py); the engine only guarantees the format of requests,
responses and status updates.
"""

import logging
import os
from typing import Annotated
from pathlib import Path as FilePath

from fastapi import FastAPI, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import testbed
from models import APIResponse, ErrorType, ExperimentId, ResponseCode, StartRequest
from utils import APIException, doc, error, success

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("translation_engine")

app = FastAPI(
    title=f"6G-DALI Translation Engine - {testbed.TESTBED_NAME}",
    version="1.0.0",
    description=(
        "Translates the common 6G-DALI experiment API into this testbed's API. "
        "Every response uses the APIResponse format. Status updates "
        "(PENDING / RUNNING / COMPLETED / FAILED) are POSTed to the "
        "`status_update_url` given in the start request."
    ),
    docs_url=None,   # replaced by the offline /docs route below
    redoc_url=None,
)

# =============================================================================
# Endpoints
# =============================================================================

@app.post(
    "/6gdali/experiment/start",
    tags=["Experiment"],
    summary="Start a new experiment",
    response_model=APIResponse,
    responses={
        200: doc("EXPERIMENT_START_ACCEPTED", success(
            ResponseCode.EXPERIMENT_START_ACCEPTED, "Experiment start request accepted.",
            {"experiment_id": "exp0001"})),
        400: doc("INVALID_EXPERIMENT_ID / INVALID_METADATA / INVALID_CONFIGURATION", error(
            ResponseCode.INVALID_EXPERIMENT_ID, "Invalid experiment ID. Fix the fields listed in error.details.",
            ErrorType.VALIDATION_ERROR,
            [{"loc": ["body", "exp_id"],
              "msg": "Value error, Experiment ID must start with a lowercase letter (a-z)."}])),
        409: doc("EXPERIMENT_ALREADY_EXISTS", error(
            ResponseCode.EXPERIMENT_ALREADY_EXISTS, "Experiment 'exp0001' already exists.",
            ErrorType.CONFLICT)),
        422: doc("INVALID_REQUEST", error(
            ResponseCode.INVALID_REQUEST, "Request validation failed. Fix the fields listed in error.details.",
            ErrorType.VALIDATION_ERROR,
            [{"loc": ["body", "status_update_url"], "msg": "Input should be a valid URL"}])),
        500: doc("TESTBED_ERROR / INTERNAL_ERROR", error(
            ResponseCode.TESTBED_ERROR, "The local testbed failed.", ErrorType.TESTBED_ERROR)),
        503: doc("TESTBED_UNAVAILABLE", error(
            ResponseCode.TESTBED_UNAVAILABLE, "The testbed is currently unavailable.",
            ErrorType.TESTBED_ERROR)),
    },
)
async def start_experiment(data: StartRequest):
    # `data` is already validated here (exp_id rule, config, URL).
    exp_id = data.exp_id

    await testbed.start_experiment(exp_id, data.config, str(data.status_update_url))

    # Only for accepted experiments: metadata goes to the testbed's metadata
    # generation solution. It is not used to run the experiment.
    await testbed.process_metadata(exp_id, data.metadata)

    logger.info("Experiment '%s' start accepted.", exp_id)
    return success(ResponseCode.EXPERIMENT_START_ACCEPTED,
                   "Experiment start request accepted.", {"experiment_id": exp_id})


@app.delete(
    "/6gdali/experiment/stop/{experiment_id}",
    tags=["Experiment"],
    summary="Stop an experiment",
    response_model=APIResponse,
    responses={
        200: doc("EXPERIMENT_STOP_ACCEPTED", success(
            ResponseCode.EXPERIMENT_STOP_ACCEPTED, "Experiment 'exp0001' stop request accepted.",
            {"experiment_id": "exp0001"})),
        400: doc("INVALID_EXPERIMENT_ID", error(
            ResponseCode.INVALID_EXPERIMENT_ID, "Invalid experiment ID. Fix the fields listed in error.details.",
            ErrorType.VALIDATION_ERROR,
            [{"loc": ["path", "experiment_id"],
              "msg": "Value error, Experiment ID must start with a lowercase letter (a-z)."}])),
        404: doc("EXPERIMENT_NOT_FOUND", error(
            ResponseCode.EXPERIMENT_NOT_FOUND, "Experiment 'exp0001' not found.",
            ErrorType.NOT_FOUND)),
        422: doc("INVALID_REQUEST", error(
            ResponseCode.INVALID_REQUEST, "Request validation failed. Fix the fields listed in error.details.",
            ErrorType.VALIDATION_ERROR)),
        500: doc("TESTBED_ERROR / INTERNAL_ERROR", error(
            ResponseCode.TESTBED_ERROR, "The local testbed failed.", ErrorType.TESTBED_ERROR)),
    },
)
async def stop_experiment(
    experiment_id: Annotated[ExperimentId, Path(
        description="Experiment ID. Must start with a lowercase letter (a-z).",
        examples=["exp0001"])],
):
    exp_id = experiment_id

    # The testbed decides whether the experiment exists (404) and stops it.
    await testbed.stop_experiment(exp_id)

    logger.info("Experiment '%s' stop accepted.", exp_id)
    return success(ResponseCode.EXPERIMENT_STOP_ACCEPTED,
                   f"Experiment '{exp_id}' stop request accepted.", {"experiment_id": exp_id})


# =============================================================================
# Error handlers - make sure EVERY error uses the standard APIResponse format
# =============================================================================

@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    return JSONResponse(status_code=exc.http_status, content=exc.body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]

    # Pick the most specific code from where the errors are. `details` always
    # lists EVERY problem (loc = path to the field, msg = what is wrong), so
    # the caller can fix the whole body in one go.
    #   bad experiment ID  -> 400 INVALID_EXPERIMENT_ID
    #   bad metadata       -> 400 INVALID_METADATA
    #   anything else      -> 422 INVALID_REQUEST
    fields = {d["loc"][1] for d in details if len(d["loc"]) > 1}
    if fields & {"exp_id", "experiment_id"}:
        code, status, message = ResponseCode.INVALID_EXPERIMENT_ID, 400, "Invalid experiment ID."
    elif "metadata" in fields:
        code, status, message = ResponseCode.INVALID_METADATA, 400, "Invalid metadata."
    else:
        code, status, message = ResponseCode.INVALID_REQUEST, 422, "Request validation failed."

    return JSONResponse(status_code=status, content=error(
        code, f"{message} Fix the fields listed in error.details.",
        ErrorType.VALIDATION_ERROR, details))


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 405:
        body = error(ResponseCode.METHOD_NOT_ALLOWED, "Method not allowed.",
                     ErrorType.VALIDATION_ERROR)
    else:
        body = error(ResponseCode.ENDPOINT_NOT_FOUND, "Endpoint not found.",
                     ErrorType.NOT_FOUND, {"path": request.url.path})
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unexpected error")
    return JSONResponse(status_code=500, content=error(
        ResponseCode.INTERNAL_ERROR, "Internal Translation Engine error.",
        ErrorType.ADAPTER_ERROR))


# =============================================================================
# Swagger UI served from ./static, so the docs work without Internet access
# =============================================================================

STATIC_DIR = FilePath(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title,
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="/static/swagger-ui/favicon-32x32.png",
    )


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/docs")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
