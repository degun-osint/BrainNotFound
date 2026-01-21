# Guide de Creation de Quiz - BrainNotFound

Ce document explique comment creer des quiz au format Markdown pour l'application BrainNotFound.

## Structure Generale

Un quiz est compose de :
- Un titre (ligne commencant par `#`)
- Une description optionnelle (texte apres le titre)
- Des questions (lignes commencant par `##`)

```markdown
# Titre du Quiz

Description optionnelle du quiz ici.

## TYPE - Texte de la question [X points]
...
```

---

## Types de Questions

### 1. Question a Choix Multiple (QCM)

**Syntaxe :**
```markdown
## QCM - Texte de la question [X points]
- [ ] Option incorrecte
- [x] Option correcte
- [ ] Option incorrecte
```

**Regles :**
- Commencer par `## QCM -`
- Les options utilisent la syntaxe checkbox Markdown
- `- [ ]` = option incorrecte
- `- [x]` = option correcte (peut y en avoir plusieurs)
- Le nombre de points est entre crochets `[X points]`

**Exemple - Reponse unique :**
```markdown
## QCM - Quelle est la capitale de la France ? [2 points]
- [ ] Lyon
- [x] Paris
- [ ] Marseille
- [ ] Bordeaux
```

**Exemple - Reponses multiples :**
```markdown
## QCM - Quels sont des langages de programmation ? [3 points]
- [x] Python
- [ ] HTML
- [x] Java
- [x] C++
- [ ] CSS
```

> **Note :** Si plusieurs options sont correctes, l'etudiant devra toutes les selectionner pour obtenir les points.

---

### 2. Question Ouverte

**Syntaxe :**
```markdown
## OUVERTE - Texte de la question [X points]
### Reponse attendue
Texte de la reponse modele ici...
```

**Regles :**
- Commencer par `## OUVERTE -`
- La reponse attendue est precedee de `### Reponse attendue`
- La reponse de l'etudiant sera evaluee par IA (Claude) en comparaison avec la reponse attendue
- L'IA attribue une note partielle selon la pertinence de la reponse

**Exemple :**
```markdown
## OUVERTE - Expliquez le concept de recursivite en programmation [5 points]
### Reponse attendue
La recursivite est une technique de programmation ou une fonction s'appelle elle-meme
pour resoudre un probleme. Elle necessite :
1. Un cas de base (condition d'arret)
2. Un cas recursif qui reduit le probleme

Exemple : calcul de factorielle
- fact(0) = 1 (cas de base)
- fact(n) = n * fact(n-1) (cas recursif)
```

**Exemple avec reponse detaillee :**
```markdown
## OUVERTE - Decrivez les trois piliers de la programmation orientee objet [6 points]
### Reponse attendue
Les trois piliers de la POO sont :

1. **Encapsulation** : Regrouper les donnees et les methodes qui les manipulent
   dans une meme unite (classe), en cachant les details d'implementation.

2. **Heritage** : Permettre a une classe d'heriter des proprietes et methodes
   d'une autre classe, favorisant la reutilisation du code.

3. **Polymorphisme** : Capacite d'un objet a prendre plusieurs formes, permettant
   d'utiliser une interface commune pour des types differents.
```

---

## Ajout d'Images

Les images peuvent etre ajoutees dans les questions et les options QCM.

**Syntaxe :**
```markdown
![description](nom_fichier.png)
```

**Dans une question :**
```markdown
## QCM - Quel composant est represente sur ce schema ? [2 points]
![Schema electronique](resistor.png)
- [ ] Condensateur
- [x] Resistance
- [ ] Diode
```

**Dans les options :**
```markdown
## QCM - Quel logo represente Python ? [1 points]
- [x] ![Logo Python](python_logo.png)
- [ ] ![Logo Java](java_logo.png)
- [ ] ![Logo Ruby](ruby_logo.png)
```

> **Note :** Les images doivent etre uploadees via l'interface d'administration avant de les referencer dans le Markdown.

---

## Systeme de Points

- Chaque question a un nombre de points defini entre crochets : `[X points]`
- Pour les QCM : tout ou rien (toutes les bonnes reponses = points, sinon 0)
- Pour les questions ouvertes : note partielle possible (evaluee par IA)
- Le total des points est calcule automatiquement

**Conseils :**
- Questions faciles : 1-2 points
- Questions moyennes : 2-4 points
- Questions difficiles : 4-6 points
- Questions de synthese : 5-10 points

---

## Quiz Complet - Exemple

```markdown
# Introduction a Python

Ce quiz evalue vos connaissances de base en Python.

## QCM - Quel mot-cle permet de definir une fonction en Python ? [1 points]
- [ ] function
- [x] def
- [ ] func
- [ ] define

## QCM - Quels types de donnees sont mutables en Python ? [2 points]
- [x] list
- [ ] tuple
- [x] dict
- [ ] str
- [x] set

## QCM - Quelle est la sortie de print(type(3.14)) ? [1 points]
- [ ] <class 'int'>
- [x] <class 'float'>
- [ ] <class 'str'>
- [ ] <class 'decimal'>

## OUVERTE - Expliquez la difference entre une liste et un tuple en Python [3 points]
### Reponse attendue
Les principales differences sont :

1. **Mutabilite** : Les listes sont mutables (modifiables apres creation),
   les tuples sont immutables.

2. **Syntaxe** : Les listes utilisent des crochets [], les tuples des parentheses ().

3. **Performance** : Les tuples sont legerement plus rapides et utilisent moins de memoire.

4. **Cas d'usage** :
   - Listes pour des collections qui changent
   - Tuples pour des donnees fixes (coordonnees, retours multiples de fonction)

## OUVERTE - Ecrivez une fonction qui calcule la factorielle d'un nombre [4 points]
### Reponse attendue
def factorielle(n):
    if n <= 1:
        return 1
    return n * factorielle(n - 1)

# Version iterative aussi acceptee :
def factorielle_iter(n):
    resultat = 1
    for i in range(2, n + 1):
        resultat *= i
    return resultat

## QCM - Quel operateur permet de verifier l'egalite de valeur ? [1 points]
- [ ] =
- [x] ==
- [ ] ===
- [ ] is
```

---

## Bonnes Pratiques

### Pour les QCM
- Proposer 3-5 options par question
- Eviter les options evidemment fausses
- Pour les questions a reponses multiples, indiquer "plusieurs reponses possibles" dans la question
- Varier la position de la bonne reponse

### Pour les Questions Ouvertes
- Fournir une reponse attendue detaillee pour guider l'evaluation IA
- Inclure les points cles que l'etudiant doit mentionner
- Preciser si du code est attendu
- Mentionner les variantes acceptables

### General
- Equilibrer QCM et questions ouvertes
- Commencer par des questions faciles
- Augmenter progressivement la difficulte
- Verifier l'orthographe et la clarte des questions
- Tester le quiz avant de le publier

---

## Parametres Supplementaires

Lors de la creation du quiz dans l'interface admin :

| Parametre | Description |
|-----------|-------------|
| **Limite de temps** | Duree maximale en minutes (optionnel) |
| **Date de disponibilite** | Date/heure a partir de laquelle le quiz est accessible |
| **Actif/Inactif** | Permet de masquer le quiz aux etudiants |

---

## Resume des Syntaxes

| Element | Syntaxe |
|---------|---------|
| Titre du quiz | `# Titre` |
| Question QCM | `## QCM - Question [X points]` |
| Question ouverte | `## OUVERTE - Question [X points]` |
| Option incorrecte | `- [ ] Option` |
| Option correcte | `- [x] Option` |
| Reponse attendue | `### Reponse attendue` |
| Image | `![description](fichier.png)` |
| Points | `[X points]` |
