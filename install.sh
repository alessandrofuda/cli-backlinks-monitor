#!/bin/bash
set -euo pipefail

INSTALL_DIR="/opt/backlink-monitor"
SERVICE_NAME="backlink-monitor"
USER_NAME="backlinkmon"

if [ "$EUID" -ne 0 ]; then
    echo "Esegui questo script come root (o con sudo)."
    exit 1
fi

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installazione Backlink Monitor in $INSTALL_DIR"

# Crea directory di installazione
mkdir -p "$INSTALL_DIR"

# Copia i file principali
cp "$SRC_DIR/backlink_monitor.py" "$INSTALL_DIR/"
cp "$SRC_DIR/config.json" "$INSTALL_DIR/"
cp "$SRC_DIR/requirements.txt" "$INSTALL_DIR/"

# Permessi restrittivi: solo l'utente del servizio può leggere la config
chmod 750 "$INSTALL_DIR"
chmod 640 "$INSTALL_DIR/config.json"
chmod 750 "$INSTALL_DIR/backlink_monitor.py"
chmod 644 "$INSTALL_DIR/requirements.txt"

# Crea l'utente dedicato se non esiste
if ! id "$USER_NAME" &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" "$USER_NAME"
    echo "==> Creato utente sistema: $USER_NAME"
fi

# Assegna ownership
chown -R "$USER_NAME:$USER_NAME" "$INSTALL_DIR"

# Permessi extra per il file di log
touch "$INSTALL_DIR/backlink_monitor.log"
chown "$USER_NAME:$USER_NAME" "$INSTALL_DIR/backlink_monitor.log"
chmod 640 "$INSTALL_DIR/backlink_monitor.log"

# Installa unità systemd
cp "$SRC_DIR/systemd/backlink-monitor.service" "/etc/systemd/system/"
cp "$SRC_DIR/systemd/backlink-monitor.timer" "/etc/systemd/system/"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME.timer"

# Non avvia automaticamente: l'utente deve prima configurare SMTP
echo ""
echo "==> Installazione completata."
echo ""
echo "PASSAGGI RIMANENTI:"
echo "1. Modifica la configurazione SMTP in:"
echo "   $INSTALL_DIR/config.json"
echo ""
echo "   Inserisci: user Gmail, App Password e destinatari."
echo ""
echo "2. Aggiungi gli URL da monitorare:"
echo "   $INSTALL_DIR/backlink_monitor.py add 'https://esempio.com/articolo'"
echo ""
echo "3. Testa senza inviare email:"
echo "   $INSTALL_DIR/backlink_monitor.py check"
echo ""
echo "4. Avvia il timer systemd:"
echo "   systemctl start $SERVICE_NAME.timer"
echo ""
echo "Comandi utili:"
echo "  systemctl status $SERVICE_NAME.timer"
echo "  systemctl list-timers $SERVICE_NAME.timer"
echo "  journalctl -u $SERVICE_NAME.service"
echo "  tail -f $INSTALL_DIR/backlink_monitor.log"
