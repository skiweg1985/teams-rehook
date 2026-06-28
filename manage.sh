#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR="${SCRIPT_DIR}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"
ENV_EXAMPLE="${ENV_EXAMPLE:-${ROOT_DIR}/.env.example}"
BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups}"
COMPOSE="${COMPOSE:-docker compose}"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  COLOR_STEP=$(printf '\033[1;34m')
  COLOR_OK=$(printf '\033[1;32m')
  COLOR_WARN=$(printf '\033[1;33m')
  COLOR_ERR=$(printf '\033[1;31m')
  COLOR_MUTED=$(printf '\033[0;36m')
  COLOR_RESET=$(printf '\033[0m')
else
  COLOR_STEP=
  COLOR_OK=
  COLOR_WARN=
  COLOR_ERR=
  COLOR_MUTED=
  COLOR_RESET=
fi

step() {
  printf '\n%s==> %s%s\n' "${COLOR_STEP}" "$*" "${COLOR_RESET}"
}

ok() {
  printf '%s[OK]%s %s\n' "${COLOR_OK}" "${COLOR_RESET}" "$*"
}

warn() {
  printf '%s[WARN]%s %s\n' "${COLOR_WARN}" "${COLOR_RESET}" "$*" >&2
}

err() {
  printf '%s[ERR]%s %s\n' "${COLOR_ERR}" "${COLOR_RESET}" "$*" >&2
}

note() {
  printf '%s[INFO]%s %s\n' "${COLOR_MUTED}" "${COLOR_RESET}" "$*"
}

suggest() {
  printf '%s[HINT]%s %s\n' "${COLOR_MUTED}" "${COLOR_RESET}" "$*" >&2
}

die() {
  err "$*"
  exit 1
}

die_with_hint() {
  err "$1"
  suggest "$2"
  exit 1
}

timestamp() {
  date +%Y%m%d-%H%M%S
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

command_hint() {
  case "$1" in
    docker) printf '%s' "Install/start Docker and rerun ./manage.sh doctor." ;;
    git) printf '%s' "Install Git and rerun the command." ;;
    curl) printf '%s' "Install curl or open the printed URL manually." ;;
    openssl) printf '%s' "Install OpenSSL or ensure shasum is available." ;;
    *) printf 'Install %s and rerun the command.' "$1" ;;
  esac
}

require_command() {
  command_exists "$1" || die_with_hint "$1 is required for this command." "$(command_hint "$1")"
}

run_compose() {
  # shellcheck disable=SC2086
  (cd "${ROOT_DIR}" && $COMPOSE "$@")
}

docker_daemon_available() {
  command_exists docker && docker info >/dev/null 2>&1
}

compose_available() {
  command_exists docker && run_compose version >/dev/null 2>&1
}

stack_is_running() {
  if ! command_exists docker; then
    return 1
  fi
  stack_running_ids=$(run_compose ps --status running -q 2>/dev/null || true)
  [ -n "${stack_running_ids}" ]
}

ensure_env() {
  [ -f "${ENV_FILE}" ] || die_with_hint ".env not found." "Run ./manage.sh setup first."
}

ensure_no_extra_args() {
  [ "$#" -eq 0 ] || die_with_hint "Unexpected argument: $1" "Run ./manage.sh help for the supported command syntax."
}

is_interactive() {
  [ -t 0 ]
}

trim_trailing_slash() {
  printf '%s' "${1%/}"
}

require_hostname() {
  case "$1" in
    ""|*/*|*:*|*[\ \	]*)
      die_with_hint "Host name must not contain a scheme, port, path, or spaces." "Example: app.example.com"
      ;;
    -*|*.|*..*|*.-*|*-.*)
      die_with_hint "Host name is not valid." "Example: app.example.com"
      ;;
    *[!A-Za-z0-9.-]*)
      die_with_hint "Host name may only use letters, numbers, dots, and hyphens." "Example: app.example.com"
      ;;
    *)
      ;;
  esac
}

hostname_from_url() {
  existing_url=$1
  if [ -z "${existing_url}" ]; then
    return 0
  fi

  printf '%s' "${existing_url}" | awk '
    {
      url=$0
      sub(/^[A-Za-z][A-Za-z0-9+.-]*:\/\//, "", url)
      sub(/\/.*$/, "", url)
      sub(/:[0-9]+$/, "", url)
      print url
    }
  '
}

port_from_url() {
  existing_url=$1
  if [ -z "${existing_url}" ]; then
    return 0
  fi

  printf '%s' "${existing_url}" | awk '
    {
      url=$0
      sub(/^[A-Za-z][A-Za-z0-9+.-]*:\/\//, "", url)
      sub(/\/.*$/, "", url)
      if (match(url, /:[0-9]+$/)) {
        print substr(url, RSTART + 1)
      }
    }
  '
}

scheme_from_url() {
  existing_url=$1
  if [ -z "${existing_url}" ]; then
    return 0
  fi

  printf '%s' "${existing_url}" | awk '
    {
      url=$0
      if (match(url, /^[A-Za-z][A-Za-z0-9+.-]*:\/\//)) {
        scheme=substr(url, 1, RLENGTH)
        sub(/:\/\//, "", scheme)
        print scheme
      }
    }
  '
}

require_scheme() {
  case "$1" in
    http|https) ;;
    *)
      die_with_hint "Publish scheme must be http or https." "Choose either http or https."
      ;;
  esac
}

require_optional_port() {
  value=$1
  [ -z "${value}" ] && return 0
  require_positive_port "${value}"
}

public_port_prompt_default() {
  existing_public_port=$1

  if [ -n "${existing_public_port}" ]; then
    printf '%s' "${existing_public_port}"
    return 0
  fi

  printf '%s' ""
}

build_app_url() {
  scheme=$1
  host=$2
  port=${3:-}

  if [ -z "${port}" ]; then
    printf '%s://%s' "${scheme}" "${host}"
    return 0
  fi

  case "${scheme}:${port}" in
    http:80|https:443) printf '%s://%s' "${scheme}" "${host}" ;;
    *) printf '%s://%s:%s' "${scheme}" "${host}" "${port}" ;;
  esac
}

backup_env() {
  ensure_env
  backup="${ENV_FILE}.backup-$(timestamp)"
  cp "${ENV_FILE}" "${backup}"
  ok "Backed up .env to ${backup}"
}

active_keys() {
  [ -f "$1" ] || return 0
  awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/ {
      line=$0
      sub(/^[[:space:]]*/, "", line)
      split(line, parts, "=")
      print parts[1]
    }
  ' "$1"
}

env_value() {
  key=$1
  file=$2
  awk -v key="${key}" '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    {
      line=$0
      sub(/^[[:space:]]*/, "", line)
      if (index(line, key "=") == 1) {
        sub("^[^=]*=", "", line)
        print line
        found=1
        exit
      }
    }
    END { if (!found) exit 1 }
  ' "${file}" 2>/dev/null || true
}

set_env_value() {
  key=$1
  value=$2
  file=$3
  tmp="${file}.tmp-$$"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { done=0 }
    /^[[:space:]]*#/ { print; next }
    /^[[:space:]]*$/ { print; next }
    {
      line=$0
      trimmed=line
      sub(/^[[:space:]]*/, "", trimmed)
      if (index(trimmed, key "=") == 1) {
        print key "=" value
        done=1
      } else {
        print
      }
    }
    END {
      if (!done) print key "=" value
    }
  ' "${file}" > "${tmp}"
  mv "${tmp}" "${file}"
}

confirm_or_abort() {
  prompt=$1
  assume_yes=$2
  non_interactive=$3

  if [ "${assume_yes}" = true ]; then
    note "${prompt} -> yes"
    return 0
  fi
  if [ "${non_interactive}" = true ] || ! is_interactive; then
    die_with_hint "Confirmation required for this action." "Rerun with --yes to accept the prompt automatically."
  fi

  printf '%s [y/N] ' "${prompt}"
  IFS= read -r answer
  case "${answer}" in
    y|Y|yes|YES) return 0 ;;
    *) die "Aborted." ;;
  esac
}

confirm_default_yes() {
  prompt=$1
  assume_yes=$2
  non_interactive=$3

  if [ "${assume_yes}" = true ] || [ "${non_interactive}" = true ] || ! is_interactive; then
    note "${prompt} -> yes"
    return 0
  fi

  printf '%s [Y/n] ' "${prompt}"
  IFS= read -r answer
  case "${answer}" in
    ""|y|Y|yes|YES) return 0 ;;
    n|N|no|NO) return 1 ;;
    *) die "Aborted." ;;
  esac
}

confirm_keyword_or_abort() {
  keyword=$1
  message=$2
  assume_yes=$3
  non_interactive=$4

  if [ "${assume_yes}" = true ]; then
    note "${message} -> ${keyword}"
    return 0
  fi
  if [ "${non_interactive}" = true ] || ! is_interactive; then
    die_with_hint "Typed confirmation required for this action." "Rerun with --yes to confirm non-interactively."
  fi

  printf '%s Type %s to continue: ' "${message}" "${keyword}"
  IFS= read -r answer
  [ "${answer}" = "${keyword}" ] || die "Confirmation did not match ${keyword}."
}

prompt_value() {
  prompt=$1
  default_value=${2:-}
  non_interactive=$3

  if [ "${non_interactive}" = true ] || ! is_interactive; then
    printf '%s' "${default_value}"
    return 0
  fi

  if [ -n "${default_value}" ]; then
    printf '%s [%s] ' "${prompt}" "${default_value}" >&2
  else
    printf '%s ' "${prompt}" >&2
  fi
  IFS= read -r answer
  if [ -n "${answer}" ]; then
    printf '%s' "${answer}"
  else
    printf '%s' "${default_value}"
  fi
}

prompt_required_value() {
  prompt=$1
  default_value=${2:-}
  non_interactive=$3

  required_value=$(prompt_value "${prompt}" "${default_value}" "${non_interactive}")
  if [ -n "${required_value}" ]; then
    printf '%s' "${required_value}"
    return 0
  fi
  die_with_hint "${prompt} is required." "Rerun interactively or provide a profile with defaults."
}

require_positive_port() {
  value=$1
  case "${value}" in
    ''|*[!0-9]*) die_with_hint "Port must be a number." "Use a value between 1 and 65535." ;;
  esac
  if [ "${value}" -lt 1 ] || [ "${value}" -gt 65535 ]; then
    die_with_hint "Port must be between 1 and 65535." "Choose a free TCP port in that range."
  fi
}

write_minimal_env() {
  http_port=$1
  https_port=$2
  app_url=$3
  postgres_password=$4
  secure_cookie=$5
  compose_subnet=$6
  trusted_proxy_ips=$7
  tmp="${ENV_FILE}.tmp-$$"
  cat > "${tmp}" <<EOF
# Proxy listener ports (host -> HAProxy container 80/443)
PROXY_HTTP_PORT=${http_port}
PROXY_HTTPS_PORT=${https_port}
COMPOSE_APP_SUBNET=${compose_subnet}

# Public app URLs exposed by the proxy / load balancer
APP_PUBLIC_BASE_URL=${app_url}
FRONTEND_BASE_URL=${app_url}
CORS_ORIGINS=${app_url}

# Database
POSTGRES_DB=app
POSTGRES_USER=app
POSTGRES_PASSWORD=${postgres_password}

# Teams delivery
BOT_DELIVERY_MODE=real

# Additional trusted upstream reverse proxies
TRUSTED_PROXY_IPS=${trusted_proxy_ips}

# Session cookies
SESSION_SECURE_COOKIE=${secure_cookie}
EOF
  mv "${tmp}" "${ENV_FILE}"
}

normalize_profile() {
  case "$1" in
    local|default|1) printf '%s' "local" ;;
    production|reverse|reverse-proxy|2) printf '%s' "production" ;;
    custom|3) printf '%s' "custom" ;;
    *)
      die_with_hint "Unknown setup profile: $1" "Use local, production, or custom."
      ;;
  esac
}

choose_setup_profile() {
  non_interactive=$1
  if [ "${non_interactive}" = true ] || ! is_interactive; then
    printf '%s' "local"
    return 0
  fi

  printf '%s\n' "Choose a setup profile:" >&2
  printf '  1) local/default       HTTPS on localhost, ports 8080/8443, random DB password\n' >&2
  printf '  2) production/reverse  Listener ports, publish scheme, public DNS name, optional public port\n' >&2
  printf '  3) custom              Adjust listener ports, publish scheme, public DNS name, and public port\n' >&2
  profile_choice=$(prompt_value "Profile" "1" false)
  normalize_profile "${profile_choice}"
}

print_setup_summary() {
  profile=$1
  http_port=$2
  https_port=$3
  app_url=$4
  secure_cookie=$5
  using_random_postgres_password=$6
  compose_subnet=$7
  trusted_proxy_ips=$8

  step "Configuration summary"
  printf '  Profile:            %s\n' "${profile}"
  printf '  HTTP listener:      %s\n' "${http_port}"
  printf '  HTTPS listener:     %s\n' "${https_port}"
  printf '  Public URL:         %s\n' "${app_url}"
  printf '  Compose subnet:     %s\n' "${compose_subnet}"
  if [ -n "${trusted_proxy_ips}" ]; then
    printf '  Trusted proxies:    %s\n' "${trusted_proxy_ips}"
  else
    printf '  Trusted proxies:    %s\n' "(none)"
  fi
  printf '  Secure cookies:     %s\n' "${secure_cookie}"
  if [ "${using_random_postgres_password}" = true ]; then
    printf '  Postgres password:  generated and stored in .env\n'
  else
    printf '  Postgres password:  fixed local default\n'
  fi
}

setup_env() {
  setup_assume_yes=false
  setup_non_interactive=false
  setup_profile=

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --yes|-y) setup_assume_yes=true ;;
      --non-interactive) setup_non_interactive=true ;;
      --profile)
        shift || die_with_hint "--profile requires a value." "Use local, production, or custom."
        setup_profile=$1
        ;;
      --profile=*) setup_profile=${1#*=} ;;
      --help|-h) usage_command setup; return 0 ;;
      *)
        die_with_hint "Unknown option for setup: $1" "Run ./manage.sh help setup."
        ;;
    esac
    shift
  done

  if [ -n "${setup_profile}" ]; then
    setup_profile=$(normalize_profile "${setup_profile}")
  else
    setup_profile=$(choose_setup_profile "${setup_non_interactive}")
  fi

  if [ "${setup_non_interactive}" = true ] && [ "${setup_profile}" = "custom" ]; then
    die_with_hint "Custom profile needs interactive input." "Use local/production or rerun without --non-interactive."
  fi

  if [ -f "${ENV_FILE}" ]; then
    confirm_or_abort "Replace existing .env with a fresh guided configuration?" "${setup_assume_yes}" "${setup_non_interactive}"
    backup_env
  fi

  step "Preparing ${setup_profile} profile"

  http_port=8080
  https_port=8443
  secure_cookie=true
  app_url="https://localhost:8443"
  using_random_postgres_password=true
  postgres_password=$(generate_password)
  compose_subnet=$(env_value COMPOSE_APP_SUBNET "${ENV_FILE}")
  [ -n "${compose_subnet}" ] || compose_subnet="172.30.0.0/24"
  trusted_proxy_ips=$(env_value TRUSTED_PROXY_IPS "${ENV_FILE}")

  case "${setup_profile}" in
    local)
      note "Using the recommended local defaults."
      ;;
    production)
      http_port=$(prompt_value "HTTP listener port" "80" "${setup_non_interactive}")
      https_port=$(prompt_value "HTTPS listener port" "443" "${setup_non_interactive}")
      require_positive_port "${http_port}"
      require_positive_port "${https_port}"
      existing_public_url=$(env_value APP_PUBLIC_BASE_URL "${ENV_FILE}")
      existing_public_scheme=$(scheme_from_url "${existing_public_url}")
      existing_public_host=$(hostname_from_url "${existing_public_url}")
      existing_public_port=$(port_from_url "${existing_public_url}")
      if [ -z "${existing_public_scheme}" ]; then
        existing_public_scheme="https"
      fi
      public_scheme=$(prompt_required_value "Publish scheme (http/https)" "${existing_public_scheme}" "${setup_non_interactive}")
      require_scheme "${public_scheme}"
      app_host=$(prompt_required_value "App Public DNS Name" "${existing_public_host}" "${setup_non_interactive}")
      require_hostname "${app_host}"
      public_port_default=$(public_port_prompt_default "${existing_public_port}")
      if [ "${public_scheme}" = "https" ]; then
        public_port=$(prompt_value "Public HTTPS URL Port (empty = default 443)" "${public_port_default}" "${setup_non_interactive}")
        secure_cookie=true
      else
        public_port=$(prompt_value "Public HTTP URL Port (empty = default 80)" "${public_port_default}" "${setup_non_interactive}")
        secure_cookie=false
      fi
      require_optional_port "${public_port}"
      app_url=$(build_app_url "${public_scheme}" "${app_host}" "${public_port}")
      trusted_proxy_ips=$(prompt_value "Trusted upstream proxy IPs or CIDRs (comma-separated, empty = none)" "${trusted_proxy_ips}" "${setup_non_interactive}")
      if ! confirm_default_yes "Generate a random bundled Postgres password?" "${setup_assume_yes}" "${setup_non_interactive}"; then
        postgres_password=app
        using_random_postgres_password=false
      fi
      ;;
    custom)
      http_port=$(prompt_value "HTTP listener port" "8080" "${setup_non_interactive}")
      https_port=$(prompt_value "HTTPS listener port" "8443" "${setup_non_interactive}")
      require_positive_port "${http_port}"
      require_positive_port "${https_port}"
      existing_public_url=$(env_value APP_PUBLIC_BASE_URL "${ENV_FILE}")
      existing_public_scheme=$(scheme_from_url "${existing_public_url}")
      existing_public_host=$(hostname_from_url "${existing_public_url}")
      existing_public_port=$(port_from_url "${existing_public_url}")
      if [ -z "${existing_public_scheme}" ]; then
        existing_public_scheme="https"
      fi
      if [ -z "${existing_public_host}" ]; then
        existing_public_host="localhost"
      fi
      public_scheme=$(prompt_required_value "Publish scheme (http/https)" "${existing_public_scheme}" "${setup_non_interactive}")
      require_scheme "${public_scheme}"
      app_host=$(prompt_required_value "App Public DNS Name" "${existing_public_host}" "${setup_non_interactive}")
      require_hostname "${app_host}"
      public_port_default=$(public_port_prompt_default "${existing_public_port}")
      if [ "${public_scheme}" = "https" ]; then
        public_port=$(prompt_value "Public HTTPS URL Port (empty = default 443)" "${public_port_default}" "${setup_non_interactive}")
        secure_cookie=true
      else
        public_port=$(prompt_value "Public HTTP URL Port (empty = default 80)" "${public_port_default}" "${setup_non_interactive}")
        secure_cookie=false
      fi
      require_optional_port "${public_port}"
      app_url=$(build_app_url "${public_scheme}" "${app_host}" "${public_port}")
      trusted_proxy_ips=$(prompt_value "Trusted upstream proxy IPs or CIDRs (comma-separated, empty = none)" "${trusted_proxy_ips}" "${setup_non_interactive}")
      if ! confirm_default_yes "Generate a random bundled Postgres password?" "${setup_assume_yes}" "${setup_non_interactive}"; then
        postgres_password=app
        using_random_postgres_password=false
      fi
      ;;
  esac

  print_setup_summary "${setup_profile}" "${http_port}" "${https_port}" "${app_url}" "${secure_cookie}" "${using_random_postgres_password}" "${compose_subnet}" "${trusted_proxy_ips}"
  write_minimal_env "${http_port}" "${https_port}" "${app_url}" "${postgres_password}" "${secure_cookie}" "${compose_subnet}" "${trusted_proxy_ips}"
  ok "Wrote guided .env configuration."
  if [ "${using_random_postgres_password}" = true ]; then
    note "A random bundled Postgres password was stored in .env."
  fi

  step "Next URLs"
  print_urls
  note "Open the UI, create the first admin, then configure Microsoft identity in Settings."

  if stack_is_running; then
    ok "Stack is already running."
    return 0
  fi

  if confirm_default_yes "Start the stack now?" "${setup_assume_yes}" "${setup_non_interactive}"; then
    run_start_compose
  else
    suggest "Run ./manage.sh start when you are ready."
  fi
}

init_env() {
  ensure_no_extra_args "$@"
  [ -f "${ENV_EXAMPLE}" ] || die_with_hint ".env.example not found." "Restore .env.example or set ENV_EXAMPLE to the template path."
  if [ -f "${ENV_FILE}" ]; then
    note ".env already exists; leaving it unchanged."
    return 0
  fi
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  ok "Created .env from .env.example."
}

warn_if_value() {
  key=$1
  bad=$2
  message=$3
  value=$(env_value "${key}" "${ENV_FILE}")
  if [ "${value}" = "${bad}" ]; then
    warn "${message}"
  fi
}

warn_if_empty() {
  key=$1
  message=$2
  value=$(env_value "${key}" "${ENV_FILE}")
  if [ -z "${value}" ]; then
    warn "${message}"
  fi
}

warn_unsafe_defaults() {
  warn_if_value POSTGRES_USER app "POSTGRES_USER is the local default; use a deployment-specific user outside local/dev."
  warn_if_value POSTGRES_PASSWORD app "POSTGRES_PASSWORD is the local default; change it before production use."
  warn_if_empty SETTINGS_ENC_KEY "SETTINGS_ENC_KEY is empty; production should set a stable secret."
  warn_if_empty MONITORING_API_KEY "MONITORING_API_KEY is empty; the monitoring endpoint will return 503."
  if [ "$(env_value SESSION_SECURE_COOKIE "${ENV_FILE}")" = "false" ]; then
    warn "SESSION_SECURE_COOKIE=false; set it to true behind HTTPS."
  fi
}

check_env_core() {
  ensure_env
  env_missing=0

  if [ ! -f "${ENV_EXAMPLE}" ]; then
    warn ".env.example not found; skipping key comparison."
  else
    for key in $(active_keys "${ENV_EXAMPLE}"); do
      if ! active_keys "${ENV_FILE}" | grep -qx "${key}"; then
        err "Missing key in .env: ${key}"
        env_missing=1
      fi
    done
  fi

  warn_unsafe_defaults

  if [ "${env_missing}" -eq 0 ]; then
    ok ".env contains every active key from .env.example."
    return 0
  fi
  return 1
}

check_env() {
  ensure_no_extra_args "$@"
  check_env_core
}

sync_env() {
  ensure_no_extra_args "$@"
  ensure_env
  sync_added=0
  sync_tmp_missing=$(mktemp)
  trap 'rm -f "${sync_tmp_missing}"' EXIT HUP INT TERM

  for key in $(active_keys "${ENV_EXAMPLE}"); do
    if ! active_keys "${ENV_FILE}" | grep -qx "${key}"; then
      value=$(env_value "${key}" "${ENV_EXAMPLE}")
      printf '%s=%s\n' "${key}" "${value}" >> "${sync_tmp_missing}"
      sync_added=$((sync_added + 1))
    fi
  done

  if [ "${sync_added}" -eq 0 ]; then
    ok ".env already has every active key from .env.example."
    rm -f "${sync_tmp_missing}"
    trap - EXIT HUP INT TERM
    return 0
  fi

  backup_env
  {
    printf '\n# Added by ./manage.sh on %s\n' "$(timestamp)"
    cat "${sync_tmp_missing}"
  } >> "${ENV_FILE}"
  rm -f "${sync_tmp_missing}"
  trap - EXIT HUP INT TERM
  ok "Added ${sync_added} missing key(s) to .env."
}

run_start_compose() {
  require_command docker
  step "Starting Compose stack"
  if ! docker_daemon_available; then
    die_with_hint "Docker is installed but the daemon is not reachable." "Start Docker Desktop or your Docker service, then rerun ./manage.sh start."
  fi
  run_compose up -d --build
  ok "Compose stack is starting."
}

maybe_start_stack() {
  ensure_env
  if stack_is_running; then
    ok "Stack is already running."
    print_urls
    return 0
  fi
  run_start_compose
}

start_stack() {
  start_setup_args=

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --yes|-y|--non-interactive|--profile|--profile=*|--help|-h)
        if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
          usage_command start
          return 0
        fi
        if [ "$1" = "--profile" ]; then
          [ "$#" -ge 2 ] || die_with_hint "--profile requires a value." "Use local, production, or custom."
          start_setup_args="${start_setup_args} $1 $2"
          shift 2
          continue
        fi
        start_setup_args="${start_setup_args} $1"
        ;;
      *)
        die_with_hint "Unknown option for start: $1" "Run ./manage.sh help start."
        ;;
    esac
    shift
  done

  if [ ! -f "${ENV_FILE}" ]; then
    note ".env not found; running guided setup first."
    # shellcheck disable=SC2086
    setup_env ${start_setup_args}
    return 0
  fi
  maybe_start_stack
}

stop_stack() {
  ensure_no_extra_args "$@"
  require_command docker
  step "Stopping Compose stack"
  run_compose down
  ok "Compose stack stopped."
}

restart_stack() {
  ensure_no_extra_args "$@"
  ensure_env
  require_command docker
  step "Recreating Compose services"
  if ! docker_daemon_available; then
    die_with_hint "Docker is installed but the daemon is not reachable." "Start Docker Desktop or your Docker service, then rerun ./manage.sh restart."
  fi
  run_compose up -d --build --force-recreate
  ok "Compose services recreated with the current .env values."
}

status_stack() {
  ensure_no_extra_args "$@"
  require_command docker
  step "Compose service status"
  run_compose ps
}

logs_stack() {
  require_command docker
  if [ "$#" -gt 1 ]; then
    die_with_hint "logs accepts at most one optional service name." "Example: ./manage.sh logs backend"
  fi
  step "Following Compose logs"
  if [ "$#" -gt 0 ]; then
    run_compose logs -f "$1"
  else
    run_compose logs -f
  fi
}

update_stack() {
  ensure_no_extra_args "$@"
  ensure_env
  require_command git
  require_command docker
  step "Updating repository"
  (cd "${ROOT_DIR}" && git pull --ff-only)
  step "Rebuilding services"
  run_compose build
  run_compose up -d
  ok "Repository updated and services refreshed."
}

base_url() {
  value=$(env_value APP_PUBLIC_BASE_URL "${ENV_FILE}")
  [ -n "${value}" ] || value="http://localhost:8080"
  trim_trailing_slash "${value}"
}

doctor_record() {
  doctor_total=$((doctor_total + 1))
  case "$1" in
    ok) doctor_ok=$((doctor_ok + 1)); ok "$2" ;;
    warn) doctor_warn=$((doctor_warn + 1)); warn "$2" ;;
    err) doctor_fail=$((doctor_fail + 1)); err "$2" ;;
  esac
}

readyz_check_mode() {
  readyz_url=$1
  if curl -fsS --max-time 5 "${readyz_url}" >/dev/null 2>&1; then
    printf '%s' "verified"
    return 0
  fi
  case "${readyz_url}" in
    https://localhost:*|https://127.0.0.1:*|https://[::1]:*)
      if curl -kfsS --max-time 5 "${readyz_url}" >/dev/null 2>&1; then
        printf '%s' "insecure-local"
        return 0
      fi
      ;;
  esac
  return 1
}

doctor() {
  if [ "$#" -gt 0 ]; then
    case "$1" in
      --help|-h) usage_command doctor; return 0 ;;
      *) die_with_hint "Unknown option for doctor: $1" "Run ./manage.sh help doctor." ;;
    esac
  fi

  step "Running diagnostics"
  doctor_total=0
  doctor_ok=0
  doctor_warn=0
  doctor_fail=0

  if command_exists docker; then
    doctor_record ok "Docker CLI is available."
    if docker_daemon_available; then
      doctor_record ok "Docker daemon is reachable."
    else
      doctor_record err "Docker daemon is not reachable."
    fi
  else
    doctor_record err "Docker CLI is not installed."
  fi

  if compose_available; then
    doctor_record ok "Compose is available."
  else
    doctor_record err "Compose could not be executed via '${COMPOSE}'."
  fi

  if [ -f "${ENV_FILE}" ]; then
    if check_env_core >/dev/null 2>&1; then
      doctor_record ok ".env is present and has the expected active keys."
    else
      doctor_record warn ".env is present but needs attention; run ./manage.sh check-env."
    fi
  else
    doctor_record err ".env is missing."
  fi

  if compose_available && [ -f "${ENV_FILE}" ]; then
    doctor_services=$(run_compose ps --services 2>/dev/null || true)
    doctor_running_services=$(run_compose ps --status running --services 2>/dev/null || true)
    doctor_service_count=$(printf '%s\n' "${doctor_services}" | awk 'NF { count++ } END { print count + 0 }')
    doctor_running_count=$(printf '%s\n' "${doctor_running_services}" | awk 'NF { count++ } END { print count + 0 }')

    if [ "${doctor_service_count}" -eq 0 ]; then
      doctor_record warn "No Compose services are defined or reachable for this project."
    elif [ "${doctor_running_count}" -eq 0 ]; then
      doctor_record warn "Compose services are defined, but none are running."
    elif [ "${doctor_running_count}" -lt "${doctor_service_count}" ]; then
      doctor_record warn "${doctor_running_count}/${doctor_service_count} Compose services are running."
    else
      doctor_record ok "All ${doctor_service_count} Compose services are running."
    fi
  fi

  if [ -f "${ENV_FILE}" ]; then
    doctor_url=$(base_url)/api/v1/readyz
    if command_exists curl; then
      doctor_readyz_mode=$(readyz_check_mode "${doctor_url}" || true)
      if [ "${doctor_readyz_mode}" = "verified" ]; then
        doctor_record ok "Backend readiness endpoint is healthy (${doctor_url})."
      elif [ "${doctor_readyz_mode}" = "insecure-local" ]; then
        doctor_record warn "Backend readiness endpoint is healthy, but the local HTTPS certificate is not trusted by curl (${doctor_url})."
      else
        doctor_record err "Backend readiness endpoint did not respond successfully (${doctor_url})."
      fi
    else
      doctor_record warn "curl is not installed; skipping readiness probe."
    fi
  fi

  step "Doctor summary"
  printf '  Checks:   %s\n' "${doctor_total}"
  printf '  Passed:   %s\n' "${doctor_ok}"
  printf '  Warnings: %s\n' "${doctor_warn}"
  printf '  Failed:   %s\n' "${doctor_fail}"

  if [ "${doctor_fail}" -gt 0 ]; then
    suggest "Run ./manage.sh status and ./manage.sh logs backend for the failing services."
    return 1
  fi
  if [ "${doctor_warn}" -gt 0 ]; then
    suggest "Run ./manage.sh check-env to review environment warnings."
  fi
}

postgres_env() {
  key=$1
  value=$(env_value "${key}" "${ENV_FILE}")
  [ -n "${value}" ] || value=$2
  printf '%s' "${value}"
}

backup_db() {
  ensure_no_extra_args "$@"
  ensure_env
  require_command docker
  mkdir -p "${BACKUP_DIR}"
  db=$(postgres_env POSTGRES_DB app)
  user=$(postgres_env POSTGRES_USER app)
  out="${BACKUP_DIR}/teams-rehook-$(timestamp).sql"
  step "Creating database backup"
  run_compose exec -T postgres pg_dump -U "${user}" -d "${db}" > "${out}"
  ok "Wrote ${out}"
}

restore_db() {
  restore_assume_yes=false
  restore_non_interactive=false
  restore_backup=

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --yes|-y) restore_assume_yes=true ;;
      --non-interactive) restore_non_interactive=true ;;
      --help|-h) usage_command restore-db; return 0 ;;
      --*)
        die_with_hint "Unknown option for restore-db: $1" "Run ./manage.sh help restore-db."
        ;;
      *)
        if [ -n "${restore_backup}" ]; then
          die_with_hint "restore-db accepts a single backup path." "Example: ./manage.sh restore-db backups/latest.sql"
        fi
        restore_backup=$1
        ;;
    esac
    shift
  done

  ensure_env
  require_command docker
  [ -n "${restore_backup}" ] || die_with_hint "restore-db requires a backup path." "Example: ./manage.sh restore-db backups/latest.sql"
  [ -f "${restore_backup}" ] || die_with_hint "Backup not found: ${restore_backup}" "Check the path or run ./manage.sh backup-db first."
  db=$(postgres_env POSTGRES_DB app)
  user=$(postgres_env POSTGRES_USER app)

  confirm_keyword_or_abort "RESTORE" "Restore ${restore_backup} into database ${db}. This can overwrite data." "${restore_assume_yes}" "${restore_non_interactive}"
  step "Restoring database backup"
  run_compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${user}" -d "${db}" < "${restore_backup}"
  ok "Restore finished."
}

sql_identifier() {
  printf '%s' "$1" | sed 's/"/""/g'
}

sql_literal() {
  printf '%s' "$1" | sed "s/'/''/g"
}

generate_password() {
  if command_exists openssl; then
    openssl rand -hex 24
  elif command_exists shasum; then
    date +%s | shasum -a 256 | awk '{print $1}'
  else
    date +%s | cksum | awk '{print $1}'
  fi
}

rotate_db_password() {
  rotate_assume_yes=false
  rotate_non_interactive=false
  rotate_new_password=

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --yes|-y) rotate_assume_yes=true ;;
      --non-interactive) rotate_non_interactive=true ;;
      --help|-h) usage_command rotate-db-password; return 0 ;;
      --*)
        die_with_hint "Unknown option for rotate-db-password: $1" "Run ./manage.sh help rotate-db-password."
        ;;
      *)
        if [ -n "${rotate_new_password}" ]; then
          die_with_hint "rotate-db-password accepts at most one optional password argument." "Run ./manage.sh help rotate-db-password."
        fi
        rotate_new_password=$1
        ;;
    esac
    shift
  done

  ensure_env
  require_command docker
  active_database_url=$(env_value DATABASE_URL "${ENV_FILE}")
  if [ -n "${active_database_url}" ]; then
    die_with_hint "rotate-db-password only manages the bundled Postgres fallback. DATABASE_URL is active." "Rotate that database externally and then update .env manually."
  fi

  if [ -z "${rotate_new_password}" ]; then
    rotate_new_password=$(generate_password)
  fi

  user=$(postgres_env POSTGRES_USER app)
  db=$(postgres_env POSTGRES_DB app)
  escaped_user=$(sql_identifier "${user}")
  escaped_password=$(sql_literal "${rotate_new_password}")

  confirm_keyword_or_abort "ROTATE" "Rotate the bundled Postgres password for user ${user} and restart the backend." "${rotate_assume_yes}" "${rotate_non_interactive}"
  step "Rotating bundled Postgres password"
  run_compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${user}" -d "${db}" -c "ALTER USER \"${escaped_user}\" WITH PASSWORD '${escaped_password}';" >/dev/null

  backup_env
  set_env_value POSTGRES_PASSWORD "${rotate_new_password}" "${ENV_FILE}"
  run_compose up -d backend
  ok "Rotated the bundled Postgres password and restarted the backend."
}

print_urls() {
  ensure_no_extra_args "$@"
  ensure_env
  url=$(base_url)
  printf 'UI:        %s\n' "${url}"
  printf 'API docs:  %s/api/v1/docs\n' "${url}"
  printf 'Readyz:    %s/api/v1/readyz\n' "${url}"
}

usage() {
  cat <<'EOF'
Usage:
  ./manage.sh <command> [options]

Core commands:
  setup                       Guided .env wizard with setup profiles
  start                       Build and start the Compose stack
  stop                        Stop the Compose stack
  restart                     Recreate services and reload .env values
  status                      Show Compose service status
  logs [service]              Follow Compose logs
  doctor                      Run environment and health diagnostics
  print-urls                  Print UI, API docs, and readyz URLs

Environment commands:
  init-env                    Create .env from .env.example if missing
  check-env                   Check .env keys and warn about unsafe defaults
  sync-env                    Add missing active keys from .env.example to .env

Maintenance commands:
  update                      Pull, build, and start the stack
  backup-db                   Write a pg_dump backup to backups/
  restore-db <backup.sql>     Restore a SQL backup with typed confirmation
  rotate-db-password [pass]   Rotate bundled Postgres password safely

Help:
  help [command]              Show general or command-specific help
  -h, --help                  Show general help

Examples:
  ./manage.sh setup
  ./manage.sh setup --profile production
  ./manage.sh start --yes
  ./manage.sh doctor
  ./manage.sh restore-db backups/teams-rehook-20260628-230000.sql
EOF
}

usage_command() {
  case "${1:-}" in
    ""|help)
      usage
      ;;
    setup)
      cat <<'EOF'
Usage:
  ./manage.sh setup [--profile local|production|custom] [--yes] [--non-interactive]

Profiles:
  local/default    HTTPS on localhost, ports 8080/8443, random bundled DB password
  production       Listener ports, publish scheme, public DNS name, and optional public port
  custom           Interactive prompts for listener ports, publish scheme, public DNS name, public port, and DB password mode

Options:
  --profile <name>     Preselect a setup profile
  --yes, -y            Accept confirmations automatically
  --non-interactive    Use defaults without prompting where possible

Examples:
  ./manage.sh setup
  ./manage.sh setup --profile local --yes
  ./manage.sh setup --profile production
EOF
      ;;
    start)
      cat <<'EOF'
Usage:
  ./manage.sh start [setup-options]

Behavior:
  Starts the Compose stack. If .env is missing, the setup wizard runs first.
  If the stack is already running, this command leaves it in place and only prints the known URLs.

Supported setup options when .env is missing:
  --profile <name>     local, production, or custom
  --yes, -y            Accept confirmations automatically
  --non-interactive    Use defaults without prompting where possible

Examples:
  ./manage.sh start
  ./manage.sh start --yes
EOF
      ;;
    restart)
      cat <<'EOF'
Usage:
  ./manage.sh restart

Behavior:
  Recreates the Compose services with the current .env values.
  This is the safe choice after changing environment variables, image build context, or proxy settings.

Example:
  ./manage.sh restart
EOF
      ;;
    update)
      cat <<'EOF'
Usage:
  ./manage.sh update

Behavior:
  Pulls the current branch with ff-only, rebuilds the images, and refreshes the Compose stack.
  Use this after repository changes. Use ./manage.sh restart after .env-only changes.

Example:
  ./manage.sh update
EOF
      ;;
    doctor)
      cat <<'EOF'
Usage:
  ./manage.sh doctor

Checks:
  - Docker CLI availability
  - Docker daemon reachability
  - Compose availability
  - .env presence and active keys
  - Running Compose services
  - /api/v1/readyz health endpoint

Example:
  ./manage.sh doctor
EOF
      ;;
    restore-db)
      cat <<'EOF'
Usage:
  ./manage.sh restore-db <backup.sql> [--yes] [--non-interactive]

Safety:
  Interactive runs require typing RESTORE exactly.
  Non-interactive runs must use --yes.

Example:
  ./manage.sh restore-db backups/latest.sql
EOF
      ;;
    rotate-db-password)
      cat <<'EOF'
Usage:
  ./manage.sh rotate-db-password [new-password] [--yes] [--non-interactive]

Safety:
  Interactive runs require typing ROTATE exactly.
  Non-interactive runs must use --yes.

Notes:
  If no password is supplied, a new random password is generated and stored in .env.
  This command only manages the bundled Postgres fallback when DATABASE_URL is not active.

Examples:
  ./manage.sh rotate-db-password
  ./manage.sh rotate-db-password 'new-secret-value' --yes
EOF
      ;;
    *)
      die_with_hint "Unknown help topic: $1" "Run ./manage.sh help to list supported commands."
      ;;
  esac
}

cmd=${1:-}
if [ -z "${cmd}" ]; then
  usage
  exit 1
fi
shift || true

case "${cmd}" in
  setup) setup_env "$@" ;;
  init-env) init_env "$@" ;;
  check-env) check_env "$@" ;;
  sync-env) sync_env "$@" ;;
  start) start_stack "$@" ;;
  stop) stop_stack "$@" ;;
  restart) restart_stack "$@" ;;
  status) status_stack "$@" ;;
  logs) logs_stack "$@" ;;
  update) update_stack "$@" ;;
  doctor) doctor "$@" ;;
  backup-db) backup_db "$@" ;;
  restore-db) restore_db "$@" ;;
  rotate-db-password) rotate_db_password "$@" ;;
  print-urls) print_urls "$@" ;;
  help|-h|--help) usage_command "${1:-}" ;;
  *)
    usage
    die_with_hint "Unknown command: ${cmd}" "Run ./manage.sh help to see the available commands."
    ;;
esac
