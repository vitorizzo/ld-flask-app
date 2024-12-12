#!/bin/bash
# Script per configurare il virtual environment e installare le librerie

echo "Creazione del virtual environment..."
python3 -m venv venv

echo "Attivazione del virtual environment..."
source venv/bin/activate

echo "Installazione delle dipendenze da requirements.txt..."
pip install -r requirements.txt

echo "Virtual environment configurato correttamente!"
