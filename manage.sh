#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR="${SCRIPT_DIR}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"
ENV_EXAMPLE="${ENV_EXAMPLE:-${ROOT_DIR}/.env.example}"
BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups}"
COMPOSE="${COMPOSE:-docker compose}"

usage() {
  cat <<'EOF'
Usage: ./manage.sh <command> [args]

Commands:
  setup                       Create or replace .env with guided defaults and optionally start the stack
  init-env                    Create .env from .env.example if missing
  check-env                   Check .env keys and warn about unsafe defaults
  sync-env                    Add missing active keys from .env.example to .env
  start                       Build and start the Compose stack (runs setup first if .env is missing)
  stop                        Stop the Compose stack
  restart                     Restart the Compose stack
  status                      Show Compose service status
  logs [service]              Follow Compose logs
  update                      Pull, build, and start the stack
  doctor                      Check Compose status and backend readiness
  backup-db                   Write a pg_dump backup to backups/
  restore-db <backup.sql>     Restore a SQL backup with confirmation
  rotate-db-password [pass]   Rotate bundled Postgres password and restart backend
  print-urls                  Print UI, API docs, and readyz URLs
EOF
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '%s\n' "$*"
}

timestamp() {
  date +%Y%m%d-%H%M%S
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

run_compose() {
  # shellcheck disable=SC2086
  (cd "${ROOT_DIR}" && $COMPOSE "$@")
}

stack_is_running() {
  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi
  [ -n "$(run_compose ps --status running -q 2>/dev/null)" ]
}

ensure_env() {
  [ -f "${ENV_FILE}" ] || die ".env not found. Run ./manage.sh setup first."
}

backup_env() {
  ensure_env
  backup="${ENV_FILE}.backup-$(timestamp)"
  cp "${ENV_FILE}" "${backup}"
  info "Backed up .env to ${backup}"
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

confirm() {
  prompt=$1
  printf '%s [y/N] ' "${prompt}"
  read answer
  case "${answer}" in
    y|Y|yes|YES) return 0 ;;
    *) die "Aborted" ;;
  esac
}

confirm_default_yes() {
  prompt=$1
  printf '%s [Y/n] ' "${prompt}"
  read answer
  case "${answer}" in
    ""|y|Y|yes|YES) return 0 ;;
    n|N|no|NO) return 1 ;;
    *) die "Aborted" ;;
  esac
}

prompt_value() {
  prompt=$1
  default_value=${2:-}
  if [ -n "${default_value}" ]; then
    printf '%s [%s] ' "${prompt}" "${default_value}"
  else
    printf '%s ' "${prompt}"
  fi
  read answer
  if [ -n "${answer}" ]; then
    printf '%s' "${answer}"
  else
    printf '%s' "${default_value}"
  fi
}

require_positive_port() {
  value=$1
  case "${value}" in
    ''|*[!0-9]*) die "Port must be a number" ;;
  esac
  if [ "${value}" -lt 1 ] || [ "${value}" -gt 65535 ]; then
    die "Port must be between 1 and 65535"
  fi
}

write_minimal_env() {
  http_port=$1
  https_port=$2
  app_url=$3
  postgres_password=$4
  secure_cookie=$5
  tmp="${ENV_FILE}.tmp-$$"
  cat > "${tmp}" <<EOF
# Proxy listener ports (host -> HAProxy container 80/443)
PROXY_HTTP_PORT=${http_port}
PROXY_HTTPS_PORT=${https_port}

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

# Session cookies
SESSION_SECURE_COOKIE=${secure_cookie}
EOF
  mv "${tmp}" "${ENV_FILE}"
}

setup_env() {
  http_port=8080
  https_port=8443
  secure_cookie=true
  app_url="https://localhost:8443"
  using_random_postgres_password=true

  if [ -f "${ENV_FILE}" ]; then
    confirm "Replace existing .env with guided defaults?"
    backup_env
  fi

  if confirm_default_yes "Use recommended local defaults (HTTPS, standard ports, random DB password)?"; then
    postgres_password=$(generate_password)
  else
    http_port=$(prompt_value "HTTP port" "8080")
    require_positive_port "${http_port}"

    if confirm_default_yes "Run locally with HTTPS at https://localhost:8443?"; then
      https_port=$(prompt_value "HTTPS port" "8443")
      require_positive_port "${https_port}"
      secure_cookie=true
      app_url="https://localhost:${https_port}"
    else
      secure_cookie=false
      app_url="http://localhost:${http_port}"
    fi

    if confirm_default_yes "Generate a random bundled Postgres password?"; then
      postgres_password=$(generate_password)
    else
      postgres_password=app
      using_random_postgres_password=false
    fi
  fi

  write_minimal_env "${http_port}" "${https_port}" "${app_url}" "${postgres_password}" "${secure_cookie}"
  info "Wrote guided .env configuration"
  if [ "${using_random_postgres_password}" = true ]; then
    info "A random bundled Postgres password was written to .env."
  fi
  print_urls
  info "Open the UI, create the first admin, then configure Microsoft identity in Settings."
  if stack_is_running; then
    info "Stack is already running."
    return 0
  fi
  if confirm_default_yes "Start the stack now?"; then
    run_start_compose
  else
    info "Run ./manage.sh start when you are ready."
  fi
}

init_env() {
  [ -f "${ENV_EXAMPLE}" ] || die ".env.example not found"
  if [ -f "${ENV_FILE}" ]; then
    info ".env already exists; leaving it unchanged"
    return
  fi
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  info "Created .env from .env.example"
}

check_env() {
  ensure_env
  missing=0
  for key in $(active_keys "${ENV_EXAMPLE}"); do
    if ! active_keys "${ENV_FILE}" | grep -qx "${key}"; then
      printf 'Missing key: %s\n' "${key}"
      missing=1
    fi
  done

  warn_unsafe_defaults

  if [ "${missing}" -eq 0 ]; then
    info "No missing active keys from .env.example"
  else
    return 1
  fi
}

warn_if_value() {
  key=$1
  bad=$2
  message=$3
  value=$(env_value "${key}" "${ENV_FILE}")
  if [ "${value}" = "${bad}" ]; then
    printf 'Warning: %s\n' "${message}"
  fi
}

warn_if_empty() {
  key=$1
  message=$2
  value=$(env_value "${key}" "${ENV_FILE}")
  if [ -z "${value}" ]; then
    printf 'Warning: %s\n' "${message}"
  fi
}

warn_unsafe_defaults() {
  warn_if_value POSTGRES_USER app "POSTGRES_USER is the local default; use a deployment-specific user outside local/dev."
  warn_if_value POSTGRES_PASSWORD app "POSTGRES_PASSWORD is the local default; change it before production use."
  warn_if_empty SETTINGS_ENC_KEY "SETTINGS_ENC_KEY is empty; simple deployments can bootstrap it, but production should set a stable secret."
  warn_if_empty MONITORING_API_KEY "MONITORING_API_KEY is empty; monitoring endpoint will return 503."
  if [ "$(env_value SESSION_SECURE_COOKIE "${ENV_FILE}")" = "false" ]; then
    printf 'Warning: SESSION_SECURE_COOKIE=false; set true behind HTTPS.\n'
  fi
}

sync_env() {
  ensure_env
  added=0
  tmp_missing=$(mktemp)
  trap 'rm -f "${tmp_missing}"' EXIT

  for key in $(active_keys "${ENV_EXAMPLE}"); do
    if ! active_keys "${ENV_FILE}" | grep -qx "${key}"; then
      value=$(env_value "${key}" "${ENV_EXAMPLE}")
      printf '%s=%s\n' "${key}" "${value}" >> "${tmp_missing}"
      added=$((added + 1))
    fi
  done

  if [ "${added}" -eq 0 ]; then
    info ".env already has every active key from .env.example"
    return
  fi

  backup_env
  {
    printf '\n# Added by ./manage.sh on %s\n' "$(timestamp)"
    cat "${tmp_missing}"
  } >> "${ENV_FILE}"
  info "Added ${added} missing key(s) to .env"
}

run_start_compose() {
  require_command docker
  run_compose up -d --build
}

maybe_start_stack() {
  ensure_env
  if stack_is_running; then
    info "Stack is already running."
    print_urls
    return 0
  fi
  run_start_compose
}

start_stack() {
  if [ ! -f "${ENV_FILE}" ]; then
    info ".env not found; running guided setup."
    setup_env
    return 0
  fi
  maybe_start_stack
}

stop_stack() {
  require_command docker
  run_compose down
}

restart_stack() {
  ensure_env
  require_command docker
  run_compose restart
}

status_stack() {
  require_command docker
  run_compose ps
}

logs_stack() {
  require_command docker
  if [ "$#" -gt 0 ]; then
    run_compose logs -f "$1"
  else
    run_compose logs -f
  fi
}

update_stack() {
  ensure_env
  require_command git
  require_command docker
  (cd "${ROOT_DIR}" && git pull --ff-only)
  run_compose build
  run_compose up -d
}

base_url() {
  value=$(env_value APP_PUBLIC_BASE_URL "${ENV_FILE}")
  [ -n "${value}" ] || value="http://localhost:8080"
  printf '%s' "${value%/}"
}

doctor() {
  ensure_env
  require_command docker
  run_compose ps
  url="$(base_url)/api/v1/readyz"
  if command -v curl >/dev/null 2>&1; then
    info "Checking ${url}"
    curl -fsS "${url}" >/dev/null && info "readyz OK"
  else
    info "curl not found; skipping readyz check"
  fi
}

postgres_env() {
  key=$1
  value=$(env_value "${key}" "${ENV_FILE}")
  [ -n "${value}" ] || value=$2
  printf '%s' "${value}"
}

backup_db() {
  ensure_env
  require_command docker
  mkdir -p "${BACKUP_DIR}"
  db=$(postgres_env POSTGRES_DB app)
  user=$(postgres_env POSTGRES_USER app)
  out="${BACKUP_DIR}/teams-rehook-$(timestamp).sql"
  run_compose exec -T postgres pg_dump -U "${user}" -d "${db}" > "${out}"
  info "Wrote ${out}"
}

restore_db() {
  ensure_env
  require_command docker
  backup=${1:-}
  [ -n "${backup}" ] || die "restore-db requires a backup path"
  [ -f "${backup}" ] || die "Backup not found: ${backup}"
  db=$(postgres_env POSTGRES_DB app)
  user=$(postgres_env POSTGRES_USER app)
  confirm "Restore ${backup} into database ${db}? This can overwrite data."
  run_compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${user}" -d "${db}" < "${backup}"
  info "Restore finished"
}

sql_identifier() {
  printf '%s' "$1" | sed 's/"/""/g'
}

sql_literal() {
  printf '%s' "$1" | sed "s/'/''/g"
}

generate_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    date +%s | sha256sum | awk '{print $1}'
  fi
}

rotate_db_password() {
  ensure_env
  require_command docker
  active_database_url=$(env_value DATABASE_URL "${ENV_FILE}")
  if [ -n "${active_database_url}" ]; then
    die "rotate-db-password only manages the bundled Postgres fallback. DATABASE_URL is active; rotate that database externally and update .env manually."
  fi

  new_password=${1:-}
  if [ -z "${new_password}" ]; then
    new_password=$(generate_password)
  fi

  user=$(postgres_env POSTGRES_USER app)
  db=$(postgres_env POSTGRES_DB app)
  escaped_user=$(sql_identifier "${user}")
  escaped_password=$(sql_literal "${new_password}")

  confirm "Rotate password for bundled Postgres user ${user} and restart backend?"
  run_compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${user}" -d "${db}" -c "ALTER USER \"${escaped_user}\" WITH PASSWORD '${escaped_password}';" >/dev/null

  backup_env
  set_env_value POSTGRES_PASSWORD "${new_password}" "${ENV_FILE}"
  run_compose up -d backend
  info "Rotated bundled Postgres password and restarted backend"
}

print_urls() {
  ensure_env
  url=$(base_url)
  printf 'UI:        %s\n' "${url}"
  printf 'API docs:  %s/api/v1/docs\n' "${url}"
  printf 'Readyz:    %s/api/v1/readyz\n' "${url}"
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
  help|-h|--help) usage ;;
  *) usage; die "Unknown command: ${cmd}" ;;
esac
