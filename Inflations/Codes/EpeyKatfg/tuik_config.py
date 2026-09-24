"""
tuik_config.py — EpeyKatfg: epey category → COICOP mapping and TÜİK 2026 weights.

Compute-layer config for the EpeyKatfg sector (Layer 2 of the katfg harness
plan, docs/site-analysis/katfg-harness-plan.md §3).

Provides
--------
- ``EPEY_CATEGORY_TO_TUIK`` : epey category slug → TÜİK main-group code
- ``TUIK_WEIGHTS``          : 2026 CPI weights (2025=100) for the groups that
                              EpeyKatfg contributes to
- ``normalised_weights``    : rescale weights to 100% over a present subset

Weight values are identical to the repository-wide table
(Inflations/Codes/tuik_config.py, TÜİK 2026, base 2025=100).
Mappings flagged "verify" in the harness plan are kept for now; drop any line
here and re-run materialize.py to exclude that category from the pipeline.
"""

# ── epey category slug → COICOP main group ────────────────────────────────────
EPEY_CATEGORY_TO_TUIK = {
    "akilli-saat": "08",
    "akilli-telefonlar": "08",
    "anakart": "08",
    "ates-olcer": "06",
    "ayakkabi": "03",
    "banyo-tartisi": "13",
    "bebek-arabasi": "13",
    "bebek-bezi": "13",
    "bellek-ram": "08",
    "biberon": "13",
    "bilgisayar-kasasi": "08",
    "bisiklet": "09",
    "blender": "05",
    "bulasik-makinesi": "05",
    "buzdolabi": "05",
    "camasir-kurutma-makinesi": "05",
    "camasir-makinesi": "05",
    "cay-makinesi": "05",
    "derin-dondurucu": "05",
    "dikey-supurge": "05",
    "dondurma-makinesi": "05",
    "drone": "09",
    "ekmek-kizartma-makinesi": "05",
    "ekran-karti": "08",
    "elektrikli-dis-fircasi": "13",
    "epilator": "13",
    "fritoz": "05",
    "hafiza-karti": "08",
    "hava-nemlendirici": "05",
    "hava-temizleyici": "05",
    "isitici": "05",
    "islemci": "08",
    "kahve-makinesi": "05",
    "klavye-mouse": "08",
    "klima": "05",
    "kombi": "05",
    "kondisyon-bisikleti": "09",
    "kosu-bandi": "09",
    "kulaklik": "08",
    "kurutma-makinesi": "05",
    "laptop": "08",
    "lastik": "07",
    "masaj-aleti": "06",
    "masaustu-bilgisayar": "08",
    "matkap": "05",
    "monitor": "08",
    "nebulizator": "06",
    "ocak": "05",
    "oksimetre": "06",
    "oyuncak": "09",
    "parfum": "13",
    "robot-supurge": "05",
    "saat": "03",
    "sac-kurutma-makinesi": "13",
    "sac-sekillendirici": "13",
    "sarj-aleti": "08",
    "sarj-kablosu": "08",
    "seker-olcum-cihazi": "06",
    "ses-sistemi": "09",
    "spor-aletleri": "09",
    "spor-ayakkabi": "03",
    "su-sebili": "05",
    "supurge": "05",
    "tablet": "08",
    "tansiyon-aleti": "06",
    "tasınabilir-disk": "08",
    "televizyon": "09",
    "telsiz-telefon": "08",
    "tencere-tava": "05",
    "tens-cihazi": "06",
    "testere": "05",
    "tiras-makinesi": "13",
    "tost-makinesi": "05",
    "tuslu-telefon": "08",
    "usb-hub": "08",
    "utu": "05",
    "valiz": "03",
    "vantilator": "05",
    "yatak": "05",
    "yazici": "08",
    "yemek-takimi": "05",
}

# ── TÜİK 2026 TÜFE main-group weights (2025=100) for covered groups ──────────
TUIK_WEIGHTS = {
    "03": {"name": "Giyim ve ayakkabı",                                   "weight": 7.9038},
    "05": {"name": "Mobilya, mefruşat ve ev ekipmanları",                  "weight": 7.9201},
    "06": {"name": "Sağlık",                                              "weight": 2.7923},
    "07": {"name": "Ulaştırma",                                           "weight": 16.6169},  # tentative: lastik (tyres)
    "08": {"name": "Bilgi ve iletişim",                                    "weight": 3.1035},
    "09": {"name": "Eğlence, dinlence, spor ve kültür",                    "weight": 4.3382},
    "13": {"name": "Kişisel bakım, sosyal koruma ve diğer",                "weight": 4.4935},
}


def normalised_weights(present_codes: list[str]) -> dict:
    """Rescale weights to sum to 100% over the present (tracked) codes."""
    raw = {c: TUIK_WEIGHTS[c]["weight"] for c in present_codes if c in TUIK_WEIGHTS}
    total = sum(raw.values())
    if total == 0:
        return {}
    return {c: (w / total) * 100.0 for c, w in raw.items()}
