# API, transactions externes et banque

Azula fournit deux écrans : **Intégrations API** pour les administrateurs et **Banque et transactions** pour les administrateurs et comptables. Les données sont limitées à la société du compte connecté, également dans les recherches et les totaux.

## Intégrations

Une intégration décrit une application de type site Web/boutique, transactions, banque ou autre. Son nom de fournisseur est un renseignement libre : l'enregistrer n'établit aucune connexion avec ce fournisseur. Aucun compte bancaire externe, abonnement ou transfert n'est créé par Azula.

L'administrateur crée une clé avec un nom, une date d'expiration et des autorisations explicites. Le secret aléatoire n'est affiché qu'une fois ; la base conserve son empreinte SHA-256, son préfixe et ses métadonnées. La révocation est définitive. Une intégration désactivée suspend toutes ses clés. À chaque appel, l'API vérifie également que le créateur est toujours actif, administrateur et membre de la même société. Les clés expirent au plus tard après un an.

Conserver la clé côté serveur dans le gestionnaire de secrets de l'application. Ne pas l'intégrer à un JavaScript public. L'authentification Bearer concerne exclusivement `/api/external/v1/`. Elle ne permet pas d'utiliser les routes de gestion `/api/`, qui conservent leurs sessions et leur protection CSRF. Aucune session de navigateur ne remplace le Bearer sur l'API externe.

Le contrat JSON est disponible dans l'écran et sur `GET /api/integrations/schema/` (session administrateur). Une application munie d'une clé peut le lire sur `GET /api/external/v1/schema/`. Les exemples affichés dans l'écran ne lancent aucune requête et contiennent uniquement des espaces réservés.

| Opération externe | Autorisation | Résultat |
| --- | --- | --- |
| `GET catalog/` | `catalog:read` | Articles actifs et prix de vente ; prix d'achat exclus |
| `GET customers/` | `customers:read` | ID, nom, e-mail, adresse et identifiant fiscal ; coordonnées bancaires et notes internes exclues |
| `POST customers/` | `customers:write` | Création d'un client avec nom, e-mail, adresse et identifiant fiscal |
| `GET invoices/` | `invoices:read` | Liste des factures et de leurs lignes |
| `POST invoices/` | `invoices:write` | Création d'un brouillon via le service de facturation existant |
| `POST transactions/` | `transactions:write` | Réception d'une information de transaction, sans règlement comptable |
| `GET bank-transactions/` | `banking:read` | Lecture des transactions bancaires importées |

Les chemins ci-dessus sont relatifs à `/api/external/v1/`. Les listes utilisent `page`, `page_size` (50 par défaut, 100 maximum) ; catalogue, clients et factures acceptent `search` (128 caractères maximum). Les écritures exigent `Idempotency-Key`, 1 à 128 caractères. La clé est isolée par société et intégration. La répétition exacte renvoie le même corps et `Idempotency-Replayed: true`, code HTTP 200 ; la première exécution renvoie 201. Réutiliser une clé pour un autre contenu ou une autre action renvoie 409. Les clés d'accès d'une même intégration partagent ce registre, ce qui permet de faire tourner les secrets sans perdre les reprises.

Exemple de transaction :

```json
{
  "external_id": "commande-001",
  "date": "2026-09-10",
  "amount": "100.00",
  "currency": "EUR",
  "reference": "Commande 001"
}
```

Le montant est une chaîne décimale signée, non nulle, avec six décimales maximum. La devise doit correspondre à celle de la société. `external_id` est unique par intégration : un nouvel envoi identique n'insère pas de deuxième transaction ; un contenu différent avec le même identifiant renvoie 409. Les transactions apparaissent **Reçu, à examiner**. Elles ne constituent pas une preuve de réception des fonds et ne déclenchent ni validation de facture, ni règlement, ni transfert.

## Banque et import CSV

L'écran permet de créer et modifier des comptes, renseigner banque, IBAN et BIC, les archiver, importer un relevé, rechercher des lignes et filtrer par compte, dates et état de rapprochement. L'IBAN est contrôlé par sa structure et sa clé modulo 97 ; le BIC par sa structure. Ces vérifications ne prouvent pas l'existence du compte. La devise du compte correspond à la société ; la devise et la précision de la société sont figées dès qu'un compte bancaire ou une transaction externe existe.

Le total affiché est la somme exacte des lignes importées répondant aux filtres. Il ne représente pas le solde bancaire réel. Aucun solde d'ouverture ni synchronisation bancaire automatique n'est supposé.

Le fichier CSV doit être en UTF-8, avec une virgule comme séparateur, une ligne d'en-tête, au plus 500 lignes et 250 000 octets. Les champs entre guillemets et les descriptions contenant des virgules sont acceptés. Colonnes obligatoires : `external_id,date,amount,description` ; `reference` est facultative. Les dates suivent `AAAA-MM-JJ` et les montants utilisent un point décimal.

```csv
external_id,date,amount,description,reference
TX-001,2026-09-10,100.00,Encaissement,INV-2026-000001
TX-002,2026-09-10,-3.25,Frais bancaires,FRAIS-001
```

L'import passe par deux actions : **Prévisualiser sans importer**, puis **Confirmer l'import de ces lignes**. La confirmation renvoie le contenu et l'empreinte de la prévisualisation, liée au compte et à sa devise. Modifier le texte ou le compte invalide la prévisualisation. Les vérifications sont répétées côté serveur sous verrou de société. Un import est intégralement accepté ou rejeté. Les identifiants présents dans le compte avec le même contenu sont comptés comme doublons et ignorés ; un même identifiant avec un autre contenu entraîne un conflit 409 sans insertion partielle. Aucun montant n'est converti en flottant.

Routes de gestion (sessions et CSRF) :

- `/api/integrations/` : liste, création, modification ; `/api/integration-keys/` : liste, création ; `POST /api/integration-keys/{id}/revoke/` : révocation.
- `/api/bank-accounts/` : liste, création, modification ; `POST /api/bank-accounts/{id}/import/` : `{csv, confirm:false}` pour prévisualiser, puis `{csv, confirm:true, preview_digest}` pour confirmer.
- `/api/bank-transactions/` : liste et détail ; `GET summary/` : nombre, somme décimale et devise. Filtres `account`, `reconciled=true|false`, `date_from`, `date_to`, `search`.
- `POST /api/bank-transactions/{id}/reconcile/` : `{invoice:123, confirm:true}`.
- `/api/external-transactions/` : liste et détail des transactions externes reçues, consultation financière uniquement.

## Rapprochement

Une ligne d'encaissement positive peut être affectée manuellement à une facture validée de la même société et devise, pour son montant exact. L'utilisateur recherche la facture, la sélectionne puis coche la confirmation. Le service de règlement existant vérifie notamment le reste dû, la précision figée, la date et la période comptable ouverte. Il écrit le règlement et l'écriture comptable dans la même transaction que le rapprochement. Une seconde confirmation identique renvoie le résultat existant ; choisir une autre facture après rapprochement est refusé.

Les lignes importées, les informations de transaction externe et les registres d'idempotence ne sont ni supprimables ni modifiables. PostgreSQL protège directement leur immutabilité et leurs relations de société. Le seul changement d'une ligne bancaire autorisé est son premier rapprochement complet avec un règlement cohérent. L'IBAN et la devise d'un compte contenant des lignes ne sont plus modifiables.

## Périmètre restant

Les connecteurs propres à une banque, à un prestataire de paiement ou à une boutique restent à réaliser après identification du fournisseur et de ses accès. Cette version n'implémente pas OAuth bancaire, virements, prélèvements, webhooks sortants, remboursement automatique, rapprochement de dépenses, partage d'une ligne entre plusieurs factures ni gestion des devises avec change. Les fichiers CSV à colonnes différentes doivent être convertis vers le format documenté avant import. L'API externe crée des brouillons ; les validations et encaissements restent des actions humaines dans Azula.
