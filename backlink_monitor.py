#!/usr/bin/env python3
"""
Backlink Monitor CLI

Monitora i backlink da siti esterni al tuo sito target.
Se un backlink manca o la pagina non è raggiungibile, invia un alert email.
Supporta report periodici anche quando tutto è ok.
"""

import argparse
import json
import logging
import smtplib
import sys
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from html.parser import HTMLParser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_CONFIG = {
    "target": "https://mysite.com",
    "recipients": ["my-address@example.com"],
    "smtp": {
        "host": "smtp.gmail.com",
        "port": 587,
        "user": "tua-email@gmail.com",
        "password": "APP_PASSWORD"
    },
    "check_interval_days": 3,
    "send_ok_report": True,
    "log": {
        "file": "backlink_monitor.log",
        "max_bytes": 1048576,
        "backup_count": 3
    },
    "urls": []
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class LinkExtractor(HTMLParser):
    """Estrae tutti gli href dai tag <a>."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            for name, value in attrs:
                if name.lower() == "href" and value:
                    self.links.append(value)


def script_dir() -> Path:
    """Restituisce la directory in cui risiede lo script."""
    return Path(__file__).resolve().parent


def default_config_path() -> Path:
    """Restituisce il path di default del file di configurazione."""
    return script_dir() / "config.json"


def normalize_url(url: str) -> str:
    """
    Normalizza un URL per la deduplicazione.
    Rimuove spazi, fragment e il trailing slash.
    """
    url = url.strip()
    if not url:
        return url
    # Rimuove il fragment
    url = url.split("#", 1)[0]
    # Lowercase
    url = url.lower()
    # Rimuove il trailing slash: https://example.com/ e https://example.com
    # sono considerati lo stesso URL per evitare doppioni.
    url = url.rstrip("/")
    return url


def load_config(path: Path) -> dict:
    """Carica la configurazione da file JSON."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict, path: Path) -> None:
    """Salva la configurazione su file JSON."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def configure_logging(config: dict) -> None:
    """Configura il logger con rotazione su file e output su console."""
    log_cfg = config.get("log", {})
    log_file = log_cfg.get("file", "backlink_monitor.log")
    max_bytes = log_cfg.get("max_bytes", 1048576)
    backup_count = log_cfg.get("backup_count", 3)

    # Se il path del log è relativo, lo mettiamo nella directory dello script
    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = script_dir() / log_path

    handlers = [
        RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers
    )


def extract_domain(target: str) -> str:
    """Estrae il dominio di target rimuovendo scheme e path."""
    parsed = urlparse(target)
    domain = parsed.netloc or parsed.path
    return domain.lower().lstrip("www.")


def fetch_page(url: str) -> tuple:
    """
    Scarica una pagina web.
    Ritorna (html_text, final_url) oppure lancia un'eccezione in caso di errore.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "identity",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        # Legge al massimo 5 MB per evitare pagine enormi
        data = response.read(5 * 1024 * 1024)
        final_url = response.geturl()
        charset = response.headers.get_content_charset("utf-8")
        html = data.decode(charset, errors="replace")
        return html, final_url


def check_backlink(url: str, target_domain: str) -> dict:
    """
    Verifica se la pagina all'URL contiene un link al dominio target.
    Ritorna un dict con 'url', 'status' ('ok' | 'missing' | 'error') e 'info'.
    """
    result = {"url": url, "status": "error", "info": ""}
    try:
        html, final_url = fetch_page(url)
        parser = LinkExtractor()
        parser.feed(html)

        target_lower = target_domain.lower()
        found = False
        for href in parser.links:
            if target_lower in href.lower():
                found = True
                break

        if found:
            result["status"] = "ok"
            result["info"] = f"backlink trovato (final url: {final_url})"
        else:
            result["status"] = "missing"
            result["info"] = f"nessun link a {target_domain} trovato"

    except urllib.error.HTTPError as e:
        result["info"] = f"HTTP {e.code} {e.reason}"
    except urllib.error.URLError as e:
        result["info"] = f"errore di connessione: {e.reason}"
    except TimeoutError:
        result["info"] = "timeout durante il download"
    except Exception as e:
        result["info"] = f"errore: {e}"

    return result


def send_email(subject: str, body: str, config: dict) -> bool:
    """Invia un'email tramite SMTP."""
    smtp_cfg = config.get("smtp", {})
    host = smtp_cfg.get("host", "")
    port = smtp_cfg.get("port", 587)
    user = smtp_cfg.get("user", "")
    password = smtp_cfg.get("password", "")
    recipients = config.get("recipients", [])

    if not host or not user or not password:
        logging.warning("Configurazione SMTP incompleta: email non inviata.")
        return False

    if not recipients:
        logging.warning("Nessun destinatario configurato: email non inviata.")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()

        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())
        server.quit()
        logging.info("Email inviata con successo a: %s", ", ".join(recipients))
        return True
    except Exception as e:
        logging.error("Errore durante l'invio dell'email: %s", e)
        return False


def format_report(results: list, target: str) -> str:
    """Formatta il corpo dell'email di report/alert."""
    lines = [
        f"Backlink Monitor Report - {target}",
        "=" * 50,
        ""
    ]

    ok = [r for r in results if r["status"] == "ok"]
    missing = [r for r in results if r["status"] == "missing"]
    errors = [r for r in results if r["status"] == "error"]

    lines.append(f"Totale URL controllati: {len(results)}")
    lines.append(f"OK: {len(ok)}")
    lines.append(f"Backlink mancanti: {len(missing)}")
    lines.append(f"Errori di raggiungibilità: {len(errors)}")
    lines.append("")

    if missing:
        lines.append("--- BACKLINK MANCANTI ---")
        for r in missing:
            lines.append(f"[MISSING] {r['url']}")
            lines.append(f"          {r['info']}")
        lines.append("")

    if errors:
        lines.append("--- ERRORI ---")
        for r in errors:
            lines.append(f"[ERROR] {r['url']}")
            lines.append(f"        {r['info']}")
        lines.append("")

    if not missing and not errors:
        lines.append("Tutti i backlink monitorati sono presenti e raggiungibili.")
        lines.append("")

    lines.append("--- ELENCO COMPLETO ---")
    for r in results:
        status_label = r["status"].upper()
        lines.append(f"[{status_label}] {r['url']}")

    return "\n".join(lines)


def run_check(config: dict, dry_run: bool = False) -> list:
    """Esegue il check su tutti gli URL e opzionalmente invia l'email."""
    target = config.get("target", "")
    target_domain = extract_domain(target)
    urls = config.get("urls", [])

    if not urls:
        logging.warning("Nessun URL da monitorare. Usa 'add <url>' per aggiungerne uno.")
        return []

    logging.info("Inizio check per target: %s", target)
    results = []
    for url in urls:
        logging.info("Controllo: %s", url)
        result = check_backlink(url, target_domain)
        results.append(result)
        logging.info("Risultato: %s - %s", result["status"].upper(), result["info"])

    missing_or_error = any(r["status"] in ("missing", "error") for r in results)

    if dry_run:
        logging.info("Modalità dry-run: nessuna email inviata.")
        print("\n" + format_report(results, target))
        return results

    body = format_report(results, target)

    if missing_or_error:
        subject = f"[ALERT] Backlink mancanti per {target_domain}"
        send_email(subject, body, config)
    elif config.get("send_ok_report", True):
        subject = f"[OK] Backlink monitoraggio giornaliero per {target_domain}"
        send_email(subject, body, config)
    else:
        logging.info("Tutto ok e send_ok_report disabilitato: nessuna email inviata.")

    return results


def ensure_config_exists(path: Path) -> dict:
    """Carica il config se esiste, altrimenti stampa un errore e esce."""
    if not path.exists():
        logging.error("File di configurazione non trovato: %s", path)
        logging.error("Esegui 'backlink_monitor.py init' per crearlo.")
        sys.exit(1)
    return load_config(path)


def cmd_init(args):
    """Comando init: crea il file di configurazione di default."""
    path = args.config
    if path.exists() and not args.force:
        print(f"Il file di configurazione esiste già: {path}")
        print("Usa --force per sovrascriverlo.")
        return

    save_config(DEFAULT_CONFIG, path)
    print(f"Creato file di configurazione: {path}")
    print("Modifica i campi 'smtp.user', 'smtp.password' e 'recipients' prima di usare il tool.")


def cmd_add(args):
    """Comando add: aggiunge un URL con deduplicazione."""
    path = args.config
    config = ensure_config_exists(path)
    new_url = normalize_url(args.url)

    if not new_url:
        print("URL non valido.")
        return

    existing = [normalize_url(u) for u in config.get("urls", [])]
    if new_url in existing:
        print(f"URL già presente: {args.url}")
        return

    config["urls"].append(args.url.strip())
    save_config(config, path)
    print(f"Aggiunto URL: {args.url.strip()}")


def cmd_remove(args):
    """Comando remove: rimuove un URL."""
    path = args.config
    config = ensure_config_exists(path)
    target_url = normalize_url(args.url)

    urls = config.get("urls", [])
    new_urls = [u for u in urls if normalize_url(u) != target_url]

    if len(new_urls) == len(urls):
        print(f"URL non trovato: {args.url}")
        return

    config["urls"] = new_urls
    save_config(config, path)
    print(f"Rimosso URL: {args.url}")


def cmd_list(args):
    """Comando list: elenca gli URL monitorati."""
    path = args.config
    config = ensure_config_exists(path)
    urls = config.get("urls", [])

    if not urls:
        print("Nessun URL monitorato.")
        return

    print(f"URL monitorati ({len(urls)}):")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")


def cmd_check(args):
    """Comando check: esegue il check senza inviare email."""
    path = args.config
    config = ensure_config_exists(path)
    configure_logging(config)
    run_check(config, dry_run=True)


def cmd_run(args):
    """Comando run: esegue il check e invia email."""
    path = args.config
    config = ensure_config_exists(path)
    configure_logging(config)
    run_check(config, dry_run=False)


def main():
    parser = argparse.ArgumentParser(
        description="Monitora i backlink esterni a un sito e invia alert email."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help=f"Percorso del file di configurazione (default: {default_config_path()})"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Crea il file di configurazione di default")
    p_init.add_argument("--force", action="store_true", help="Sovrascrive il file se esiste")
    p_init.set_defaults(func=cmd_init)

    p_add = subparsers.add_parser("add", help="Aggiunge un URL da monitorare")
    p_add.add_argument("url", help="URL del sito esterno da monitorare")
    p_add.set_defaults(func=cmd_add)

    p_remove = subparsers.add_parser("remove", help="Rimuove un URL monitorato")
    p_remove.add_argument("url", help="URL da rimuovere")
    p_remove.set_defaults(func=cmd_remove)

    p_list = subparsers.add_parser("list", help="Elenca gli URL monitorati")
    p_list.set_defaults(func=cmd_list)

    p_check = subparsers.add_parser("check", help="Esegue un check senza inviare email")
    p_check.set_defaults(func=cmd_check)

    p_run = subparsers.add_parser("run", help="Esegue il check e invia le email")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
