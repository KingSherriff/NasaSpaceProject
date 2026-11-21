# ---
# jupyter:
#   jupytext:
#     formats: notebooks//ipynb,scripts//py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.6
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Explore the pipeline
# All the code lives in the `analog_engine` package; this notebook only runs steps and looks at results.
# From a terminal the same thing is `python -m analog_engine [download planets base score frontend]`.

# %%
import sys
from pathlib import Path

ROOT = Path.cwd().resolve()
while not (ROOT / "analog_engine").is_dir():  # works from AnalogEngine/, notebooks/ or scripts/
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import pandas as pd

from analog_engine import filters, likeness, pipeline, plots, scoring, validation
from analog_engine.config import PROCESSED, RAW

# %% [markdown]
# ## Run steps (comment out what is already up to date)

# %%
pipeline.download()                  # raw data, skips files on disk
pipeline.run_planets()               # Moon / Mars terrain tables
pipeline.run_base()                  # Earth table + filters + likeness -> cells.parquet
pipeline.run_score()                 # applications -> cells_scored.parquet
pipeline.run_frontend()              # frontend_cells.json

# %% [markdown]
# ## Screening

# %%
cells = pd.read_parquet(PROCESSED / "cells.parquet")
display(filters.funnel(cells))
display(validation.check_screening(cells))
plots.screening_map(cells, validation.screening_sites()); plt.show()

# %% [markdown]
# ## Moon / Mars likeness

# %%
matches = pd.read_parquet(PROCESSED / "site_matches.parquet")
display(matches[matches["rank"] == 1].drop(columns=["rank", "site_cell_id"]
        + [c for c in matches if c.startswith("dz_")]).round(2))
for body in likeness.BODIES:
    print(f"Most {body}-like Earth cells:")
    display(cells.nlargest(5, f"{body}_like")[["cell_id", "lat", "lon", *likeness.TOPO_FEATURES, f"{body}_like"]].round(2))

# %% [markdown]
# ## Applications

# %%
scored = pd.read_parquet(PROCESSED / "cells_scored.parquet")
apps = [a.name for a in scoring.APPLICATIONS]
for app in scoring.APPLICATIONS:
    print(app.name)
    display(scoring.top(scored, app))
display(validation.check_applications(scored, apps))

# %%
plots.label_maps(scored, apps, validation.application_sites()); plt.show()
plots.quality_maps(scored, apps); plt.show()
