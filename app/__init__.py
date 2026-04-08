"""Module contents."""

def get_logger(name=__name__, log_level="DEBUG"):
    """Convenience function to set up a nice logger with the specified
    name and log level.
    """
    import logging

    logger = logging.getLogger(name)
    log_level = getattr(logging, log_level.upper())
    logger.setLevel(log_level)
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter(
        '{asctime}: {name:20} (L{lineno}): {levelname}: {message}',
        datefmt='%Y-%m-%d %H:%M:%S', style='{'))
    logger.addHandler(log_handler)
    logger.handlers = [log_handler]
    return logger
