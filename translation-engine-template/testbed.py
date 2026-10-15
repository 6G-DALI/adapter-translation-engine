"""
TESTBED-SPECIFIC LOGIC - this is the file you implement.

translation_engine.py calls three functions:

    start_experiment(exp_id, config, status_update_url)  on start
    process_metadata(exp_id, metadata)                   on start, after a successful start_experiment
    stop_experiment(exp_id)                              on stop

When they are called, the request is already validated:
  - exp_id is non-empty and starts with a lowercase letter (a-z),
  - metadata has all the fixed keys (models.Metadata),
  - config is a valid Configuration (models.py),
  - status_update_url is a valid http(s) URL.

What the engine does NOT do - this is your responsibility:
  - Keep track of experiments. The engine stores no state. If you need to
    know which experiments exist, their local IDs or where to send their
    status updates, store it yourself (memory, file, database, the
    testbed's own API...).
  - Decide when an experiment changes state, and report it with:

        await send_status_update(exp_id, NewAdapterState.RUNNING, status_update_url)

    The engine guarantees only that the update has the correct format.

Rules:
  1. Only send NewAdapterState values (PENDING, RUNNING, COMPLETED, FAILED).
  2. Every started experiment must end with COMPLETED or FAILED.
     Send COMPLETED ONLY when ALL of these succeeded:
       a) the experiment ran successfully,
       b) the dataset AND its metadata were generated,
       c) the files were uploaded by the DS connector.
     Any failure in between (run, dataset, metadata, upload) -> send FAILED.
  3. Return quickly (a few seconds). For long operations, start them in the
     background with asyncio.create_task(...) and report when done.
  4. To return an error, raise APIException (see utils.py). Any other
     exception is returned as 500 INTERNAL_ERROR.
  5. Use async libraries (httpx.AsyncClient) - blocking calls freeze the server.

As shipped, this file SIMULATES a testbed so the template runs on its own.
Replace the parts marked "TODO" with your testbed's logic.
"""

import asyncio
import logging
from typing import Dict

from models import Configuration, ErrorType, Metadata, NewAdapterState, ResponseCode
from utils import APIException, send_status_update

logger = logging.getLogger("translation_engine.testbed")

# TODO: your testbed's name (shown in the Swagger title).
TESTBED_NAME = "Example Testbed (simulated)"


# -----------------------------------------------------------------------------
# Experiment state - OWNED BY THE TESTBED
# -----------------------------------------------------------------------------
# SIMULATION ONLY: a dict in memory, lost on restart.
# TODO: replace with however your testbed tracks its experiments.
# Here: exp_id -> status_update_url (needed to report status on stop).
_experiments: Dict[str, str] = {}


# -----------------------------------------------------------------------------
# Metadata
# -----------------------------------------------------------------------------

async def process_metadata(exp_id: str, metadata: Metadata) -> None:
    """
    Pass the experiment metadata to your testbed's metadata generation
    solution. Metadata is NOT used to run the experiment.

    `metadata` is already validated (models.Metadata): all fixed keys are
    present and well-formed. Read fields as metadata.title, metadata.keywords,
    metadata.testbed_context.network_domain..., or metadata.model_dump() for a dict.

    Called right after start_experiment() succeeds. If it raises, the
    Framework receives an error although the experiment has been started:
    handle failures here (log, retry, or stop the experiment) as suits you.
    """
    # TODO: hand the metadata to your metadata generation solution, e.g.
    #
    #    async with httpx.AsyncClient() as client:
    #        await client.post(f"{METADATA_SERVICE_URL}/experiments/{exp_id}",
    #                          json=metadata.model_dump())
    logger.info("[SIMULATION] metadata for '%s': %s", exp_id, metadata.model_dump())


# -----------------------------------------------------------------------------
# Start
# -----------------------------------------------------------------------------

async def start_experiment(
    exp_id: str, config: Configuration, status_update_url: str
) -> None:
    """Translate the common start request to your testbed and start it."""

    # 1. Your own checks. Example: reject an experiment you already run.
    if exp_id in _experiments:
        raise APIException(
            409, ResponseCode.EXPERIMENT_ALREADY_EXISTS,
            f"Experiment '{exp_id}' already exists.", ErrorType.CONFLICT,
        )

    # 2. Translate the common config into your testbed's request.
    #    TODO: map your Configuration fields, e.g.
    #    local_request = {"name": exp_id, "scenario": config.scenario_name,
    #                     "duration_s": config.duration}
    local_request = {"name": exp_id, **config.model_dump()}

    # 3. Start the experiment on your testbed.
    #    TODO: replace this simulation with the real call, e.g.
    #
    #    try:
    #        async with httpx.AsyncClient(timeout=10) as client:
    #            resp = await client.post(f"{TESTBED_URL}/jobs", json=local_request)
    #    except httpx.TransportError:   # testbed offline / unreachable / no answer
    #        raise APIException(503, ResponseCode.TESTBED_UNAVAILABLE,
    #                           "The testbed is currently unavailable.",
    #                           ErrorType.TESTBED_ERROR)
    #    if resp.status_code >= 400:
    #        raise APIException(500, ResponseCode.TESTBED_ERROR,
    #                           "Testbed refused the experiment.",
    #                           ErrorType.TESTBED_ERROR, details=resp.text)
    logger.info("[SIMULATION] start on testbed: %s", local_request)

    # 4. Save what you need later (here: where to send status updates).
    _experiments[exp_id] = status_update_url

    # 5. Report status when your testbed says it's running. Here we pretend
    #    deployment takes 1 second, in the background so the reply isn't delayed.
    async def simulate_deployment():
        await asyncio.sleep(1)
        if exp_id in _experiments:  # not stopped meanwhile
            await send_status_update(exp_id, NewAdapterState.RUNNING, status_update_url)

    asyncio.create_task(simulate_deployment())


# -----------------------------------------------------------------------------
# Stop
# -----------------------------------------------------------------------------

async def stop_experiment(exp_id: str) -> None:
    """Stop the experiment on your testbed."""

    # 1. Find the experiment in YOUR state.
    status_update_url = _experiments.get(exp_id)
    if status_update_url is None:
        raise APIException(
            404, ResponseCode.EXPERIMENT_NOT_FOUND,
            f"Experiment '{exp_id}' not found.", ErrorType.NOT_FOUND,
        )

    # 2. Stop it on your testbed.
    #    TODO: replace this simulation with the real call, e.g.
    #
    #    async with httpx.AsyncClient() as client:
    #        resp = await client.delete(f"{TESTBED_URL}/jobs/{exp_id}")
    #    if resp.status_code >= 400:
    #        await send_status_update(exp_id, NewAdapterState.FAILED, status_update_url)
    #        raise APIException(500, ResponseCode.TESTBED_ERROR,
    #                           "Testbed failed to stop the experiment.",
    #                           ErrorType.TESTBED_ERROR)
    logger.info("[SIMULATION] stop on testbed: %s", exp_id)

    # 3. Update your state and report the final status.
    #    COMPLETED only once the run succeeded, the dataset and metadata were
    #    generated AND the DS connector uploaded the files. If any step fails,
    #    send FAILED instead. In a real testbed this usually happens later,
    #    when your pipeline finishes - not here in the stop handler.
    #    SIMULATION: we pretend every step succeeded immediately.
    del _experiments[exp_id]
    await send_status_update(exp_id, NewAdapterState.COMPLETED, status_update_url)
