# BioSync
by [Moritz Wunderwald](mailto:code@moritzwunderwald.de), 2025-2026

[![DOI](https://zenodo.org/badge/917213362.svg)](https://doi.org/10.5281/zenodo.24318412)

Interactive visual toolbox for windowed cross-correlation analysis, optimized for IBI and EDA biosignal data. Load dyad recordings, tune parameters, inspect results, and export or batch-process datasets.

## Using BioSync

Detailed instruction on installation, running, building and updating BioSync are provided here: **[app/README.md](app/README.md)**.

## Citing BioSync

If you use BioSync in your research, please cite it:

>Wunderwald, M., Gordon, I., Tünte, M., & Höhl, S. (2026). BioSync (Version v1.0.1) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.24318412

That DOI always points to the latest version. To cite the exact version you used, pick it from the version list on the [Zenodo record](https://doi.org/10.5281/zenodo.24318412). GitHub's "Cite this repository" button gives APA and BibTeX formats.

---

## Project Structure

```
BioSync/
├── app/              # Main application 
├── simulated_data/   # Jupyter notebook generating dyadic IBI test data
└── preprocessing/    # preprocessing utilities
```