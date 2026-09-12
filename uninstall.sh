#!/bin/bash
launchctl bootout "gui/$(id -u)/com.jnavarro.vuelos-mad" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.jnavarro.vuelos-mad.plist"
echo "Agente desinstalado."
