# Établissements et groupes

Une seule instance de BrainNotFound peut accueillir plusieurs établissements, chacun avec ses groupes, ses intervenants, ses apprenants et ses contenus.

## Concepts

### Établissement

Un **établissement** est une entité indépendante : une école, une entreprise, un service, un organisme de formation. Il porte les quotas et l'abonnement, et regroupe :

- ses groupes ;
- les personnes membres de ces groupes ;
- ses quiz et entretiens.

### Groupe

Un **groupe** rassemble des personnes au sein d'un établissement : une classe, une promotion, une session de formation, une équipe. Chaque membre y a un rôle, **apprenant** ou **intervenant**.

Les quiz et entretiens sont assignés à un ou plusieurs groupes. Un apprenant ne voit que les contenus de ses groupes ; un contenu sans groupe n'est visible par aucun apprenant (l'administration le signale par un badge « Aucun groupe »).

## Hiérarchie

```
Instance BrainNotFound
├── Établissement A (École Alpha)
│   ├── Groupe L1 Info
│   │   ├── Intervenant : M. Martin
│   │   ├── Apprenant 1
│   │   └── Apprenant 2
│   └── Groupe L2 Info
└── Établissement B (Entreprise Beta)
    ├── Groupe Formation Sécurité
    └── Groupe Formation Dev
```

## Rôles

Les droits se combinent sur deux niveaux.

### Rôle global

| Rôle | Droits |
|------|--------|
| **Super-administrateur** | Tout : établissements, utilisateurs, paramètres du site, sauvegardes, fournisseur d'IA |
| **Administrateur d'établissement** | Tous les groupes, intervenants, apprenants et contenus des établissements qu'il administre |
| **Aucun** | Droits définis groupe par groupe (cas de la plupart des comptes) |

### Rôle dans un groupe

| Rôle | Droits |
|------|--------|
| **Intervenant** | Gère ce groupe : ses apprenants, ses contenus et leurs résultats. Aucun droit sur les autres groupes. |
| **Apprenant** | Passe les quiz et entretiens du groupe, consulte ses résultats. |

Le rôle s'attribue groupe par groupe : une même personne peut être intervenante dans un groupe et apprenante dans un autre (un formateur qui suit lui-même une formation, par exemple).

### Qui peut modifier qui

Un intervenant peut modifier le profil de ses apprenants (nom, email, mot de passe, groupes) : un compte de rang inférieur, qui partage un groupe qu'il gère et dont tous les groupes sont dans son périmètre. Pour supprimer un compte, il faut gérer tous les groupes de ce compte. Personne ne peut modifier un compte de même rang ou de rang supérieur au sien, sauf le super-administrateur.

## Gérer les établissements

### La fiche de l'établissement

Un clic sur le nom d'un établissement ouvre sa fiche, qui rassemble tout, en onglets :

- **Groupes** : liste avec code d'accès, nombre d'apprenants et d'intervenants, et **Nouveau groupe** ;
- **Administrateurs** : liste, ajout par recherche, retrait (réservé aux super-administrateurs) ;
- **Contenus** : quiz et entretiens de l'établissement, avec le badge « Aucun groupe » pour ceux qu'aucun apprenant ne voit ;
- **Quotas et abonnement** : usage des limites fixes et des quotas IA du mois.

Un administrateur d'établissement retrouve sa fiche dans le menu **Établissement** ; s'il en administre plusieurs, le menu affiche leur liste.

> Réservé aux super-administrateurs. Un administrateur d'établissement consulte la fiche de ses établissements et gère leurs groupes.

### Créer un établissement

1. Menu **Établissements** > **Nouveau**
2. Renseignez le nom (le slug est généré s'il est laissé vide), le contact et, si besoin, les quotas et l'abonnement
3. **Créer l'établissement**

### Nommer un administrateur d'établissement

Deux chemins :

- depuis la fiche de l'établissement, onglet **Administrateurs** : cherchez la personne par nom, identifiant ou email, puis **Nommer admin** ;
- depuis la fiche d'un utilisateur : **Rôle global** > **Administrateur d'établissement**, puis cochez les établissements à administrer.

### Rattacher un groupe à un établissement

Un groupe se crée directement dans un établissement (**Nouveau groupe** depuis sa fiche, ou champ **Établissement** du formulaire). Un groupe « Sans établissement » se rattache via **Modifier** dans la liste des groupes. Un administrateur d'établissement ne peut déplacer un groupe que vers un établissement qu'il administre.

### Désactiver ou supprimer

**Désactiver** (case **Établissement actif** dans **Modifier**) : les données sont conservées, mais l'établissement n'accepte plus d'inscription et les fonctions IA sont coupées, comme à l'expiration de l'abonnement.

**Supprimer** efface définitivement l'établissement, ses groupes, ses quiz et entretiens avec leurs résultats. La page de suppression détaille ce qui va disparaître et demande de taper le nom de l'établissement pour confirmer. Une sauvegarde complète est faite juste avant (visible dans **Paramètres**, préfixe `backup_avant_suppression_`).

Une case, cochée par défaut, supprime aussi les comptes qui n'appartiennent qu'à cet établissement (apprenants, intervenants, administrateurs) avec leurs résultats. Les comptes rattachés à un autre établissement, et les super-administrateurs, sont conservés et simplement retirés. Les quiz et entretiens d'autres établissements assignés à ces groupes sont conservés : seule l'assignation disparaît.

## Gérer un groupe

### Créer un groupe

1. Menu **Groupes** > **Nouveau**
2. Renseignez le nom, l'établissement, une description et le nombre maximum de membres (0 = illimité)
3. **Créer le groupe**

Seuls les administrateurs (d'établissement ou super) créent des groupes ; ils y nomment ensuite les intervenants.

### La page du groupe

Un clic sur le nom d'un groupe ouvre sa page, qui rassemble tout :

- **Apprenants** : liste, dernière connexion, quiz complétés ; création (**Nouvel apprenant**), import CSV, ajout d'une personne existante, retrait du groupe (le compte et ses résultats sont conservés) ;
- **Intervenants** : pour nommer un intervenant, ajoutez la personne au groupe puis utilisez **Nommer intervenant du groupe** dans l'onglet Apprenants ; **Repasser apprenant** fait l'inverse ;
- **Contenus** : quiz et entretiens assignés, avec le taux de réponse du groupe ;
- **Accès au groupe** : code d'accès, lien d'invitation, **Nouveau code** ;
- **Envoyer un email** au groupe, **Exporter les résultats** en CSV.

### Code d'accès et lien d'invitation

Chaque groupe a un code de 8 caractères, généré automatiquement. Il sert :

- à l'inscription (obligatoire : on ne peut pas s'inscrire sans code) ;
- depuis **Mon profil**, pour rejoindre un groupe supplémentaire avec un compte existant.

Le lien d'invitation (`/register?code=CODE`) préremplit le code. **Nouveau code** invalide l'ancien code et l'ancien lien.

Un code est refusé si le groupe est inactif ou complet, ou si l'établissement a expiré, est désactivé ou a atteint son nombre maximum d'utilisateurs.

### Invitations par email

Un compte créé sans mot de passe reçoit un lien pour choisir le sien, valable 72 heures. Depuis la page du groupe ou la fiche de la personne, un intervenant peut renvoyer ce lien (**Envoyer un lien pour choisir un mot de passe**) ou le copier pour un compte sans email réel.

## Filtrer par établissement

Les administrateurs de plusieurs établissements voient un sélecteur dans la barre de navigation : **Tous les établissements**, ou un établissement en particulier. Le filtre s'applique aux quatre listes (groupes, utilisateurs, quiz, entretiens), qui le rappellent au-dessus des résultats avec un lien **Voir tous les établissements**.

Les listes ont la même barre de filtres :

| Liste | Filtres |
|-------|---------|
| **Groupes** | État (actifs, inactifs), recherche par nom ou code d'accès |
| **Utilisateurs** | Groupe, rôle, recherche par nom, identifiant ou email ; tri par colonne |
| **Quiz**, **Entretiens** | Groupe, état (actifs, inactifs, sans groupe), recherche par titre |

Le filtre « Sans groupe » retrouve les contenus qu'aucun apprenant ne peut voir.

## Déplacer des personnes

Dans **Utilisateurs**, cochez les personnes puis choisissez l'action : **Ajouter au groupe**, **Retirer du groupe** ou **Remplacer les groupes**. Le remplacement ne touche que les groupes de votre périmètre : une personne inscrite aussi dans un groupe que vous ne gérez pas y reste.

## Quotas et abonnement

> Réglés par les super-administrateurs, dans la fiche de l'établissement.

### Limites

| Limite | Effet quand elle est atteinte |
|--------|-------------------------------|
| **Max utilisateurs** | Plus d'inscription, de création ni d'import de compte dans l'établissement |
| **Max groupes** | Plus de création de groupe |
| **Max quiz** | Plus de création ni de duplication de quiz |
| **Corrections IA / mois** | Les nouvelles réponses ouvertes passent « à corriger » : l'intervenant les note à la main, l'apprenant voit une note provisoire |
| **Générations quiz / mois** | Générateur de quiz indisponible |
| **Analyses de groupe / mois** | Analyse IA des résultats d'un groupe indisponible |
| **Entretiens IA / mois** | Plus de nouvel entretien |

La valeur **0** signifie **illimité**. Les compteurs mensuels repartent à zéro le premier du mois ; la fiche de l'établissement affiche l'usage du mois.

### Alertes quota

1. **Établissements** > **Modifier**
2. Section **Alertes quota** : cochez **Activer les alertes quota**
3. Réglez le seuil (alerte quand il reste X % d'un quota, 10 % par défaut)
4. Vérifiez l'**email du contact** : c'est lui qui reçoit l'alerte

L'email liste tous les quotas proches de leur limite. Une seule alerte est envoyée par mois.

### Abonnement

La **date d'expiration** est facultative (vide = sans expiration). Une fois passée :

- l'établissement n'accepte plus d'inscription ni d'ajout par code ;
- les fonctions IA sont coupées (correction, génération, analyses, entretiens) ; les réponses ouvertes passent « à corriger » ;
- les quiz restent accessibles et les QCM continuent d'être notés.

La fiche de l'établissement affiche le nombre de jours restants.

## Bonnes pratiques

- **Un établissement par entité** qui a ses propres quotas ou ses propres administrateurs ; **un groupe par cohorte** (classe, promotion, session).
- **Nommage cohérent** : `L3-Info-2026`, `Formation-Cyber-T1`.
- **Moindre privilège** : super-administrateur pour l'exploitation de l'instance, administrateur d'établissement pour la gestion courante, intervenant pour les formateurs.
- **Fin de session** : générez un nouveau code pour fermer les inscriptions au groupe, ou désactivez le groupe.
