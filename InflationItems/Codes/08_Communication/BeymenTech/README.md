# Beymen teknoloji scraper (GitHub Actions)

## TÜİK 08 kalemleri

| Kalem | Ürün var mı | Kaynak (Beymen "Teknoloji" kategorisi 95935) |
|---|---|---|
| Cep telefonu | ✅ | iPhone akıllı telefonlar |
| Bilgisayar | ✅ | Dizüstü bilgisayarlar, tabletler |
| Bilgisayar çevre birimleri | ✅ | Monitör, klavye, mouse, yazıcı, harici disk |
| Ses ve görüntü ekipmanı | ✅ | Kulaklık, hoparlör, fotoğraf makinesi, projeksiyon cihazı |
| Televizyon | ✅ | Smart TV'ler |
| Diğer iletişim cihazları | ✅ | Akıllı saatler |
| Bilgi ve iletişim aksesuarları | ✅ | Kılıflar, şarj cihazları, saat kordonları |
| Cep telefonu hizmet ücreti | — | |
| İnternet hizmet ücreti | — | |
| Bilgi ve iletişim ekipmanı bakım / onarım ücreti | — | |
| Dijital içerik / streaming platform aboneliği | — | |

Kapsam dışı (aynı CSV'ye yazılır): oyun konsolları ve VR gözlükleri, küçük ev aletleri,
kişisel bakım cihazları. Kategori, sunucudaki `../Beymen/` ile aynı (2026-10-11'de
10.770 ürün, sunucu dosyasında 10.933).

## Nasıl çalışır

SeleniumBase (UC modu) ile `beymen.com/tr/teknoloji-95935` sayfası açılıp cookie'ler alınır;
ürünler sonra bu cookie'lerle `/api/product/list` API'sinden sayfa sayfa `requests` ile çekilir.

## Çalıştırma

```bash
python InflationItems/Codes/08_Communication/BeymenTech/scraper.py
```

`.github/workflows/beymen.yml` ile her gün 13:00'te (İstanbul) çalışır ve CSV'yi commit'ler.

## Çıktı

`InflationItems/Datas/08_Communication/Beymen/beymen_tech_YYYY-MM-DD.csv`

`product-name, product-price`
