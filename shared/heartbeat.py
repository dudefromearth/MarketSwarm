# shared/heartbeat.py

import threading
import time
import json
import redis


def _build_redis_client(config):
    """
    Resolve Redis connection for heartbeat using Truth.json topology.
    Heartbeat ALWAYS uses system-redis.
    SetupBase projects buses into config["buses"].
    """
    try:
        url = config["buses"]["system-redis"]["url"]
    except KeyError as e:
        raise RuntimeError(
            "Heartbeat cannot start: config.buses['system-redis'].url not found"
        ) from e

    return redis.Redis.from_url(url)


def start_heartbeat(
    service_name,
    config,
    logger,
    payload_fn=None,
):
    """
    Threaded heartbeat publisher.
    Consumes *service-local* config projected by SetupBase.
    """
    stop_event = threading.Event()

    # Service-local heartbeat config (SetupBase projection)
    try:
        hb_cfg = config["heartbeat"]
        interval = hb_cfg["interval_sec"]
        ttl = hb_cfg["ttl_sec"]
    except KeyError as e:
        raise RuntimeError(
            "Heartbeat cannot start: config['heartbeat'] missing or malformed"
        ) from e

    key = f"{service_name}:heartbeat"

    redis_client = _build_redis_client(config)

    def run():
        logger.info(
            f"🔌 heartbeat thread started "
            f"(bus=system-redis, key={key}, interval={interval}s, ttl={ttl}s)"
        )

        while not stop_event.is_set():
            try:
                payload = (
                    payload_fn() if payload_fn else
                    {
                        "service": service_name,
                        "ts": time.time(),
                    }
                )

                redis_client.set(
                    key,
                    json.dumps(payload),
                    ex=ttl,
                )

            except Exception:
                logger.exception("heartbeat publish failed")

            stop_event.wait(interval)

        logger.info("🔌 heartbeat thread stopped")

    thread = threading.Thread(
        target=run,
        name=f"{service_name}-heartbeat",
        daemon=True,
    )
    thread.start()

    return stop_event