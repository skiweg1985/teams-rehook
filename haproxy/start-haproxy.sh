#!/bin/sh
set -eu

CERT_DIR=/certs
KEY_PATH="${CERT_DIR}/localhost.key"
CRT_PATH="${CERT_DIR}/localhost.crt"
PEM_PATH="${CERT_DIR}/localhost.pem"
CONFIG_PATH=/usr/local/etc/haproxy/localhost-openssl.cnf

mkdir -p "${CERT_DIR}"

if [ ! -f "${PEM_PATH}" ]; then
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
fi

exec haproxy -f /usr/local/etc/haproxy/haproxy.cfg
