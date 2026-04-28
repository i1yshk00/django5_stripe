#!/usr/bin/env bash

# Скрипт-обертка над Docker Compose для проекта.
#
# Он нужен по двум причинам:
# 1. не заставлять каждый раз помнить, какой compose-файл отвечает за dev,
#    а какой за production-like запуск;
# 2. дать простой и очевидный интерфейс через флаги `-d/--dev`.
#
# Правила работы:
# - без флагов запускается production-like compose;
# - с `-d`, `-dev` или `--dev` запускается локальный dev-compose;
# - все остальные аргументы прозрачно передаются в `docker compose`.
#
# Примеры:
#   ./run-docker.sh
#   ./run-docker.sh -d
#   ./run-docker.sh -dev
#   ./run-docker.sh -d up --build
#   ./run-docker.sh down

set -euo pipefail


# По умолчанию используем production-like compose-файл.
compose_file="docker-compose.yml"
mode_name="prod"

# Все аргументы, не являющиеся флагом выбора режима, будут переданы дальше.
passthrough_args=()

for arg in "$@"; do
    case "$arg" in
        -d|-dev|--dev)
            compose_file="docker-compose.dev.yml"
            mode_name="dev"
            ;;
        -p|-prod|--prod)
            compose_file="docker-compose.yml"
            mode_name="prod"
            ;;
        *)
            passthrough_args+=("$arg")
            ;;
    esac
done

# Если пользователь не передал явную compose-команду, выбираем самый частый
# сценарий: поднять контейнеры и при необходимости пересобрать образ.
if [ ${#passthrough_args[@]} -eq 0 ]; then
    passthrough_args=(up --build)
fi

echo "Запуск Docker Compose в режиме: ${mode_name}"
echo "Используемый compose-файл: ${compose_file}"

exec docker compose -f "${compose_file}" "${passthrough_args[@]}"
