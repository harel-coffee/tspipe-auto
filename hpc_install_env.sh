#!/bin/bash
cd
module load python/3.8
virtualenv ~/featstore
source ~/featstore/bin/activate
pip install --no-index --upgrade pip
pip install --no-index pandas scipy scikit_learn matplotlib seaborn
pip install --no-index jupyterlab click h5py
pip install tsfresh

# create bash script for opening jupyter notebooks https://stackoverflow.com/a/4879146/9214620
cat << EOF >$VIRTUAL_ENV/bin/notebook.sh
#!/bin/bash
unset XDG_RUNTIME_DIR
jupyter-lab --ip \$(hostname -f) --no-browser
EOF

chmod u+x $VIRTUAL_ENV/bin/notebook.sh