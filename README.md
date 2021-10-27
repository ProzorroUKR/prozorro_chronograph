
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


3. Config settings (env variables):

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

4. Workflow

Main idea of this service is to change tender's statuses and set date for start auction.
Service set tasks depending from tender's field `next_check` and set deferred tasks to apscheduler
that calls needed functions. Two key features are in functions `recheck_tender()` and `resync_tender()`.

**recheck_tender():**
Patch tender only with *tender_id* (on API side it triggers tender's status changing)

**resync_tender():**
Gets full tender, checks conditions and patch tender (or tender's lots) with `auctionPeriod::startDate`
