# TCGIP — Trading Card Game Inventory Project

Progetto Django per gestire e valorizzare una collezione di carte (Magic, Pokémon, One Piece...).

## Funzionalità principali

- **Collezione**: cataloga le tue copie fisiche (`owned` / `sold`), con foto, condizioni, grading PSA/BGS/CGC/SGC, prezzi di acquisto e valore di mercato. Vista **per gioco** (sezioni con logo e conteggio) oppure lista piatta filtrata/paginata.
- **Grafico andamento valore**: la home mostra il valore totale della collezione nel tempo con menu **3D / 7D / 14D / 1M / 3M / 6M / 1Y / 5Y / ALL**. Il grafico usa valori *relativi* (primo punto = 100) e mostra la variazione % nel periodo selezionato.
- **Snapshot giornalieri**: `ValueSnapshot` salva una riga per giorno/utente; viene creata/aggiornata automaticamente visitando la home o modificando la collezione.
- **Catalogo con immagini**: il catalogo si popola automaticamente da API pubbliche con l'immagine vera di ogni carta:
  - **Magic** → Scryfall (`import_scryfall`)
  - **Pokémon** → Pokémon TCG API (`import_pokemon`, PNG)
  - **Yu-Gi-Oh!** → YGOProDeck (`import_ygo`, JPG)
  - Altri giochi/One Piece → import CSV manuale dal catalogo.
- **Aggiungi/modifica carta**: la carta si cerca da una casella di ricerca (autocomplete su `GET /cards/api/search/?q=`) invece di un `<select>` con migliaia di voci.
- Il marketplace è **disabilitato per ora** (codice ancora nella cartella `marketplace/`, non nell'`INSTALLED_APPS`).

## Setup (sviluppo)

```bash
uv sync
python manage.py migrate
python manage.py runserver
```

Crea un superuser con `python manage.py createsuperuser`.

## Seed del catalogo da Scryfall

Popola il database con espansioni e carte reali (ogni carta ha `rarity` e `image_url`). Tutti i comandi sono **idempotenti**: rieseguirli non crea duplicati e completa eventuali campi vuoti.

**Magic (Scryfall, PNG):**
```bash
python manage.py import_scryfall --sets one               # una espansione
python manage.py import_scryfall --sets one,neo,woe --limit 500
python manage.py import_scryfall --sets one --download-images          # copie locali jpg
python manage.py import_scryfall --sets one --download-images --full-images  # PNG ad alta risoluzione
```

**Pokémon (Pokémon TCG API, PNG):**
```bash
python manage.py import_pokemon --sets sv1,mew
python manage.py import_pokemon --sets base1 --api-key TUA_CHIAVE --download-images
```
La chiave della Pokémon TCG API è gratuita (https://dev.pokemontcg.io); senza chiave i limiti di velocità sono più bassi ma funziona.

**Yu-Gi-Oh! (YGOProDeck, JPG, senza chiave):**
```bash
python manage.py import_ygo --sets "Justice Hunters"
python manage.py import_ygo --sets "Legend of Blue Eyes White Dragon" --download-images
```

**Altri giochi (One Piece, personalizzate):** import CSV dal pannello admin (`/admin-tools/import-cards/`) o dalla tua collezione (`/collection/import/`).

## Grafici e snapshot

- Lo snapshot di oggi viene ricalcolato a ogni visita della home e a ogni modifica della collezione (aggiunta, modifica, vendita, cancellazione, import CSV).
- Lo storico giornaliero si costruisce visitando la home nei vari giorni.

## Produzione (deploy)

L'app è pronta per i classici "container/web service" (Render, Railway, Fly.io, Heroku, una VPS...):

1. **Variabili d'ambiente** (vedi `.env.example`):
   - `DJANGO_SECRET_KEY` — genera una con `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
   - `DJANGO_DEBUG=False`
   - `DJANGO_ALLOWED_HOSTS=il-tuo-dominio,...`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://il-tuo-dominio`
   - `DATABASE_URL` — ad es. `postgres://...`; senza, si usa `db.sqlite3`
2. **Avvio** (approccio gunicorn + WhiteNoise per gli static):
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
   ```
   WhiteNoise serve già `static/` in produzione (nessun nginx necessario per gli static).
3. **Caricare su GitHub**:
   ```bash
   git remote add origin https://github.com/TUO-UTENTE/TCGIP.git
   git push -u origin master
   ```
   Poi collega il repo alla piattaforma scelta e imposta le variabili d'ambiente.

> Nota: `db.sqlite3`, `staticfiles/`, `.env` e i file caricati (`media/`) sono esclusi da git via `.gitignore`.

> Média/upload: WhiteNoise serve solo gli `static/`. Le immagini caricate (`media/`) vanno salvate su uno storage persistente della piattaforma (volume o object storage) puntando `DJANGO_MEDIA_ROOT` di conseguenza.

## Test

```bash
python manage.py test
```

## Struttura rilevante

| Percorso | Contenuto |
|---|---|
| `cards/services.py` | range del grafico, snapshot, serie relative e % |
| `cards/importers.py` | helper condivisi per gli import API (fetch, upsert, immagini) |
| `cards/management/commands/import_scryfall.py` | seed Magic da Scryfall |
| `cards/management/commands/import_pokemon.py` | seed Pokémon dalla Pokémon TCG API |
| `cards/management/commands/import_ygo.py` | seed Yu-Gi-Oh! da YGOProDeck |
| `cards/templates/cards/collection_form.html` | autocomplete carta |
| `cards/templates/cards/collection_list.html` | collezione per-gioco / lista piatta |
| `templates/home.html` | grafico con menu range |
| `config/settings.py` | configurazione 12-factor (env) per sviluppo e produzione |

