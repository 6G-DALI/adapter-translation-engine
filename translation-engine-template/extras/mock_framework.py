"""
OPTIONAL - a fake Framework that prints the status updates it receives.
Not needed to run the engine; useful to test status updates locally.

    python extras/mock_framework.py        # listens on port 9000

Then use "status_update_url": "http://localhost:9000/status" in the start request.
"""

from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()


@app.post("/{path:path}")
async def receive(path: str, request: Request):
    print("STATUS UPDATE:", await request.json(), flush=True)
    return {"received": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
