# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [Semantic Versioning](https://semver.org/lang/de/).

## [0.1.2]

### Behoben

* `zip_release` aus `hacs.json` entfernt. HACS las Manifest und `hacs.json`
  dadurch aus dem Release-Asset statt aus dem Repository, was die
  HACS-Validierung nicht auflösen konnte.

## [0.1.1]

### Geändert

* Releases entstehen jetzt vollständig in GitLab: das HACS-Zip wird dort als
  Release-Asset veröffentlicht und unverändert nach GitHub gespiegelt.
* Die Prüfungen von hassfest laufen in der Pipeline mit, die HACS-Validierung
  nach dem Spiegeln auf GitHub.

## [0.1.0]

* Erste Veröffentlichung: Eastron-SDM-Energiezähler über ein
  Modbus-Ethernet-Gateway (RTU over TCP), vollständig lokal. Mehrere Zähler
  teilen sich ein Gateway und erscheinen je als eigenes Gerät.
* Unterstützte Modelle: SDM120 (1P2W) und SDM630 (3P4W). Das Modell wird
  anhand des Meter-Codes automatisch erkannt.
* Blindenergie-Register nutzen die Geräteklasse `reactive_energy`; dadurch
  setzt die Integration Home Assistant 2025.6.0 voraus.
* Diagnose je Zähler sowie ein mitgeliefertes Marken-Icon.
