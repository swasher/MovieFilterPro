#!/bin/sh

set -e

export DJANGO_SOCKET_PATH="${DJANGO_SOCKET_PATH:-/shared/sockets/django.sock}"

mkdir -p "$(dirname "$DJANGO_SOCKET_PATH")"

envsubst '${DJANGO_SOCKET_PATH}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
