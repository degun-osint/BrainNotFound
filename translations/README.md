# Translations

This directory contains the translation files for BrainNotFound internationalization.

## Structure

```
translations/
  fr/LC_MESSAGES/messages.po  # French translations (source language)
  en/LC_MESSAGES/messages.po  # English translations
```

## Commands

### Extract translatable strings
```bash
pybabel extract -F babel.cfg -k _l -o messages.pot .
```

### Initialize a new language
```bash
pybabel init -i messages.pot -d translations -l <language_code>
```

### Update existing translations after code changes
```bash
pybabel extract -F babel.cfg -k _l -o messages.pot .
pybabel update -i messages.pot -d translations
```

### Compile translations (required after editing .po files)
```bash
pybabel compile -d translations
```

## Docker usage

Run these commands inside the Docker container:
```bash
docker-compose exec web pybabel extract -F babel.cfg -k _l -o messages.pot .
docker-compose exec web pybabel compile -d translations
```

## Adding new translations

1. Add `_l('Your text')` in Python code or `{{ _('Your text') }}` in templates
2. Run `pybabel extract` and `pybabel update`
3. Edit the `.po` files to add translations
4. Run `pybabel compile`
5. Restart the application
