#!/usr/bin/env bash
set -euo pipefail

data_dir="/home/mfc/data"
env_file="$data_dir/.mfc-status-logger.env"

mkdir -p "$data_dir"

ts=$(date '+%d-%m-%Y_%H-%M-%S')
log_file="$data_dir/mfc_status_log_${ts}.csv"

printf 'MFC_STATUS_CSV=%s\nMFC_STATUS_PER_RUN_FILE=0\n' "$log_file" > "$env_file"

if [[ ! -s "$log_file" ]]; then
  echo "Timestamp UTC,Timestamp Local,MFC Id,Serial,Address,Gas,Setpoint,Flow,Raw Setpoint,Raw Flow,Calibration,MFC Id,Serial,Address,Gas,Setpoint,Flow,Raw Setpoint,Raw Flow,Calibration" > "$log_file"
fi

ln -sfn "$log_file" "$data_dir/latest.csv"
