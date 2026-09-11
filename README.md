# Azula

ERP web en développement : fiches clients détaillées, tarifs personnalisés, catalogue sans stock, facturation avec remises, atelier d’impression, tableau de bord, exports et espace d’intégrations. Vue 3/TypeScript et Django REST Framework, avec **PostgreSQL uniquement**.

Les API versionnées permettent à un site ou à une application externe de consulter le catalogue, créer des clients et des brouillons, ou transmettre des transactions. Le module bancaire importe les relevés CSV et rapproche les encaissements avec les factures sur confirmation. Les connexions directes aux prestataires et les transferts de fonds restent à configurer ou développer selon les services choisis. Voir [les fonctions et leurs limites](docs/evolution-erp.md).

Le module [Abonnements](docs/abonnements.md) prépare la vente d’un accès mensuel ou annuel par société via Stripe Checkout, avec portail client, notifications signées et contrôle d’accès serveur. Il est désactivé par défaut : les tarifs, le compte Stripe et l’activation réelle restent à choisir par l’exploitant. Les sociétés déjà présentes conservent leur accès et aucun paiement n’est créé par la mise à jour.

L’interface est disponible en français, anglais, arabe, allemand et turc. La langue de l’utilisateur, celle du document, la devise et les conventions régionales sont distinctes. Les traductions initiales nécessitent une relecture humaine.

Ce prototype n’est ni un ERP complet, ni un logiciel audité ou fiscalement certifié. Aucun pays fiscal n’est configuré. Les documents imprimés portent une mention de démonstration. La taxe de 20 % du scénario est une donnée d’essai.

## Démarrage avec Docker Compose

Sur le **serveur de développement**, installer Docker avec Compose et Python 3 pour générer la configuration. Docker n’est pas nécessaire sur les postes utilisateurs : un navigateur et l’accès au serveur suffisent.

Sous Windows, utiliser [Docker Desktop avec WSL 2](https://docs.docker.com/desktop/setup/install/windows-install/). À la première installation de [WSL](https://learn.microsoft.com/en-us/windows/wsl/install), redémarrer Windows lorsque demandé pour terminer l’activation de la plateforme de virtualisation, puis démarrer Docker Desktop avant les commandes ci-dessous.

Depuis la racine, dans PowerShell ou un terminal macOS :

```text
python scripts/setup_env.py
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py bootstrap_admin --username administrateur --company-name "Ma société" --currency EUR
```

La commande demande deux fois un mot de passe d’au moins 12 caractères, sans mot de passe partagé. `EUR` est un exemple explicite à remplacer par votre choix ; la langue ne choisit jamais la devise. Le premier administrateur crée la société et son plan de comptes de démonstration. Une deuxième initialisation est refusée.

Ouvrir **http://localhost:8080**. Dans les paramètres, vérifier les coordonnées, la devise, la précision et créer une période ouverte couvrant les dates de facture et de règlement. Les migrations sont une étape explicite ; le démarrage du serveur ne modifie pas automatiquement le schéma.

Sous macOS, employer `python3` à la place de `python` si nécessaire. Pour un environnement sans Docker, suivre [le guide Windows/macOS](docs/development.md).

## Déploiement Internet à 0 €

L’instance **[azula.onrender.com](https://azula.onrender.com)** est déployée sur **Render Free**, avec une base **Neon Free** séparée, à Francfort. La version ERP du **10 septembre 2026**, commit `bef3209cc84203f1cfe236fbe5d321fe5db76e71`, est confirmée `live` sur Render. La sauvegarde, les migrations et les contrôles de conservation des données et droits existants ont réussi. Les contrôles publics HTTPS, API, navigation et mobile arabe ont également réussi ; les résultats sont dans [verification.md](docs/verification.md).

Les accès Internet sont conservés sur le poste de déploiement dans `.local/azula-cloud-access.json`, hors Git ; ils sont distincts des accès locaux et n’ont pas été modifiés par cette mise à jour. Les vérifications HTTPS et du thème bleu du 7 septembre concernent le déploiement initial.

Le profil [render.yaml](render.yaml) et [le guide de déploiement](docs/deployment.md) documentent l’installation et son évolution vers des offres payantes sans réécrire l’application. Render Free met l’application en veille après 15 minutes sans activité ; le premier accès peut être plus lent. Les données restent dans Neon, dans les quotas gratuits. Aucun abonnement payant n’a été souscrit ; les déploiements automatiques sont désactivés.

## Parcours de démonstration manuel

Le catalogue comprend les classes d’articles, entrepôts, unités, prix d’achat et de vente, code-barres, fabricant, fournisseur, caractéristiques et photos par URL HTTPS. Les fiches clients regroupent les coordonnées, conditions, tarifs et relevés. Consulter [la liste des prix](docs/catalogue.md), [les clients et tarifs](docs/clients-et-tarifs.md), et [l’édition et l’impression](docs/documents.md). Cette évolution utilise les migrations ERP `0005` à `0007` et celles de l’application `connections` ; les contrôles et l’état de publication sont détaillés dans [verification.md](docs/verification.md).

1. Se connecter avec l’administrateur créé. Ajouter une période ouverte dans les paramètres.
2. Créer un client, puis une facture avec une ligne : quantité `1`, prix hors taxe `100.00`, taxe de test `20`.
3. Enregistrer le brouillon : les montants calculés par le serveur sont `100.00`, `20.00`, `120.00`.
4. Valider : numéro unique et copie figée du document. Le journal contient client au débit `120.00`, revenu au crédit `100.00`, taxe au crédit `20.00`.
5. Enregistrer un règlement manuel de `50.00`, à une date incluse dans une période ouverte : banque au débit `50.00`, client au crédit `50.00`, solde `70.00`.
6. Enregistrer `70.00` : solde nul. Une répétition avec la même clé d’idempotence ne crée aucun règlement supplémentaire.
7. Consulter le journal et la balance de la période. Changer les langues de l’interface. Pour une facture arabe, choisir cette langue **avant** validation puis ouvrir la version imprimable.

L’impression utilise le navigateur, y compris sa fonction « Enregistrer au format PDF ». Il n’existe pas d’export PDF serveur. Les factures validées ne sont plus modifiables ou annulables ; les avoirs et remboursements sont hors de cette tranche.

## Données synthétiques facultatives

L’application normale ne crée aucun faux client, facture ou chiffre d’activité. Les commandes suivantes sont réservées à une installation jetable. Activer explicitement `ALLOW_DEMO_DATA=1` dans `.env`, conserver `ENVIRONMENT=development`, puis recréer le conteneur backend si nécessaire :

```text
docker compose up -d backend
docker compose exec backend python manage.py seed_demo --company 1 --confirm-synthetic
```

Le scénario crée une facture de `120.00` et un premier règlement de `50.00`. Pour préparer un volume de mesure, employer **une installation avec une base jetable dédiée**, puis :

```text
docker compose exec backend python manage.py seed_performance --company 1 --confirm-synthetic --invoices 100000 --customers 10000 --batch-size 1000
```

Le générateur volumétrique crée des **brouillons avec lignes**, sans fabriquer de journal comptable validé. Ces deux commandes refusent l’environnement `production` et n’effacent aucune donnée. Désactiver `ALLOW_DEMO_DATA` après usage.

## Vérifications et documentation

Les résultats réellement obtenus et leurs limites sont consignés dans [le rapport de vérification](docs/verification.md). La CI lance les migrations depuis une base vide, les tests PostgreSQL, les contrôles frontend et Playwright ; elle a réussi pour le [commit déployé `bef3209c`](https://github.com/abdelmac/Azula/actions/runs/34512026795), avec 310 cas backend. Les 18 tests Vitest et les 24 scénarios Chrome ont également réussi en local, sur des données de test séparées.

- [Installation et développement Windows/macOS](docs/development.md)
- [Architecture, permissions et règles comptables](docs/architecture.md)
- [Exploitation, HTTPS, sauvegarde et restauration](docs/operations.md)
- [Protocole et mesures de performance](docs/performance.md)
- [Suivi et feuille de route](docs/status.md)
- [Évolution des fonctions ERP et limites](docs/evolution-erp.md)
- [Clients, tarifs et articles détaillés](docs/clients-et-tarifs.md)
- [Factures et atelier d’impression](docs/documents.md)

Une installation sur un serveur du réseau local peut fonctionner sans Internet après installation des dépendances. Il faut rester connecté à ce serveur : aucune synchronisation ni utilisation autonome hors ligne n’est proposée.
