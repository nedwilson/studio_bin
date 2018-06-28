#!/bin/bash

folder=$1

new_py_path="${IH_SHOW_ROOT}/../SHARED/lib/nuke/pipeline"

export PYTHONPATH=$PYTHONPATH:$new_py_path

pyplatform=`python -c 'import sys; print sys.platform'`

nuke_exe_path=`cat $IH_SHOW_CFG_PATH | grep Nuke | grep $pyplatform | awk -F= '{print $2}'`

nuke_dir=`dirname $nuke_exe_path`

python_bin="${nuke_dir}/python"

echo "Using python binary at ${python_bin}"

si_script="$(dirname "$0")/scan_ingest.py"

$python_bin $si_script $folder
