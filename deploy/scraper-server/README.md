# TechnologicalProducts scraper sunucusu

Hedef sunucu: Ubuntu 22.04, 2 vCPU, 1.9 GB RAM, cron. Kod kaynağı:
`InflationItems/Codes/TechnologicalProducts/` (upstream `TUGC3/InflationResearchStudy`
commit `9cb747a`, 2026-09-22, sunucu için düzenlendi).

## Sunucudaki yapı

`<repo-root>` = repoyu klonladığın dizin. Script'ler kendi konumundan bulur, sabit yol yok.

```
<repo-root>/
  deploy/scraper-server/   setup.sh, crontab.txt, requirements.txt, bin/ (kaynak)
  bin/                     setup.sh'ın kopyaladığı çalışan script'ler:
    run_scraper.sh         tek scraper'ı kilit + timeout + disk kontrolüyle çalıştırır
    cleanup.sh             günlük: 30 günden eski loglar, geçici Chrome profilleri
    export_data.sh         haftalık: CSV'leri tek .tar.gz yapar (--delete ile siler)
  venv/                    Python 3.11 (uv), sabit sürümlü paketler
  .env                     opsiyonel ayarlar
  InflationItems/Codes/TechnologicalProducts/...              scraper kodu
  InflationItems/Datas/TechnologicalProducts/<Mağaza>/*.csv   çıktı
  server_logs/<scraper>_<tarih>.log   her çalıştırmanın tam logu
  log.txt                  her çalıştırma için tek satır: OK / FAILED / TIMEOUT / SKIPPED
```

`bin/`, `venv/`, `server_logs/`, `export/`, `log.txt`, `.env` gitignore'da.

## Kurulum (bir kere)

Sadece gereken iki klasörü çeken sparse clone; repodaki diğer mağazaların verileri inmez
ve sonradan `git pull` scraper çıktılarıyla çakışmaz (`InflationItems/Datas` checkout
dışında kalır):

```bash
apt-get update && apt-get install -y git
git clone --filter=blob:none --no-checkout https://github.com/vinnipukh/inflationstudymirror.git <repo-root>
cd <repo-root>
git sparse-checkout set --cone deploy/scraper-server InflationItems/Codes/TechnologicalProducts
git checkout main
bash deploy/scraper-server/setup.sh
```

`setup.sh` tekrar çalıştırılabilir. Yaptıkları: saat dilimini Europe/Istanbul yapar,
Google Chrome kurar, uv ile Python 3.11 venv oluşturur, sabit sürümlü paketleri
yükler, `bin/` script'lerini kopyalar, crontab'a sadece kendi bloğunu yazar (başka
cron işlerine dokunmaz).

Kontrol: `bin/run_scraper.sh huawei && tail -3 log.txt`

Kod güncellemesi (repoda scraper değişirse):

```bash
cd <repo-root> && git pull && bash deploy/scraper-server/setup.sh
```

Git'siz alternatif: Windows'ta repo kökünde paketi yap, sunucuda `<repo-root>` içine aç,
`bash setup.sh` çalıştır.

```powershell
tar --exclude __pycache__ -czf scraper.tgz -C deploy/scraper-server . -C ../.. InflationItems/Codes/TechnologicalProducts
```

## Program (Istanbul saati, her gün)

Süre, ürün sayısı ve tepe bellek 2026-09-28 tarihli tam çalıştırmalardan ölçüldü
(geliştirici PC'si; sunucuda CPU daha yavaş, timeout'lar ~3-4 kat pay bırakır).
Bellek = USS (process'e özel bellek, Chrome alt process'leri dahil).

| Saat | İş | Ölçülen süre | Ürün | Tepe RAM | Timeout | Browser |
|---|---|---|---|---|---|---|
| 00:30 | cleanup | - | - | - | - | - |
| 01:00 | samsung | 1 dk | 412 | 61 MB | 20 dk | yok |
| 01:10 | huawei | 0.5 dk | 108 | 22 MB | 10 dk | yok |
| 01:20 | pozitif | 1 dk | 1.239 | 30 MB | 15 dk | yok |
| 01:30 | dr | 1 dk | 1.345 | ~95 MB | 20 dk | yok |
| 02:00 | beymen | 10.5 dk | 10.659 | 22 MB | 45 dk | sadece 403 gelirse |
| 03:00 | koctas | 16.5 dk | 5.617 | 619 MB | 60 dk | her zaman, her 6 sayfada yenilenir |
| 04:00 | vatan | ~19 dk (yavaşlatıldı, ~45 dk bekle) | 5.497 | ~105 MB | 120 dk | yok |

Tüm işler aynı kilidi (`flock /tmp/scraper.lock`) kullanır, yani biri geç kalırsa
sıradaki bekler; iki scraper asla aynı anda çalışmaz. Her çalıştırmadan sonra
kalan Chrome process'leri öldürülür.

## Haftalık rutin

```bash
<repo-root>/bin/export_data.sh --delete
```

Arşiv dosyası: `<repo-root>/export/data_<tarih>.tar.gz`. Bugünün dosyaları arşive
girmez (o sırada bir scraper yazıyor olabilir). Windows'ta indir:

```powershell
scp root@SUNUCU_IP:<repo-root>/export/data_*.tar.gz .
```

İndirdikten sonra sunucuda: `rm <repo-root>/export/data_*.tar.gz`

## Durum kontrolü

```bash
tail -30 <repo-root>/log.txt
```

`SKIPPED: only N MB free` görürsen disk dolmuş demektir: export yap, sonra sil.
Disk kontrolü 1.5 GB boş alanın altında scraper çalıştırmaz.
`FAILED` görürsen ilgili `server_logs/<scraper>_<tarih>.log` dosyasına bak.

## Düzenlemeler (upstream'e göre)

Kapsam her mağazada sitemap / sitenin kendi ürün sayısıyla kontrol edildi (2026-09-28).

- **Huawei** (68 → 108): Selenium kaldırıldı. Tam e-ticaret kataloğu
  (`/.rest/service/ecommerce/v1/products/tr`, ~290 ID) + fiyat API'si
  (`queryMinPriceAndInv`); sadece fiyatı olanlar (satışta) yazılır. İsim kategori
  sayfalarının JSON'undan; aksesuarlar hiçbir sayfada listelenmiyor, onların adı URL'den
  üretilir ve `listed_on_site=False` olur. Garanti/test (`offer`) ürünleri hariç.
- **Pozitif** (507 → 1.239): kategori sayfası taraması yerine WooCommerce Store API
  (`/wp-json/wc/store/v1/products`, tüm katalog). Stokta olmayan ve outlet ürünler artık
  atılmıyor; `in_stock`, `is_outlet` sütunları var.
- **Beymen** (9.600 → 10.659): sabit 200 sayfa limiti ~1.000 ürünü kesiyordu; artık API'nin
  `totalPageCount` değeri kullanılıyor, ürün ID ile tekilleştiriliyor. Önce browser'sız
  (`curl_cffi`, Chrome TLS); 403 gelirse tek seferlik headless Chrome ile Akamai cookie'si.
- **Samsung** (405 → 412): upstream `KeyError: 'sku'` ile çöküyordu, düzeltildi; `id` ve
  `category` sütunları. Lifestyle TV (The Frame) kategorisi eklendi. Kategori taramasından
  sonra b2c sitemap'indeki tüm model kodları kartvizit API'sine sorulur, fiyatlı olup
  eksik kalanlar eklenir (sitemap'teki ~950 model satıştan kalkmış, fiyatsız).
- **Koçtaş** (1.671 → 5.617): 4 kategori ID'si yanlış kategoriye gidiyordu (106001 =
  Jeneratörler vb.), düzeltildi; `site_category` sitenin gerçek kategori adını yazar.
  Sayfa limiti 7 → 40 (kategoriler 25-27 sayfa). Headless UA düzeltmesi (Akamai
  "HeadlessChrome"u reddediyor), Chrome sürümü otomatik algılanıyor. RAM: 3. parti
  script'ler bloklanıyor, Chrome her 6 sayfada ve çökünce yenileniyor (3.4 GB → 619 MB).
  `--disable-site-isolation-trials` / `--js-flags` gibi RAM flag'leri Akamai engeline
  sebep oldu, kullanmayın.
- **DR** (1.345): değişiklik yok; sitede görünen kategori sayılarıyla uyumlu. Paralellik 1.
- **Vatan** (5.497): çıktı `Datas/` altına. Format upstream ile aynı: başlıksız, `;`
  ayraçlı `isim;fiyat`. Aynı gün tekrarlanan taramalardan sonra Cloudflare IP'yi
  30+ dk banladı (Error 1015); bekleme süreleri 1.5-3 sn'ye çıkarıldı, ban sürerse
  tarama durur, veri kaydedilir ve `log.txt`'de FAILED görünür.

## .env (opsiyonel)

```
CHROME_VERSION_MAIN=153   # Chrome sürüm algılama bir gün bozulursa sabitle
```
