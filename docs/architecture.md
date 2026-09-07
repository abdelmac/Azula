# Architecture et conventions de la première tranche

## Organisation

`frontend/` contient une application Vue 3, TypeScript, Vue Router et Vue I18n. `backend/config/` configure Django ; `backend/erp/` contient les modèles, services comptables, sérialiseurs et endpoints. Le module comptable reste dans le monolithe afin de conserver une transaction PostgreSQL pour une opération métier entière. Les limites des sous-domaines sont les services et les routes, sans microservices ni queue.

Une société est initialisée par installation. L’utilisateur porte une clé de société obligatoire ; les objets métier portent également cette clé. Les listes, recherches, détails et relations sont filtrés côté serveur. Des tests créent une seconde société pour vérifier l’isolation, sans ajouter de sélecteur multisociété au produit.

Les sessions Django remplacent les jetons navigateur. Le cookie de session est HttpOnly et SameSite=Lax, Secure en production. Le frontend récupère un jeton CSRF, y compris avant la connexion. Le serveur impose CSRF sur les actions et limite les tentatives de connexion dans PostgreSQL. Les réponses métier ne sont pas mises en cache ; aucun service worker.

## Permissions

| Action | Administrateur | Comptable | Commercial | Lecture seule |
|---|---|---|---|---|
| Lire clients, catalogue, factures | Oui | Oui | Oui | Oui |
| Créer/modifier/archiver les références | Oui | Oui | Oui | Non |
| Préparer et modifier un brouillon | Oui | Oui | Oui | Non |
| Valider une facture, saisir un règlement | Oui | Oui | Non | Non |
| Lire comptes, journaux, écritures, balance | Oui | Oui | Oui | Oui |
| Lire l’audit | Oui | Oui | Non | Non |
| Configurer société, périodes et utilisateurs | Oui | Non | Non | Non |
| Changer sa langue | Oui | Oui | Oui | Oui |

Le rôle administrateur cumule les droits afin de permettre l’initialisation et la démonstration. L’administration Django est en lecture seule ; les changements de droits passent par l’API auditée. Le dernier administrateur actif ne peut pas être désactivé ou rétrogradé via l’API.

## Calculs et arrondis

Les prix et quantités utilisent des `Decimal` Python et des colonnes PostgreSQL `numeric`, jamais des nombres flottants faisant foi. Les champs monétaires de l’API sont des chaînes décimales ; le navigateur ne fait que les formater.

Pour chaque ligne :

1. `net = round_half_up(quantity × unit_price, precision)`.
2. `tax = round_half_up(net × tax_rate / 100, precision)`.
3. `total = net + tax` ; les totaux de facture sont les sommes des lignes.

La précision est configurable de 0 à 4 décimales. Les prix et quantités acceptent jusqu’à 6 décimales, le taux jusqu’à 4. Le règlement doit être positif, à la précision de la facture, au plus égal au solde, et à une date au moins égale à la date de facture. Exemple d’arrondi : deux lignes de `0.005` donnent chacune `0.01` avec une précision de 2, donc `0.02` au total. Cette convention est une hypothèse de démonstration, **pas une règle fiscale universelle**.

## Transactions et immutabilité

Chaque mutation financière verrouille la ligne société avec `SELECT FOR UPDATE`. Ce choix simple sérialise les mutations d’une société, y compris les fermetures de périodes, tout en laissant les lectures normales se poursuivre. Il réduit le débit des écritures concurrentes ; une granularité plus fine doit être justifiée par mesure.

La validation recalcule le brouillon, vérifie la période, verrouille une séquence annuelle et attribue `INV-année-compteur`. Facture, snapshot, compteur, écriture et audit sont commis ensemble. Les numéros sont uniques par société ; aucun `MAX+1` libre.

Les validations et règlements demandent `Idempotency-Key`. La clé est unique par société et liée à une empreinte de l’action, du document et du contenu normalisé. Un retry renvoie l’état courant du document sans nouvel effet ; un contenu différent sous la même clé est refusé. Les clés ne sont pas supprimées. Une nouvelle opération de règlement doit avoir une nouvelle clé.

Une facture validée fige la société, le client, les lignes, les prix, taxes, dates, monnaie, précision, langue et politique d’arrondi. L’impression se fonde sur cette copie. Les changements ultérieurs des références n’altèrent pas le document. La devise et la précision comptables sont verrouillées après la première validation.

Les services vérifient l’équilibre exact débit/crédit, le montant attendu et les périodes. Des contraintes et triggers PostgreSQL ajoutent une protection contre les modifications/suppressions de documents validés, écritures, lignes, règlements, audit et clés, et contrôlent l’équilibre différé à la fin de transaction. Le propriétaire de la base ou un superutilisateur peut modifier ces protections : l’audit **n’est pas inviolable**. Les contrôles et leurs résultats sont décrits séparément dans le rapport de vérification.

## Langues, impression et performances

Les routes et catalogues de langue sont chargés à la demande, avec secours français. Les traductions concernent aussi les erreurs, états vides et notifications. Les données métier saisies restent telles quelles ; elles ne sont pas traduites automatiquement. La langue utilisateur est persistée au serveur. La langue de facture est choisie avant validation. Les paramètres régionaux servent au formatage sans modifier les valeurs stockées.

L’arabe emploie `lang`, `dir=rtl`, CSS logiques et isolation bidirectionnelle pour les références et courriels. Les polices système assurent le fonctionnement local ; vérifier la présence d’une police prenant en charge l’arabe sur les postes. L’impression est du HTML navigateur, sans moteur PDF serveur. Une relecture humaine des cinq langues et un contrôle visuel de l’arabe imprimé restent nécessaires.

L’aperçu imprimable démarre dans la langue figée du document. Son sélecteur peut traduire temporairement les libellés de l’impression dans une autre langue, sans changer le snapshot, les descriptions saisies, les montants ou la préférence utilisateur.

Les listes sont paginées côté serveur à 50 éléments, maximum 100. Les factures de liste n’embarquent pas toutes leurs lignes. Recherche temporisée côté interface, tri stable côté serveur et index liés aux filtres. Voir `performance.md` pour les budgets, le protocole et les limites mesurées.

## Références techniques consultées

- [Versions Django et support LTS](https://www.djangoproject.com/download/) : choix de la branche 5.2 LTS et de son correctif disponible.
- [Notes de version DRF](https://www.django-rest-framework.org/community/release-notes/) et [authentification par session](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication).
- [Django et PostgreSQL](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes).
- [Prérequis Vite](https://vite.dev/guide/) et [versions maintenues](https://vite.dev/releases).
- [Maintenance de Vue I18n](https://vue-i18n.intlify.dev/guide/maintenance) et [compilation compatible CSP activée par défaut depuis v10](https://vue-i18n.intlify.dev/guide/migration/breaking10#default-enable-for-jit-compilation).
- [Distribution officielle PostgreSQL pour Windows](https://www.postgresql.org/download/windows/).
