import argparse
import asyncio
import logging
import os
import queue
import sys
import threading

import config
from scraper import SkipCitySignal, StopSignal, clear_checkpoint, load_checkpoint, scrape_city

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

HELP_TEXT = """
╔══════════════════════════════════════════════╗
║           Konsol Komutları                   ║
╠══════════════════════════════════════════════╣
║  ok        → Manuel doğrulamayı onayla      ║
║  pause     → Scraper'ı duraklatır           ║
║  go        → Duraklatan scraper'ı devam et  ║
║  wait N    → N saniye bekle (örn: wait 30)  ║
║  skip      → Mevcut şehri atla              ║
║  next      → Mevcut bracket'ı atla          ║
║  stop      → Scraper'ı durdur               ║
║  status    → Mevcut durumu göster           ║
║  help      → Bu listeyi göster              ║
╚══════════════════════════════════════════════╝
"""

_current_status: dict = {"city": "-", "bracket": "-", "page": "-"}
_status_lock = threading.Lock()


def update_status(city=None, bracket=None, page=None):
    with _status_lock:
        if city:    _current_status["city"]    = city
        if bracket: _current_status["bracket"] = bracket
        if page:    _current_status["page"]    = page


def print_status():
    with _status_lock:
        s = dict(_current_status)
    print(f"\n📊 Durum: Şehir={s['city']} | Bracket={s['bracket']} | Sayfa={s['page']}\n")


def console_listener(cmd_queue, stop_event):
    """
    Single owner of stdin.  Parses commands and pushes them to cmd_queue.

    Plain strings are pushed as-is.
    `wait N` is pushed as the tuple ("wait", N) so the async side can
    await the sleep without blocking this thread.
    `pause` and `go` are pushed as plain strings; the async check_commands
    handler manipulates the _pause_event accordingly.
    """
    while not stop_event.is_set():
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        cmd = line.strip().lower()
        if not cmd:
            continue
        if cmd == "help":
            print(HELP_TEXT)
        elif cmd == "status":
            print_status()
        elif cmd.startswith("wait "):
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                secs = int(parts[1])
                cmd_queue.put(("wait", secs))
                logger.info("⚡ Komut alındı: 'wait %d'", secs)
            else:
                print("Kullanım: wait <saniye>  (örn: wait 30)")
        elif cmd in ("skip", "next", "stop", "ok", "devam", "pause", "go"):
            cmd_queue.put(cmd)
            logger.info("⚡ Komut alındı: '%s'", cmd)
        else:
            print(f"Bilinmeyen komut: '{cmd}'. Yardım için 'help' yazın.")


async def run(args):
    checkpoint = load_checkpoint() if args.resume else {}
    cities = list(config.CITIES)  # copy so we can shuffle safely

    if args.city:
        cities = [c for c in config.CITIES if c["url_slug"] == args.city.lower()]
        if not cities:
            logger.error("Geçersiz şehir slug'ı: %s", args.city)
            sys.exit(1)

    # Issue #3 — Randomise city order each run so request patterns vary.
    # Skip shuffle when --resume is active (must continue in checkpoint order)
    # and when --city is specified (single city, nothing to shuffle).
    if not args.resume and not args.city:
        import random as _rnd
        _rnd.shuffle(cities)
        logger.info("🔀 Şehir sırası rastgele belirlendi: %s",
                    " → ".join(c["name"] for c in cities))

    if not args.resume:
        for c in cities:
            p = config.get_city_csv_path(c["name"])
            if os.path.exists(p):
                os.remove(p)

    start_idx = 0
    if args.resume and checkpoint.get("city"):
        for i, c in enumerate(cities):
            if c["url_slug"] == checkpoint["city"]:
                start_idx = i
                break

    cmd_q    = queue.Queue()
    stop_ev  = threading.Event()
    threading.Thread(
        target=console_listener,
        args=(cmd_q, stop_ev),
        daemon=True,
    ).start()

    print(HELP_TEXT)
    logger.info("🚀 Scrape başlıyor...")

    try:
        for city in cities[start_idx:]:
            try:
                await scrape_city(city=city, checkpoint=checkpoint, cmd_queue=cmd_q)
                checkpoint = {}
            except SkipCitySignal:
                logger.warning("⏭️  %s atlandı.", city["name"])
                checkpoint = {}
                continue
            except StopSignal:
                logger.warning("🛑 Kullanıcı durdurdu.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop_ev.set()

    clear_checkpoint()
    logger.info("\n✅ Tamamlandı.")


def _build_parser():
    p = argparse.ArgumentParser(description="Sahibinden kira scraper")
    p.add_argument("--resume",  action="store_true", help="Checkpoint'ten devam et")
    p.add_argument("--city",    type=str, default=None, help="Tek şehir (url slug)")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug loglama")
    return p


def main():
    args = _build_parser().parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()