#!/bin/sh
set -eu

CERT_DIR=/certs
KEY_PATH="${CERT_DIR}/localhost.key"
CRT_PATH="${CERT_DIR}/localhost.crt"
PEM_PATH="${CERT_DIR}/localhost.pem"
CONFIG_PATH=/usr/local/etc/haproxy/localhost-openssl.cnf
HAPROXY_TEMPLATE=/usr/local/etc/haproxy/haproxy.cfg
HAPROXY_RENDERED=/tmp/haproxy.cfg

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

trusted_proxy_acl() {
  if [ -z "${TRUSTED_PROXY_IPS:-}" ]; then
    printf '%s\n' "acl trusted_upstream_proxy src 127.255.255.255/32"
    return 0
  fi

  trusted_proxy_values=
  old_ifs=$IFS
  IFS=,
  for part in ${TRUSTED_PROXY_IPS}; do
    trimmed=$(printf '%s' "${part}" | awk '{ gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0); print }')
    [ -n "${trimmed}" ] || continue
    if [ -n "${trusted_proxy_values}" ]; then
      trusted_proxy_values="${trusted_proxy_values} ${trimmed}"
    else
      trusted_proxy_values="${trimmed}"
    fi
  done
  IFS=$old_ifs

  if [ -z "${trusted_proxy_values}" ]; then
    printf '%s\n' "acl trusted_upstream_proxy src 127.255.255.255/32"
    return 0
  fi

  printf 'acl trusted_upstream_proxy src %s\n' "${trusted_proxy_values}"
}

render_haproxy_config() {
  trusted_proxy_line=$(trusted_proxy_acl)
  awk -v trusted_proxy_line="${trusted_proxy_line}" '
    { gsub(/__TRUSTED_UPSTREAM_PROXY_ACL__/, trusted_proxy_line) }
    { print }
  ' "${HAPROXY_TEMPLATE}" > "${HAPROXY_RENDERED}"
}

render_haproxy_config
haproxy -c -f "${HAPROXY_RENDERED}"
exec haproxy -f "${HAPROXY_RENDERED}"
