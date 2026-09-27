import logging
from apscheduler.schedulers.background import BackgroundScheduler
from database import init_db
from fetcher import fetch_all
from app import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def scheduled_fetch():
    log.info("Scheduled fetch triggered")
    fetch_all()


def main():
    init_db()
    log.info("Database initialized")

    fetch_all()

    scheduler.add_job(scheduled_fetch, "interval", hours=1, id="weather_fetch")
    scheduler.start()
    log.info("Scheduler started (interval: 1 hour)")

    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
