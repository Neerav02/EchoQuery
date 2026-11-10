import json
import time
import logging
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque

from redis_lock import get_redis_client

logger = logging.getLogger("echoquery.events")

# In-memory stream buffer fallback for local testing without active Redis
_in_memory_streams: Dict[int, deque] = defaultdict(lambda: deque(maxlen=200))

def publish_job_event(job_id: int, event_type: str, data: Dict[str, Any]) -> str:
    """
    Publishes a real-time event to Redis Pub/Sub and appends to Redis Stream for reconnect catch-up.
    Differentiates event types:
    - 'TRANSCRIPT_SEGMENT': speech transcription segment
    - 'SUMMARY_DELTA': LLM summarization token delta
    - 'JOB_STATUS': state change (PROCESSING, COMPLETED, FAILED)
    """
    client = get_redis_client()
    timestamp = time.time()
    payload = {
        "event_type": event_type,
        "job_id": job_id,
        "timestamp": timestamp,
        "data": data
    }
    payload_str = json.dumps(payload)
    event_id = f"{int(timestamp * 1000)}-0"

    if client:
        try:
            # 1. Publish to Redis Pub/Sub channel for live active listeners
            client.publish(f"job_events:{job_id}", payload_str)
            
            # 2. Append to Redis Stream for durable reconnect replay
            event_id = client.xadd(
                f"job_stream:{job_id}",
                {"payload": payload_str},
                maxlen=500
            )
            return event_id
        except Exception as e:
            logger.warning(f"Redis event publishing failed for Job #{job_id}: {e}")

    # Fallback to local in-memory stream
    _in_memory_streams[job_id].append({"id": event_id, "payload": payload})
    return event_id

def fetch_stream_history(job_id: int, last_event_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Replays historical stream events since last_event_id for reconnect recovery.
    """
    client = get_redis_client()
    events = []

    if client:
        try:
            min_id = "(" + last_event_id if last_event_id and last_event_id != "0-0" else "-"
            raw_entries = client.xrange(f"job_stream:{job_id}", min=min_id, max="+")
            for entry_id, data in raw_entries:
                if "payload" in data:
                    parsed = json.loads(data["payload"])
                    parsed["event_id"] = entry_id
                    events.append(parsed)
            return events
        except Exception as e:
            logger.warning(f"Failed to query Redis Stream for Job #{job_id}: {e}")

    # Fallback to in-memory stream history
    history = _in_memory_streams[job_id]
    seen_last = False if last_event_id else True
    for item in history:
        if not seen_last:
            if item["id"] == last_event_id:
                seen_last = True
            continue
        ev = dict(item["payload"])
        ev["event_id"] = item["id"]
        events.append(ev)

    return events

