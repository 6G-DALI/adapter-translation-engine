# 6G-DALI Translation Engine — Template

The **Translation Engine** is a small web service deployed next to each virtual
testbed. The 6G-DALI Framework sends it experiment-control requests through one
**common API**. The Translation Engine translates them into the testbed's own API
and reports the experiment's state back to the Framework.

This repository is the **template** each testbed starts from. The common API is
already implemented: endpoints, request validation, response format, error codes
and status updates. A testbed owner only implements the testbed-specific parts.

As shipped, the template **simulates a testbed**, so it runs on its own and you
can explore the API docs before writing any code.

> Full details, rules and examples are in the **Developer Guide**
> (`Translation_Engine_Developer_Guide.docx`).

---

## Folder structure

```
translation-engine-template/
├── translation_engine.py     # Common endpoints, error handling, Swagger, server start  (do not edit)
├── models.py                 # API models, experiment-ID rule, metadata, codes, states
│                             #   -> edit ONLY the "Configuration" section
├── utils.py                  # Helpers: success(), error(), APIException, send_status_update()  (do not edit)
├── testbed.py                # YOUR testbed logic: start, stop, metadata, experiment state  (edit)
├── requirements.txt          # Python dependencies (you may add your own)
├── README.md
├── static/
│   └── swagger-ui/           # Swagger UI files, bundled so /docs works offline  (do not edit)
└── extras/
    └── mock_framework.py     # Optional: fake Framework that prints status updates (local testing only)
```

---

## Quick start: run it and open the API docs

**Requirements:** Python 3.9+ and Git.

```bash
git clone https://github.com/6G-DALI/adapter-translation-engine.git
cd translation-engine-template

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python translation_engine.py
```

When the terminal shows `Uvicorn running on http://0.0.0.0:8000`, open:

| URL | What it shows |
|-----|---------------|
| http://localhost:8000/docs | **Swagger UI**: endpoints, request examples, every response code, data models |
| http://localhost:8000/openapi.json | Raw OpenAPI specification (Postman, code generators, LLM agent) |
| http://localhost:8000/ | Redirects to `/docs` |

The Swagger files are bundled, so the docs also work on a testbed network
**without Internet access**.

To change the port or interface:

```bash
PORT=8080 HOST=127.0.0.1 python translation_engine.py
```

### Try a full experiment cycle (optional)

1. In a second terminal (same folder, virtual environment activated):
   ```bash
   python extras/mock_framework.py      # listens on port 9000
   ```
2. In Swagger, open **POST /6gdali/experiment/start** → **Try it out** → **Execute**
   (keep the example body). Response: `EXPERIMENT_START_ACCEPTED`.
3. After ~1 second the mock Framework prints a `RUNNING` status update.
4. Open **DELETE /6gdali/experiment/stop/{experiment_id}**, enter `experiment-001`,
   then **Execute**. The mock Framework prints `COMPLETED`.

Also try invalid requests to see the error responses. For example, use an
`exp_id` starting with a capital letter, or remove a metadata key.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/6gdali/experiment/start` | Start an experiment |
| `DELETE` | `/6gdali/experiment/stop/{experiment_id}` | Stop an experiment |

Both replies only confirm the request was **accepted**. The experiment's progress
is reported later through status updates sent to `status_update_url`.

### Start request body

```json
{
  "exp_id": "experiment-001",
  "metadata": {
    "title": "Energy Saving Small Area Two Layers Sectorized AppOFF",
    "description": "RAN dataset generated through the EURECOM Digital Twin testbed",
    "keywords": ["Energy", "RAN", "Digital_Twin"],
    "frequency": "5",
    "unit": "seconds",
    "testbed_context": { "network_domain": "RAN" }
  },
  "status_update_url": "http://localhost:8003/6gdali/experiment/status",
  "config": { "...": "testbed-specific, defined by the testbed owner" }
}
```

| Field | Validated by the engine | Used for |
|-------|-------------------------|----------|
| `exp_id` | Required, not empty, **first character a lowercase letter `a`-`z`** | Identifies the experiment (also in the stop URL) |
| `metadata` | **Fixed keys**, all required, no extra keys: `title`, `description`, `keywords` (≥ 1), `frequency` (positive number **as a string**), `unit`, `testbed_context.network_domain` | Metadata generation only. **Not** used to run the experiment |
| `status_update_url` | Valid http(s) URL | Where experiment states are sent |
| `config` | Must match the testbed's `Configuration` model | Running the experiment |

Invalid requests are rejected **before** testbed code runs. `error.details` lists
every problem, each with its location (`loc`) and reason (`msg`), so the caller
can fix the whole body in one retry.

---

## What a testbed owner implements

| File | Item | What to do |
|------|------|------------|
| `models.py` | `class Configuration` | Declare the fields of `config` (keep `extra="forbid"`). As shipped it has no fields, so only `{}` is accepted. |
| `models.py` | `EXAMPLE_CONFIG` | A valid example `config`, shown in Swagger |
| `testbed.py` | `TESTBED_NAME` | Your testbed's name (Swagger title) |
| `testbed.py` | `_experiments` | Simulation only. Replace with your own experiment tracking. |
| `testbed.py` | `start_experiment(exp_id, config, status_update_url)` | Translate `config`, start the experiment, store `status_update_url` |
| `testbed.py` | `process_metadata(exp_id, metadata)` | Hand `metadata` to your metadata generation solution |
| `testbed.py` | `stop_experiment(exp_id)` | Stop the experiment on your testbed |

Every place to change is marked `TODO` in the code.

**Do not change:** endpoint paths, request and response models, response codes,
error types, state values, the experiment-ID rule, the `Metadata` model, the error
handlers, `translation_engine.py` or `utils.py`. The Framework relies on them
being identical on every testbed.

**The engine stores no experiment state.** Tracking experiments, including where
to send their status updates, is the testbed owner's responsibility.

---

## Sending experiment states

```python
from models import NewAdapterState
from utils import send_status_update

await send_status_update(exp_id, NewAdapterState.RUNNING, status_update_url)
```

| State | Meaning |
|-------|---------|
| `PENDING` | Accepted, not running yet |
| `RUNNING` | Running on the testbed |
| `COMPLETED` | Whole pipeline succeeded (final) |
| `FAILED` | Any step failed (final) |

> **Send `COMPLETED` only when ALL of these succeeded:**
> 1. the experiment ran successfully,
> 2. the dataset **and** its metadata were generated,
> 3. the files were uploaded by the **DS connector**.
>
> **Any failure in between is a failure: report `FAILED`.**

- Every started experiment ends with exactly one final state (`COMPLETED` or `FAILED`).
- `start_experiment()` and `stop_experiment()` must return within a few seconds.
  Run long work in the background (`asyncio.create_task(...)`) and send the state
  when it finishes.

---

## Returning errors

Raise `APIException` from `testbed.py`. The engine turns it into the standard
error response.

```python
from models import ErrorType, ResponseCode
from utils import APIException

raise APIException(
    503, ResponseCode.TESTBED_UNAVAILABLE,
    "The testbed is currently unavailable.",
    ErrorType.TESTBED_ERROR,
)
```

Do **not** use FastAPI's `HTTPException`, because it breaks the response format.
Do not invent new codes; put specifics in `details` instead.

### Response format (every endpoint, success or error)

```json
{
  "result": "error",
  "code": "INVALID_METADATA",
  "message": "Invalid metadata. Fix the fields listed in error.details.",
  "data": null,
  "error": {
    "type": "validation_error",
    "details": [{"loc": ["body", "metadata", "unit"], "msg": "Field required"}]
  },
  "timestamp": "2026-10-14T09:26:41.769000+00:00"
}
```

### Response codes

| Code | HTTP | Raised by | When |
|------|------|-----------|------|
| `EXPERIMENT_START_ACCEPTED` | 200 | Engine | Start accepted |
| `EXPERIMENT_STOP_ACCEPTED` | 200 | Engine | Stop accepted |
| `INVALID_EXPERIMENT_ID` | 400 | Engine | ID missing, empty or not starting with a-z |
| `INVALID_METADATA` | 400 | Engine | Metadata key missing, extra or invalid |
| `INVALID_CONFIGURATION` | 400 | Testbed | Valid `config` the testbed cannot run |
| `EXPERIMENT_NOT_FOUND` | 404 | Testbed | Stop for an unknown experiment |
| `ENDPOINT_NOT_FOUND` | 404 | Engine | Unknown URL |
| `METHOD_NOT_ALLOWED` | 405 | Engine | Wrong HTTP method |
| `EXPERIMENT_ALREADY_EXISTS` | 409 | Testbed | Start for an existing experiment |
| `INVALID_REQUEST` | 422 | Engine | Any other validation problem |
| `TESTBED_ERROR` | 500 | Testbed | Testbed failed or refused |
| `INTERNAL_ERROR` | 500 | Engine | Unexpected exception |
| `TESTBED_UNAVAILABLE` | 503 | Testbed | Testbed offline or unreachable |

---

## Dependencies

Python 3.9+, plus the packages in `requirements.txt`: FastAPI, Uvicorn, httpx
and Pydantic v2. Add any libraries your testbed integration needs to
`requirements.txt`.
