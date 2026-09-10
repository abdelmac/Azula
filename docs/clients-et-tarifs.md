# Clients, articles et tarifs personnalisés

La liste **Clients** recherche les noms, références, coordonnées, villes et groupes. Chaque fiche propose les coordonnées, les conditions commerciales, l’adresse de livraison, les notes et champs libres, les tarifs et le relevé de compte. Les commerciaux, comptables et administrateurs peuvent créer, modifier, archiver et réactiver les fiches ; les lecteurs peuvent les consulter et les imprimer.

La référence client, lorsqu’elle est renseignée, est unique dans la société. Deux sociétés peuvent utiliser la même référence. Les coordonnées bancaires sont des renseignements : l’IBAN est contrôlé par sa structure et sa clé de contrôle, le BIC par sa forme ; aucun compte bancaire n’est connecté et aucun virement n’est exécuté depuis la fiche.

Les conditions proposent un délai de 0 à 365 jours et une remise habituelle de 0 à 100 %. Le plafond de crédit est facultatif et informatif ; il ne bloque pas la facturation. Les montants sont transmis sous forme de chaînes décimales. Les coordonnées, adresses et tarifs modifiés ne réécrivent jamais une facture validée.

## Tarifs clients

`GET/POST /api/customer-prices/`, `GET/PATCH /api/customer-prices/{id}/` gèrent un prix HT par couple client/article dans la société. Filtres : `customer`, `product`, `archived`, `search`. Champs : `customer`, `product`, `unit_price` (chaîne décimale, jusqu’à six décimales), `archived`. Les créations/modifications sont atomiques, auditées et sérialisées avec les changements de références. Les références d’une autre société sont refusées. Un tarif archivé est conservé mais ne sert plus au préremplissage.

`GET /api/products/{id}/pricing/?customer={id}` renvoie `product`, `customer`, `unit_price`, `tax_rate`, `discount_rate`, `source`. La source est `customer` si un tarif spécifique actif existe, sinon `catalog`. La remise habituelle client s’applique séparément au prix HT. Un client ou article archivé ne peut servir à cette préparation.

## Relevé de compte

`GET /api/customers/{id}/statement/?start=2026-01-01&end=2026-12-31&page=1&page_size=50` sélectionne les factures **validées** selon leur date d’émission. Chaque ligne contient son numéro, les dates, le total, le montant réglé, le solde et ses règlements. Les règlements sont cumulés **à ce jour**, même lorsqu’ils ont été enregistrés après la période sélectionnée. Ce relevé n’est donc pas une reconstitution historique de solde à la date de fin.

Le résultat contient `count`, `next`, `previous`, `results`, `customer`, `currency`, `summary`. Le résumé couvre toutes les pages : `invoice_count`, `total`, `paid`, `balance`, `overdue` (échéance strictement antérieure à aujourd’hui). La fiche et le relevé peuvent être imprimés ou enregistrés en PDF via le navigateur. Le relevé imprime la page affichée et indique le nombre total de factures sélectionnées.

## Articles et champs libres

La fiche article ajoute nom latin/alternatif, code-barres, fabricant, fournisseur habituel, couleur, dimensions, origine, poids en kg, notes internes et champs personnalisés. Le code-barres, le fabricant et le fournisseur sont recherchables. Le poids est un décimal facultatif et non négatif ; la valeur absente reste `null`. Ces attributs ne constituent pas une gestion de stock, de lots ou de commandes fournisseur.

Les clients et articles acceptent `custom_fields`, objet de 20 paires de textes maximum, avec noms de 1 à 60 caractères et valeurs de 500 caractères maximum. Les caractères de balisage HTML sont refusés. Le formulaire propose l’ajout et le retrait de ces champs sans code HTML.

## Contrôles

Les tests PostgreSQL sont dans `backend/tests/test_partners.py` (coordonnées, validation, unicité, montants exacts, permissions, isolation, tarifs, audit et retour arrière transactionnel, relevé et conservation des factures validées). Les parcours navigateur sont dans `frontend/e2e/partners.spec.ts`, avec deux scénarios d’interface simulée et un scénario réservé au serveur PostgreSQL E2E isolé. Les exécutions et leurs résultats effectifs sont consignés dans `docs/verification.md`.
