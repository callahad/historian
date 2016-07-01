# Historian

Historian reports on your quarterly activity across GitHub, Bugzilla, and other
sources.

## Installation

```
git clone https://github.com/callahad/historian
cd historian
python3 -m venv ./venv
./venv/bin/pip3 install --upgrade pip
./venv/bin/pip3 install -r requirements.txt
```

## Running

1. Create a file called `config.ini`, using `config.ini.example` as a base.
2. `./venv/bin/python3 historian.py`
3. View output in the `out/` folder.
