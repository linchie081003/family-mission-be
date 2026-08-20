import json
import time
from pathlib import Path

_DEBUG_LOG = Path(__file__).resolve().parents[4] / "debug-b984bf.log"


def calendar_debug_log(*, location: str, message: str, data: dict, hypothesis_id: str = "CAL") -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "b984bf",
            "runId": "calendar-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # #endregion
