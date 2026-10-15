"""
API models (request bodies, responses, status updates).

Everything in this file is COMMON to all testbeds and must not be changed,
EXCEPT the section marked "TESTBED-SPECIFIC: Configuration".
"""

from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from pydantic import (
    AfterValidator, AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints,
)


# =============================================================================
# TESTBED-SPECIFIC: Configuration  (the testbed owner MUST define this)
# =============================================================================
# The template only defines the `config` key of the start request. What goes
# inside it is defined by each testbed owner, as Pydantic fields below.
# FastAPI validates every request against this model automatically: a missing
# field, wrong type or unknown key is rejected with 422 INVALID_REQUEST before
# your code runs, so testbed.py always receives a valid Configuration.
#
# Example:
#
#     class Frequency(BaseModel):
#         model_config = ConfigDict(extra="forbid")
#         interval: int = Field(..., gt=0, description="Sampling interval.")
#         unit: str = Field(..., description="Unit of interval, e.g. 'seconds'.")
#
#     class Configuration(BaseModel):
#         model_config = ConfigDict(extra="forbid")
#         scenario_name: str = Field(..., description="Scenario to deploy.")
#         duration: int = Field(..., gt=0, description="Duration of the run.")
#         frequency: Frequency
#
# Keep extra="forbid": a misspelled or unexpected key is rejected instead of
# being silently ignored. As shipped (no fields), only an empty object {} is
# accepted.

class Configuration(BaseModel):
    """Testbed-specific experiment configuration. TODO: define your fields."""

    # Reject any key that is not declared as a field below.
    model_config = ConfigDict(extra="forbid")


# Example `config` shown in Swagger "Try it out".
# TODO: replace with a valid example for your fields.
EXAMPLE_CONFIG: Dict[str, Any] = {}


# =============================================================================
# COMMON: experiment ID rule
# =============================================================================
# Required by later stages of the pipeline: the experiment ID must not be
# empty and must start with a lowercase letter a-z.
# Applied to `exp_id` in the start body AND to `experiment_id` in the stop URL.

def check_experiment_id(value: str) -> str:
    if not value:
        raise ValueError("Experiment ID cannot be empty.")
    if not ("a" <= value[0] <= "z"):
        raise ValueError("Experiment ID must start with a lowercase letter (a-z).")
    return value


# Use this type for any experiment ID; Pydantic then applies the rule above.
ExperimentId = Annotated[str, AfterValidator(check_experiment_id)]


# =============================================================================
# COMMON: metadata
# =============================================================================
# The metadata keys are fixed for all testbeds. Every key is required and no
# other key is accepted. Invalid metadata is rejected with 400 INVALID_METADATA,
# and error.details lists each field to fix (location + reason).

# A string that is not empty once surrounding spaces are removed.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def check_frequency(value: str) -> str:
    """frequency is a positive number written as a string, e.g. "5"."""
    try:
        number = float(value)
    except ValueError:
        number = 0
    if number <= 0:
        raise ValueError('frequency must be a positive number written as a string, e.g. "5".')
    return value


class TestbedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network_domain: NonEmptyStr = Field(
        ..., description="Network domain of the testbed.", examples=["RAN"]
    )


class Metadata(BaseModel):
    """Experiment metadata. Passed to the testbed's metadata generation only."""

    model_config = ConfigDict(extra="forbid")

    title: NonEmptyStr = Field(
        ..., description="Title of the experiment / dataset.",
        examples=["Energy Saving Small Area Two Layers Sectorized AppOFF"],
    )
    description: NonEmptyStr = Field(
        ..., description="Free-text description.",
        examples=["RAN dataset generated through the EURECOM Digital Twin testbed"],
    )
    keywords: List[NonEmptyStr] = Field(
        ..., min_length=1, description="At least one keyword.",
        examples=[["Energy", "RAN", "Digital_Twin"]],
    )
    frequency: Annotated[str, AfterValidator(check_frequency)] = Field(
        ..., description='Sampling frequency as a string, e.g. "5".', examples=["5"],
    )
    unit: NonEmptyStr = Field(
        ..., description="Unit of frequency.", examples=["seconds"],
    )
    testbed_context: TestbedContext


# =============================================================================
# COMMON: request sent by the Framework
# =============================================================================

class StartRequest(BaseModel):
    """Body of POST /6gdali/experiment/start."""

    exp_id: ExperimentId = Field(
        ..., description="Experiment ID. Must start with a lowercase letter (a-z).",
        examples=["experiment-001"],
    )
    metadata: Metadata = Field(
        ...,
        description=(
            "Experiment metadata (fixed keys). Handed to the testbed's metadata "
            "generation (testbed.process_metadata); NOT used to run the experiment."
        ),
    )
    status_update_url: AnyHttpUrl = Field(
        ...,
        description="Where status updates for this experiment are POSTed.",
        examples=["http://localhost:9000/status"],
    )
    config: Configuration = Field(
        ...,
        description="Testbed-specific configuration (see Configuration).",
        examples=[EXAMPLE_CONFIG],
    )


# =============================================================================
# COMMON: response envelope returned by every endpoint
# =============================================================================

class ResponseCode(str, Enum):
    """
    The only values allowed in the `code` field.

    | Code                      | HTTP | Used when                                   |
    |---------------------------|------|---------------------------------------------|
    | EXPERIMENT_START_ACCEPTED | 200  | Start request accepted                      |
    | EXPERIMENT_STOP_ACCEPTED  | 200  | Stop request accepted                       |
    | INVALID_EXPERIMENT_ID     | 400  | Experiment ID empty / not starting with a-z |
    | INVALID_METADATA          | 400  | metadata missing keys, extra keys, bad values |
    | INVALID_CONFIGURATION     | 400  | config is valid JSON but testbed can't run it |
    | EXPERIMENT_NOT_FOUND      | 404  | Stop for an unknown experiment (testbed)    |
    | ENDPOINT_NOT_FOUND        | 404  | Unknown URL                                 |
    | METHOD_NOT_ALLOWED        | 405  | Wrong HTTP method                           |
    | EXPERIMENT_ALREADY_EXISTS | 409  | Start for an existing experiment (testbed)  |
    | INVALID_REQUEST           | 422  | Body doesn't match the schema               |
    | TESTBED_ERROR             | 500  | The local testbed failed                    |
    | TESTBED_UNAVAILABLE       | 503  | The testbed is offline / unreachable        |
    | INTERNAL_ERROR            | 500  | Unexpected error in the engine              |
    """

    EXPERIMENT_START_ACCEPTED = "EXPERIMENT_START_ACCEPTED"
    EXPERIMENT_STOP_ACCEPTED = "EXPERIMENT_STOP_ACCEPTED"
    INVALID_EXPERIMENT_ID = "INVALID_EXPERIMENT_ID"
    INVALID_METADATA = "INVALID_METADATA"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    EXPERIMENT_NOT_FOUND = "EXPERIMENT_NOT_FOUND"
    ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    EXPERIMENT_ALREADY_EXISTS = "EXPERIMENT_ALREADY_EXISTS"
    INVALID_REQUEST = "INVALID_REQUEST"
    TESTBED_ERROR = "TESTBED_ERROR"
    TESTBED_UNAVAILABLE = "TESTBED_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorType(str, Enum):
    """The only values allowed in `error.type`."""

    VALIDATION_ERROR = "validation_error"  # request is wrong
    NOT_FOUND = "not_found"                # experiment / URL doesn't exist
    CONFLICT = "conflict"                  # clashes with current state
    TESTBED_ERROR = "testbed_error"        # local testbed failed
    ADAPTER_ERROR = "adapter_error"        # unexpected engine error


class APIError(BaseModel):
    type: ErrorType
    details: Optional[Any] = None


class APIResponse(BaseModel):
    """
    Every response, success or error, has exactly this shape.
    result="success" -> error is null.  result="error" -> error is set.
    """

    result: str = Field(..., description='"success" or "error"')
    code: ResponseCode
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[APIError] = None
    timestamp: str = Field(..., description="ISO-8601, UTC")


# =============================================================================
# COMMON: status update sent to the Framework (POST to status_update_url)
# =============================================================================

class NewAdapterState(str, Enum):
    """
    The only status values the Framework understands.
    Map your testbed's own states onto these four.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class AdapterStateUpdate(BaseModel):
    exp_id: str
    new_status: NewAdapterState
    timestamp: str
