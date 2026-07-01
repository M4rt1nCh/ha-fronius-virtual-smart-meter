#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

bashio::log.info "Starting Fronius Virtual Meter Bridge"
exec python3 -m app
