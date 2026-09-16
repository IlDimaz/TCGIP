# TCGIP — Trading Card Game Inventory Project

Progetto Django per gestire e valorizzare una collezione di carte (Magic, Pokémon, One Piece...).

## Funzionalità principali

- **Collezione**: cataloga le tue copie fisiche (`owned` / `sold`), con foto, condizioni, grading PSA/BGS/CGC/SGC, prezzi di acquisto e valore di mercato.
- **Grafico andamento valore**: la home mostra il valore totale della collezione nel tempo con menu **1D / 7D / 14D / 1M / 3M / 6M / 1Y / 5Y / ALL**. Il grafico usa valori *relativi* (primo punto = 100) e mostra la variazione % nel periodo selezionato.
- **Snapshot giornalieri**: `ValueSnapshot` salva una riga per giorno/utente; viene creata/aggiornata automaticamente visitando la home o modificando la collezione.
- **Catalogo con immagini**: il catalogo può essere popolato automaticamente da **Scryfall** (Magic) con immagine per ogni carta.
- **Aggiungi/modifica carta**: la carta si cerca da una casella di ricerca (autocomplete su `GET /cards/api/search/?q=`) invece di un `<select>` con migliaia di voci.
- **Ricerca collezione**: lista paginata (24 per pagina) con filtro per nome e per gioco.
- Il marketplace è **disabilitato per ora** (codice ancora nella cartella `marketplace/`, non nell'`INSTALLED_APPS`).

## Setup

```bash
uv sync
python manage.py migrate
python manage.py runserver
```

Crea un superuser con `python manage.py createsuperuser`.

## Seed del catalogo da Scryfall

Popola il database con espansioni e carte reali di Magic (ogni carta ha `rarity` e `image_url`, PNG reale da `cards.scryfall.io`):

```bash
# Singola espansione (es. Phyrexia: All Will Be One)
python manage.py import_scryfall --sets one

# Più espansioni, max N carte
python manage.py import_scryfall --sets one,neo,woe --limit 500

# Scarica anche copie locali delle immagini (jpg normali, in media/cards/catalog/)
python manage.py import_scryfall --sets one --download-images

# PNG ad alta risoluzione (file pesanti!)
python manage.py import_scryfall --sets one --download-images --full-images
```

L'importazione è **idempotente**: rieseguirla non crea duplicati e completa eventuali campi vuoti.

## Grafici e snapshot

- Lo snapshot di oggi viene ricalcolato a ogni visita della home e a ogni modifica della collezione (aggiunta, modifica, vendita, cancellazione, import CSV).
- Lo storico giornaliero si costruisce visitando la home nei vari giorni.

## Test

```bash
python manage.py test
```

## Struttura rilevante

| Percorso | Contenuto |
|---|---|
| `cards/services.py` | range del grafico, snapshot, serie relative e % |
| `cards/management/commands/import_scryfall.py` | seed catalogo Magic da Scryfall |
| `cards/templates/cards/collection_form.html` | autocomplete carta |
| `cards/templates/cards/collection_list.html` | collezione paginata con filtri |
| `templates/home.html` | grafico con menu range |

