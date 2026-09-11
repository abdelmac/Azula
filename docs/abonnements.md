# Abonnements pour utiliser Azula

Ce module vend un accès récurrent **par société**, pour tous ses utilisateurs. Les abonnements Azula sont distincts des factures que cette société émet à ses clients. Un paiement Stripe ne crée aucune facture, écriture ou recette dans sa comptabilité métier.

La page **Abonnement** présente les offres disponibles, l’état de l’accès, l’échéance et l’annulation prévue. Seul l’administrateur de la société peut lancer un paiement ou ouvrir le portail de gestion des moyens de paiement et de l’abonnement. Les autres utilisateurs peuvent consulter l’état et contacter leur administrateur.

## Parcours de paiement

1. L’administrateur choisit un tarif publié, mensuel ou annuel, confirme le renouvellement récurrent et ouvre Stripe Checkout.
2. Les coordonnées de carte sont saisies chez Stripe. Azula ne reçoit ni numéro de carte ni cryptogramme.
3. Stripe notifie le serveur sur `/api/billing/webhook/`. Le serveur vérifie la signature des octets reçus, le délai, la version de l’API et le mode test/réel, puis relit l’abonnement auprès de Stripe.
4. L’accès devient actif lorsque le dernier paiement est confirmé et l’échéance future, ou durant un essai explicitement autorisé. L’URL de retour `?checkout=success` n’accorde aucun droit : le bouton d’actualisation relit l’état serveur.
5. Le portail Stripe permet les opérations configurées par l’opérateur : moyen de paiement, consultation des justificatifs d’abonnement et résiliation. Une résiliation en fin de période conserve l’accès jusqu’à l’échéance payée. Aucun remboursement ou virement n’est déclenché par Azula.

Les états `past_due`, `unpaid`, `paused`, `canceled`, `incomplete` et `incomplete_expired` ne donnent pas d’accès, sans délai de grâce implicite. L’accès expire aussi lorsque l’échéance locale est dépassée, même si une notification est retardée. La connexion, le profil, le choix de langue, la déconnexion et l’espace Abonnement restent accessibles pour régulariser. Les API métier et l’inspection Django vérifient la même règle, y compris les appels par clé API externe.

Une seule session Checkout peut être en cours par société. Les doubles clics et reprises réseau réutilisent l’opération persistée et la clé d’idempotence Stripe. Les sessions sont configurées pour expirer après une heure. Une réponse perdue est recherchée côté Stripe avant de permettre une nouvelle session ; un résultat ambigu bloque la création au lieu de risquer une double souscription. Le retour « annuler » quitte Checkout mais laisse la session disponible pour reprendre la même offre jusqu’à son expiration.

Un essai gratuit dure 0 jour ou de 2 à 90 jours selon le tarif choisi par l’opérateur. Un essai effectivement commencé est mémorisé pour la société et n’est pas reproposé après résiliation. Un moyen de paiement est demandé pendant Checkout. Aucun essai, prix ou abonnement réel n’est inventé par cette livraison.

## Configuration de l’opérateur

Les clés et les tarifs ne sont pas modifiables depuis le compte administrateur d’une société cliente. Ils sont configurés par l’exploitant du service Azula. Le code démarre avec `BILLING_ENABLED=0` : tous les accès actuels sont conservés et aucun paiement ne peut être lancé.

Préparer d’abord une **installation de test séparée**, avec sa base PostgreSQL synthétique et les clés Stripe de test. Les abonnements de test n’accordent aucun accès en mode réel ; une installation contenant un client Stripe de test n’est pas transformée silencieusement en client réel.

Configurer hors Git :

```dotenv
BILLING_ENABLED=0
BILLING_PUBLIC_URL=https://votre-instance.example
STRIPE_LIVE_MODE=0
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

Le secret Stripe et le secret de signature sont fournis par votre compte, sans les partager dans un chat ni dans les arguments d’une commande. L’URL publique doit être l’origine exacte du service, sans chemin ni redirection fournie par le navigateur. HTTP n’est accepté que sur localhost en mode test. La version Stripe est figée dans le code ; le [contrat Stripe](billing-stripe-contract.md) précise sa valeur et les sources officielles.

Créer dans Stripe les tarifs voulus, sans activer de tarification au volume ni quantité transformée. Importer un prix existant avec la commande suivante, après remplacement des paramètres :

```console
python manage.py configure_subscription_plan --code offre-mensuelle --price-id price_VOTRE_PRIX --name "Votre offre" --description "Accès Azula pour une société" --trial-days 0
```

La commande lit le prix auprès de Stripe et copie son montant exact, sa devise et son intervalle ; elle ne crée ni prix ni abonnement à distance. Les devises ISK et UGX et les fractions d’unité monétaire mineure ne sont pas prises en charge. La disponibilité des autres devises dépend du compte Stripe. Les prix positifs, à quantité fixe et intervalle simple mensuel/annuel, sont acceptés. Un nouveau prix Stripe doit recevoir un nouveau code Azula afin de conserver les références historiques. `--inactive` retire une offre des nouvelles souscriptions, sans résilier les abonnements existants.

Configurer le webhook avec la version indiquée dans le contrat et les événements : `checkout.session.completed`, `checkout.session.expired`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`. La route publique n’utilise pas de session ni de CSRF ; seule la signature Stripe l’authentifie. Les écrans de souscription et de portail conservent les sessions HttpOnly et la protection CSRF.

Configurer aussi le portail client Stripe. N’y autoriser que les opérations souhaitées, avec résiliation en fin de période si c’est votre politique. Les changements vers des prix absents du catalogue Azula ne sont pas pris en charge. La TVA, la facturation de vos abonnements, les conditions commerciales et les éventuelles règles de remboursement restent à définir pour votre activité avant encaissement réel ; aucune configuration fiscale n’est déduite de la langue.

Après essais avec les moyens de test Stripe, configurer un environnement réel avec ses clés dédiées, ses prix et son webhook, puis activer `STRIPE_LIVE_MODE=1` et `BILLING_ENABLED=1`. Le passage en mode réel est explicite ; il n’est pas exécuté par l’installation de ce module.

## Accès des sociétés existantes

La migration ajoute une exemption aux sociétés déjà présentes. Elle ne leur impose ni achat ni résiliation et ne change aucune donnée métier. Les sociétés créées ensuite doivent posséder un abonnement valide lorsque le contrôle est activé. Une exemption existante prend fin lorsqu’une souscription payée ou un essai autorisé est confirmé.

L’exploitant peut décider explicitement d’une exemption ou d’une obligation d’abonnement avec une commande auditée :

```console
python manage.py set_subscription_access --company-id 123 --expected-name "Nom exact" --mode required --reason "Motif convenu avec la société"
```

`--mode exempt` conserve un accès accordé par l’exploitant. Cette possibilité n’est pas accessible par les API des comptes clients. Les données de la société sont conservées lorsque l’accès expire. L’ouverture autonome de nouvelles sociétés depuis une page d’inscription n’est pas comprise dans ce module.

## Exploitation et vérification

Appliquer les migrations `billing/0001` et `billing/0002` après sauvegarde, avec le rôle propriétaire. Le rôle applicatif doit pouvoir lire `billing_plan`, lire/insérer/modifier `billing_subscription` et `billing_checkoutattempt`, et lire/insérer `billing_webhookevent`, ainsi qu’utiliser leurs séquences. Il ne doit pas modifier les tarifs ni supprimer les abonnements ou événements. Les anciens privilèges restent inchangés.

Les événements traités sont dédupliqués et leurs empreintes conservées. La transaction verrouille la société ; elle enregistre le nouvel état et l’audit ensemble. Une erreur réseau laisse l’événement non traité afin que Stripe le renvoie. La vérification relit l’état courant de Stripe au lieu d’appliquer aveuglément des notifications arrivées dans le désordre. Surveiller les échecs du webhook et les reprendre depuis le tableau de bord Stripe après correction ; aucun abonnement ne devient payé à partir d’une réponse du navigateur.

Les résultats réellement exécutés et les limites d’activation sont consignés dans [verification.md](verification.md). Les simulations automatisées ne remplacent pas un essai Checkout complet sur le compte Stripe retenu.
