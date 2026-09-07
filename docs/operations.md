# Exploitation et sauvegardes

## Serveur central et HTTPS

Docker Compose expose par défaut l’application uniquement sur `127.0.0.1:8080`. Aucun déploiement public n’est réalisé par les commandes du dépôt. Pour servir des utilisateurs sur le réseau, installer un proxy HTTPS sur le serveur ; lui seul reçoit le trafic utilisateur et transmet à ce port privé.

En exploitation, configurer explicitement :

```dotenv
ENVIRONMENT=production
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=erp.exemple-interne.fr
CSRF_TRUSTED_ORIGINS=https://erp.exemple-interne.fr
ALLOW_DEMO_DATA=0
TRUST_HTTPS_PROXY=1
TRUSTED_PROXY=ADRESSE_IP_DU_PROXY
```

Conserver une clé Django longue et aléatoire, un mot de passe PostgreSQL propre à l’installation et un rôle applicatif non superutilisateur. Protéger `.env` avec les droits de fichiers/ACL du compte de service. Le proxy doit **écraser** `X-Forwarded-Proto` et être le seul à joindre l’application lorsque `TRUST_HTTPS_PROXY=1`. Ne pas activer cette option derrière une entrée réseau non maîtrisée. Installer les certificats nécessaires sur les postes pour le réseau local.

Lancer le serveur avec `python server.py` : Waitress exige le proxy explicitement configuré, supprime les en-têtes de transfert non autorisés et transmet seulement le protocole et l’adresse cliente. La valeur `*` est réservée à une entrée privée entièrement protégée par le proxy de l’hébergeur, comme dans le [profil Render](deployment.md).

Les cookies deviennent Secure, HTTPS est imposé et HSTS est activé. Seul `/healthz/` accepte une sonde HTTP interne : elle vérifie la connexion PostgreSQL, retourne 200 ou 503 sans détails et sans cache. Lancer `python manage.py check --deploy` avec les véritables variables de production. L’image PostgreSQL du profil Compose crée `POSTGRES_USER` comme **superutilisateur de développement** : ne pas réutiliser ce compte dans l’application en exploitation. Séparer le compte administratif, le rôle propriétaire de migration et le rôle applicatif restreint, puis vérifier les droits après migration.

Exemple de droits minimaux à adapter par l’administrateur PostgreSQL, après création du rôle `azula_app` et son mot de passe via `\password` :

```sql
GRANT CONNECT ON DATABASE azula TO azula_app;
GRANT USAGE ON SCHEMA public TO azula_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO azula_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO azula_app;
REVOKE UPDATE, DELETE, TRUNCATE ON erp_entry, erp_entryline, erp_payment,
    erp_auditevent, erp_idempotencyrecord FROM azula_app;
```

Le rôle applicatif n’est propriétaire d’aucune table ni fonction et ne dispose pas de `CREATEDB`, `CREATEROLE` ou `SUPERUSER`. Les sessions et brouillons doivent rester modifiables. Les triggers protègent les lignes financières ; un administrateur de base peut toujours modifier le schéma. Il n’existe aucune promesse d’audit inviolable.

## Connexion et comptes

Les erreurs de connexion ne révèlent pas si le compte existe. Les compteurs de tentatives sont persistés dans PostgreSQL (8 échecs par nom, 30 par adresse sur une fenêtre de 15 minutes par défaut). Les clés sont hachées ; aucun mot de passe n’est journalisé. Le serveur utilise `REMOTE_ADDR` ; Waitress ne le remplace que pour le proxy explicitement autorisé, avec une chaîne d’un seul proxy. Vérifier la topologie réelle et prévoir aussi une limite au niveau du proxy si nécessaire.

Les rôles et opérations sensibles sont historisés. La modification d’un mot de passe invalide les sessions Django correspondantes. Une désactivation ou un changement de rôle est vérifié lors des requêtes suivantes. La commande initiale demande un mot de passe sans l’exposer dans les arguments. Ne pas utiliser de compte partagé dans une installation d’entreprise.

Les journaux d’application évitent les corps des requêtes et mots de passe. Les adresses, noms clients, références et métadonnées d’audit sont des données à protéger. Limiter l’accès aux sauvegardes et journaux, définir une durée de rétention selon le contexte réel. Les buckets de limitation de connexion expirent logiquement mais ne sont pas purgés automatiquement dans cette version ; prévoir une maintenance maîtrisée si leur volume augmente.

## Sauvegarde PostgreSQL

Prévoir une sauvegarde régulière, chiffrée par le système d’exploitation ou l’outil de sauvegarde, hors du serveur principal. Conserver aussi `.env` et la version de l’application dans un emplacement protégé distinct. Ne jamais committer une sauvegarde.

Avec Compose, remplacer `azula` par les noms réellement configurés. Ne pas utiliser une redirection binaire PowerShell pour le dump : écrire le fichier dans le conteneur puis copier.

```text
docker compose exec db pg_dump -U azula -d azula --format=custom --no-owner --file=/tmp/azula-backup.dump
docker compose cp db:/tmp/azula-backup.dump ./azula-backup.dump
```

Le compte de sauvegarde doit lire toutes les tables nécessaires. Sur une installation native, la commande équivalente est `pg_dump -h 127.0.0.1 -U azula -d azula -W --format=custom --no-owner --file=azula-backup.dump` ; `-W` demande le mot de passe de manière interactive.

## Restauration sur une base jetable

Ne jamais restaurer directement sur la base active pour vérifier une sauvegarde. Les commandes suivantes créent une **nouvelle** base et échouent si son nom existe déjà. Remplacer le suffixe de date par un identifiant inédit ; elles ne suppriment aucune donnée existante.

```text
docker compose cp ./azula-backup.dump db:/tmp/azula-restore.dump
docker compose exec db createdb -U azula -O azula azula_restore_20260907
docker compose exec db pg_restore -U azula -d azula_restore_20260907 --no-owner --exit-on-error /tmp/azula-restore.dump
docker compose exec db psql -U azula -d azula_restore_20260907 -c "SELECT count(*) FROM erp_invoice;"
docker compose exec db psql -U azula -d azula_restore_20260907 -c "SELECT count(*) FROM erp_payment;"
docker compose exec db psql -U azula -d azula_restore_20260907 -c "SELECT entry_id FROM erp_entryline GROUP BY entry_id HAVING sum(debit) <> sum(credit);"
```

Comparer les décomptes à ceux de la sauvegarde, vérifier l’absence d’écritures déséquilibrées, puis démarrer une instance applicative séparée pointant sur cette base pour ouvrir une facture et son audit. Un dump complet restaure les données avant les triggers ; ne pas utiliser un simple import de lignes métier dans une base déjà migrée pour contourner l’immutabilité.

Noter la durée et les résultats. La restauration n’a été vérifiée que si le rapport le dit explicitement. La suppression ultérieure de cette base jetable reste une opération administrative explicite. Ne pas employer `docker compose down -v` sur une installation dont les données doivent être conservées.

## Mises à jour

Sauvegarder et tester la restauration, appliquer les migrations d’abord sur une copie, exécuter les tests, puis arrêter temporairement les écritures durant la migration réelle. Aucun retour arrière financier par suppression n’est proposé. Conserver les numéros et clés d’idempotence. Revoir les règles du pays choisi avant tout usage comptable réel.
