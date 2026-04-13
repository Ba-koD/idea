#!/bin/sh
set -eu

: "${APP_ENV:=local}"
: "${APP_DISPLAY_NAME:=idea Service Demo}"
: "${PUBLIC_API_BASE_URL:=/api}"

export APP_ENV
export APP_DISPLAY_NAME
export PUBLIC_API_BASE_URL

envsubst '${APP_ENV} ${APP_DISPLAY_NAME} ${PUBLIC_API_BASE_URL}' \
  < /usr/share/nginx/html/config.js.template \
  > /usr/share/nginx/html/config.js
