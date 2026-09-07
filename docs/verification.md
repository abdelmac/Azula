# Vérifications effectuées le 7 septembre 2026

Ce rapport distingue les assertions exécutées des contrôles qui nécessitent encore PostgreSQL. Le parcours comptable complet n’a pas été validé dans cet environnement.

## Environnement observé

- Windows x64, version noyau `10.0.26200`.
- Intel Core i7-1165G7, 4 cœurs/8 processeurs logiques ; mémoire déclarée par Node : 15,71 Gio.
- Python 3.14.7, Django 5.2.17, DRF 3.18.0, psycopg 3.3.5.
- Node 24.19.0, Vue 3.5.42, Router 5.3.1, Vue I18n 11.4.10, Vite 8.2.2, TypeScript 6.0.3.
- pytest 9.1.1, pytest-django 4.14.0, Vitest 5.0.0, Playwright 1.63.0.
- Chrome installé : `152.0.7977.76`, exécution sans fenêtre visible.
- PostgreSQL 17.11 téléchargé depuis EDB, version du binaire serveur lue ; cluster non initialisé. Docker absent du PATH ; WSL non installé.

Ce matériel ne correspond pas au profil double cœur/4 Go. Aucun essai physique sur macOS, Safari ou une machine modeste n’est revendiqué.

## Backend

| Commande / contrôle | Résultat |
|---|---|
| `python manage.py check` | Réussi, aucun problème signalé |
| `python -m pip check` | Réussi, aucune dépendance incompatible signalée |
| `ruff check .` dans backend | Réussi |
| `python -m compileall -q config erp tests` | Réussi |
| `python -m pytest tests/test_calculation.py tests/test_api_contract.py -q -p no:cacheprovider` | **72 réussis**, dernière exécution 0,93 s |
| `python -m pytest --collect-only -q -p no:cacheprovider` | **135 collectés** ; la collecte n’exécute pas les assertions |
| `python manage.py makemigrations --check --dry-run --skip-checks` | Aucun changement de modèle détecté ; avertissement de connexion, historique en base non contrôlé |
| `python manage.py collectstatic --noinput` | Réussi, 154 fichiers copiés et 444 post-traitements |
| `check --deploy` avec `ENVIRONMENT=production` et debug désactivé | Un avertissement `security.W021` : HSTS preload volontairement désactivé ; ce contrôle statique ne valide pas une infrastructure HTTPS réelle |
| Première tentative de `pytest tests/test_accounting.py -x` | Échec à l’initialisation, timeout de connexion PostgreSQL ; aucune assertion financière d’intégration exécutée |

Les 72 tests sans base comprennent 45 tests de calculs/arrondis, valeurs limites, paramètres régionaux et empreintes, ainsi que 27 tests de formats d’entrée, refus d’accès anonyme et CSRF. Ils n’utilisent ni SQLite ni une base comptable simulée.

Les **63 tests PostgreSQL restants** comprennent 28 tests API, 29 tests financiers et 6 tests de concurrence. Les tests financiers et API utilisent des transactions réellement commises ; les tests concurrents créent des connexions PostgreSQL distinctes, vérifiées par leurs identifiants serveur, et synchronisent le démarrage par barrière.

## Frontend et navigateur

Le build, les contrôles de types et ESLint ont réussi. Vitest : **18 tests réussis dans 5 fichiers**, dernière exécution 527 ms. Ces tests contrôlent les clés des cinq catalogues, les montants formatés sans conversion flottante, les clés d’idempotence, l’omission des filtres vides dans les requêtes de liste et la déconnexion après expiration de session. Chaque catalogue contient 191 clés.

Dernière exécution de `npm run test:e2e` avec `PLAYWRIGHT_CHANNEL=chrome` : **5 réussis, 1 ignoré**, 8,9 s. Le scénario ignoré est le parcours complet sur PostgreSQL, jamais remplacé par une simulation comptable. Les essais précédents ont permis de corriger le débordement mobile causé par un libellé accessible positionné hors du conteneur de tableau, ainsi que la confirmation d’un brouillon devenu modifié.

Les essais Playwright d’interface servent le véritable build par Django/Waitress avec sa politique CSP. Les réponses métier sont des **fixtures explicites limitées aux tests** : elles ne démontrent aucune persistance, connexion réussie à un vrai compte ou comptabilisation PostgreSQL. Le scénario `workflow-chromium` exige les identifiants éphémères et une base E2E réelle ; il reste ignoré localement faute de PostgreSQL.

Les contrôles d’affichage portent sur les cinq langues, RTL, conservation des saisies après changement de langue ou coupure réseau, navigation et filtres, formulaire de facture mobile, fermeture de confirmation lorsqu’un brouillon est modifié et impression arabe. Les captures sont inspectées visuellement ; elles contiennent du texte arabe, des chiffres, `REF-A12` et `İstanbul`. Les dates latines sont isolées dans des éléments `bdi` pour conserver leur ordre en RTL.

Un PDF A4 a été généré **par Chrome dans le test**, depuis une fixture de snapshot, et non par un moteur d’export serveur du produit. Cela ne constitue pas une validation sur une imprimante réelle, toutes les polices cibles ou un document de 200 lignes. Une relecture humaine des traductions reste nécessaire.

Les fichiers locaux de rendu sont dans `frontend/test-results/` (ignorés par Git) : `invoice-arabic-print.png`, `invoice-arabic-browser.pdf`, `login-mobile.png`, `invoice-draft-desktop.png`. Les captures d’impression arabe et d’interface ont été inspectées ; les lettres arabes y sont liées et les dates latines conservent leur ordre après correction. Ceci reste un contrôle sur les fixtures décrites, pas sur une imprimante réelle.

Le bac à sable Windows a refusé certaines écritures dans les caches Vite/Ruff ; les mêmes commandes ont ensuite réussi avec l’autorisation d’exécution. Le refus initial d’import d’une DLL LightningCSS a été résolu après installation des dépendances optionnelles. Ces problèmes sont distincts du blocage persistant de `initdb`.

## Taille et distribution du frontend

Commande : `npm run size`, sur le build final. Périmètre : entrée, imports statiques transitifs, catalogue français et route de connexion, chaque fichier compressé séparément avec gzip. **65 317 octets**, soit **63,79 Kio** ; objectif de 250 Ko atteint pour ce périmètre uniquement.

| Fichier compté sous `dist/` | Octets gzip |
|---|---:|
| `assets/index-C4QMphhi.js` | 11 099 |
| `assets/vue-i18n-C314xO7f.js` | 39 708 |
| `assets/session-IPJXRrqY.js` | 4 620 |
| `assets/ErrorNotice-DL0bCoL6.js` | 1 973 |
| `assets/useApi-BPuI6ZR9-BVa2xYgF.js` | 470 |
| `assets/Icon-RCA7qdGk.js` | 718 |
| `assets/LanguagePicker-D7DrAEWV.js` | 537 |
| `assets/types-hGcSxo1r.js` | 65 |
| `assets/fr-DSrxrhUI.js` | 4 989 |
| `assets/LoginView-Cc44PRCH.js` | 1 138 |

Les autres langues, routes métier, CSS, HTML et icône ne sont pas comptés dans ce budget JavaScript. Le CSS final mesure environ 5,93 Ko gzip selon Vite. Aucun téléchargement de police externe. Le hook de build a écrit 24 variantes gzip ; le très petit chunk `types` est servi sans compression lorsqu’elle augmenterait sa taille, alors que le budget ci-dessus compte sa taille gzip par convention conservative.

Vérification avec le client de test Django, debug désactivé : ressource principale HTTP 200, `Content-Encoding: gzip`, longueur 11 099 octets ; `/login` HTTP 200 avec CSP et absence de cache, `/index.html` avec revalidation. Ce contrôle valide la sélection de ressource compressée, sans mesurer la latence réseau ni la capacité sous charge.

## Blocage PostgreSQL et contrôles à reprendre

Le programme officiel `initdb.exe` est refusé par le contrôle d’applications Windows, code `0xc0e90002`, malgré l’autorisation d’exécution et la tentative de retrait du marquage de téléchargement. Aucune politique système n’a été désactivée. Les tentatives de connexion sur le port isolé 55432 ont expiré. Aucune base réelle n’a été consultée ou modifiée.

Sur une machine équipée de Docker, reprendre exactement :

```text
python scripts/setup_env.py
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend python -m pytest
```

Puis suivre la préparation `azula_e2e` et `npm run test:e2e` de [development.md](development.md), ou exécuter la CI fournie sur une branche autorisée. La CI est écrite, mais n’a pas été lancée à distance durant ce travail.

Non réalisés : application des quatre migrations depuis une base vide, exécution des triggers PostgreSQL, rôle applicatif PostgreSQL restreint, scénario comptable réel 120/50/70 et ses retries, concurrence réelle, restauration de sauvegarde, générateur à 100 000 factures/10 000 clients, plans SQL, p95 API avec charge, mesures séparées réseau/rendu/mémoire. Docker Compose et ses images n’ont pas été exécutés sur cette machine.

Les procédures correspondantes sont fournies ; aucun résultat ni benchmark n’est inventé. La première tâche restante est l’exécution complète PostgreSQL avant toute démonstration de comptabilité présentée comme validée.
