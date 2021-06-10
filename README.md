
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
