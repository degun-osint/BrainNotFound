# Syntaxe des quiz

BrainNotFound utilise le format **Markdown** pour définir les quiz. Ce format est simple, lisible et facile à éditer.

## Structure générale

```markdown
# Titre du quiz

## TYPE - Énoncé de la question [X pts]
(contenu selon le type)
```

- Le **titre** est défini par un `#` en début de fichier
- Chaque **question** commence par `##` suivi du type et de l'énoncé
- Les **points** sont indiqués entre crochets `[X pts]`

## Types de questions

### QCM (Question à Choix Multiples)

```markdown
## QCM - Quelle est la réponse correcte ? [2 pts]
- [ ] Réponse incorrecte A
- [x] Réponse correcte
- [ ] Réponse incorrecte B
- [ ] Réponse incorrecte C
```

- Utilisez `- [ ]` pour une option incorrecte
- Utilisez `- [x]` pour la ou les réponses correctes
- Plusieurs réponses correctes sont possibles (QCM à choix multiples)

**Correction** : Automatique. L'étudiant doit cocher exactement les bonnes réponses pour avoir tous les points (tout ou rien).

### Question ouverte

```markdown
## OUVERTE - Expliquez le concept X [5 pts]
### Réponse attendue
La réponse attendue qui servira de référence pour
l'évaluation par l'IA. Soyez précis sur les points
clés que l'étudiant doit mentionner.
```

- La section `### Réponse attendue` est obligatoire
- Elle sert de référence à Claude pour évaluer la réponse de l'étudiant

**Correction** : Par l'IA (Claude). L'IA compare la réponse de l'étudiant à la réponse attendue et attribue une note avec un feedback personnalisé.

## Options avancées

### Images

Vous pouvez inclure des images dans vos questions :

```markdown
## QCM - Identifiez ce schéma [2 pts]
![Description de l'image](nom-image.png)

- [ ] Option A
- [x] Option B
- [ ] Option C
```

1. Uploadez l'image via le bouton prévu lors de l'édition
2. Référencez-la avec `![description](nom-fichier.png)`

### Code

Pour les questions techniques, utilisez les blocs de code :

````markdown
## OUVERTE - Que fait ce code ? [3 pts]

```python
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
```

### Réponse attendue
Cette fonction calcule le factoriel de n de manière
récursive. Elle retourne 1 si n est inférieur ou égal
à 1, sinon elle multiplie n par le factoriel de (n-1).
````

### Sévérité de la correction IA

Trois niveaux disponibles dans les paramètres du quiz :

| Niveau | Description |
|--------|-------------|
| **Gentil** | Valorise les efforts, tolérant sur la formulation |
| **Normal** | Équilibre entre précision et compréhension |
| **Strict** | Exige une réponse précise et complète |

## Bonnes pratiques

### Pour les QCM

- Proposez 3 à 5 options par question
- Évitez les options évidement fausses
- Formulez des distracteurs plausibles
- Une seule bonne réponse par défaut (sauf QCM multiples explicites)

### Pour les questions ouvertes

- Rédigez une réponse attendue **détaillée**
- Mentionnez les **mots-clés** et **concepts** importants
- Indiquez les **critères d'évaluation** si nécessaire
- Adaptez les points à la complexité de la question

### Exemple complet

```markdown
# Examen Python - Semestre 1

## QCM - Quel mot-clé définit une fonction en Python ? [1 pt]
- [ ] function
- [ ] func
- [x] def
- [ ] define

## QCM - Lesquels sont des types mutables ? [2 pts]
- [x] list
- [ ] tuple
- [x] dict
- [ ] str

## OUVERTE - Expliquez la différence entre une liste et un tuple [4 pts]
### Réponse attendue
Une liste est un type mutable : on peut modifier ses éléments,
en ajouter ou en supprimer après création. Elle utilise les
crochets [].

Un tuple est immutable : une fois créé, il ne peut pas être
modifié. Il utilise les parenthèses ().

Les tuples sont plus rapides et peuvent servir de clés de
dictionnaire, contrairement aux listes.

## OUVERTE - Écrivez une fonction qui inverse une chaîne [5 pts]
### Réponse attendue
```python
def reverse_string(s):
    return s[::-1]
```
Ou avec une boucle :
```python
def reverse_string(s):
    result = ""
    for char in s:
        result = char + result
    return result
```
```
