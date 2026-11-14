# Setup Mamba
cd ~/Downloads
wget "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
bash Miniforge3-Linux-x86_64.sh        # accept the defaults, say "yes" to init
exec $SHELL

# Setup Environment
mamba env create -f environment.lock.yml
mamba activate spaceapps

# Verify that GDAL can read HDF4
python -c "from osgeo import gdal; print(gdal.__version__, gdal.GetDriverByName('HDF4'))"

# Start development
mamba activate spaceapps
jupyter lab
