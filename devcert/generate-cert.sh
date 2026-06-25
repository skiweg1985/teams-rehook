#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/devcert"
CONFIG_PATH="${ROOT_DIR}/haproxy/localhost-openssl.cnf"
KEY_PATH="${OUT_DIR}/localhost.key"
CRT_PATH="${OUT_DIR}/localhost.crt"
PEM_PATH="${OUT_DIR}/localhost.pem"

mkdir -p "${OUT_DIR}"

openssl req \
  -x509 \
  -nodes \
  -newkey rsa:4096 \
  -days 3650 \
  -sha256 \
  -keyout "${KEY_PATH}" \
  -out "${CRT_PATH}" \
  -config "${CONFIG_PATH}" \
  -extensions v3_req

cat "${KEY_PATH}" "${CRT_PATH}" > "${PEM_PATH}"

printf 'Wrote %s\n' "${PEM_PATH}"
