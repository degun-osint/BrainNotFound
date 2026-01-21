# Quiz de Programmation Python

## QCM - Quel est le type de données pour stocker une séquence ordonnée d'éléments modifiables ? [1 points]
- [ ] tuple
- [x] list
- [ ] set
- [ ] dict

## QCM - Quels sont les types de données immuables en Python ? (plusieurs réponses) [2 points]
- [x] tuple
- [ ] list
- [x] str
- [ ] dict
- [x] int

## QCM - Quelle méthode permet d'ajouter un élément à la fin d'une liste ? [1 points]
- [ ] add()
- [x] append()
- [ ] insert()
- [ ] push()

## OUVERTE - Expliquez la différence entre une liste et un tuple en Python [3 points]
### Réponse attendue
Une liste est une structure de données mutable (modifiable) en Python, tandis qu'un tuple est immuable (non modifiable). Les listes utilisent des crochets [] et permettent d'ajouter, supprimer ou modifier des éléments après leur création. Les tuples utilisent des parenthèses () et une fois créés, leurs éléments ne peuvent pas être modifiés. Les tuples sont généralement plus performants et utilisés pour des données qui ne doivent pas changer.

## QCM - Quelle est la sortie de : print(type([1, 2, 3])) ? [1 points]
- [ ] <class 'tuple'>
- [x] <class 'list'>
- [ ] <class 'array'>
- [ ] <class 'set'>

## OUVERTE - Qu'est-ce qu'une fonction récursive ? Donnez un exemple simple [4 points]
### Réponse attendue
Une fonction récursive est une fonction qui s'appelle elle-même pour résoudre un problème en le décomposant en sous-problèmes plus simples. Elle doit avoir une condition d'arrêt (cas de base) pour éviter une boucle infinie. Exemple : la fonction factorielle - factorial(n) = n * factorial(n-1) avec factorial(0) = 1 comme cas de base.

## QCM - Quel mot-clé est utilisé pour gérer les exceptions en Python ? [1 points]
- [ ] catch
- [x] except
- [ ] error
- [ ] handle

## OUVERTE - Expliquez le concept de compréhension de liste en Python avec un exemple [3 points]
### Réponse attendue
La compréhension de liste est une syntaxe concise pour créer des listes en Python. Elle permet de créer une nouvelle liste en appliquant une expression à chaque élément d'une séquence existante, avec possibilité de filtrage. Exemple : [x**2 for x in range(10) if x % 2 == 0] crée une liste des carrés des nombres pairs de 0 à 9.
