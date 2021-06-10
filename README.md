# Prozorro chronograph

## Install

1. Install requirements

```
virtualenv -p python3.8.2 venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Optional for running tests
```
git clone git@github.com:ProzorroUKR/openprocurement.api.git src/opcr
```
Change in src/opcr/requirements.txt
```
python-json-logger==2.0.1
```
to
```
python-json-logger==0.1.11
```
then run
```
pip install -e src/opcr
```

To run tests

- ```docker-compose up api``` in dev-env
- ```pip install -e .```
- Add this strings in end of file ```dev-env/api/etc/auth.ini```
```
[admins]
test = token
```
- Startup mongo on host and port as set in ```tests/__init__.py``` or config to yourself

Then you can run tests
```
pytest tests/
```
