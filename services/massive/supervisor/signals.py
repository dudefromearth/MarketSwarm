import signal


def install_signal_handlers(logger, stop_cb):
    def handle(sig, frame):
        logger.warning(f"[SUPERVISOR] received signal {sig}", emoji="🛑")
        stop_cb()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)