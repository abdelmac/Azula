# Contrat Stripe de l’abonnement Azula

Vérifié le 11 septembre 2026. Le module `backend/billing/provider.py` prépare les appels Stripe Checkout et Billing. Ses tests utilisent uniquement des réponses et signatures synthétiques : aucun compte Stripe, abonnement réel ou paiement n’a été créé par ces tests.

## Version et configuration

L’intégration fixe **`2026-08-26.dahlia`**, version publique stable publiée dans le [journal officiel Stripe](https://docs.stripe.com/changelog). L’en-tête `Stripe-Version` est envoyé à chaque appel. Le point de réception webhook doit utiliser exactement cette même version ; une version différente est rejetée afin de conserver un contrat explicite.

| Réglage Django | Contrat |
| --- | --- |
| `STRIPE_SECRET_KEY` | Clé privée `sk_test_…` ou restreinte `rk_test_…` en test ; mode `live` seulement avec `STRIPE_LIVE_MODE=True`. |
| `STRIPE_WEBHOOK_SECRET` | Secret de signature `whsec_…` du point de réception choisi. |
| `STRIPE_API_VERSION` | `2026-08-26.dahlia` uniquement pour cette implémentation. |
| `STRIPE_LIVE_MODE` | Booléen strict, `False` par défaut. |

Ces valeurs restent dans l’environnement serveur. Elles ne sont exposées ni au navigateur ni aux réponses d’erreur. Les réglages du mode réel doivent être effectués seulement après configuration et contrôle du compte, des tarifs et du point de réception.

## Fonctions du transport

Toutes les fonctions retournent un dictionnaire ou lèvent `ProviderError`, avec le code public `billing_unavailable` ; `verify_event` utilise `billing_invalid_event`. Les identifiants et les types d’objets retournés sont vérifiés. La vérification des droits, de la société, du tarif et de l’état de paiement appartient au service métier.

| Fonction | Opération |
| --- | --- |
| `create_customer(company_id, name, email, idempotency_key)` | Crée un client Stripe avec la métadonnée `azula_company_id`. |
| `create_checkout(customer_id, price_id, company_id, success_url, cancel_url, idempotency_key, trial_days=0, expires_at=None, checkout_reference=None)` | Crée une session d’abonnement pour un tarif existant, quantité fixe de 1. |
| `create_portal(customer_id, return_url)` | Ouvre une nouvelle session du portail client Stripe. |
| `retrieve_subscription(subscription_id)` | Relit l’abonnement actuel avec `expand[]=latest_invoice`. |
| `retrieve_price(price_id)` | Relit le tarif et ses paramètres décimaux et récurrents. |
| `retrieve_checkout(session_id)` | Relit une session ouverte, terminée ou expirée. |
| `expire_checkout(session_id)` | Demande l’expiration d’une session, avec clé d’idempotence déterministe. |
| `find_checkout(customer_id, checkout_reference)` | Recherche la référence d’une tentative après une réponse de création perdue. |
| `verify_event(raw_body, signature_header)` | Vérifie un événement signé de type snapshot, sans requête réseau. |

Checkout utilise `mode=subscription`, `client_reference_id` et `azula_company_id` sur la session et l’abonnement. Le moyen de paiement est collecté, y compris avec un essai configuré. Le montant vient du tarif Stripe ; le navigateur ne fournit aucun montant. La conversion Adaptive Pricing est explicitement désactivée pour conserver la devise du tarif affiché. Le service fournit une échéance `expires_at` stable et la conserve lors des reprises ; Stripe accepte une expiration entre 30 minutes et 24 heures après création. [Création d’une session Checkout](https://docs.stripe.com/api/checkout/sessions/create).

Les créations client et Checkout réutilisent la clé et le contenu fournis par le service. Une nouvelle session de portail reçoit une nouvelle clé d’idempotence ; aucune relance automatique n’est effectuée par le transport. Le portail nécessite une configuration préalable dans le compte Stripe. [Portail client](https://docs.stripe.com/api/customer_portal/sessions/create).

La référence stable de tentative est conservée dans `metadata.azula_checkout_attempt`. Sa recherche lit au maximum 100 sessions du client concerné, sans filtre d’état : une session déjà terminée ou expirée doit pouvoir être retrouvée. Les liaisons client, type, mode et URL sont vérifiées. Plusieurs correspondances sur la page sont rejetées ; une absence avec `has_more=true` est ambiguë et produit une erreur, jamais une autorisation implicite de recréer. Cette recherche ne garantit pas l’absence de doublons au-delà de la page lorsque la référence a été trouvée ; le service maintient l’unicité des tentatives actives. [Liste des sessions Checkout](https://docs.stripe.com/api/checkout/sessions/list).

## Montants, périodes et règlement

Un tarif possède `currency` en minuscules, `unit_amount` entier en unité mineure et `unit_amount_decimal` chaîne décimale, éventuellement nulls selon son mode. `recurring` fournit `interval`, `interval_count` et `usage_type`. `tax_behavior` indique si le tarif inclut la taxe, l’exclut ou ne le précise pas. Le service doit refuser un tarif incompatible avec son contrat ; le transport ne crée ni tarif ni règle fiscale. [Objet Price](https://docs.stripe.com/api/prices/object).

Les décimaux JSON sont lus en `Decimal`, jamais en float. La précision d’affichage dépend de la devise Stripe, indépendamment de celle des factures métier Azula. Les devises sans décimale sont `BIF CLP DJF GNF JPY KMF KRW MGA PYG RWF VND VUV XAF XOF XPF`, hors cas particulier UGX. ISK et UGX exigent une représentation API à deux décimales avec un montant divisible par 100 : leur import initial peut être refusé. HUF et TWD utilisent deux décimales pour les paiements ; leur exception concerne les virements sortants. [Devises Stripe](https://docs.stripe.com/currencies?locale=en-GB).

Stripe documente également `BHD JOD KWD OMR TND` comme devises à trois décimales pour les comptes des Émirats arabes unis ; leur disponibilité dépend du pays du compte. [Devises et produits disponibles aux Émirats](https://support.stripe.com/questions/which-payments-methods-and-products-are-available-in-the-uae).

Les périodes d’abonnement sont portées par **`items.data[].current_period_start` et `current_period_end`**. Elles ont quitté la racine de l’abonnement depuis Basil. Le service Azula doit vérifier l’item et son tarif avant de retenir une date d’accès. [Migration des périodes Stripe](https://docs.stripe.com/changelog/basil/2025-03-31/deprecate-subscription-current-period-start-and-end).

La dernière facture est développée à la lecture de l’abonnement. Sa liaison moderne est `parent.type=subscription_details`, puis `parent.subscription_details.subscription`. Le service vérifie aussi le client et le règlement ; un retour navigateur vers la page de succès ne prouve pas un paiement. [Nouvelle structure des factures Stripe](https://docs.stripe.com/changelog/basil/2025-03-31/adds-new-parent-field-to-invoicing-objects). L’état payé est `status=paid` et le solde restant est `amount_remaining` ; ne pas dépendre d’un ancien champ booléen `paid`. [Objet Invoice](https://docs.stripe.com/api/invoices/object).

## Limites du transport et des notifications

Les appels utilisent uniquement `https://api.stripe.com/v1/…`, avec validation TLS par Python, délai socket de 10 secondes et lecture de réponse plafonnée à 1 Mio. Aucun proxy d’environnement ou suivi de redirection HTTP n’est utilisé. Les URLs présentées au navigateur doivent avoir pour hôte exact `checkout.stripe.com` ou `billing.stripe.com`, en HTTPS, sans identifiant utilisateur ni port alternatif. Les URLs de retour sont construites par le serveur ; HTTP est accepté seulement en mode test pour localhost.

Le webhook vérifie les octets bruts par HMAC SHA-256, compare les signatures en temps constant et accepte plusieurs signatures `v1` pour la rotation du secret. La fenêtre temporelle est de 300 secondes dans les deux directions. Corps supérieur à 1 Mio, JSON ambigu avec clés répétées, valeurs non finies, mode ou version incorrects sont rejetés. Le contrat concerne les événements snapshot v1 ; les notifications thin v2 nécessiteraient une autre implémentation. [Réception et signatures des événements Stripe](https://docs.stripe.com/webhooks).

Le transport ne journalise aucun corps fournisseur. Il ne conserve pas lui-même les événements ni les essais de paiement : le service métier doit rendre le traitement idempotent, ignorer les doublons et relire l’abonnement actuel pour éviter qu’une livraison tardive rétablisse un ancien droit d’accès.

## Vérification effectuée

`python -m pytest tests/test_billing_provider.py -p no:cacheprovider` : 108 cas réussis sous Python 3.14.7, sans réseau ni base, avec configuration PostgreSQL synthétique non accessible. Les vérifications couvrent signatures, rotation, dates limites, modes, contenu JSON exact, redirections, erreurs, taille maximale, stabilité des paramètres de création et recherches de tentatives ambiguës. `ruff check --no-cache billing/provider.py tests/test_billing_provider.py` a également réussi. Un essai Stripe en environnement de test reste nécessaire après fourniture du compte et des tarifs.
