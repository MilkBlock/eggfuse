#!/bin/sh
set -eu
export PARTNER_INDEX_OUT="${HEAD_JOINT_OUT:-$ARTIFACT_ROOT/head-joint}"
mkdir -p "$PARTNER_INDEX_OUT/tmp"
export TMPDIR="$PARTNER_INDEX_OUT/tmp"
if [ "$#" -gt 0 ]; then exec sh partner_index_reproduce.sh "$@"; fi
sh partner_index_reproduce.sh head_joint_worlds.py prepare
sh partner_index_reproduce.sh head_joint_trials.py evaluate
sh partner_index_reproduce.sh head_joint_lures.py evaluate
sh partner_index_reproduce.sh head_joint_trials.py live
sh partner_index_reproduce.sh head_joint_trials.py cost
sh partner_index_reproduce.sh head_joint_egg.py live
