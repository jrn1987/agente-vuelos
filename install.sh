#!/bin/bash
# Instala el agente como servicio de macOS (corre cada hora, también tras reiniciar).
set -e
PLIST="$HOME/Library/LaunchAgents/com.jnavarro.vuelos-mad.plist"
cp /Users/jnavarro/agente/com.jnavarro.vuelos-mad.plist "$PLIST"
launchctl bootout "gui/$(id -u)/com.jnavarro.vuelos-mad" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Agente instalado. Estado:"
launchctl print "gui/$(id -u)/com.jnavarro.vuelos-mad" | head -5
