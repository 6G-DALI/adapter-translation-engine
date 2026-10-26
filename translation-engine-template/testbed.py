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
  6. Never let an experiment run forever: keep the max-duration watchdog.

Running and stopping experiments:
  - The Framework starts AND stops every experiment. There is no duration in
    the config, and the testbed does not stop experiments by itself.
  - A watchdog is armed for every experiment when it starts.
  - Stop endpoint called  -> the watchdog is cancelled, then your stopping
                             procedure runs (stop_procedure()).
  - Stop endpoint NOT called within MAX_EXPERIMENT_DURATION seconds
                          -> the watchdog calls the same stop_procedure().
    This protects the testbed if the LLM agent forgets, hallucinates or
    fails: otherwise the experiment would keep running unnoticed.
  - MAX_EXPERIMENT_DURATION is an environment variable, set at deployment:
        MAX_EXPERIMENT_DURATION=7200 python translation_engine.py

As shipped, this file SIMULATES a testbed so the template runs on its own.
Replace the parts marked "TODO" with your testbed's logic.
"""

import asyncio
import logging
import os
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
# Here: exp_id -> status_update_url, for experiments currently running.
_experiments: Dict[str, str] = {}


# -----------------------------------------------------------------------------
# Safety net: maximum experiment duration (watchdog)
# -----------------------------------------------------------------------------
# Set at deployment with the environment variable MAX_EXPERIMENT_DURATION
# (seconds, default 3600). Choose the longest run your testbed should allow.

def _read_max_duration() -> float:
    raw = os.getenv("MAX_EXPERIMENT_DURATION", "3600")
    try:
        value = float(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise ValueError(
            f"MAX_EXPERIMENT_DURATION must be a positive number of seconds, got {raw!r}."
        )
    return value


MAX_EXPERIMENT_DURATION = _read_max_duration()

# exp_id -> watchdog task
_watchdogs: Dict[str, asyncio.Task] = {}


def _start_watchdog(exp_id: str) -> None:
    """Arm the watchdog for a newly started experiment."""
    _watchdogs[exp_id] = asyncio.create_task(_watchdog(exp_id))
    logger.info("Watchdog armed for '%s': max %.0f s.", exp_id, MAX_EXPERIMENT_DURATION)


def _cancel_watchdog(exp_id: str) -> None:
    """Disarm the watchdog (the stop endpoint was called in time)."""
    task = _watchdogs.pop(exp_id, None)
    if task is not None:
        task.cancel()


async def _watchdog(exp_id: str) -> None:
    """Stop the experiment if the stop endpoint was not called in time."""
    await asyncio.sleep(MAX_EXPERIMENT_DURATION)
    _watchdogs.pop(exp_id, None)
    if exp_id in _experiments:
        logger.warning(
            "Experiment '%s': no stop request after %.0f s (MAX_EXPERIMENT_DURATION). "
            "Stopping it.", exp_id, MAX_EXPERIMENT_DURATION,
        )
        await stop_procedure(exp_id, reason="max duration reached")


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
    #    local_request = {"name": exp_id, "scenario": config.scenario_name}
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

    # 4. Save what you need later (here: where to send status updates),
    #    and arm the watchdog (keep this line).
    _experiments[exp_id] = status_update_url
    _start_watchdog(exp_id)

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
    """Called by the stop endpoint. Cancels the watchdog, then stops."""

    # 1. Find the experiment in YOUR state.
    if exp_id not in _experiments:
        raise APIException(
            404, ResponseCode.EXPERIMENT_NOT_FOUND,
            f"Experiment '{exp_id}' not found.", ErrorType.NOT_FOUND,
        )

    # 2. The Framework stopped it in time: the watchdog is no longer needed.
    _cancel_watchdog(exp_id)

    # 3. Run your stopping procedure.
    await stop_procedure(exp_id, reason="stop request")


async def stop_procedure(exp_id: str, reason: str) -> None:
    """
    YOUR stopping procedure. Called by the stop endpoint, or by the watchdog
    when no stop request arrived within MAX_EXPERIMENT_DURATION.
    `reason` is "stop request" or "max duration reached".
    """
    # Remove the experiment from the running ones first, so a stop request
    # arriving while the watchdog is stopping it gets 404, not a second stop.
    status_update_url = _experiments.pop(exp_id)

    # 1. Stop it on your testbed.
    #    TODO: replace this simulation with the real call, e.g.
    #
    #    async with httpx.AsyncClient() as client:
    #        resp = await client.delete(f"{TESTBED_URL}/jobs/{exp_id}")
    #    if resp.status_code >= 400:
    #        await send_status_update(exp_id, NewAdapterState.FAILED, status_update_url)
    #        raise APIException(500, ResponseCode.TESTBED_ERROR,
    #                           "Testbed failed to stop the experiment.",
    #                           ErrorType.TESTBED_ERROR)
    logger.info("[SIMULATION] stop on testbed: %s (%s)", exp_id, reason)

    # 2. Report the final status.
    #    COMPLETED only once the run succeeded, the dataset and metadata were
    #    generated AND the DS connector uploaded the files. If any step fails,
    #    send FAILED instead. In a real testbed this usually happens later,
    #    when your pipeline finishes - not here.
    #    A watchdog stop is treated like a normal stop here (the data collected
    #    so far is processed). If a forced stop makes your data unusable,
    #    report FAILED when reason == "max duration reached".
    #    SIMULATION: we pretend every step succeeded immediately.
    await send_status_update(exp_id, NewAdapterState.COMPLETED, status_update_url)
