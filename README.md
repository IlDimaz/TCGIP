# TCGIP — Trading Card Game Inventory Project

A Django web application for managing and tracking the value of a physical trading card collection, supporting games such as **Magic: The Gathering, Pokémon, One Piece, and Yu-Gi-Oh!**

Market values are **not based on external pricing APIs or third-party market data**. This avoids relying on external price sources that can be wrong and don't provide any information regarding for languages outside ENG and JAP, but it also means that meaningful market valuation data is not currently available beyond the information manually provided by the user, as such the value should be checked on reliable sources.

## Main Features

* **Collection management**: catalog your physical card copies (`owned` / `sold`) with photos, condition, grading (PSA/BGS/CGC/SGC), purchase prices, and market values. The collection can be displayed **by game** (with game logos and card counts) or as a flat, filterable, and paginated list.
* **Collection value chart**: the home page displays the total collection value over time, with selectable ranges: **3D / 7D / 14D / 1M / 3M / 6M / 1Y / 5Y / ALL**. Values are displayed **relatively** (the first point is normalized to 100), together with the percentage change over the selected period.
* **Daily snapshots**: `ValueSnapshot` stores one value per user and day. The snapshot is automatically created or updated when visiting the home page or modifying the collection.
* **Card catalog with images**: the catalog can be populated automatically from public APIs, including the actual image of each card:

  * **Magic: The Gathering** → Scryfall (`import_scryfall`)
  * **Pokémon** → Pokémon TCG API (`import_pokemon`, PNG)
  * **Yu-Gi-Oh!** → YGOProDeck (`import_ygo`, JPG)
  * **Other games / One Piece** → manual CSV import from the catalog.
* **Card search and editing**: cards are selected through a search box with autocomplete (`GET /cards/api/search/?q=`) instead of a `<select>` containing thousands of entries.
* **Marketplace**: currently **disabled**. The marketplace code is still available in the `marketplace/` directory but is not included in `INSTALLED_APPS`.

## Setup

### Development

```bash
uv sync
python manage.py migrate
python manage.py runserver
```

## Catalog Seeding

The database can be populated with real sets and cards. Each imported card includes information such as `rarity` and `image_url`.

All import commands are **idempotent**: running them multiple times does not create duplicates and fills in missing fields when possible.

### Magic: The Gathering — Scryfall

Images are available as PNG files.

```bash
python manage.py import_scryfall --sets one
python manage.py import_scryfall --sets one,neo,woe --limit 500
python manage.py import_scryfall --sets one --download-images
python manage.py import_scryfall --sets one --download-images --full-images
```

* `--sets` specifies one or more set codes.
* `--limit` limits the number of imported cards.
* `--download-images` downloads local card images.
* `--full-images` downloads the high-resolution PNG versions.

### Pokémon — Pokémon TCG API

```bash
python manage.py import_pokemon --sets sv1,mew
python manage.py import_pokemon --sets base1 --api-key YOUR_API_KEY --download-images
```

The Pokémon TCG API key is free and can be obtained from [dev.pokemontcg.io](https://dev.pokemontcg.io?utm_source=chatgpt.com).

The API can also be used without a key, although rate limits are lower.

### Yu-Gi-Oh! — YGOProDeck

No API key is required.

```bash
python manage.py import_ygo --sets "Justice Hunters"
python manage.py import_ygo --sets "Legend of Blue Eyes White Dragon" --download-images
```

### Other Games / Custom Sets

For games such as **One Piece**, cards can be imported manually using CSV files:

* From the Django admin: `/admin-tools/import-cards/`
* From the user's collection: `/collection/import/`

## Charts and Snapshots

The current day's collection snapshot is recalculated whenever:

* the home page is visited;
* a card is added;
* a card is edited;
* a card is sold;
* a card is deleted;
* a collection is imported from CSV.

The historical daily series is therefore built as the application is used over time by visiting the home page on different days.

## Production Deployment

The application is suitable for deployment on standard container or web-service platforms such as **Render, Railway, Fly.io, Heroku, or a VPS**.

### 1. Environment Variables

See `.env.example`.

```env
DJANGO_SECRET_KEY=...
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com,...
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com
DATABASE_URL=postgres://...
```

A secure Django secret key can be generated with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

If `DATABASE_URL` is not provided, the application uses the local `db.sqlite3` database.

### 2. Start the Application

The production setup uses **Gunicorn + WhiteNoise** for serving static files:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
```

WhiteNoise handles the `static/` files in production, so a separate Nginx configuration is not required for static assets.

### 3. GitHub

Add the repository as a remote and push:

```bash
git remote add origin https://github.com/YOUR-USERNAME/TCGIP.git
git push -u origin master
```

The repository can then be connected to the deployment platform of your choice, with the required environment variables configured there.

> **Note:** `db.sqlite3`, `staticfiles/`, `.env`, and uploaded files in `media/` are excluded from Git through `.gitignore`.

> **Media / uploads:** WhiteNoise only serves `static/` files. User-uploaded images in `media/` should be stored on persistent storage provided by the deployment platform (such as a persistent volume or object storage), with `DJANGO_MEDIA_ROOT` configured accordingly.

## Relevant Project Structure

| Path                                           | Description                                                           |
| ---------------------------------------------- | --------------------------------------------------------------------- |
| `cards/services.py`                            | Chart ranges, snapshots, relative series, and percentage calculations |
| `cards/importers.py`                           | Shared helpers for API imports (fetching, upserting, and images)      |
| `cards/management/commands/import_scryfall.py` | Magic: The Gathering catalog import from Scryfall                     |
| `cards/management/commands/import_pokemon.py`  | Pokémon catalog import from the Pokémon TCG API                       |
| `cards/management/commands/import_ygo.py`      | Yu-Gi-Oh! catalog import from YGOProDeck                              |
| `cards/templates/cards/collection_form.html`   | Card autocomplete/search interface                                    |
| `cards/templates/cards/collection_list.html`   | Game-based collection view / flat list                                |
| `templates/home.html`                          | Collection value chart and range selector                             |
| `config/settings.py`                           | 12-factor configuration for development and production                |
