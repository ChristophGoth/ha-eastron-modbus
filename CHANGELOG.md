# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [Semantic Versioning](https://semver.org/lang/de/).

## [0.2.1]

### Behoben

* "Gerät löschen" schlug mit `AttributeError: 'ConfigEntry' object has no
  attribute 'runtime_data'` fehl, wenn der Eintrag nicht geladen war. Zähler
  werden jetzt über eine am Gerät hinterlegte Slave-Adresse aufgelöst, sodass
  das Entfernen auch bei nicht startender Integration funktioniert. Bereits
  angelegte Geräte werden über ihren Namen zugeordnet.

### Geändert

* Ein Zähler, der nicht antwortet, verhindert nicht mehr den Start der
  gesamten Integration. Die übrigen Zähler am Gateway werden normal
  eingerichtet, der fehlende wird protokolliert und übersprungen. Nur wenn
  kein einziger Zähler antwortet, wird der Eintrag zurückgestellt — dann
  liegt es am Gateway, nicht am Zähler.

## [0.2.0]

### Hinzugefügt

* Einzelne Zähler lassen sich nachträglich entfernen und hinzufügen, ohne die
  Integration neu einzurichten: über die Optionen des Eintrags oder direkt über
  "Gerät löschen" auf der Geräteseite eines Zählers. Die übrigen Zähler am
  selben Gateway behalten dabei ihre Entitäten und deren Verlauf.

### Geändert

* Die Optionen zeigen jetzt ein Menü. Das Abfrageintervall liegt darin unter
  "Abfrageintervall ändern".

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
