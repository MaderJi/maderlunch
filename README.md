# MaderLunch

Interne Kantinen- und Essensbestell-App der Mader GmbH & Co. KG.

- **Stack:** Django 5, PostgreSQL 16, Gunicorn, Bootstrap 5, HTMX (optional), Docker Compose.
- **Architektur:** schlanker Monolith. Zwei Container (`web` + `db`). TLS-Terminierung durch FortiGate-VIP.
- **Auth:** lokale Benutzerkonten + (vorbereitet) Microsoft Entra ID via OIDC.

> Ausführliche Architektur-, Datenmodell- und Auth-Dokumentation siehe `MADERLUNCH_ARCHITECTURE.md` (separat in der Projektablage).

---

## Schnellstart (Dev)

Voraussetzung: Docker + Docker Compose v2.

```bash
cp .env.example .env
# In .env mindestens DJANGO_SECRET_KEY und POSTGRES_PASSWORD setzen.
docker compose up -d --build
```

Beim ersten Start laufen Migrations + collectstatic automatisch (siehe `scripts/entrypoint.sh`).

### Seed-Daten anlegen (nur Dev)

```bash
docker compose exec web python manage.py seed_dev
```

Dadurch werden angelegt:

- 4 Standorte (Leinfelden-Echterdingen, Ditzingen, Heidenheim, Eichenau)
- je eine Kantine pro Standort
- Beispiel-Kategorien, Allergene, Zusatzstoffe, Produkte
- Speisepläne für die nächsten 5 Werktage
- Kostenstellen, Default-Zuschuss 30 %
- Demo-Login `admin` / `Admin12345!` (Admin)
- Demo-Login `user` / `User12345!` (normaler User)

**Niemals in Produktion ausführen.**

### Eigenen lokalen Benutzer anlegen

```bash
docker compose exec web python manage.py createlocaluser \
    --username m.mueller --first Marie --last Müller \
    --email marie.mueller@mader.eu --role User --employee-id 12345
```

Das Initialpasswort wird **einmal** auf der Konsole ausgegeben — danach an den Nutzer übergeben. Beim ersten Login wird ein Passwortwechsel erzwungen.

### Health-Check

```
GET /healthz/
```

Antwortet mit `200 OK` und JSON `{"status":"ok","db":"ok"}`, sonst `503`.

---

## Betrieb hinter FortiGate-VIP (TLS-Offload)

Der Compose-Stack läuft bewusst ohne eigenen Reverse Proxy. TLS wird auf der Forti terminiert (konsistent zu anderen internen Mader-Apps).

**Forti-VIP-Konfiguration (Pflicht-Header):**

| Header              | Wert      |
|---------------------|-----------|
| `X-Forwarded-Proto` | `https`   |
| `X-Forwarded-For`   | Client-IP |
| `X-Forwarded-Host`  | FQDN      |

Diese Header müssen am Frontend **gesetzt** werden, nicht nur durchgereicht — sonst kann ein interner Client `X-Forwarded-Proto: https` mitschicken und Django täuschen.

**Django-Konfiguration (`.env` produktiv):**

```bash
DJANGO_BEHIND_TLS_PROXY=True
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=lunch.intern.mader.eu
```

`DJANGO_BEHIND_TLS_PROXY=True` aktiviert in `settings.py`:

- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
- `USE_X_FORWARDED_HOST = True`
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`

**Empfohlenes Port-Binding** in `docker-compose.yml`:

```yaml
ports:
  - "10.x.x.x:8000:8000"   # nur an VM-interne IP binden
```

So ist `web` nur über die Forti-VIP erreichbar.

---

## Microsoft Entra ID (Phase 2 — vorbereitet, im MVP nicht aktiv)

Im Code vorbereitet:

- `accounts/auth_backends.py::EntraOIDCBackend` (Verknüpfung über stabile `tenant_id` + `object_id`)
- `accounts/models.py::EntraIdentity`, `EntraGroupMapping`
- `mozilla-django-oidc` ist in `requirements.txt`.
- Alle OIDC-Settings in `settings.py` sind hinter `OIDC_ENABLED` gekapselt.

**Aktivierung (Checkliste):**

1. App-Registrierung im Mader-Tenant anlegen, Redirect-URI: `https://lunch.intern.mader.eu/oidc/callback/`.
2. Client-Secret erzeugen, Tenant-ID notieren.
3. Sicherstellen, dass das interne CA-Zertifikat auf allen Endgeräten als Root vertraut wird (GPO/Intune/MDM).
4. In `.env` setzen: `OIDC_ENABLED=True`, `OIDC_RP_CLIENT_ID`, `OIDC_RP_CLIENT_SECRET`, `OIDC_TENANT_ID`.
5. In `config/settings.py`: `mozilla_django_oidc` zu `INSTALLED_APPS` hinzufügen, Backend in `AUTHENTICATION_BACKENDS` aktivieren.
6. In `config/urls.py`: `path("oidc/", include("mozilla_django_oidc.urls"))` aktivieren.
7. Container neu bauen und starten.

**Verknüpfungslogik (Erstanmeldung):**

- Existiert bereits ein lokales `UserProfile` mit identischer E-Mail → automatische Verknüpfung, Audit-Eintrag `entra.link`.
- Existiert kein Profil → Login wird abgelehnt (keine Auto-Anlage im MVP). Audit-Eintrag mit `result="no_local_profile"`.

---

## Backup / Restore (PostgreSQL)

**Backup:**

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup_$(date +%F).sql
```

**Restore:**

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup_YYYY-MM-DD.sql
```

Empfehlung: tägliches `pg_dump` per Cron-Job auf der VM, Auslagerung über das bestehende Veeam-Backup der VM.

---

## Audit-Log

- Alle sicherheitsrelevanten Aktionen werden in der Tabelle `audit_auditlog` erfasst.
- Action-Keys sind in `audit/services.py::ACTIONS` whitelistet (Tippfehler-Schutz).
- Sensible Felder werden vor dem Speichern in `meta` automatisch redigiert (Passwörter, Tokens, Cookies).
- Im Django-Admin ist der Log read-only — Append-Only auf App-Ebene.

---

## CSV-Export

- Endpunkt: `/billing/export/orders.csv?from=YYYY-MM-DD&to=YYYY-MM-DD` (nur Admin)
- Schema-Version steht in der ersten Spalte (`schema_version`).
- Bei jedem Schema-Wechsel **`CSV_SCHEMA_VERSION`** in `billing/exporters.py` hochzählen + dokumentieren.
- Sortierung deterministisch → Reproduzierbarkeit garantiert.
- UTF-8 mit BOM, Trennzeichen `;` (Excel-DE).

---

## Wichtige URLs

| Pfad                      | Zweck                                |
|---------------------------|--------------------------------------|
| `/`                       | Dashboard (heute)                    |
| `/plan/`                  | Wochenansicht Speiseplan             |
| `/my/`                    | Meine Bestellungen                   |
| `/pickup/`                | Ausgabeansicht (Admin)               |
| `/billing/export/`        | CSV-Export-Formular (Admin)          |
| `/admin/`                 | Django-Admin (Stammdaten, Audit-Log) |
| `/accounts/login/`        | Lokaler Login                        |
| `/accounts/password/change/` | Passwort ändern                  |
| `/healthz/`               | Health-Check                         |

---

## Nicht im MVP (bewusst weggelassen)

- Eigener Reverse Proxy (Forti macht TLS).
- Redis (Sessions in DB — bei 60 Usern völlig ausreichend).
- Celery / asynchrone Worker (Exporte synchron).
- Prometheus/Grafana (Logs + Health-Endpoint reichen).
- PDF-Export (CSV-Hooks vorhanden).
- Bewirtung-UI (Modell `GuestOrder` existiert, View kommt in Phase 2).
- Entra-Group → Django-Group Mapping aktiv (Tabelle existiert, Resolver in Phase 2).
- E-Mail-Benachrichtigungen.

---

## Lizenz / Eigentum

Internes Werk der Mader GmbH & Co. KG. Eigenständige Entwicklung. Übernimmt keine Texte, Logos oder Designs Dritter.
