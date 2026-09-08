# Vérifications effectuées jusqu’au 8 septembre 2026

## Paramètres de catalogue — 8 septembre 2026

L’évolution décrite dans [catalogue.md](catalogue.md) ajoute les classes, entrepôts, unités, prix d’achat distinct du prix de vente, caractéristiques et photos HTTPS. La liste des prix comporte recherche F3, filtres combinés, tri, archivage et impression de la page courante. Les 39 nouveaux textes sont traduits dans chacun des cinq catalogues (230 clés par langue).

| Contrôle exécuté | Résultat |
| --- | --- |
| `python -m pytest -p no:cacheprovider` dans Docker, sources actuelles montées en lecture seule | **212 réussis en 116,99 s**, base séparée `test_azula_catalog`, créée et supprimée par pytest |
| `ruff check` complet dans le conteneur | Réussi ; contrôles ciblés après correction des chaînes vides également réussis |
| `manage.py makemigrations --check --dry-run` | Aucun changement manquant ; connexion au catalogue PostgreSQL système, sans migration d’une base métier |
| `npm run check`, `npm run lint`, `npm run test` | Réussis ; **18 tests Vitest** |
| `npm run build`, puis `docker compose build backend` | Réussis ; le build Docker final inclut les derniers ajustements des champs et filtres |
| Playwright avec Chrome, exécuté par `.local/rerun_docker_e2e.py` | **9 réussis en 22,0 s, aucun ignoré** : 7 essais avec fixtures explicites et 2 parcours PostgreSQL réels sur `azula_e2e` |

Les **51 nouveaux cas backend** couvrent les permissions, l’isolement entre sociétés des relations et recherches, les prix décimaux exacts et inconnus, les URL HTTPS sans identifiants, les références archivées, le rollback de l’audit et la conservation du snapshot d’une facture validée. Un test exécute réellement la migration `0004 → 0005` et vérifie les données antérieures, uniquement dans la base pytest. La première exécution avait relevé une chaîne vide acceptée comme prix d’achat inconnu ; le champ exact refuse désormais les chaînes vides ou blanches et n’accepte que `null` pour un prix inconnu. La suite complète a ensuite réussi.

La CI GitHub du commit applicatif `23d4a5aefb8edb9ed4c1a0f39fd3734650e3dfbe` a également réussi : [exécution 34223222111](https://github.com/abdelmac/Azula/actions/runs/34223222111). Elle reproduit les vérifications avec PostgreSQL et Chromium sur Linux, dans son environnement isolé.

Le nouveau parcours navigateur réel crée une classe, un entrepôt, une unité, un article, puis vérifie recherche et filtres, affichage achat/vente, édition d’un prix d’achat devenu inconnu, archivage/restauration et utilisation du prix de vente en facture. Le prix `12.345678` est conservé ; la ligne facturée est arrondie à `12.35` HT, `2.47` de taxe et `14.82` TTC. Le parcours comptable antérieur avec règlements de 50 puis 70 réussit également.

Les nouveaux essais d’interface vérifient les saisies après erreur et changement de langue, un prix au-delà de la précision entière de JavaScript, le rôle lecture seule, une photo HTTPS interceptée par une fixture, le raccourci F3 et l’impression. Les captures `catalogue-postgresql-desktop.png` et `catalogue-ar-mobile.png` dans `frontend/test-results/` ont été inspectées : thème bleu, listes et caractères mixtes lisibles, pas de débordement global sur mobile 390 × 844 ; la table large défile dans son propre conteneur. Un PDF de la liste avec fixtures a été généré par Chrome ; aucune imprimante réelle ni URL de photo externe réelle n’a été utilisée pour ces tests.

La migration a été appliquée uniquement à `azula_e2e` et aux bases pytest. Le conteneur temporaire du port 8081 a été supprimé, la base synthétique conservée. **Cette évolution du catalogue n’est pas encore publiée sur Render** : l’instance Internet et l’instance locale du port 8080 conservent leur version précédente. La règle `AGENTS.md` « Aucune opération sur une base réelle » impose de clarifier l’autorisation avant la sauvegarde et la migration de la base Internet existante. Les résultats du déploiement du 7 septembre ci-dessous concernent cette version précédente.

## Version publiée le 7 septembre 2026

Azula fonctionne localement avec PostgreSQL dans Docker et en ligne sur **[azula.onrender.com](https://azula.onrender.com)**. Après adaptation du thème et des réglages d’hébergement, les **161 tests backend**, **18 tests frontend** et **6 tests navigateur**, dont le parcours comptable complet, ont réussi. Les contrôles HTTPS de l’instance publique ont également réussi. Ce rapport précise les contrôles effectués et les limites restantes.

## Thème bleu et déploiement Internet

Le thème reprend les bleus du logo fourni : marine, bleu vif et cyan, avec des fonds clairs ; les couleurs sémantiques des erreurs et statuts restent distinctes. La navigation, la connexion, les formulaires, l’impression et le favicon ont été adaptés. Le bouton primaire blanc sur `#075ad6` présente un contraste calculé de 6,10:1. La capture authentifiée locale a été inspectée après reconstruction Docker, sans erreur JavaScript.

Le lanceur Waitress accepte le port de l’hébergeur et un proxy HTTPS explicitement configuré. `/healthz/` vérifie PostgreSQL sans divulguer d’erreur de connexion. La configuration prend en charge les URL PostgreSQL hébergées, la vérification TLS et les connexions poolées ; les secrets `.env` récursifs sont exclus du contexte Docker.

Derniers contrôles : build Docker réussi ; **161 tests pytest en 68,28 s**, Ruff réussi ; contrôles TypeScript et ESLint réussis ; **18 tests Vitest** ; **6 tests Playwright en 10,9 s, aucun ignoré**. Ces derniers utilisent l’image actualisée sur 8081 et la base synthétique `azula_e2e` ; seul le mot de passe de son compte `e2e-admin` a été renouvelé pour l’essai. Le conteneur temporaire a été supprimé, la base conservée. Le compte et les données de l’instance 8080 n’ont pas été réinitialisés.

Le service Render Free et la base Neon Free dédiés ont été créés à Francfort. Render indique le déploiement **`live`**, avec le commit exact `d9adab96940aa96b2c6a001c867b06e946a99440`. Sa CI GitHub a réussi : [exécution 34163887967](https://github.com/abdelmac/Azula/actions/runs/34163887967). La base a été migrée avec TLS `verify-full`, en utilisant explicitement `/etc/ssl/certs/ca-certificates.crt`. Le plan gratuit a été contrôlé dans les réponses des fournisseurs ; aucun abonnement payant, disque Render ni déploiement automatique n’a été activé. Le profil et les procédures sont dans `render.yaml` et [deployment.md](deployment.md).

La base Internet est distincte de l’installation locale. Son rôle `azula_app`, créé par SQL, n’est ni propriétaire ni administrateur et ne peut pas modifier ou supprimer les écritures, règlements, événements d’audit et enregistrements d’idempotence existants. La connexion poolée a été vérifiée avec ce rôle et le chiffrement de la connexion cliente confirmé par `pgconn.ssl_in_use`. Le contrôle `pg_stat_ssl` sur le pooler décrit une autre liaison, entre le proxy et PostgreSQL. `migrate --check`, `check --deploy` et la création du premier administrateur ont réussi. Les secrets Internet, différents des accès locaux, sont hors Git et leurs fichiers limités au compte Windows courant. Aucun client ni facture n’a été créé sur cette base.

Contrôles Chrome réellement exécutés sur `https://azula.onrender.com` :

- `/healthz/` : HTTP 200, `status=ok`, cache désactivé ; PostgreSQL répond.
- `/login` : HTTP 200 et en-tête HSTS ; connexion administrateur puis liste des factures authentifiée HTTP 200.
- Cookie de session `Secure`, `HttpOnly` et `SameSite=Lax` ; lecture anonyme des factures refusée en 401 et POST client sans CSRF refusé en 403.
- Couleur du bouton primaire `rgb(7, 90, 214)`, français sur écran 1440 × 960 et arabe RTL sur mobile 390 × 844, sans débordement horizontal ni erreur JavaScript.
- Captures `.local/screenshots/azula-cloud-fr.png` et `.local/screenshots/azula-cloud-ar-mobile.png` inspectées après chargement de la liste ; langue du compte remise en français.

Ces contrôles distants ne créent aucun client ni facture. Le parcours financier complet reste vérifié sur les bases PostgreSQL de test séparées. L’offre gratuite met le serveur en veille ; la restauration de sauvegarde et la capacité sous charge n’ont pas été testées. Les chiffres détaillés plus bas consignent également le lancement local précédent.

## Environnement observé

- Windows x64, version noyau `10.0.26200`.
- Intel Core i7-1165G7, 4 cœurs/8 processeurs logiques ; mémoire déclarée par Node : 15,71 Gio.
- Python 3.14.7, Django 5.2.17, DRF 3.18.0, psycopg 3.3.5.
- Node 24.19.0, Vue 3.5.42, Router 5.3.1, Vue I18n 11.4.10, Vite 8.2.2, TypeScript 6.0.3.
- pytest 9.1.1, pytest-django 4.14.0, Vitest 5.0.0, Playwright 1.63.0.
- Chrome installé : `152.0.7977.76`, exécution sans fenêtre visible.
- PostgreSQL 17.11 téléchargé depuis EDB, version du binaire serveur lue ; cluster non initialisé. Lors des premiers contrôles, Docker était absent du PATH et WSL non installé ; voir l’installation des prérequis ci-dessous.

Ce matériel ne correspond pas au profil double cœur/4 Go. Aucun essai physique sur macOS, Safari ou une machine modeste n’est revendiqué.

## Installation des prérequis — 07/09/2026

WSL **2.7.13** a été installé par la commande Microsoft `wsl --install --no-distribution --web-download` (code de sortie `0`). Après le redémarrage Windows requis pour activer `VirtualMachinePlatform`, WSL 2 est disponible.

Docker Desktop **4.90.0** a été installé pour l’utilisateur dans `%LOCALAPPDATA%\Programs\DockerDesktop`, avec le backend WSL 2. Le moteur Docker **29.7.2** et Docker Compose **5.5.1** répondent. `docker compose config --quiet` et `docker compose up -d --build` réussissent : PostgreSQL **17.11** est `healthy`, le backend est actif sur **127.0.0.1:8080**, et PostgreSQL n’est pas publié sur un port hôte. Le build Vue et la collecte des ressources statiques ont réussi dans l’image.

Le fichier `.env` existant a été préservé. Toutes les migrations Django et les quatre migrations `erp` ont été appliquées depuis une base vide. Le premier administrateur a été créé par `bootstrap_admin` : société locale « Azula - Developpement », devise de démonstration explicitement choisie `EUR`, sans pays fiscal. Son mot de passe aléatoire est conservé dans `.local/azula-access.json`, ignoré par Git et accessible uniquement au compte Windows courant (ACL vérifiée). Aucun client ni facture de test n’a été ajouté à cette instance.

Chrome a vérifié sur `http://localhost:8080` : page de connexion HTTP 200, connexion du compte administrateur, profil authentifié HTTP 200 et écran Factures vide, sans erreur JavaScript. La capture `.local/screenshots/azula-running.png` a été inspectée. Une période ouverte reste à créer dans les paramètres avant la première validation de facture.

## Backend

| Commande / contrôle | Résultat |
|---|---|
| `python manage.py check` dans le conteneur | Réussi, aucun problème signalé |
| `python -m pip check` dans le conteneur | Réussi, aucune dépendance incompatible signalée |
| `python -m ruff check --no-cache .` dans le conteneur | Réussi |
| `python -m pytest -p no:cacheprovider` dans le conteneur | **135 réussis en 46,62 s**, base séparée `test_azula_launch` |
| `python manage.py migrate --noinput`, puis `migrate --check` | Réussis, toutes les migrations appliquées |
| `python manage.py makemigrations --check --dry-run` | Réussi, aucun changement détecté ; historique PostgreSQL contrôlé |
| `python -m compileall -q config erp tests` | Réussi |
| `python -m pytest tests/test_calculation.py tests/test_api_contract.py -q -p no:cacheprovider` | **72 réussis**, dernière exécution 0,93 s |
| `python -m pytest --collect-only -q -p no:cacheprovider` | **135 collectés** ; la collecte n’exécute pas les assertions |
| `python manage.py makemigrations --check --dry-run --skip-checks` | Aucun changement de modèle détecté ; avertissement de connexion, historique en base non contrôlé |
| `python manage.py collectstatic --noinput` | Réussi, 154 fichiers copiés et 444 post-traitements |
| `check --deploy` avec `ENVIRONMENT=production` et debug désactivé | Un avertissement `security.W021` : HSTS preload volontairement désactivé ; ce contrôle statique ne valide pas une infrastructure HTTPS réelle |
| Première tentative de `pytest tests/test_accounting.py -x` | Échec à l’initialisation, timeout de connexion PostgreSQL ; aucune assertion financière d’intégration exécutée |

Les 72 tests sans base comprennent 45 tests de calculs/arrondis, valeurs limites, paramètres régionaux et empreintes, ainsi que 27 tests de formats d’entrée, refus d’accès anonyme et CSRF. Ils n’utilisent ni SQLite ni une base comptable simulée.

Les **63 tests PostgreSQL réussis** comprennent 28 tests API, 29 tests financiers et 6 tests de concurrence. Les tests financiers et API utilisent des transactions réellement commises ; les tests concurrents créent des connexions PostgreSQL distinctes, vérifiées par leurs identifiants serveur, et synchronisent le démarrage par barrière. La suite a été lancée avec `ENVIRONMENT=test`, `DB_NAME=postgres` et `TEST_DB_NAME=test_azula_launch` ; pytest a créé et supprimé sa base de test séparée de l’instance Azula. Les tentatives sans PostgreSQL du tableau ci-dessus sont conservées comme historique.

## Frontend et navigateur

Le build dans Docker, `npm run check`, `npm run lint` et `npm run test` ont réussi. Vitest : **18 tests réussis dans 5 fichiers**. Ces tests contrôlent les clés des cinq catalogues, les montants formatés sans conversion flottante, les clés d’idempotence, l’omission des filtres vides dans les requêtes de liste et la déconnexion après expiration de session. Chaque catalogue contient 191 clés.

Dernière exécution de `npm run test:e2e` avec `PLAYWRIGHT_CHANNEL=chrome` : **6 réussis, aucun ignoré, aucun flaky**, en **9,295 s**. Le rapport HTML Playwright confirme 5 tests `ui-chromium` et 1 test `workflow-chromium`. Le parcours réel PostgreSQL a réussi en 3,086 s : connexion, création d’un client, facture de 120, règlements de 50 puis 70, répétition idempotente, écritures équilibrées et affichage de la facture arabe. Les essais précédents ont permis de corriger un débordement mobile et la confirmation d’un brouillon devenu modifié.

Les cinq essais Playwright d’interface servent le véritable build par Django/Waitress avec sa politique CSP, avec des **fixtures explicites limitées aux tests**. Le scénario `workflow-chromium` utilise au contraire l’API réelle et une base PostgreSQL séparée `azula_e2e`, avec des identifiants aléatoires éphémères et un conteneur publié uniquement sur `127.0.0.1:8081`. Le conteneur temporaire a été supprimé après les essais ; la base E2E est conservée. L’instance Azula sur 8080 reste active. L’enveloppe Python locale a rencontré après les tests une erreur d’affichage de la flèche Unicode sous Windows cp1252 ; elle a été corrigée en UTF-8. Les résultats ci-dessus ont été confirmés directement dans le rapport Playwright existant, sans relance ni échec applicatif.

Les contrôles d’affichage portent sur les cinq langues, RTL, conservation des saisies après changement de langue ou coupure réseau, navigation et filtres, formulaire de facture mobile, fermeture de confirmation lorsqu’un brouillon est modifié et impression arabe. Les captures sont inspectées visuellement ; elles contiennent du texte arabe, des chiffres, `REF-A12` et `İstanbul`. Les dates latines sont isolées dans des éléments `bdi` pour conserver leur ordre en RTL.

Un PDF A4 a été généré **par Chrome dans le test**, depuis une fixture de snapshot, et non par un moteur d’export serveur du produit. Cela ne constitue pas une validation sur une imprimante réelle, toutes les polices cibles ou un document de 200 lignes. Une relecture humaine des traductions reste nécessaire.

Les fichiers locaux de rendu sont dans `frontend/test-results/` (ignorés par Git) : `invoice-arabic-print.png`, `invoice-arabic-browser.pdf`, `login-mobile.png`, `invoice-draft-desktop.png`. Les captures d’impression arabe et d’interface ont été inspectées ; les lettres arabes y sont liées et les dates latines conservent leur ordre après correction. Ceci reste un contrôle sur les fixtures décrites, pas sur une imprimante réelle.

Le bac à sable Windows a refusé certaines écritures dans les caches Vite/Ruff ; les mêmes commandes ont ensuite réussi avec l’autorisation d’exécution. Le refus initial d’import d’une DLL LightningCSS a été résolu après installation des dépendances optionnelles. Ces problèmes sont distincts du blocage persistant de `initdb`.

## Taille et distribution du frontend

Mesure précédemment effectuée avec `npm run size` sur le build Windows : entrée, imports statiques transitifs, catalogue français et route de connexion, chaque fichier compressé séparément avec gzip. **65 317 octets**, soit **63,79 Kio** ; objectif de 250 Ko atteint pour ce périmètre uniquement. La taille n’a pas été remesurée sur le nouveau build Linux Docker.

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

## Incident initial et contrôles restant à effectuer

Le programme natif `initdb.exe` avait été refusé par le contrôle d’applications Windows, code `0xc0e90002`. Aucune politique système n’a été désactivée. L’installation autorisée de Docker et WSL, puis le redémarrage Windows, ont permis de lancer PostgreSQL dans le conteneur Linux. Cette première étape ne concernait que des bases locales de développement et de test ; la nouvelle base Internet a ensuite été initialisée séparément comme décrit plus haut.

Pour reproduire le démarrage et les tests sur une installation de développement :

```text
python scripts/setup_env.py
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend python -m pytest
```

Puis suivre la préparation `azula_e2e` et `npm run test:e2e` de [development.md](development.md), ou exécuter la CI fournie sur une branche autorisée. La CI GitHub du commit `9743c85` a réussi lors de la préparation du déploiement.

Non réalisés : restauration de sauvegarde, générateur à 100 000 factures/10 000 clients, plans SQL, p95 API avec charge, mesures séparées réseau/rendu/mémoire, macOS/Safari et matériel double cœur/4 Go. Le rôle de développement local fourni par l’image garde des droits étendus ; le rôle applicatif restreint est en place sur Neon. La relecture humaine des langues et l’impression sur les équipements cibles restent nécessaires.

Les procédures correspondantes sont fournies ; aucun benchmark n’est revendiqué. Le parcours comptable de démonstration et les tests PostgreSQL sont maintenant exécutés avec succès ; cela ne constitue pas un audit fiscal ou une validation de production.
