# MaderLunch — Auth-Patch (Entra App Roles + lokale User)

Patch zum bestehenden MaderLunch-Skelett. Führt das hierarchische Rollenmodell
und die Entra-Integration via App Roles ein.

## Übersicht der Änderungen

| Datei | Art | Inhalt |
|---|---|---|
| `accounts/models.py` | **ersetzen** | `role` und `auth_source` an `UserProfile`, `EntraIdentity` erweitert, `EntraGroupMapping` entfernt |
| `accounts/adapters.py` | **NEU** | allauth-Adapter mit App-Roles-Mapping, JIT-Provisioning, E-Mail-Konflikt-Verknüpfung |
| `accounts/permissions.py` | **NEU** | Decorators `manager_required`, `admin_required`; Mixins für CBVs |
| `accounts/admin.py` | **ersetzen** | `EntraGroupMapping` raus, Rollen-Felder rein |
| `accounts/migrations/0002_role_auth_source.py` | **NEU** | Migration für neue Felder |
| `accounts/management/commands/createlocaluser.py` | **ersetzen** | `--role`-Parameter, ADMIN setzt is_staff/is_superuser |
| `accounts/urls.py` | **entfernen** | allauth liefert jetzt /accounts/* |
| `config/settings.py` | **ersetzen** | allauth + Microsoft-Provider integriert |
| `config/urls.py` | **anpassen** | `path("accounts/", include("allauth.urls"))` |
| `requirements.txt` | **ergänzen** | `django-allauth`, `PyJWT[crypto]`, `requests` |
| `.env.example` | **ergänzen** | `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` |
| `templates/account/login.html` | **NEU** | Login-Seite mit Microsoft-Button + lokalem Login |
| `templates/socialaccount/authentication_error.html` | **NEU** | Fehlerseite bei Entra-Login-Problemen |

## Rollenmodell (Entscheidungsdoku)

Drei Rollen, hierarchisch:

```
USER < MANAGER < ADMIN
```

| Rolle | Quelle | Rechte |
|---|---|---|
| **USER** | Entra-Gruppe `MaderLunch-Users` ODER lokales Konto mit `role=USER` | Essen bestellen |
| **MANAGER** | Entra-Gruppe `MaderLunch-Managers` ODER lokales Konto mit `role=MANAGER` | + Essen/Preise verwalten, Exporte, lokale User & Gäste pflegen |
| **ADMIN** | Entra-Gruppe `MaderLunch-Admins` ODER lokales Konto mit `role=ADMIN` | + Django-Admin (`is_staff` + `is_superuser`) |

Hierarchie wird in Code über Properties am `UserProfile` abgebildet:

```python
profile.is_manager   # True für MANAGER und ADMIN
profile.is_app_admin # True nur für ADMIN
```

In Views:

```python
@manager_required
def export_orders(request): ...

@admin_required
def manage_system(request): ...
```

In Templates:

```django
{% if user.profile.is_manager %}
  <a href="{% url 'lunch:export' %}">Export</a>
{% endif %}
```

## Entra-Konfiguration (Voraussetzung)

Muss in Entra Admin Center fertig sein, bevor der Code lauffähig wird:

1. App-Registrierung "MaderLunch" mit Redirect-URIs:
   - `https://lunch.mader.eu/accounts/microsoft/login/callback/`
   - `http://localhost:8000/accounts/microsoft/login/callback/` (Dev)
2. Drei App Roles (Value-Felder exakt so):
   - `User`
   - `Manager`
   - `Admin`
3. Drei Sicherheitsgruppen den App Roles zugewiesen:
   - `MaderLunch-Users` → User
   - `MaderLunch-Managers` → Manager
   - `MaderLunch-Admins` → Admin
4. Enterprise Application: `Assignment required = Yes`
5. API Permissions: `openid`, `profile`, `email`, `User.Read` (delegated) + Admin Consent
6. Client Secret erzeugt, Value sicher abgelegt

Der `roles`-Claim wird automatisch ins ID-Token geschrieben, sobald App Roles
definiert und zugewiesen sind. Eine zusätzliche Optional-Claim-Konfiguration
ist nicht nötig (und in der UI auch nicht vorgesehen).

## Login-Verhalten

**Lokaler Login** (`/accounts/login/` mit Username + Passwort):
- Funktioniert für lokale Konten, die per `createlocaluser` angelegt wurden
- Break-Glass-Admin nutzt diesen Weg

**Entra-Login** (`/accounts/microsoft/login/`):
- User klickt "Mit Microsoft-Konto anmelden" → OAuth-Redirect zu Entra
- Bei Erfolg landet er auf Callback-URL mit ID-Token
- Adapter:
  1. Prüft, ob `sociallogin.is_existing` (bekannter Entra-Account) → wenn ja: nur Rollen syncen
  2. Sonst: prüft E-Mail-Konflikt mit lokalem User → wenn ja: verknüpfen
  3. Sonst: legt neuen User + UserProfile + EntraIdentity an (JIT)
  4. Bei jedem Login: `roles`-Claim → höchste Rolle → `profile.role` + Django-Flags
  5. `EntraIdentity.last_login_at` und `last_roles_claim` werden aktualisiert

**Wichtig:** Bei Entra-Logins ist Entra die Source-of-Truth für die Rolle.
Manuelle Änderungen an `profile.role` über den Django-Admin werden beim
nächsten Entra-Login überschrieben. Für lokale Konten gilt das nicht.

## Migration / Inbetriebnahme

```bash
# 1. Code-Patches anwenden (Dateien überschreiben)

# 2. Dependencies installieren
docker compose build web

# 3. Migration ausführen
docker compose run --rm web python manage.py migrate accounts

# 4. .env mit Entra-Werten füllen, dann
docker compose up -d

# 5. Break-Glass-Admin lokal anlegen (für Notfall, wenn Entra ausfällt)
docker compose exec web python manage.py createlocaluser \
    --username breakglass --first Break --last Glass \
    --email breakglass@mader.eu --role ADMIN \
    --no-force-password-change
# Passwort sicher im IT-Tresor speichern
```

## Test-Plan

In dieser Reihenfolge testen:

1. **Lokaler Break-Glass-Login** → `/admin/` öffnet sich → IT-Backup gesichert.
2. **Entra-Login als User-Gruppe-Mitglied** → wird angelegt, `role=USER`, kein `/admin/`-Zugriff.
3. **Entra-Login als Manager-Gruppe-Mitglied** → `role=MANAGER`, Manager-Views erreichbar, `/admin/` nicht.
4. **Entra-Login als Admin-Gruppe-Mitglied** → `role=ADMIN`, `/admin/` erreichbar.
5. **Rollen-Wechsel-Test**: User in Entra-Gruppe verschieben (z.B. von Users in Managers),
   Browser-Cookies löschen, neu einloggen → `profile.role` aktualisiert sich sofort.
6. **E-Mail-Konflikt-Test**: lokalen User mit `xyz@mader.eu` per `createlocaluser` anlegen,
   dann mit demselben Entra-Konto einloggen → kein Duplikat, `auth_source` wechselt auf `ENTRA`.

## Debugging

Wenn der `roles`-Claim nicht ankommt, ist im Log zu sehen:

```
INFO accounts.adapters: Entra-Login synchronisiert: user=... role=USER is_staff=False roles_claim=[]
```

Bei leerem `roles_claim` prüfen:
1. User wirklich in einer Entra-Sicherheitsgruppe? (`MaderLunch-Users` / `-Managers` / `-Admins`)
2. Sicherheitsgruppe einer App Role in der Enterprise App zugewiesen?
3. Admin-Consent erteilt? (API Permissions in der App-Registrierung)

Token-Inhalt direkt prüfen: https://jwt.ms (Microsoft-Tool). Dazu in der App-Registrierung
temporär eine Redirect-URI `https://jwt.ms` hinzufügen, dort einloggen, Token-Inhalt sehen,
URI wieder entfernen.

## Was bewusst NICHT geändert wurde

- `lunch/*`, `billing/*`, `audit/*` — Geschäftslogik bleibt wie sie ist
- `GuestOrder` bleibt — alternative Lösung für "Esser ohne Login" über Host-Mechanik
- Bestell- und Speiseplan-Logik
- Subsidy-Resolver
- Audit-Hooks
- Docker-Setup (Compose, Dockerfile, entrypoint.sh)

Falls später noch `Eater`-Profile für Gäste *ohne* Host-Bezug nötig werden,
wäre das ein eigener kleiner Patch in `lunch/models.py`. Im aktuellen Scope
nicht enthalten.
