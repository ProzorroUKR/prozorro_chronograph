
# Prozorro chronograph

## Install

1. Install requirements

```
virtualenv -p python3.8.2 venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Optional for running tests

Clone and config openprocurement.api
```
git clone git@github.com:ProzorroUKR/openprocurement.api.git src/opcr
cd src/opcr git checkout tags/2.6.35
cd -
cp etc/*.ini src/opcr/etc/
```

Setup
- ```docker-compose up api```
- ```pip install -e .```

Then you can run tests
```
pytest tests/
```

If you want config manually, don't forget set needed variables in ```tests/__init__.py```


## Config settings (env variables):

**Required**

- ```API_OPT_FIELDS``` - Fields to parse from feed (need for crawler)
- ```PUBLIC_API_HOST``` - API host on which chronograph will iterate by feed (need for crawler also)
- ```MONGODB_URL``` - String of connection to database (need for crawler also)

**Optional**
- ```CRAWLER_USER_AGENT``` - Set value of variable to all requests header `User-Agent`
- ```MONGODB_DATABASE``` - Name of database
- ```MONGODB_PLANS_COLLECTION``` - Name of collection where will be stored plans (everything connected with tenders)
- ```MONGODB_CONFIG_COLLECTION``` - Name collection for chronograph settings (weekends and max streams count)
- ```APSCHEDULER_DATABASE``` - Database where apscheduler stores tasks
- ```URL_SUFFIX``` - Suffix where could be passed get params for requests
- ```SANDBOX_MODE``` - If True set auctionPeriod::startDate as soon as possible (to current time with small gap)

**Doesn't set by env**
- ```ROUNDING, MIN_PAUSE, BIDDER_TIME, SERVICE_TIME``` - Used to speed up auctionPeriod in `SANDBOX_MODE`
- ```SMOOTHING_MIN, SMOOTHING_REMIN, SMOOTHING_MAX``` - Used to spread apscheduler intervals (not to run all tasks in one moment)
- ```INVALID_STATUSES``` - Statuses in which chronograph will ignore `next_check` and not set up future tasks
- ```STREAMS``` - number of streams for auction plans


## Database config

`config` collection init on start in function `init_database()`. 
Init 2 points: streams count and working days.

### Streams

Streams is number of auctions that could be started in parallel.
By default, set 300 streams for one day. If streams doesn't have free slots for 
current date, so chronograph plan auction on next day, and it repeats recursively,
while free slot wouldn't be found. Each stream has slots.
Slot is time, when one tender could start auction. Slot time set
from `WORKING_DAY_START` to `WORKING_DAY_END` each 30 minutes.

### Working days

Working days is setting by application start and pick them from lib standards
(git+git://github.com/ProzorroUKR/standards.git). On start up reads json and store
them in `config::working_days` collection. If `config::working_days` is not empty,
it takes existing data in collection and update it with data from standards 
(not delete old, but add new, that doesn't exist in).

## Workflow

Main idea of this service is to change tender's statuses and set date for start auction.
Service set tasks depending from tender's field `next_check` and set deferred tasks to apscheduler
that calls needed functions. Two key features are in functions `recheck_tender()` and `resync_tender()`.

**recheck_tender():**
Patch tender only with *tender_id* (on API side it triggers tender's status changing)

**resync_tender():**
Gets full tender, checks conditions and patch tender (or tender's lots) with `auctionPeriod::startDate`


## API

Chronograph has self API endpoints for some actions.

- GET `/resync/{tender_id}` - trigger resync manually
- GET `/recheck/{tender_id}` - trigger recheck manually
- GET `/jobs` - Returns list of all future jobs in apscheduler 
- GET `/calendar` - Returns working_days list
- POST `/calendar/{date}` - Add {date} to working_days list
- DELETE `/calendar/{date}` - Remove {date} to working_days list
