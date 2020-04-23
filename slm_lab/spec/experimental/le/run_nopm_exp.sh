#!/usr/bin/env bash

# Run this file
# ./slm_lab/spec/experimental/le/run_nopm_exp.sh

#conda activate lab

python3 run_lab.py slm_lab/spec/experimental/le/ipd_nopm_rf.json ipd_rf_nopm_le_self_play train
python3 run_lab.py slm_lab/spec/experimental/le/ipd_nopm_rf.json ipd_rf_nopm_le_with_naive_coop train
python3 run_lab.py slm_lab/spec/experimental/le/ipd_nopm_rf.json ipd_rf_nopm_le_with_naive_opponent train

