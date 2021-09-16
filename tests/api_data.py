import os
from copy import deepcopy
from datetime import timedelta, datetime
from pytz import timezone

SANDBOX_MODE = os.environ.get("SANDBOX_MODE", False)
TZ = timezone(os.environ["TZ"] if "TZ" in os.environ else "Europe/Kiev")
now = datetime.now(TZ)

test_identifier = {
    "scheme": "UA-EDR",
    "id": "00037256",
    "uri": "http://www.dus.gov.ua/",
    "legalName": "Державне управління справами",
}

test_organization = {
    "name": "Державне управління справами",
    "identifier": test_identifier,
    "address": {
        "countryName": "Україна",
        "postalCode": "01220",
        "region": "м. Київ",
        "locality": "м. Київ",
        "streetAddress": "вул. Банкова, 11, корпус 1",
    },
    "contactPoint": {"name": "Державне управління справами", "telephone": "+0440000000"},
    "scale": "micro",
}

test_author = test_organization.copy()
del test_author["scale"]

test_procuring_entity = test_author.copy()
test_procuring_entity["kind"] = "general"
test_milestones = [
    {
        "id": "a" * 32,
        "title": "signingTheContract",
        "code": "prepayment",
        "type": "financing",
        "duration": {"days": 2, "type": "banking"},
        "sequenceNumber": 0,
        "percentage": 45.55,
    },
    {
        "title": "deliveryOfGoods",
        "code": "postpayment",
        "type": "financing",
        "duration": {"days": 900, "type": "calendar"},
        "sequenceNumber": 0,
        "percentage": 54.45,
    },
]

test_item = {
    "description": "футляри до державних нагород",
    "classification": {"scheme": "ДК021", "id": "44617100-9", "description": "Cartons"},
    "additionalClassifications": [
        {"scheme": "ДКПП", "id": "17.21.1", "description": "папір і картон гофровані, паперова й картонна тара"}
    ],
    "unit": {"name": "item", "code": "4A"},
    "quantity": 5,
    "deliveryDate": {
        "startDate": (now + timedelta(days=2)).isoformat(),
        "endDate": (now + timedelta(days=5)).isoformat(),
    },
    "deliveryAddress": {
        "countryName": "Україна",
        "postalCode": "79000",
        "region": "м. Київ",
        "locality": "м. Київ",
        "streetAddress": "вул. Банкова 1",
    },
}

test_tender_data = {
    "title": "футляри до державних нагород",
    "mainProcurementCategory": "goods",
    "procuringEntity": test_procuring_entity,
    "value": {"amount": 500, "currency": "UAH"},
    "minimalStep": {"amount": 15, "currency": "UAH"},
    "items": [deepcopy(test_item)],
    "enquiryPeriod": {"endDate": (now + timedelta(days=9)).isoformat()},
    "tenderPeriod": {"endDate": (now + timedelta(days=18)).isoformat()},
    "procurementMethodType": "belowThreshold",
    "milestones": test_milestones,
}
if SANDBOX_MODE:
    test_tender_data["procurementMethodDetails"] = "quick, accelerator=1440"

test_bids = [
    {"tenderers": [test_organization], "value": {"amount": 469, "currency": "UAH", "valueAddedTaxIncluded": True}},
    {"tenderers": [test_organization], "value": {"amount": 479, "currency": "UAH", "valueAddedTaxIncluded": True}},
]
test_lots = [
    {
        "title": "lot title",
        "description": "lot description",
        "value": test_tender_data["value"],
        "minimalStep": test_tender_data["minimalStep"],
    }
]
test_features = [
    {
        "code": "code_item",
        "featureOf": "item",
        "relatedItem": "1",
        "title": "item feature",
        "enum": [{"value": 0.01, "title": "good"}, {"value": 0.02, "title": "best"}],
    },
    {
        "code": "code_tenderer",
        "featureOf": "tenderer",
        "title": "tenderer feature",
        "enum": [{"value": 0.01, "title": "good"}, {"value": 0.02, "title": "best"}],
    },
]