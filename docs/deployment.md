# Déploiement Internet : commencer à 0 €

Le profil [render.yaml](../render.yaml) prépare **un service Docker Render Free à Francfort**, relié à **PostgreSQL Neon Free**. Le même conteneur sert Vue et Django sur une seule origine HTTPS ; les données et sessions restent dans PostgreSQL. Ce fichier ne crée aucune ressource tant qu’il n’est pas importé dans un compte Render. Aucun hébergement connecté ni déploiement réussi n’est présumé par ce guide.

L’offre convient au lancement d’une démonstration accessible sur Internet. Le tarif visé est 0 € dans les quotas gratuits, sans domaine acheté. Un usage métier continu demandera de revoir disponibilité, sauvegardes et capacité.

## Ce que contient le profil

Le plan `free` est explicite, sans disque, base Render, tâche planifiée ou service supplémentaire. `autoDeployTrigger: off` désactive les déploiements automatiques ; le premier import du Blueprint reste une création suivie d’un premier déploiement. La clé Django est générée par Render ; `DATABASE_URL` est demandée comme secret à l’import. Le [schéma officiel du Blueprint](https://render.com/docs/blueprint-spec) décrit ces champs.

Le lanceur écoute sur `0.0.0.0:$PORT`, avec le port fourni par Render. `RENDER_EXTERNAL_HOSTNAME` configure automatiquement l’hôte autorisé et l’origine CSRF HTTPS. Pour un futur domaine personnalisé, ajouter son nom exact à `DJANGO_ALLOWED_HOSTS` et son origine HTTPS à `CSRF_TRUSTED_ORIGINS`.

`TRUST_HTTPS_PROXY=1` et `TRUSTED_PROXY=*` sont propres à cette topologie : le port HTTP du conteneur n’est pas directement joignable depuis Internet, le proxy Render termine TLS et relaie les requêtes. Waitress n’accepte que le protocole et l’adresse cliente transmis par ce proxy ; il ignore les hôtes transférés. Ne pas copier cette confiance sur un serveur directement exposé. [Réseau et terminaison TLS Render](https://render.com/docs/web-services).

## Préparer PostgreSQL avant le premier déploiement

Créer un projet **Neon Free**, une base **vide dédiée à Azula** et choisir PostgreSQL 17, idéalement dans la région AWS Francfort. Cette procédure ne copie pas la base locale et ne touche pas à une base métier existante. Conserver l’URL directe du propriétaire pour les migrations, et réserver un deuxième rôle au serveur web.

Dans les étapes suivantes, les valeurs `A_REMPLACER` sont des indications, jamais des identifiants utilisables. Les fichiers `.env.production-*` sont exclus de Git et du contexte Docker. Les créer dans l’éditeur, avec des droits de lecture limités au compte local ; ne pas coller leurs secrets dans le terminal, les journaux ou une conversation.

Créer `.env.production-migrate` à la racine :

```dotenv
ENVIRONMENT=production
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=A_REMPLACER_PAR_UNE_CLE_ALEATOIRE_LONGUE
DJANGO_ALLOWED_HOSTS=localhost
ALLOW_DEMO_DATA=0
DATABASE_URL=A_REMPLACER_PAR_URL_NEON_DIRECTE_DU_PROPRIETAIRE
DB_SSLMODE=verify-full
DB_SSLROOTCERT=/etc/ssl/certs/ca-certificates.crt
DB_CONN_MAX_AGE=0
DB_TRANSACTION_POOLING=0
```

Générer la clé locale dans un gestionnaire de mots de passe, avec au moins 64 caractères aléatoires. Cette clé temporaire sert aux commandes d’administration ; le mot de passe du premier utilisateur ne dépend pas de sa valeur. Conserver `channel_binding=require` si Neon l’inclut dans son URL. `verify-full` vérifie le certificat et son nom d’hôte, avec le fichier d’autorités Debian explicitement indiqué : la valeur `system` n’a pas trouvé le bon magasin avec le libpq binaire de cette image. La connexion Neon a réussi avec ce chemin sans réduire la vérification TLS. [Connexion PostgreSQL sécurisée chez Neon](https://neon.com/blog/avoid-mitm-attacks-with-psql-postgres-16).

Construire la version qui sera publiée, puis appliquer les migrations sur cette nouvelle base :

```text
docker build --tag azula-deploy .
docker run --rm --env-file .env.production-migrate azula-deploy python manage.py migrate --noinput
docker run --rm --env-file .env.production-migrate azula-deploy python manage.py migrate --check
```

Ces conteneurs n’exposent aucun port et quittent après la commande. Le service web n’exécute jamais automatiquement les migrations. Render Free ne propose pas de shell et les commandes de pré-déploiement nécessitent une instance payante : l’administration initiale se fait donc depuis le poste local. [Limites Free](https://render.com/docs/free), [étapes de déploiement](https://render.com/docs/deploys).

## Créer le rôle applicatif et le premier administrateur

Ouvrir un conteneur local d’administration :

```text
docker run --rm -it postgres:17.11-bookworm bash
```

Dans ce conteneur temporaire, installer les autorités racines puis ouvrir `psql` avec l’hôte direct, le nom de base et le propriétaire indiqués par Neon. Le mot de passe sera demandé sans affichage :

```text
apt-get update
apt-get install -y --no-install-recommends ca-certificates
psql "host=A_REMPLACER dbname=A_REMPLACER user=A_REMPLACER sslmode=verify-full sslrootcert=/etc/ssl/certs/ca-certificates.crt channel_binding=require" -W
```

Dans cette session, créer le rôle par SQL. Les rôles créés dans l’interface, l’API ou la CLI Neon héritent de `neon_superuser` ; un rôle créé par SQL n’en hérite pas. [Privilèges Neon](https://neon.com/docs/reference/compatibility).

```sql
CREATE ROLE azula_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\password azula_app
```

Saisir un mot de passe aléatoire distinct. Toujours sur la base Azula migrée, appliquer les droits suivants ; remplacer `azula` par son nom exact si nécessaire :

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE azula TO azula_app;
GRANT USAGE ON SCHEMA public TO azula_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO azula_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO azula_app;
REVOKE UPDATE, DELETE, TRUNCATE ON erp_entry, erp_entryline, erp_payment,
    erp_auditevent, erp_idempotencyrecord FROM azula_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON django_migrations FROM azula_app;
```

Ne pas donner la propriété des tables, l’appartenance au rôle propriétaire ou le droit de créer des objets à `azula_app`. Réappliquer les droits adaptés après toute migration ajoutant des tables. Les règles de modification des factures et les triggers restent actifs.

Quitter `psql` avec `\q`, puis le conteneur avec `exit` ; seule la session d’administration locale est supprimée.

Créer `.env.production-app` sur le modèle du fichier de migration, en remplaçant `DATABASE_URL` par l’URL de **azula_app**, et `DB_TRANSACTION_POOLING` par `1`. Sélectionner l’URL poolée de Neon pour le service web ; son hôte contient `-pooler`. Le dépôt désactive les curseurs serveur et les requêtes préparées persistantes pour ce mode. Les migrations conservent la connexion directe du propriétaire. [Pool de connexions Neon](https://neon.com/docs/connect/connection-pooling).

Initialiser le premier administrateur avec le rôle applicatif :

```text
docker run --rm -it --env-file .env.production-app azula-deploy python manage.py bootstrap_admin --username administrateur --company-name "Ma société" --currency EUR
```

Remplacer société et devise par les choix de l’installation. Saisir un nouveau mot de passe personnel, différent de celui de l’installation locale. La commande refuse une base déjà initialisée. Après connexion, créer une période comptable ouverte dans les paramètres.

## Importer dans Render et vérifier

Connecter le dépôt contenant cette version à Render, puis créer un **Blueprint** utilisant `render.yaml`. Vérifier que l’aperçu contient un seul service `azula`, en **Free**, à **Frankfurt**. Pour `DATABASE_URL`, renseigner uniquement l’URL poolée de `azula_app`. Le compte propriétaire reste hors de Render. Le sous-domaine HTTPS `onrender.com` fourni évite l’achat d’un domaine. [Premier déploiement Render](https://render.com/docs/your-first-deploy).

Avant de considérer l’instance disponible, vérifier sur l’URL réellement attribuée :

1. `/healthz/` répond 200 avec `{"status":"ok"}` ; cette sonde vérifie PostgreSQL, pas la présence des migrations.
2. La connexion fonctionne, HTTPS ne boucle pas et les cookies de session sont `Secure`, `HttpOnly`, `SameSite=Lax`.
3. Une requête métier anonyme est refusée ; une action sans CSRF est refusée.
4. Les écrans et ressources du thème Azula chargent en français et en arabe sur ordinateur et mobile.
5. Les contrôles Django `check --deploy` et `migrate --check` réussissent avec la configuration finale, via un conteneur local sans port publié. Le parcours financier s’exécute sur une base de recette séparée.

Render génère initialement une clé de 256 bits encodée sur 44 caractères. Django peut signaler `security.W009` car son contrôle demande 50 caractères. Pour un contrôle sans avertissement, remplacer le secret généré par une clé aléatoire d’au moins 64 caractères **avant les premières connexions**, puis redéployer ; ne pas masquer le contrôle.

Documenter les résultats réellement obtenus dans [verification.md](verification.md). Tant que ces étapes distantes ne sont pas exécutées, le dépôt est préparé au déploiement, sans attestation de disponibilité Internet.

## Quotas et évolution du budget

Conditions consultées le **7 septembre 2026**, à revérifier lors de la création :

| Service | Offre gratuite et conséquence |
| --- | --- |
| Render Free | Veille après 15 minutes sans trafic ; réveil pouvant prendre environ une minute. 750 heures d’instances partagées par espace et par mois. Disque local éphémère, une instance, quotas de compilation et transfert. Sans moyen de paiement, les dépassements bloquent des fonctions au lieu de facturer un supplément. |
| Neon Free | 0,5 Go de stockage et 100 CU-heures de calcul par projet et par mois, sans limite temporelle annoncée ; mise en veille automatique. Une base Render Free expirerait après 30 jours : elle n’est pas créée par ce profil. |

Sources : [limites Render](https://render.com/docs/free), [offres Neon](https://neon.com/pricing). Sur un compte Render disposant déjà d’un moyen de paiement, revoir les limites de dépenses avant la création : `plan: free` ne rend pas tous les dépassements de l’espace gratuits.

Suivre les quotas dans les deux consoles. Ne pas ajouter de ping externe permanent pour empêcher la veille : les sondes SQL consomment aussi du calcul Neon. Les redémarrages du conteneur préservent les données PostgreSQL mais ne remplacent pas une sauvegarde ; suivre [la sauvegarde et restauration](operations.md).

Lorsque le budget augmente, passer le même service Render à une instance payante pour une disponibilité continue, puis augmenter Neon selon stockage et calcul réellement observés. Le monolithe Docker, les sessions Django et PostgreSQL restent identiques ; aucune réécriture frontend/backend n’est nécessaire. Mettre alors en place des sauvegardes avec restauration testée, l’administration des migrations et le suivi des erreurs. Les montées de gamme et leurs coûts restent un choix explicite.
