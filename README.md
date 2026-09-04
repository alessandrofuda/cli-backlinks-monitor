# Backlink Monitor

Tool CLI leggero per monitorare i backlink da siti esterni a [https://longtermemory.com](https://longtermemory.com).

Se un backlink scompare o la pagina esterna non è raggiungibile, invia un alert email.  
Supporta anche l'invio di un report periodico quando tutto è ok.

## Caratteristiche

- Sviluppato in **Python 3**, usa solo la libreria standard (nessuna dipendenza esterna).
- Configurazione in **JSON** semplice.
- Gestione URL da riga di comando con deduplicazione.
- Log rotante automatico (massimo ~4 MB totali).
- Scheduling affidabile tramite **systemd timer**.
- Report via email SMTP (testato con Gmail).

## Requisiti

- Ubuntu (o altra distribuzione Linux con systemd).
- Python 3.7 o superiore.
- Accesso root per l'installazione del servizio systemd.

## Installazione rapida

```bash
cd /percorso/del/progetto
sudo ./install.sh
```

Lo script:

- copia i file in `/opt/backlink-monitor`;
- crea un utente sistema dedicato `backlinkmon`;
- installa il servizio e il timer systemd;
- **non avvia** il timer finché non hai configurato l'SMTP.

## Configurazione

Dopo l'installazione, modifica:

```bash
sudo nano /opt/backlink-monitor/config.json
```

### Gmail / App Password

Per usare Gmail devi generare una **App Password**:

1. Abilita l'autenticazione a due fattori su Google.
2. Vai su [Gestione account Google → Sicurezza → Verifica in due passaggi → App Password](https://myaccount.google.com/apppasswords).
3. Genera una password per app "Mail" su "Altro" (nome a piacere, es. `backlink-monitor`).
4. Copia la password di 16 caratteri nel campo `smtp.password`.

Esempio configurazione:

```json
{
  "target": "https://longtermemory.com",
  "recipients": ["alessandro.fuda@gmail.com"],
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "user": "tua-email@gmail.com",
    "password": "xxxx xxxx xxxx xxxx"
  },
  "check_interval_days": 3,
  "send_ok_report": true,
  "log": {
    "file": "backlink_monitor.log",
    "max_bytes": 1048576,
    "backup_count": 3
  },
  "urls": []
}
```

> **Nota:** l'App Password va inserita senza spazi: `"xxxx xxxx xxxx xxxx"` diventa `"xxxxxxxxxxxxxxxx"`.

## Comandi CLI

Tutti i comandi vanno eseguiti come utente che può leggere/scrivere `/opt/backlink-monitor`, generalmente `root`:

```bash
/opt/backlink-monitor/backlink_monitor.py <comando>
```

### `init`

Crea il file di configurazione di default.

```bash
/opt/backlink-monitor/backlink_monitor.py init --force
```

### `add`

Aggiunge un URL da monitorare (con deduplicazione).

```bash
/opt/backlink-monitor/backlink_monitor.py add 'https://esempio.com/articolo'
```

### `remove`

Rimuove un URL.

```bash
/opt/backlink-monitor/backlink_monitor.py remove 'https://esempio.com/articolo'
```

### `list`

Elenca gli URL monitorati.

```bash
/opt/backlink-monitor/backlink_monitor.py list
```

### `check`

Esegue il check **senza inviare email**. Utile per testare.

```bash
/opt/backlink-monitor/backlink_monitor.py check
```

### `run`

Esegue il check e invia email se necessario. Questo è il comando eseguito dal timer systemd.

```bash
/opt/backlink-monitor/backlink_monitor.py run
```

## Scheduling

Il timer è configurato per eseguire il check **ogni 3 giorni** a partire dall'ultima esecuzione (`OnUnitActiveSec=3d`).

Avvia il timer:

```bash
sudo systemctl start backlink-monitor.timer
```

Verifica lo stato:

```bash
sudo systemctl status backlink-monitor.timer
sudo systemctl list-timers backlink-monitor.timer
```

Vedi gli ultimi log:

```bash
sudo journalctl -u backlink-monitor.service -n 50
```

## Cambiare la frequenza

Modifica il file timer:

```bash
sudo nano /etc/systemd/system/backlink-monitor.timer
```

Esempi:

```ini
# Ogni giorno
OnUnitActiveSec=1d

# Ogni 12 ore
OnUnitActiveSec=12h

# Ogni settimana
OnUnitActiveSec=1w
```

Dopo la modifica:

```bash
sudo systemctl daemon-reload
sudo systemctl restart backlink-monitor.timer
```

## Log

Il file di log ruota automaticamente quando raggiunge 1 MB, mantenendo fino a 3 backup.

```bash
sudo tail -f /opt/backlink-monitor/backlink_monitor.log
```

## Sicurezza

- Il file `config.json` ha permessi `640` ed è leggibile solo da `root` e dall'utente `backlinkmon`.
- L'utente `backlinkmon` è un utente di sistema senza shell di login (`/usr/sbin/nologin`).
- Non committare mai `config.json` con la vera App Password in un repository pubblico.

## Disinstallazione

```bash
sudo systemctl stop backlink-monitor.timer
sudo systemctl disable backlink-monitor.timer
sudo rm -f /etc/systemd/system/backlink-monitor.{service,timer}
sudo rm -rf /opt/backlink-monitor
sudo userdel backlinkmon
sudo systemctl daemon-reload
```

## Licenza

Uso personale / libero. Modifica come preferisci.
