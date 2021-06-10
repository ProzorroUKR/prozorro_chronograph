import os

os.environ["PUBLIC_API_HOST"] = "http://localhost:8000"
os.environ["APSCHEDULER_DATABASE"] = "apscheduler-tests"
os.environ["MONGODB_URL"] = "mongodb://root:example@localhost:27017"
os.environ["MONGODB_DATABASE"] = "prozorro-chronograph-test"
os.environ["API_TOKEN"] = "chronograph"
os.environ["COUCH_URL"] = "http://admin:admin@localhost:5984/"
