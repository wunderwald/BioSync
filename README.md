# BioSync
by [Moritz Wunderwald](mailto:code@moritzwunderwald.de), 2025-2026

Interactive visual toolbox for working with windowed cross-correlation, optimized for IBI and EDA data. Validate data, tune parameters, run batches and further analysis.

---

## Project Structure

```
BioSync/
├── app/              # Main application 
├── simulated_data/   # Jupyter notebook for generating test data
├── preprocessing/    # preprocessing utilities
└── materials/        # Reference papers and code
```

For a detailed breakdown of the application architecture, module responsibilities, and initialization order, see [app/README.md](app/README.md).

---

## Setup

The software is in the subdirectory `app/`. Install dependencies and run:

```bash
cd app
pip install -r requirements.txt
python app.py
```