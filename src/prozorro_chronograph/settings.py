import os
from pytz import timezone
from datetime import time, timedelta
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler as Scheduler
from apscheduler.executors.asyncio import AsyncIOExecutor
from prozorro_crawler.settings import logger

MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://root:example@localhost:27017")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "prozorro-chronograph")
MONGODB_PLANS_COLLECTION = os.environ.get("MONGODB_COLLECTION", "plans")
MONGODB_CONFIG_COLLECTION = os.environ.get("MONGODB_CONFIG_COLLECTION", "config")
APSCHEDULER_DATABASE = os.environ.get("APSCHEDULER_DATABASE", "apscheduler")

PUBLIC_API_HOST = os.environ.get("PUBLIC_API_HOST", "https://lb-api-sandbox-2.prozorro.gov.ua")
API_VERSION = os.environ.get("API_VERSION", "2.5")
BASE_URL = f"{PUBLIC_API_HOST}/api/{API_VERSION}/tenders"
URL_SUFFIX = os.environ.get("CHRONOGRAPH_URL_SUFFIX", "")
API_TOKEN = os.environ.get("API_TOKEN", "chronograph")
CHRONOGRAPH_HOST = os.environ.get("CHRONOGRAPH_HOST", "http://localhost:8080")
SANDBOX_MODE = os.environ.get("SANDBOX_MODE", False)
TZ = timezone(os.environ["TZ"] if "TZ" in os.environ else "Europe/Kiev")
SENTRY_DSN = os.environ.get("SENTRY_DSN")

WORKING_DAY_START = time(11, 0)
WORKING_DAY_END = time(16, 0)
ROUNDING = timedelta(minutes=15)
MIN_PAUSE = timedelta(minutes=3)
BIDDER_TIME = timedelta(minutes=6)
SERVICE_TIME = timedelta(minutes=9)
SMOOTHING_MIN = 10
SMOOTHING_REMIN = 60
SMOOTHING_MAX = 300
INVALID_STATUSES = ("unsuccessful", "complete", "cancelled")
STREAMS = 300

LOGGER = logger

jobstores = {"default": MongoDBJobStore(database=APSCHEDULER_DATABASE, host=MONGODB_URL)}
executors = {"default": AsyncIOExecutor()}
scheduler = Scheduler(jobstores=jobstores, executors=executors, timezone=TZ)
