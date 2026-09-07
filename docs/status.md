# État de la première tranche

## Implémenté

- Socle Vue 3/TypeScript/Vite/Router/I18n et Django REST Framework, PostgreSQL exclusif.
- Sessions, protection CSRF, limitation des connexions persistante, premier administrateur par commande, quatre rôles.
- Configuration de la société, utilisateurs, langues, devise/précision et périodes.
- Clients et catalogue : création, lecture, modification, archivage, recherche/tri/pagination serveur.
- Factures brouillon, calcul Decimal serveur, validation atomique, numérotation, snapshot figé.
- Règlements manuels partiels/complets, solde exact, idempotence et protection contre dépassement.
- Comptes/journaux de démonstration, écritures automatiques, balance par période et historique d’audit.
- Contraintes et triggers PostgreSQL pour les invariants, restrictions API et admin sur les objets validés.
- Cinq catalogues traduits, RTL, impression HTML depuis le snapshot, ressources locales.
- Tests Python unitaires, tests PostgreSQL financiers/API/concurrence, Vitest et scénarios Playwright.
- Dépendances verrouillées, Docker Compose, CI PostgreSQL, installation Windows/macOS et documentation d’exploitation.
- Générateurs synthétiques protégés, protocole de mesure HTTP et calcul de taille JavaScript.

« Implémenté » décrit la présence du code. Cela ne signifie pas que tous les parcours ont été exécutés ; les résultats exacts sont dans [verification.md](verification.md).

Contrôles réellement réussis après adaptation du thème bleu et préparation de l’hébergement : **161 tests Python**, dont les 63 tests PostgreSQL API/comptabilité/concurrence et le contrôle de santé PostgreSQL, **18 tests Vitest**, **6 tests Chrome sans aucun ignoré**, build/types/lints. Le parcours réel client → facture 120 → règlements 50/70 → journal → impression arabe a réussi sur la base séparée `azula_e2e`. La mesure antérieure du JavaScript du premier écran sur Windows est de 65 317 octets gzip ; elle n’a pas été remesurée dans Docker.

Le profil Internet **Render Free + Neon Free** est préparé, avec port configurable, proxy HTTPS explicite, URL PostgreSQL/TLS et sonde de santé. Les comptes d’hébergement et le déploiement distant restent à terminer ; voir [deployment.md](deployment.md).

## Démarrage local vérifié

- Docker Desktop 4.90.0, WSL 2.7.13, moteur Docker 29.7.2 et Compose 5.5.1 installés et disponibles après redémarrage Windows.
- `docker compose up -d --build` réussi ; PostgreSQL 17.11 sain et Azula actif uniquement sur `http://localhost:8080`.
- Migrations appliquées depuis une base vide, contrôles Django, tests d’intégration/concurrence et parcours réel de bout en bout réussis.
- Premier administrateur local créé ; mot de passe aléatoire dans `.local/azula-access.json`, hors Git, droits Windows restreints. Société de développement en EUR, sans pays fiscal. Connexion réelle vérifiée dans Chrome ; aucun client ni facture de test dans cette instance.
- L’ancien refus de `initdb.exe` natif par Windows ne bloque plus le lancement via Docker. Aucune politique de sécurité n’a été désactivée.

## À vérifier sur une machine équipée

Restent les générateurs volumétriques, plans SQL, p95 API et restauration d’une sauvegarde. La CI GitHub du commit `9743c85` a réussi. Pour utiliser l’instance locale, créer une période comptable ouverte dans les paramètres avant de valider la première facture.

Restent également la relecture humaine des cinq langues, l’impression arabe sur les polices/imprimantes cibles, Safari/macOS, les autres moteurs de navigateur et l’essai sur un vrai ordinateur double cœur/4 Go. Les essais avec fixtures visuelles ne remplacent pas la démonstration de données réellement comptabilisées.

## Feuille de route hors tranche

- Choix du pays et analyse des obligations fiscales ; aucun régime fiscal déduit de la langue.
- Avoirs/remboursements puis corrections comptables contrôlées. En attendant, annulation/modification des documents validés refusée.
- Achats, fournisseurs, stock, paie, fabrication.
- Rapprochement bancaire, connexions bancaires et paiements réels.
- Devises multiples/conversion et facturation électronique réglementaire.
- Synchronisation hors ligne, applications natives et éventuelle offre SaaS.
- Après mesures : pagination par curseur si nécessaire, index de recherche spécialisés et verrouillage plus fin des écritures.

Aucun faux écran ni bouton inactif n’annonce ces modules comme disponibles.
