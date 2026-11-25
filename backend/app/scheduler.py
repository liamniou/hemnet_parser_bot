import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.services import boundaries, images, notifications, scanner

log = logging.getLogger(__name__)


def _safe(fn, *args):
    def run():
        try:
            fn(*args)
        except Exception:
            log.exception("Job %s failed", fn.__name__)

    run.__name__ = run.__qualname__ = fn.__name__
    return run


def build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}
    )
    sched.add_job(
        _safe(scanner.run_due_scans),
        "interval",
        minutes=1,
        id="scans",
        next_run_time=datetime.now(),
    )
    sched.add_job(_safe(scanner.fetch_details), "interval", seconds=30, id="details")
    sched.add_job(_safe(scanner.check_removed), "interval", minutes=10, id="removed")
    sched.add_job(_safe(images.archive_pending), "interval", seconds=30, id="images")
    sched.add_job(_safe(notifications.dispatch_pending), "interval", seconds=15, id="notify")
    # Map outlines for every area, so borders show instantly. Cheap when all are cached.
    sched.add_job(
        _safe(boundaries.prefetch),
        "interval",
        hours=1,
        id="outlines",
        next_run_time=datetime.now() + timedelta(minutes=2),
    )
    return sched
