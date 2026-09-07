# Développer sous Windows et macOS

## Prérequis

Python 3.14, Node 24 LTS et PostgreSQL 17. Les versions effectivement installées sont consignées dans `verification.md`, les dépendances Python dans `backend/requirements.txt` et JavaScript dans `frontend/package-lock.json`. Aucun service payant nécessaire. Les ressources du frontend sont servies localement, sans CDN ni police externe obligatoire.

Créer une base **de développement dédiée**, un rôle avec mot de passe, et lui permettre `CREATEDB` seulement si les tests pytest doivent créer leur base jetable. Ne pas attribuer `SUPERUSER` au rôle applicatif en exploitation. Dans une session administrative `psql`, exemple :

```sql
CREATE ROLE azula LOGIN CREATEDB;
\password azula
CREATE DATABASE azula OWNER azula;
```

`\password` demande le mot de passe sans l’inscrire dans l’historique SQL. Employer la valeur locale `DB_PASSWORD` ou modifier `.env` de manière cohérente. Ne jamais fournir les mots de passe dans des URL ou arguments affichés.

## Windows PowerShell

```powershell
python scripts/setup_env.py
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py collectstatic --noinput
.\.venv\Scripts\python.exe backend/manage.py bootstrap_admin --username administrateur --company-name "Ma société" --currency EUR
cd backend
..\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8080 --threads=8 config.wsgi:application
```

Le lancement par `waitress-serve` sert le build frontend et l’API ensemble. Il fonctionne sans activer de script PowerShell de venv ni modifier la politique d’exécution.

Pour le rechargement pendant le développement, lancer `..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000` depuis `backend/`, puis `npm.cmd run dev` dans un deuxième terminal placé dans `frontend/`. Le proxy Vite transmet `/api` à Django. Utiliser `http://127.0.0.1:5173`.

## macOS

```sh
python3 scripts/setup_env.py
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py collectstatic --noinput
.venv/bin/python backend/manage.py bootstrap_admin --username administrateur --company-name "Ma société" --currency EUR
cd backend
../.venv/bin/waitress-serve --listen=127.0.0.1:8080 --threads=8 config.wsgi:application
```

En développement, `../.venv/bin/python manage.py runserver 127.0.0.1:8000` et `npm run dev` dans deux terminaux. Le parcours est prévu pour un navigateur Windows/macOS ; seuls les moteurs effectivement exécutés dans le rapport sont considérés vérifiés.

## Tests

Depuis `backend/` avec le Python du venv (Windows `..\.venv\Scripts\python.exe`, macOS `../.venv/bin/python`) :

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pytest
ruff check .
```

La configuration pytest utilise PostgreSQL et crée `test_azula` par défaut. Le nom est modifiable avec `TEST_DB_NAME`. Réserver ce nom aux tests ; ne jamais diriger les tests vers une base existante réelle. Les tests de concurrence emploient des transactions et connexions séparées. `--collect-only` vérifie la collecte, sans exécuter les assertions métier.

Depuis `frontend/` :

```text
npm ci
npm run check
npm run lint
npm run test
npm run build
npm run size
npx playwright install chromium
npm run test:e2e
```

Les tests de parcours demandent une base séparée `azula_e2e`, `ENVIRONMENT=test`, `DB_NAME=azula_e2e`, `E2E_USERNAME` et un `E2E_PASSWORD` aléatoire de 12 caractères minimum dans l’environnement. Appliquer les migrations puis lancer `python scripts/prepare_e2e.py` depuis la racine. Cette commande refuse les autres noms de base et une base déjà initialisée. Playwright démarre le serveur si besoin ; `E2E_BASE_URL` permet de cibler un serveur local déjà lancé. Voir `.github/workflows/verify.yml` pour le protocole complet automatisé.

Sans `E2E_PASSWORD`, seul le projet d’affichage `ui-chromium` utilise des réponses de test explicites ; le parcours PostgreSQL est marqué ignoré. Ces contrôles d’interface ne prouvent aucune écriture comptable. `npm run test:e2e -- --project=ui-chromium` les exécute séparément. `PLAYWRIGHT_CHANNEL=chrome` permet d’utiliser Chrome installé au lieu d’un Chromium téléchargé. Avec les identifiants E2E, le serveur démarré est Django/Waitress sur le build de production.

Exemple complet E2E **dans un terminal dédié**, avec un serveur PostgreSQL de développement déjà configuré et le rôle `azula`. Créer d’abord une base neuve (la commande échoue si elle existe) : `createdb -h 127.0.0.1 -U azula -W -O azula azula_e2e`.

PowerShell, depuis la racine :

```powershell
$env:ENVIRONMENT='test'
$env:DB_NAME='azula_e2e'
$env:E2E_USERNAME='e2e-admin'
$env:E2E_PASSWORD = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe scripts/prepare_e2e.py
cd frontend
npm.cmd run build
npm.cmd run test:e2e
```

macOS, depuis la racine :

```sh
export ENVIRONMENT=test DB_NAME=azula_e2e E2E_USERNAME=e2e-admin
export E2E_PASSWORD="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
.venv/bin/python backend/manage.py migrate
.venv/bin/python scripts/prepare_e2e.py
cd frontend
npm run build
npm run test:e2e
```

Le mot de passe est transmis aux processus sans être affiché ; ne pas le copier dans des logs. Fermer ce terminal après les essais pour éviter de réutiliser ces variables par erreur. La base E2E contient uniquement des données synthétiques et ne remplace jamais `azula`. Le rôle et le mot de passe PostgreSQL doivent correspondre à `.env`, indépendamment du mot de passe utilisateur E2E.

## Renouveler les dépendances

Le fichier `.in` décrit les dépendances directes ; `.txt` verrouille aussi les transitives. Pour renouveler, utiliser un venv neuf, installer le `.in`, vérifier les versions et recréer le `.txt` avec `python -m pip freeze`. Toujours relancer les tests PostgreSQL et frontend. Pour JavaScript, employer `npm install --save-exact`, conserver `package-lock.json`, puis `npm ci` pour les installations reproductibles.
